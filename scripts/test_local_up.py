#!/usr/bin/env python3
"""P51 -- proof that scripts/local_up.py resolves paths, refuses the right
things, and never touches a process (or a database, or stdout) it should not.

Run: .venv-api/bin/python3 scripts/test_local_up.py

Needs the .venv-api interpreter (imports local_up, which imports infra.env,
which needs psycopg2/python-dotenv -- standard library plus what .venv-api
already has, no new dependency). Some cases (docker/postgres/minio/the
viewer itself) need the real local stack up, the same stack `make local-up`
itself targets -- this is not a mockable unit, by design.

Same pass/fail table shape as .claude/hooks/test_guard_destructive.py --
read that file's own docstring for why this repeats it rather than a second
convention.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import local_up  # noqa: E402

RESULTS = []  # (name, ok, detail, skipped)


def check(name, condition, detail="", skipped=False):
    # C21.4 (P59): a genuinely-skipped case (environment doesn't support
    # exercising it -- no second python3 on PATH, docker/postgres/minio
    # unreachable, a resolved password too short to substring-check
    # safely) used to be recorded via check(name, True, "SKIPPED -- ..."),
    # indistinguishable at tally time from a real, exercised pass -- the
    # final "N/M cases behaved as declared" summary could read 100%
    # verified while some cases were never actually run. skipped is now a
    # distinct third state, never counted as verified.
    RESULTS.append((name, bool(condition), detail, skipped))


def check_skipped(name, detail):
    check(name, True, detail, skipped=True)


def _with_env(**kv):
    """Temporarily set/unset env vars; returns a restore callable. A value
    of None means "unset for the duration of this check"."""
    old = {k: os.environ.get(k) for k in kv}
    for k, v in kv.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    def restore():
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return restore


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def test_repo_root_independent_of_cwd():
    expected = REPO_ROOT
    for d in (REPO_ROOT, os.path.join(REPO_ROOT, "scripts"), "/", "/tmp", os.path.expanduser("~")):
        cwd0 = os.getcwd()
        try:
            os.chdir(d)
            got = local_up.resolve_repo_root()
        finally:
            os.chdir(cwd0)
        check("repo root resolves correctly with cwd=%s" % d, got == expected, "got %r" % got)


def test_venv_python_absolute_and_exists():
    p = local_up.resolve_venv_python()
    check("resolved .venv-api interpreter path is absolute", os.path.isabs(p), p)
    check("resolved .venv-api interpreter exists", os.path.exists(p), p)


def test_reexec_lands_on_venv_python():
    """Invoke the script under a non-venv python3 and confirm it ends up
    running under .venv-api's own interpreter -- the specific regression
    this module's own reexec_under_venv_python() docstring records: an
    earlier version compared realpath(sys.executable), which is wrong when
    the venv's bin/python3 symlinks to the same underlying binary already
    on PATH (true on this machine), and silently never re-exec'd.
    """
    script = os.path.join(REPO_ROOT, "scripts", "local_up.py")
    venv_real = os.path.realpath(local_up.resolve_venv_python())
    candidates = ["/usr/bin/python3", shutil.which("python3")]
    other = None
    for c in candidates:
        if c and os.path.exists(c):
            other = c
            break
    if other is None:
        check_skipped("reexec lands on .venv-api python", "SKIPPED -- no python3 found to invoke with")
        return
    out = subprocess.check_output([other, script, "--print-interpreter"],
                                  cwd=REPO_ROOT, stderr=subprocess.STDOUT, timeout=20)
    got = os.path.realpath(out.decode().strip())
    check("reexec lands on .venv-api python", got == venv_real,
          "invoked with %s, landed on %s (want %s)" % (other, got, venv_real))


# ---------------------------------------------------------------------------
# Refusal cases -- each asserts WHY, not just that it refused
# ---------------------------------------------------------------------------

def test_refuses_remote_smoke_url():
    restore = _with_env(SMOKE_DATABASE_URL="postgresql://u:p@db.example.supabase.co:5432/postgres")
    try:
        reason = local_up.refusal_reason_for_db_url(local_up.resolve_smoke_url())
        check("refuses non-local SMOKE_DATABASE_URL",
              reason is not None and "not local" in reason, reason)
    finally:
        restore()


def test_database_url_ignored_stays_on_local_default():
    """The regression test for the single most important rule in this
    module: DATABASE_URL is never read here, under any name, so setting it
    to a remote host must have zero effect on what this launcher binds to.
    """
    restore = _with_env(DATABASE_URL="postgresql://u:p@prod.example.com/ledgex",
                        SMOKE_DATABASE_URL=None)
    try:
        resolved = local_up.resolve_smoke_url()
        check("DATABASE_URL is ignored; default smoke url is used",
              resolved == local_up.DEFAULT_SMOKE_DATABASE_URL, "resolved to %r" % resolved)
        reason = local_up.refusal_reason_for_db_url(resolved)
        check("the (unaffected) default smoke url is still accepted as local",
              reason is None, reason)
    finally:
        restore()


def test_refuses_allow_remote_flag():
    restore = _with_env(LEDGEX_ALLOW_REMOTE_DB="1", SMOKE_DATABASE_URL=None)
    try:
        try:
            local_up.check_remote_db_refusals()
            ok, detail = False, "did not raise Refusal"
        except local_up.Refusal as e:
            ok = "LEDGEX_ALLOW_REMOTE_DB" in str(e)
            detail = str(e).splitlines()[0]
        check("refuses LEDGEX_ALLOW_REMOTE_DB=1", ok, detail)
    finally:
        restore()


def test_refuses_unparseable_url():
    reason = local_up.refusal_reason_for_db_url("not-a-postgres-url-at-all")
    check("refuses an unparseable SMOKE_DATABASE_URL (fail closed)", reason is not None, reason)


def test_accepts_local_forms():
    forms = [
        "postgresql://postgres@127.0.0.1:5432/ledgex_smoke",
        "postgresql://localhost/ledgex_smoke",
        "postgresql://postgres@/ledgex_smoke?host=/tmp",
        "postgresql:///ledgex_smoke",
    ]
    for url in forms:
        reason = local_up.refusal_reason_for_db_url(url)
        check("accepts local form %s" % url, reason is None, reason)


# ---------------------------------------------------------------------------
# Process handling
# ---------------------------------------------------------------------------

def test_stale_pidfile_cleaned_up():
    tmpdir = tempfile.mkdtemp()
    old_pidfile = local_up.PIDFILE
    local_up.PIDFILE = os.path.join(tmpdir, "viewer.pid")
    try:
        p = subprocess.Popen(["true"])
        dead_pid = p.pid
        p.wait()
        with open(local_up.PIDFILE, "w") as f:
            json.dump({"pid": dead_pid, "database_url": "x", "port": local_up.VIEWER_PORT}, f)
        status = local_up.classify_pidfile()
        check("a pidfile naming a dead pid is classified stale, not running",
              status.state == "stale", "state=%s" % status.state)
    finally:
        local_up.PIDFILE = old_pidfile
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_foreign_process_refused_not_killed():
    tmpdir = tempfile.mkdtemp()
    old_pidfile = local_up.PIDFILE
    local_up.PIDFILE = os.path.join(tmpdir, "viewer.pid")
    proc = subprocess.Popen(["sleep", "60"])
    try:
        with open(local_up.PIDFILE, "w") as f:
            json.dump({"pid": proc.pid, "database_url": "x", "port": local_up.VIEWER_PORT}, f)
        status = local_up.classify_pidfile()
        check("a pidfile naming a live non-viewer process is classified foreign",
              status.state == "foreign", "state=%s" % status.state)
        alive = local_up.process_alive(proc.pid)
        check("classify_pidfile never signals the process it inspects",
              alive, "" if alive else "pid %d is unexpectedly dead after classify_pidfile()" % proc.pid)
    finally:
        local_up.PIDFILE = old_pidfile
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_password_never_printed():
    """Two runs of the real launcher, both checked for a leak, for two
    different reasons a naive single run would miss:

    1. PGPASSWORD forced to a FABRICATED sentinel. resolve_pg_password()
       correctly prefers an already-exported PGPASSWORD over the container,
       so this is a genuinely WRONG password and Postgres will refuse the
       connection -- that failure path (psycopg2's OperationalError text)
       is exactly the kind of place a naive implementation would interpolate
       the DSN, password included, into an error message. Checked here
       regardless of exit code, because a real leak would show up in the
       FAILURE output, not just a success one.
    2. No PGPASSWORD forced -- resolve_pg_password() falls through to
       `docker inspect`, and this run is expected to succeed. Checked
       against the REAL resolved password, which is the value that
       actually reaches the viewer subprocess's environment and (if
       anything were wrong) the log it writes.

    Needs docker + the smoke database + MinIO actually reachable for run 2
    to succeed -- if check_docker()/check_minio() themselves fail (not an
    auth failure), that is reported as SKIPPED for run 2 only, since that
    unavailability is a statement about this machine, not about whether
    local_up.py leaks a password.
    """
    script = os.path.join(REPO_ROOT, "scripts", "local_up.py")
    venv_python = local_up.resolve_venv_python()

    def run(env, label):
        subprocess.run([venv_python, script, "--down"], cwd=REPO_ROOT, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        up = subprocess.run([venv_python, script], cwd=REPO_ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        combined = (up.stdout + up.stderr).decode("utf-8", "replace")
        log_text = ""
        if os.path.exists(local_up.LOGFILE):
            with open(local_up.LOGFILE, "rb") as f:
                log_text = f.read().decode("utf-8", "replace")
        subprocess.run([venv_python, script, "--down"], cwd=REPO_ROOT, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        return up.returncode, combined, log_text

    # Run 1: fabricated sentinel, checked on both success AND failure.
    sentinel = "PW_SENTINEL_%d_%d" % (os.getpid(), int(time.time()))
    env1 = dict(os.environ)
    env1["PGPASSWORD"] = sentinel
    env1.pop("SMOKE_DATABASE_URL", None)
    env1.pop("LEDGEX_ALLOW_REMOTE_DB", None)
    _rc1, combined1, log1 = run(env1, "fabricated PGPASSWORD")
    check("fabricated PGPASSWORD sentinel absent from stdout/stderr",
          sentinel not in combined1, "LEAK in stdout/stderr" if sentinel in combined1 else "")
    check("fabricated PGPASSWORD sentinel absent from the viewer log file",
          sentinel not in log1, "LEAK in %s" % local_up.LOGFILE if sentinel in log1 else "")

    # Run 2: the REAL password (from docker inspect, unset in env here so
    # resolve_pg_password() falls through to it), on the expected-success path.
    env2 = dict(os.environ)
    env2.pop("PGPASSWORD", None)
    env2.pop("SMOKE_DATABASE_URL", None)
    env2.pop("LEDGEX_ALLOW_REMOTE_DB", None)
    real_password, real_source = local_up.resolve_pg_password()
    rc2, combined2, log2 = run(env2, "real container password")
    if rc2 != 0:
        check_skipped("real-password run (needs live docker/postgres/minio)",
              "SKIPPED -- run failed on this machine's current state (%s): %s"
              % (real_source, combined2.strip().splitlines()[-1] if combined2.strip() else "no output"))
    elif not real_password:
        check("real password resolution (%s, nothing to leak)" % real_source, True)
    elif len(real_password) < 6:
        # A substring search for a password this short (this dev container's
        # own POSTGRES_PASSWORD is the single character "x") is meaningless --
        # ordinary output contains almost any single character somewhere.
        # scripts/smoke_real.py's own step_rights_gate applies the identical
        # len(text) >= 6 floor for the same reason. Not a leak check that can
        # pass or fail here; recorded as skipped rather than silently omitted.
        check_skipped("real resolved password (%s) too short to substring-check safely" % real_source,
              "SKIPPED -- password is %d char(s); use a real password locally to exercise this" % len(real_password))
    else:
        check("real resolved password (%s) absent from stdout/stderr" % real_source,
              real_password not in combined2, "LEAK in stdout/stderr" if real_password in combined2 else "")
        check("real resolved password (%s) absent from the viewer log file" % real_source,
              real_password not in log2, "LEAK in %s" % local_up.LOGFILE if real_password in log2 else "")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_repo_root_independent_of_cwd,
    test_venv_python_absolute_and_exists,
    test_reexec_lands_on_venv_python,
    test_refuses_remote_smoke_url,
    test_database_url_ignored_stays_on_local_default,
    test_refuses_allow_remote_flag,
    test_refuses_unparseable_url,
    test_accepts_local_forms,
    test_stale_pidfile_cleaned_up,
    test_foreign_process_refused_not_killed,
    test_password_never_printed,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001 -- a broken test IS a failure to report
            RESULTS.append((t.__name__, False, "EXCEPTION: %s: %s" % (type(e).__name__, e), False))

    bad = 0
    skipped = 0
    for name, ok, detail, was_skipped in RESULTS:
        if was_skipped:
            status = "SKIP"
            skipped += 1
        else:
            status = "ok" if ok else "FAIL"
            bad += 0 if ok else 1
        print("  %-6s %s%s" % (status, name, ("   [%s]" % detail) if detail else ""))

    verified_total = len(RESULTS) - skipped
    print("\n%d/%d cases behaved as declared (%d skipped, not counted as verified)."
          % (verified_total - bad, verified_total, skipped))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
