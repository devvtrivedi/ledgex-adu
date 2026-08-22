#!/usr/bin/env python3
"""P51 -- one-command local viewer launcher: `make local-up` / `make local-down`.

WHAT THIS IS FOR. `make smoke-real` (P50) proved the machine is wired up in
one command instead of a manual walkthrough. Starting the viewer itself was
still that manual walkthrough: derive PGPASSWORD from the `ledgex` container
by hand, export it into one shell, then run uvicorn with a hand-typed
DATABASE_URL -- and the moment that terminal closes, or you `cd` somewhere
else, the exports are gone and a relative `.venv-api/bin/python3` silently
resolves to nothing. This script is the fix: `make local-up` starts (or
reports) the viewer with no credential ever typed or exported by hand, and
`make local-down` stops only the one process it started.

REUSE, NOT REINVENTION. The env-binding and refusal logic here is the same
judgment scripts/smoke_real.py's step_env() already made -- SMOKE_DATABASE_URL
only, never DATABASE_URL, refuse a non-local host, refuse
LEDGEX_ALLOW_REMOTE_DB=1 -- imported from infra.env (_is_local, resolved_host)
rather than re-derived. P47 finding #44 is on record about what a second
hand-rolled copy of that judgment costs (migrate_baseline.py silently dropped
the `?host=/tmp` form and had to be repaired).

WHY A SINGLE FILE WITH A --down FLAG, NOT TWO SCRIPTS. Path resolution,
re-exec-under-the-venv-interpreter and pidfile classification are identical
for start and stop; a second script would either import this one (indirection
for no reason) or duplicate all three (exactly the P47 mistake this module's
own previous paragraph just described). One file, one flag, argued once.

THE RE-EXEC TRICK. Repo root is derived from os.path.abspath(__file__), never
cwd, never an env var -- so this script works when invoked by absolute path
from anywhere. But infra.env (imported below, deferred) needs psycopg2 and
python-dotenv, which live only in .venv-api. Rather than add a dependency
anywhere or require the caller to remember which interpreter to use, this
script re-execs itself under .venv-api/bin/python3 (resolved as an absolute
path off the repo root) the moment it notices it is running under a different
one. That is the single trick that makes "run it from anywhere, under
whatever python3 happens to be on PATH" actually true.

WRITES NOTHING PERMANENT. Unlike smoke_real.py, this script makes no database
writes of its own -- it only starts/health-checks/stops a local HTTP process.
Its only state is a pidfile and a log file under /tmp/ledgex-local/.
"""
import argparse
import collections
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

DEFAULT_SMOKE_DATABASE_URL = "postgresql://postgres@127.0.0.1:5432/ledgex_smoke"
DEFAULT_OBJECT_STORE_URL = "http://localhost:9000"
DEFAULT_PG_CONTAINER = "ledgex"

VIEWER_HOST = "127.0.0.1"
VIEWER_PORT = 8420
VIEWER_URL = "http://%s:%d" % (VIEWER_HOST, VIEWER_PORT)
HEALTH_TIMEOUT_S = 15
STOP_GRACE_S = 10

STATE_DIR = "/tmp/ledgex-local"
PIDFILE = os.path.join(STATE_DIR, "viewer.pid")
LOGFILE = os.path.join(STATE_DIR, "viewer.log")


class Refusal(Exception):
    """A condition this launcher must refuse rather than paper over.

    Raised, not returned -- same shape as scripts/smoke_real.py's
    StepFailed, for the same reason: it can be raised from anywhere inside a
    helper without every call site checking a return value, and it carries
    text meant to be read directly by whoever hits it.
    """


PidStatus = collections.namedtuple("PidStatus", "state info")
# state is one of:
#   "absent"  -- no pidfile
#   "stale"   -- pidfile names a pid that is not running
#   "foreign" -- pidfile names a live pid whose command line is NOT ours
#   "ours"    -- pidfile names a live pid that IS our viewer


# ---------------------------------------------------------------------------
# Path / interpreter resolution -- pure and side-effect free so tests can
# call these directly under any interpreter without triggering a re-exec.
# ---------------------------------------------------------------------------

def resolve_repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_venv_python(root=None):
    return os.path.join(root or resolve_repo_root(), ".venv-api", "bin", "python3")


def reexec_under_venv_python():
    """If this process does not have .venv-api's own venv activated, become it.

    Deliberately checks sys.prefix, NOT realpath(sys.executable) against the
    target. .venv-api/bin/python3 is a symlink to the same underlying
    Homebrew python3.14 binary this machine's plain `python3` on PATH also
    resolves to -- so comparing REALPATHs finds them equal even when the
    venv is not active at all, and the re-exec silently never fires,
    leaving infra.env's `import psycopg2` below to fail on a perfectly
    normal-looking interpreter. sys.prefix does not have this problem: a
    venv's whole purpose is to make sys.prefix point at the venv directory
    regardless of which real binary its bin/python3 symlinks to, so it is
    the one thing that actually distinguishes "venv active" from "same
    binary, no venv" here. (Caught by running this function for real and
    watching ModuleNotFoundError: psycopg2 come out of a process that
    reported its own sys.executable as the venv path's realpath -- worth
    recording so the next rewrite does not reintroduce it.)
    """
    target = resolve_venv_python()
    if not os.path.exists(target):
        sys.stderr.write(
            "FAIL local-up: %s does not exist.\n"
            "This launcher needs the API virtualenv (FastAPI/uvicorn, plus\n"
            "infra.env's own psycopg2/python-dotenv). Create .venv-api first.\n"
            % target)
        sys.exit(1)
    venv_dir = os.path.dirname(os.path.dirname(target))  # .../.venv-api
    if os.path.realpath(sys.prefix) != os.path.realpath(venv_dir):
        os.execv(target, [target, os.path.abspath(__file__)] + sys.argv[1:])


# ---------------------------------------------------------------------------
# Environment binding -- reuses infra.env rather than re-deriving it (see
# module docstring). Imported lazily so importing this module never requires
# psycopg2/python-dotenv to be installed (only running it past this point
# does, and by then reexec_under_venv_python() has already guaranteed we are
# under an interpreter that has them).
# ---------------------------------------------------------------------------

def resolve_smoke_url():
    """SMOKE_DATABASE_URL, defaulting to the local smoke database.

    NEVER DATABASE_URL, under any name, anywhere in this module. The
    repo-root .env sets DATABASE_URL to a live hosted database and
    load_dotenv searches upward from the cwd (P39, README finding #43) --
    reading it here, even as a fallback, is the single most important thing
    this launcher must not do.
    """
    return os.environ.get("SMOKE_DATABASE_URL") or DEFAULT_SMOKE_DATABASE_URL


def refusal_reason_for_db_url(url):
    """None if `url` is an acceptable local-database target, else the exact
    reason it is refused. A pure function so tests can exercise every
    accept/refuse case directly, without spinning up docker/postgres/minio.
    """
    from infra.env import _is_local, resolved_host
    if not _is_local(url):
        host = resolved_host(url)
        where = "host %r" % host if host else "a host this guard could not parse"
        return (
            "SMOKE_DATABASE_URL resolves to %s, which is not local.\n"
            "This launcher binds only to a local database -- see .env.example and\n"
            "LOCAL_SMOKE.md. Set SMOKE_DATABASE_URL to a local database, e.g.\n"
            "%s" % (where, DEFAULT_SMOKE_DATABASE_URL))
    return None


def check_remote_db_refusals():
    """Raise Refusal for either way this launcher must never reach a
    non-local database; otherwise return the accepted smoke_url.

    Order matches scripts/smoke_real.py's step_env(): host-locality first,
    then the LEDGEX_ALLOW_REMOTE_DB escape hatch -- not because order
    matters much here, but because a second copy of this judgment that
    disagrees with the first even in ordering is exactly the drift P47
    finding #44 is on record about.
    """
    smoke_url = resolve_smoke_url()
    reason = refusal_reason_for_db_url(smoke_url)
    if reason:
        raise Refusal(reason)
    if os.environ.get("LEDGEX_ALLOW_REMOTE_DB") == "1":
        raise Refusal(
            "LEDGEX_ALLOW_REMOTE_DB=1 is set in this environment.\n"
            "That escape hatch exists in infra.env.get_db() for a deliberate\n"
            "operator write to a real database. A local viewer launcher is never\n"
            "that -- unset it and re-run `make local-up`.")
    return smoke_url


def resolve_pg_password():
    """(password_or_None, source_label). The label is what gets printed or
    logged -- NEVER the password itself. Order: an already-exported
    PGPASSWORD wins (the operator said so explicitly); otherwise read
    POSTGRES_PASSWORD out of `docker inspect <container>`'s Config.Env,
    container name from LEDGEX_PG_CONTAINER (default "ledgex" -- the
    container this task's own current-state section names as the one to
    use, NOT ledgex_tier2_syntax); otherwise assume trust auth.
    """
    if os.environ.get("PGPASSWORD"):
        return os.environ["PGPASSWORD"], "from PGPASSWORD"
    container = os.environ.get("LEDGEX_PG_CONTAINER") or DEFAULT_PG_CONTAINER
    try:
        out = subprocess.check_output(
            ["docker", "inspect", container, "--format", "{{json .Config.Env}}"],
            stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        return None, "not required"
    try:
        env_list = json.loads(out.decode("utf-8", "replace"))
    except ValueError:
        return None, "not required"
    for entry in env_list:
        if entry.startswith("POSTGRES_PASSWORD="):
            return entry.split("=", 1)[1], "from container env"
    return None, "not required"


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def check_docker():
    rc = subprocess.call(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if rc != 0:
        raise Refusal(
            "docker daemon is not reachable (`docker info` failed).\n"
            "Start Docker Desktop (or your daemon) and re-run `make local-up`.")


def check_smoke_database(smoke_url):
    """Connect AND confirm this is actually the smoke database -- migrated
    at least as far as db/migrations/ on disk. Reuses LOCAL_SMOKE.md
    section 2's exact one-time-setup wording rather than inventing a second
    phrasing of the same three commands.
    """
    import psycopg2
    try:
        conn = psycopg2.connect(smoke_url)
    except Exception as e:
        raise Refusal(
            "cannot connect to the smoke database (%s: %s).\n"
            "One-time setup, from the repo root:\n"
            "    createdb ledgex_smoke\n"
            "    make schema DATABASE_URL=%s\n"
            "    psql %s -v ON_ERROR_STOP=1 -f db/seeds/day4_sources.sql"
            % (type(e).__name__, str(e).strip(),
               DEFAULT_SMOKE_DATABASE_URL, DEFAULT_SMOKE_DATABASE_URL))
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT count(*) FROM schema_migrations")
                n_ledger = cur.fetchone()[0]
            except Exception:
                conn.rollback()
                raise Refusal(
                    "schema_migrations does not exist -- ledgex_smoke has never been\n"
                    "migrated. One-time setup:\n"
                    "    make schema DATABASE_URL=%s\n"
                    "    psql %s -v ON_ERROR_STOP=1 -f db/seeds/day4_sources.sql"
                    % (DEFAULT_SMOKE_DATABASE_URL, DEFAULT_SMOKE_DATABASE_URL))
            mig_dir = os.path.join(REPO_ROOT, "db", "migrations")
            n_files = len([f for f in os.listdir(mig_dir) if f.endswith(".sql")])
            if n_ledger < n_files:
                conn.rollback()
                raise Refusal(
                    "schema_migrations has %d rows but db/migrations/ has %d .sql files --\n"
                    "ledgex_smoke is behind. Bring it forward:\n"
                    "    make migrate DATABASE_URL=%s" % (n_ledger, n_files, smoke_url))
            cur.execute("SELECT count(*) FROM source")
            n_sources = cur.fetchone()[0]
            conn.rollback()
        return n_ledger, n_files, n_sources
    finally:
        conn.close()


def check_minio():
    """Service health only -- GET .../minio/health/live. Bucket
    verification is `make smoke-real` step 5's job, and it needs
    object-store credentials this launcher has no reason to require. Saying
    that honestly here matches the coverage-honesty discipline the rest of
    this repo already uses (make golden, make test, smoke_real.py's own
    NOT_PROVEN block).
    """
    url = os.environ.get("OBJECT_STORE_URL")
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(REPO_ROOT, ".env"), override=False)
        except ImportError:
            pass
        url = os.environ.get("OBJECT_STORE_URL") or DEFAULT_OBJECT_STORE_URL
    health_url = url.rstrip("/") + "/minio/health/live"
    try:
        with urllib.request.urlopen(health_url, timeout=8) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        raise Refusal(
            "cannot reach the object store at %s (%s).\n"
            "If this is the local MinIO container, start it and re-run `make local-up`."
            % (url, type(e).__name__))
    if status >= 400:
        raise Refusal("object store health check at %s returned HTTP %d." % (health_url, status))
    return url, status


# ---------------------------------------------------------------------------
# Pidfile / process bookkeeping
# ---------------------------------------------------------------------------

def read_pidfile():
    try:
        with open(PIDFILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def write_pidfile(pid, database_url):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = PIDFILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({
            "pid": pid,
            "database_url": database_url,
            "port": VIEWER_PORT,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }, f)
    os.replace(tmp, PIDFILE)


def remove_pidfile():
    try:
        os.remove(PIDFILE)
    except FileNotFoundError:
        pass


def process_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours to signal-probe
    return True


def process_cmdline(pid):
    """Best-effort full command line for `pid`, or "" if unreadable. Uses
    `ps`, not /proc -- /proc does not exist on macOS, and this repo's own
    dev machine is a Mac.
    """
    try:
        out = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="],
                                      stderr=subprocess.DEVNULL, timeout=5)
        return out.decode("utf-8", "replace").strip()
    except Exception:
        return ""


def is_viewer_cmdline(cmdline):
    return "uvicorn" in cmdline and "api.main:app" in cmdline and str(VIEWER_PORT) in cmdline


def classify_pidfile():
    """The four-way state this launcher's idempotency and stop logic both
    key off. Never signals or kills anything -- purely a read, which is
    what lets scripts/test_local_up.py call it directly against a harmless
    `sleep 60` stand-in without any risk.
    """
    info = read_pidfile()
    if info is None:
        return PidStatus("absent", None)
    pid = info.get("pid")
    if not isinstance(pid, int) or not process_alive(pid):
        return PidStatus("stale", info)
    if not is_viewer_cmdline(process_cmdline(pid)):
        return PidStatus("foreign", info)
    return PidStatus("ours", info)


def port_listener_info():
    """Best-effort (pid, command) of whatever is listening on VIEWER_PORT
    when there is no pidfile to explain it. None if nothing is listening or
    `lsof` is unavailable -- lsof ships with macOS, so absence here just
    means "cannot confirm", not "nothing there".
    """
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", "-iTCP:%d" % VIEWER_PORT, "-sTCP:LISTEN", "-Fpc"],
            stderr=subprocess.DEVNULL, timeout=5).decode("utf-8", "replace")
    except Exception:
        return None
    pid, cmd = None, None
    for line in out.splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif line.startswith("c"):
            cmd = line[1:]
    return (pid, cmd or "?") if pid else None


# ---------------------------------------------------------------------------
# Health check / log tail
# ---------------------------------------------------------------------------

def health_check(timeout_s=HEALTH_TIMEOUT_S):
    """Poll GET /v1/rights until 200, with backoff. Returns (ok, elapsed_s).
    /v1/rights is the same endpoint scripts/smoke_real.py's step_viewer
    already treats as "the viewer is up" -- not re-derived, just reused.
    """
    url = VIEWER_URL + "/v1/rights"
    t0 = time.monotonic()
    delay = 0.25
    while time.monotonic() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True, time.monotonic() - t0
        except Exception:
            pass
        time.sleep(delay)
        delay = min(delay * 1.5, 2.0)
    return False, time.monotonic() - t0


def log_tail(n=20):
    try:
        with open(LOGFILE, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return "(no log file at %s)" % LOGFILE
    lines = data.decode("utf-8", "replace").splitlines()
    return "\n".join(lines[-n:]) if lines else "(log file is empty)"


# ---------------------------------------------------------------------------
# Spawning
# ---------------------------------------------------------------------------

def build_child_env(smoke_url):
    """The viewer's environment, built explicitly rather than inherited
    as-is. DATABASE_URL is OVERRIDDEN here regardless of what is already in
    os.environ or .env -- the same fix P39 gave scripts/smoke_real.py's
    step_env(), because api/main.py reaches Postgres through
    infra.env.get_db(), whose load_dotenv(override=False) would otherwise
    leave an already-set DATABASE_URL (from a hand-run `export`, or from
    .env if something upstream already loaded it) exactly as-is.
    LEDGEX_ALLOW_REMOTE_DB is stripped even though check_remote_db_refusals()
    already refuses to reach this point if it is set -- belt and suspenders
    per this task's own requirement, not because it is expected to fire.
    """
    env = dict(os.environ)
    env["DATABASE_URL"] = smoke_url
    env.pop("LEDGEX_ALLOW_REMOTE_DB", None)
    return env


def spawn_viewer(child_env):
    os.makedirs(STATE_DIR, exist_ok=True)
    argv = [resolve_venv_python(), "-m", "uvicorn", "api.main:app",
            "--host", VIEWER_HOST, "--port", str(VIEWER_PORT)]
    kwargs = {}
    if hasattr(os, "setsid"):
        kwargs["start_new_session"] = True  # detach from this session/controlling tty
    with open(LOGFILE, "ab") as log_f:
        p = subprocess.Popen(argv, cwd=REPO_ROOT, env=child_env,
                             stdout=log_f, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, **kwargs)
    return p.pid


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _safe_db_display(smoke_url):
    # Mirrors scripts/smoke_real.py's own safe_db formatting: everything
    # after '@' only, so a URL that DID carry an inline credential (this
    # project's default does not -- password travels via PGPASSWORD) still
    # never gets printed whole.
    return smoke_url.split("@")[-1]


def print_fail(message, action="local-up"):
    sys.stderr.write("FAIL %s: %s\n" % (action, message))


def print_pass_block(n_ledger, n_sources, object_store_url, pid, elapsed, smoke_url):
    db = smoke_url.rsplit("/", 1)[-1].split("?")[0]
    print("PASS docker      daemon reachable")
    print("PASS database    %s @ %s (%d migrations, %d sources)" % (
        db, _safe_db_display(smoke_url), n_ledger, n_sources))
    print("PASS minio       service healthy (bucket not checked -- see smoke-real)")
    print("PASS viewer      pid %d, healthy in %.1fs" % (pid, elapsed))
    print("Viewer:  %s" % VIEWER_URL)
    print("Log:     %s" % LOGFILE)
    print("Stop:    make local-down")


def print_already_running(info, elapsed):
    print("PASS viewer      already running, pid %s, healthy in %.1fs" % (info["pid"], elapsed))
    print("Database: %s (bound when started; not re-checked here)" % _safe_db_display(info.get("database_url", "?")))
    print("Viewer:  %s" % VIEWER_URL)
    print("Log:     %s" % LOGFILE)
    print("Stop:    make local-down")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_up():
    smoke_url = check_remote_db_refusals()

    status = classify_pidfile()
    if status.state == "ours":
        info = status.info
        ok, elapsed = health_check(timeout_s=5)
        if not ok:
            raise Refusal(
                "pid %s (our own pidfile, %s) is running but not answering healthy at\n"
                "%s/v1/rights.\n"
                "Last log lines:\n%s\n"
                "Run `make local-down` then `make local-up` again."
                % (info["pid"], PIDFILE, VIEWER_URL, log_tail()))
        if info.get("database_url") != smoke_url:
            raise Refusal(
                "a viewer is already running (pid %s) bound to %s, not %s.\n"
                "Refusing to start a second one on the same port. Stop it first:\n"
                "    make local-down"
                % (info["pid"], _safe_db_display(info.get("database_url", "?")),
                   _safe_db_display(smoke_url)))
        print_already_running(info, elapsed)
        return 0

    if status.state == "foreign":
        info = status.info
        raise Refusal(
            "pidfile %s names pid %s, but its command line is not our viewer:\n"
            "  %s\n"
            "Refusing to touch it -- it is either a recycled pid or something else\n"
            "entirely. If it is stale, remove %s by hand after checking."
            % (PIDFILE, info["pid"], process_cmdline(info["pid"]) or "(process vanished)", PIDFILE))

    if status.state == "stale":
        remove_pidfile()  # falls through to a fresh start below

    listener = port_listener_info()
    if listener is not None:
        pid, cmd = listener
        raise Refusal(
            "port %d is already in use by pid %s (%s), which this launcher did not\n"
            "start -- there is no pidfile naming it. Refusing to start a second\n"
            "listener, and refusing to kill a process this tool does not own."
            % (VIEWER_PORT, pid, cmd))

    check_docker()
    password, _pw_source = resolve_pg_password()
    if password is not None:
        os.environ["PGPASSWORD"] = password  # this process only; never printed
    n_ledger, _n_files, n_sources = check_smoke_database(smoke_url)
    object_store_url, _minio_status = check_minio()

    child_env = build_child_env(smoke_url)
    pid = spawn_viewer(child_env)
    write_pidfile(pid, smoke_url)

    ok, elapsed = health_check()
    if not ok:
        # This is OUR fresh start failing -- clean up fully, so a failed
        # `make local-up` leaves nothing running and nothing to confuse the
        # next run's idempotency check.
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        remove_pidfile()
        raise Refusal(
            "viewer did not become healthy within %ds.\n"
            "Last log lines (%s):\n%s" % (HEALTH_TIMEOUT_S, LOGFILE, log_tail()))

    print_pass_block(n_ledger, n_sources, object_store_url, pid, elapsed, smoke_url)
    return 0


def cmd_down():
    status = classify_pidfile()
    if status.state == "absent":
        print("nothing to stop (no pidfile at %s)" % PIDFILE)
        return 0
    if status.state == "stale":
        remove_pidfile()
        print("nothing to stop (pidfile named a process that was no longer running; cleaned up %s)" % PIDFILE)
        return 0
    if status.state == "foreign":
        info = status.info
        print_fail(
            "pidfile %s names pid %s, but its command line is not our viewer:\n"
            "  %s\n"
            "Refusing to signal it. If it is stale, remove %s by hand after checking."
            % (PIDFILE, info["pid"], process_cmdline(info["pid"]) or "(process vanished)", PIDFILE),
            action="local-down")
        return 1

    info = status.info
    pid = info["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        remove_pidfile()
        print("nothing to stop (pid %d had already exited)" % pid)
        return 0

    deadline = time.monotonic() + STOP_GRACE_S
    while time.monotonic() < deadline and process_alive(pid):
        time.sleep(0.3)
    if process_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        time.sleep(0.5)

    remove_pidfile()
    print("stopped viewer (pid %d)" % pid)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_argparser():
    p = argparse.ArgumentParser(
        description="Start (default) or stop the local LedgeX viewer, bound only to the local smoke database.")
    p.add_argument("--down", action="store_true", help="stop the viewer this launcher started")
    p.add_argument("--print-interpreter", action="store_true",
                   help="print sys.executable and exit -- proves the re-exec landed on .venv-api; debug/test only")
    return p


def main():
    reexec_under_venv_python()  # must be first: everything below may import infra.env
    args = build_argparser().parse_args(sys.argv[1:])
    if args.print_interpreter:
        print(sys.executable)
        return 0
    try:
        return cmd_down() if args.down else cmd_up()
    except Refusal as e:
        print_fail(str(e), action="local-down" if args.down else "local-up")
        return 1


if __name__ == "__main__":
    sys.exit(main())
