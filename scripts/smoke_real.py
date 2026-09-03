#!/usr/bin/env python3
"""P50 -- one local end-to-end command: `make smoke-real`.

WHAT THIS IS FOR. Everything this repo already builds is proved in pieces --
`make db-test` for the invariant suite, `make conformance` for the pack,
`make liveness` for the sources, `make viewer-test` for the I6 gate on one
seeded fixture. None of them answers the question a session actually opens
with: is this machine wired up right now -- Docker, Postgres, the object
store, the viewer, the network to San Jose -- and does a real byte from a
real city endpoint still make it all the way through to a rights-gated
answer? This target answers exactly that, in one command, and says PASS or
FAIL.

WHAT IT PROVES (each step below prints its own line, pass or fail):
  1-2   the tooling and environment binding this run will use
  3-7   services: Docker daemon, Postgres, MinIO + bucket, viewer, internet
  8     the smoke database is migrated and its sources are seeded
  9-10  a REAL fetch from a REAL San Jose endpoint, hashed, uploaded and
        snapshotted -- then the stored bytes are re-downloaded and re-hashed
        HERE, independently, and checked against snapshot.content_hash and
        snapshot.byte_size. The ingest script's own claim that it verified
        the upload is not taken as the proof; this re-does it.
  11-12 20 parcels loaded from an immutable parcels snapshot
  13-14 one parcel read back, twice: straight SQL, then over HTTP through
        the viewer at :8420 -- which is also the only thing that proves the
        viewer process is bound to the SAME database this run wrote to
        (a viewer started against some other DATABASE_URL returns 404 for a
        parcel that demonstrably exists in SQL, and step 14 says so by name)
  15    the I6 rights gate, on REAL data, BOTH directions (P55 Phase 2 Stage
        4, prompts/P55-scoped-unblock.md §11 -- re-scoped from this step's
        original single-direction shape, recorded below under WHAT CHANGED):
        every OTHER real fact the loaded parcel carries must appear under
        `facts` with its value on the wire (the ALLOWED side), and a
        permanent, dedicated smoke_real.py fixture fact -- licensed under an
        always-blocked id this step seeds itself, so this half no longer
        depends on which real licence happens to be blocked today -- must be
        reported under omitted_for_rights and its value absent from the
        response BYTES, not from a parsed dict (the BLOCKED side).

WHAT IT DOES NOT PROVE. Read this before quoting a PASS anywhere.
  - Not a substitute for `make db-test`, `make conformance`, `make golden`,
    `make test` or `make viewer-test`. It runs none of them. A green
    smoke-real means the machine is wired and one path works end to end; it
    says nothing about the invariant suite or the pack.
  - Step 15's ALLOWED side proves the gate permits WHATEVER licence the
    loaded parcel's real facts currently carry -- not that it is specifically
    cc_by_4_0_api_2026_08/cc0_api_2026_08 by name; scripts/test_scoped_
    unblock.py's T1 is what pins the real ids. Its BLOCKED side is a
    synthetic fixture (smoke_fixture.always_blocked), the same caveat
    scripts/seed_internal_test_licences.py's own permitted fixture already
    carries, restated here for the blocked side.
  - `make viewer-test` remains the fixture-seeded both-outcomes proof against
    scripts/seed_internal_test_licences.py's own data (SEED_INTERNAL_TEST_
    LICENCES=1, a separate, PERMANENT, un-deletable, deliberately opt-in
    write this target still does not trigger); step 15 is now also a
    both-outcomes proof, but against real --phase d data instead.

WHAT CHANGED (P55 Phase 2 Stage 4). Before this pass, step 15 asserted only
the blocked side, against the real cc_by_4_0 literal -- and would SKIP, not
FAIL, if the loaded parcel ever carried no cc_by_4_0 fact (§11's own gate:
Resolution B made rebuilding ledgex_smoke change exactly that literal's
own facts, which would have made this SKIP permanently and silently, the
worse-than-a-failure shape §11 argues against). SKIP no longer exists on
this step at all: it now seeds its own blocked fact deterministically, so
an empty match on either side names a real, reportable break instead.
  - Step 12 loads 20 parcels (--phase d). It never runs --phase e. The full
    ~225k load is a separate, explicit decision.
  - Step 3 proves the Docker daemon answers and prints what is running. It
    does not assert any particular container exists, because this repo ships
    no compose file to assert against.

WRITES. This target makes REAL, PERMANENT writes -- fact rows are immutable
(fact_no_delete 0017, fact_no_update 0007/0040) and snapshot rows are too
(0021, snapshot_no_update/no_delete). That is why it binds to its own
database, SMOKE_DATABASE_URL, defaulting to postgresql://localhost/
ledgex_smoke -- the same discipline, for the same reason, that gave db-test
its own DB_TEST_DATABASE_URL (P18, finding #25) and `make test` its own
TEST_DATABASE_URL. It does not read DATABASE_URL and it does not fall back
to it: a fresh clone with no ledgex_smoke database fails LOUD with the
createdb command, rather than quietly writing permanent rows into
ledgex_schema_check, which is exactly how that database got contaminated
twice (CLAUDE.md, findings #9/#24).

RE-RUNNABLE. Step 12 loads parcels only when the smoke database has none.
On every later run it reports SKIP (already loaded) and the remaining steps
still run against those rows. Nothing here deletes anything -- there is no
teardown, because there is nothing this script writes that could be deleted
even if one were wanted.
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# ---------------------------------------------------------------------------
# Configuration. Every one of these is overridable from the environment or
# the make invocation; none of them is read from .env, deliberately -- see
# the module docstring's WRITES section and infra/env.py's own P39 comment
# about load_dotenv searching upward from the repo root.
# ---------------------------------------------------------------------------
DEFAULT_SMOKE_DB = "postgresql://localhost/ledgex_smoke"
DEFAULT_VIEWER = "http://127.0.0.1:8420"

JURISDICTION_ID = "ca_san_jose"
PARCELS_SOURCE_ID = "ca_san_jose.parcels"
PERMITS_SOURCE_ID = "ca_san_jose.building_permits_active"
VIEWER_CHANNEL = "api"          # api/main.py's own VIEWER_CHANNEL, D1
TARGET_PARCELS = 20             # what --phase d loads
BLOCKED_LICENCE = "cc_by_4_0"   # kept for the module docstring's own historical

# P55 Phase 2 Stage 4, exactly per prompts/P55-scoped-unblock.md §11: a
# permanent, ca_san_jose-scoped fixture -- namespaced smoke_fixture.*,
# deliberately NOT internal_test.* (that namespace lives in a different
# jurisdiction P42 already owns; reusing it here would misattribute this
# fixture as part of that one) -- that step_rights_gate (step 15) seeds
# for itself, on the SAME real parcel step 13 already selected, so the
# blocked side of its proof no longer depends on which real licence the
# --phase d snapshot happens to load facts under.
SMOKE_FIXTURE_LICENCE_ID = "smoke_fixture.always_blocked"
SMOKE_FIXTURE_SOURCE_ID = "smoke_fixture.blocked_source"
SMOKE_FIXTURE_FIELD_KEY = "smoke_fixture.blocked_marker"
SMOKE_FIXTURE_SENTINEL = "SMOKE FIXTURE BLOCKED VALUE - MUST NOT RENDER"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class StepFailed(Exception):
    """A step's own failure, carrying text meant for a human to act on.

    Raised rather than returned so that a step body can fail from anywhere
    inside a helper without every call site checking a return value -- the
    same shape scripts/ingest_parcels.py already uses with SystemExit for a
    fatal caller-facing condition, narrowed to a type this runner can catch
    without also swallowing a genuine SystemExit from a subprocess helper.
    """


class Runner(object):
    def __init__(self):
        self.results = []
        self.ctx = {}

    def run(self, number, name, fn):
        sys.stdout.write("\n[%02d] %s\n" % (number, name))
        sys.stdout.flush()
        t0 = time.monotonic()
        try:
            detail = fn(self.ctx)
        except StepFailed as e:
            elapsed = time.monotonic() - t0
            print("     FAIL (%.1fs)" % elapsed)
            for line in str(e).splitlines():
                print("     %s" % line)
            self.results.append((number, name, FAIL, str(e).splitlines()[0]))
            return False
        except Exception as e:  # noqa: BLE001 -- an unexpected error is a FAIL
            elapsed = time.monotonic() - t0
            print("     FAIL (%.1fs) -- unexpected %s: %s" % (elapsed, type(e).__name__, e))
            self.results.append((number, name, FAIL, "%s: %s" % (type(e).__name__, e)))
            return False
        elapsed = time.monotonic() - t0
        if isinstance(detail, tuple):
            status, detail = detail
        else:
            status = PASS
        print("     %s (%.1fs) -- %s" % (status, elapsed, detail))
        self.results.append((number, name, status, detail))
        return True


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _sh(argv, timeout=30):
    """Run a command, return (returncode, stdout+stderr). Never raises on a
    non-zero exit -- every caller here wants to report the failure itself,
    with its own remediation text, rather than surface a traceback."""
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as e:
        return 127, str(e)
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
        return 124, (out or b"").decode("utf-8", "replace") + "\n(timed out)"
    return p.returncode, (out or b"").decode("utf-8", "replace")


def _pg(ctx):
    return ctx["conn"]


def _one(conn, sql, args=None):
    with conn.cursor() as cur:
        cur.execute(sql, args or ())
        row = cur.fetchone()
    return row


def _all(conn, sql, args=None):
    with conn.cursor() as cur:
        cur.execute(sql, args or ())
        rows = cur.fetchall()
    return rows


# ---------------------------------------------------------------------------
# STEP 1 -- tooling
# ---------------------------------------------------------------------------

def step_tooling(ctx):
    missing = []
    for mod in ("psycopg2", "requests", "boto3"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise StepFailed(
            "this interpreter (%s, Python %s) cannot import: %s\n"
            "These are scripts/requirements.txt dependencies, not core/'s.\n"
            "Either:  make smoke-real SMOKE_PYTHON=.venv-ingest/bin/python3\n"
            "or:      %s -m pip install -r scripts/requirements.txt"
            % (sys.executable, ".".join(str(v) for v in sys.version_info[:3]),
               ", ".join(missing), sys.executable))
    import psycopg2  # noqa: F401  -- imported for the version string below
    return "python %s at %s; psycopg2 %s" % (
        ".".join(str(v) for v in sys.version_info[:3]), sys.executable,
        psycopg2.__version__.split(" ")[0])


# ---------------------------------------------------------------------------
# STEP 2 -- environment binding
# ---------------------------------------------------------------------------

def step_env(ctx):
    # Imported, not re-derived. infra.env._is_local is the ONE place this
    # project decides whether a DATABASE_URL points at this machine, and P47
    # (finding #44) is on record about what happens when a second caller
    # rebuilds that judgment its own way: migrate_baseline silently dropped
    # the `?host=/tmp` unix-socket form and had to be repaired. Reaching past
    # the underscore is the lesser cost here; if a second consumer ever wants
    # it, promoting it to a public name is a one-line change in infra/env.py.
    from infra.env import _is_local, resolved_host

    smoke_url = os.environ.get("SMOKE_DATABASE_URL") or DEFAULT_SMOKE_DB
    ctx["smoke_url"] = smoke_url
    ctx["viewer"] = (os.environ.get("LEDGEX_VIEWER_URL") or DEFAULT_VIEWER).rstrip("/")

    host = resolved_host(smoke_url)
    if not _is_local(smoke_url):
        raise StepFailed(
            "SMOKE_DATABASE_URL resolves to host %r, which is not local.\n"
            "This target makes PERMANENT writes (fact/snapshot rows cannot be\n"
            "deleted or updated -- 0017, 0007/0040, 0021). It refuses a non-local\n"
            "target outright and has no override flag, unlike infra.env.get_db()'s\n"
            "LEDGEX_ALLOW_REMOTE_DB escape hatch: there is no legitimate reason to\n"
            "point a smoke test at a real database.\n"
            "Set SMOKE_DATABASE_URL to a local database, e.g. %s"
            % (host, DEFAULT_SMOKE_DB))

    if os.environ.get("LEDGEX_ALLOW_REMOTE_DB") == "1":
        raise StepFailed(
            "LEDGEX_ALLOW_REMOTE_DB=1 is set in this environment.\n"
            "That flag exists to let a deliberate operator write to a non-local\n"
            "database (infra/env.py). It has no business being set while a smoke\n"
            "test runs: the ingest subprocesses this script launches inherit the\n"
            "environment, and one mistyped URL then becomes a permanent write to a\n"
            "real database. Unset it and re-run.")

    # The object store is the one place this script DOES read .env, because
    # the ingest scripts it shells out to read it the same way and there is
    # no second source of truth to prefer. Read it here only to fail early
    # and by name, rather than 200 lines later inside a subprocess.
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(REPO_ROOT, ".env"), override=False)
    except ImportError:
        pass
    missing = [k for k in ("OBJECT_STORE_URL", "OBJECT_STORE_BUCKET",
                           "OBJECT_STORE_ACCESS_KEY", "OBJECT_STORE_SECRET_KEY")
               if not os.environ.get(k)]
    if missing:
        raise StepFailed(
            "missing object-store configuration: %s\n"
            "Set them in %s/.env (see .env.example) or in the environment.\n"
            "No value is printed by this script, here or anywhere below."
            % (", ".join(missing), REPO_ROOT))
    ctx["bucket"] = os.environ["OBJECT_STORE_BUCKET"]

    # Bind every subprocess explicitly. load_dotenv(override=False) inside
    # infra.env leaves an already-set DATABASE_URL alone, so setting it here
    # is what stops the repo-root .env from winning in the child -- P39's
    # "THE DEFAULT BINDING" finding, handled rather than relied upon.
    child = dict(os.environ)
    child["DATABASE_URL"] = smoke_url
    child.pop("LEDGEX_ALLOW_REMOTE_DB", None)
    ctx["child_env"] = child

    safe_db = smoke_url.split("@")[-1]
    return "smoke db -> %s | viewer -> %s | bucket -> %s" % (
        safe_db, ctx["viewer"], ctx["bucket"])


# ---------------------------------------------------------------------------
# STEP 3 -- Docker daemon
# ---------------------------------------------------------------------------

def step_docker(ctx):
    rc, out = _sh(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=20)
    if rc == 127:
        raise StepFailed("docker not found on PATH.")
    if rc != 0:
        raise StepFailed(
            "`docker info` exited %d -- the daemon is not reachable.\n"
            "Start Docker Desktop (or your daemon) and re-run.\n"
            "%s" % (rc, out.strip()))
    server = out.strip().splitlines()[-1] if out.strip() else "?"
    rc2, ps = _sh(["docker", "ps", "--format", "{{.Names}} ({{.Image}}) {{.Ports}}"], timeout=20)
    names = [ln for ln in ps.splitlines() if ln.strip()] if rc2 == 0 else []
    for ln in names:
        print("       running: %s" % ln)
    if not names:
        print("       (no containers running -- this step does not require any;"
              " see step 4 for whether Postgres is actually reachable)")
    return "daemon %s, %d container(s) running" % (server, len(names))


# ---------------------------------------------------------------------------
# STEP 4 -- Postgres
# ---------------------------------------------------------------------------

def step_postgres(ctx):
    import psycopg2
    try:
        conn = psycopg2.connect(ctx["smoke_url"])
    except Exception as e:
        raise StepFailed(
            "cannot connect to SMOKE_DATABASE_URL.\n"
            "psycopg2: %s\n"
            "If the database simply does not exist yet, create it once:\n"
            "    createdb ledgex_smoke\n"
            "    make schema DATABASE_URL=%s\n"
            "    psql %s -v ON_ERROR_STOP=1 -f db/seeds/day4_sources.sql\n"
            "This target deliberately does NOT fall back to DATABASE_URL."
            % (str(e).strip(), DEFAULT_SMOKE_DB, DEFAULT_SMOKE_DB))
    conn.autocommit = False
    ctx["conn"] = conn
    ver = _one(conn, "SHOW server_version")[0]
    try:
        postgis = _one(conn, "SELECT postgis_lib_version()")[0]
    except Exception:
        conn.rollback()
        raise StepFailed(
            "connected, but PostGIS is not installed in this database.\n"
            "§11 requires PostgreSQL 16 + PostGIS 3.4. Run `make schema` against it.")
    if not ver.startswith("16"):
        print("       WARNING: server_version=%s -- §11 specifies PostgreSQL 16."
              " Not failing this step, but a schema-dump diff against this server"
              " would be a false positive (see the Makefile's own note)." % ver)
    return "PostgreSQL %s, PostGIS %s" % (ver, postgis)


# ---------------------------------------------------------------------------
# STEP 5 -- object store
# ---------------------------------------------------------------------------

def step_object_store(ctx):
    import boto3
    import botocore.exceptions
    import requests

    endpoint = os.environ["OBJECT_STORE_URL"]
    bucket = ctx["bucket"]
    try:
        r = requests.get(endpoint.rstrip("/") + "/minio/health/live", timeout=8)
        health = "health/live %d" % r.status_code
    except Exception as e:
        # Not fatal on its own: the health path is MinIO-specific and this
        # endpoint is meant to be swappable for R2 (see .env's own comment).
        # head_bucket below is the check that actually matters.
        health = "health probe unavailable (%s)" % type(e).__name__

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["OBJECT_STORE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["OBJECT_STORE_SECRET_KEY"],
    )
    try:
        s3.head_bucket(Bucket=bucket)
    except botocore.exceptions.EndpointConnectionError as e:
        raise StepFailed(
            "cannot reach the object store at %s.\n"
            "botocore: %s\n"
            "If this is the local MinIO, start it and re-run." % (endpoint, e))
    except botocore.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code", "?")
        raise StepFailed(
            "bucket %r is not usable at %s (S3 error %s).\n"
            "If the bucket does not exist, create it WITH OBJECT LOCK ENABLED --\n"
            ".env's own comment records why: COMPLIANCE-mode Object Lock can only\n"
            "be set at bucket creation and can never be retrofitted."
            % (bucket, endpoint, code))
    ctx["s3"] = s3
    return "bucket %r reachable at %s (%s)" % (bucket, endpoint, health)


# ---------------------------------------------------------------------------
# STEP 6 -- viewer
# ---------------------------------------------------------------------------

def step_viewer(ctx):
    import requests
    base = ctx["viewer"]
    try:
        r = requests.get(base + "/v1/rights", timeout=8)
    except Exception as e:
        raise StepFailed(
            "no viewer answering at %s (%s).\n"
            "Start it from the repo root, bound to the SMOKE database:\n"
            "    DATABASE_URL=%s .venv-api/bin/python3 -m uvicorn api.main:app \\\n"
            "        --host 127.0.0.1 --port 8420\n"
            "api/main.py is localhost-only by design -- do not bind it wider."
            % (base, type(e).__name__, ctx["smoke_url"]))
    if r.status_code != 200:
        raise StepFailed("GET %s/v1/rights returned %d, expected 200.\n%s"
                         % (base, r.status_code, r.text[:400]))
    return "GET /v1/rights -> 200 at %s" % base


# ---------------------------------------------------------------------------
# STEP 7 -- outbound internet, to the real source
# ---------------------------------------------------------------------------

def step_internet(ctx):
    """Reachability of the endpoint step 9 will actually fetch.

    The URL is imported from scripts/ingest_zoning_permits.py, never
    retyped here -- a smoke test that probes a hand-copied URL and then
    fetches a different one would report green on the wrong thing.
    """
    import requests
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    from ingest_zoning_permits import ENDPOINT_URL_PERMITS

    ctx["permits_url"] = ENDPOINT_URL_PERMITS
    host = urllib.parse.urlparse(ENDPOINT_URL_PERMITS).netloc
    try:
        r = requests.get(ENDPOINT_URL_PERMITS, timeout=25, stream=True,
                         headers={"Range": "bytes=0-2047"})
    except Exception as e:
        raise StepFailed(
            "cannot reach %s (%s: %s).\n"
            "This machine needs outbound internet to the San Jose open-data hosts.\n"
            "Nothing downstream of here can run without it."
            % (host, type(e).__name__, e))
    try:
        prefix = next(r.iter_content(2048), b"")
    finally:
        r.close()
    if r.status_code >= 400:
        raise StepFailed(
            "%s answered HTTP %d for the permits CSV.\n"
            "The endpoint is reachable but not serving -- check whether the city\n"
            "moved the resource (docs/LEDGEX_SPEC.md §7 is the source list of record)."
            % (host, r.status_code))
    header = prefix.decode("utf-8", "replace").splitlines()[0][:80] if prefix else "(empty)"
    return "%s -> HTTP %d, first bytes look like: %s" % (host, r.status_code, header)


# ---------------------------------------------------------------------------
# STEP 8 -- schema and seed state of the smoke database
# ---------------------------------------------------------------------------

def step_schema(ctx):
    conn = _pg(ctx)
    try:
        n_ledger = _one(conn, "SELECT count(*) FROM schema_migrations")[0]
    except Exception:
        conn.rollback()
        raise StepFailed(
            "schema_migrations does not exist -- this database has never been\n"
            "migrated. One-time setup:\n"
            "    make schema DATABASE_URL=%s\n"
            "    psql %s -v ON_ERROR_STOP=1 -f db/seeds/day4_sources.sql"
            % (ctx["smoke_url"], ctx["smoke_url"]))
    mig_dir = os.path.join(REPO_ROOT, "db", "migrations")
    n_files = len([f for f in os.listdir(mig_dir) if f.endswith(".sql")])
    if n_ledger < n_files:
        raise StepFailed(
            "schema_migrations has %d rows but db/migrations/ has %d .sql files --\n"
            "this database is behind. Bring it forward:\n"
            "    make migrate DATABASE_URL=%s"
            % (n_ledger, n_files, ctx["smoke_url"]))

    have = dict(_all(conn, "SELECT id, licence_id FROM source WHERE id IN (%s, %s)",
                     (PARCELS_SOURCE_ID, PERMITS_SOURCE_ID)))
    conn.rollback()
    for sid in (PARCELS_SOURCE_ID, PERMITS_SOURCE_ID):
        if sid not in have:
            raise StepFailed(
                "source %r is not seeded in this database.\n"
                "A snapshot row has a foreign key to source, so the fetch in step 9\n"
                "cannot be recorded without it. Seed once:\n"
                "    psql %s -v ON_ERROR_STOP=1 -f db/seeds/day4_sources.sql"
                % (sid, ctx["smoke_url"]))
    return "%d migrations recorded (%d files on disk); sources seeded: %s" % (
        n_ledger, n_files, ", ".join("%s -> %s" % (k, v) for k, v in sorted(have.items())))


# ---------------------------------------------------------------------------
# STEP 9 -- a real fetch of a real source: hash, upload, snapshot
# ---------------------------------------------------------------------------

def step_fetch(ctx):
    """Delegates to scripts/ingest_zoning_permits.py --source permits --phase b.

    Deliberately not a hand-rolled fetch. That script is the audited path
    (C7 snapshot-every-fetch policy, two fetches proving the same content
    hashes to the same key, job_run rows either way, P45's fail-loud-on-
    non-2xx fix) -- re-implementing a "simpler" fetch here would prove a
    code path nothing else uses. The permits CSV is the smallest of the
    three active San Jose sources; the parcels GeoJSON is the same file
    --phase e reads and is not fetched by this target.
    """
    before = _one(_pg(ctx), "SELECT count(*) FROM snapshot WHERE source_id = %s",
                  (PERMITS_SOURCE_ID,))[0]
    _pg(ctx).rollback()
    argv = [sys.executable, os.path.join("scripts", "ingest_zoning_permits.py"),
            "--source", "permits", "--phase", "b"]
    print("       $ DATABASE_URL=<smoke> %s" % " ".join(argv[1:]))
    p = subprocess.Popen(argv, cwd=REPO_ROOT, env=ctx["child_env"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = p.communicate()
    text = (out or b"").decode("utf-8", "replace")
    for line in text.splitlines():
        print("       | %s" % line)
    if p.returncode != 0:
        raise StepFailed(
            "ingest_zoning_permits.py --source permits --phase b exited %d.\n"
            "Its own output is above. A non-2xx response from the city endpoint\n"
            "fails this phase deliberately (P45 Fix 2) -- the snapshot row is still\n"
            "recorded, so check `SELECT * FROM job_run ORDER BY started_at DESC`\n"
            "in the smoke database to see what came back." % p.returncode)

    row = _one(_pg(ctx),
               "SELECT id, content_hash, byte_size, media_type, object_uri, "
               "http_status, fetched_at FROM snapshot WHERE source_id = %s "
               "ORDER BY fetched_at DESC LIMIT 1", (PERMITS_SOURCE_ID,))
    _pg(ctx).rollback()
    if row is None:
        raise StepFailed("the fetch reported success but no snapshot row exists for %s."
                         % PERMITS_SOURCE_ID)
    sid, digest, byte_size, media_type, object_uri, http_status, fetched_at = row
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise StepFailed("snapshot.content_hash is not a lowercase sha-256 hex digest: %r" % digest)
    ctx["permits_snapshot"] = {
        "snapshot_id": sid, "content_hash": digest, "byte_size": byte_size,
        "media_type": media_type, "object_uri": object_uri, "http_status": http_status,
    }
    after = _one(_pg(ctx), "SELECT count(*) FROM snapshot WHERE source_id = %s",
                 (PERMITS_SOURCE_ID,))[0]
    _pg(ctx).rollback()
    novelty = "new snapshot" if after > before else "content unchanged, existing snapshot reused"
    return "%s | http %s | %s bytes | sha256 %s... | %s" % (
        novelty, http_status, "{:,}".format(byte_size), digest[:16], sid)


# ---------------------------------------------------------------------------
# STEP 10 -- independent SHA-256 verification of the stored bytes
# ---------------------------------------------------------------------------

def step_verify_hash(ctx):
    """Re-download the object and re-hash it HERE.

    Step 9's script verifies its own upload, and this step does not take
    that on trust -- the whole point of a smoke test is that the claim and
    the check come from different code. This reads snapshot.object_uri,
    streams the bytes back out of the store, and compares BOTH the digest
    and the byte count against what the snapshot row says.
    """
    snap = ctx["permits_snapshot"]
    uri = snap["object_uri"]
    if not uri.startswith("s3://"):
        raise StepFailed("snapshot.object_uri is not an s3:// URI: %r" % uri)
    rest = uri[len("s3://"):]
    bucket, _, key = rest.partition("/")
    if not key:
        raise StepFailed("snapshot.object_uri has no key: %r" % uri)

    hasher = hashlib.sha256()
    total = 0
    body = ctx["s3"].get_object(Bucket=bucket, Key=key)["Body"]
    try:
        while True:
            chunk = body.read(8 * 1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            total += len(chunk)
    finally:
        body.close()
    digest = hasher.hexdigest()

    if digest != snap["content_hash"]:
        raise StepFailed(
            "SHA-256 MISMATCH between the stored object and its snapshot row.\n"
            "  object_uri : %s\n"
            "  stored bytes sha256 : %s\n"
            "  snapshot.content_hash: %s\n"
            "This is a provenance failure, not a flake -- the snapshot row cites a\n"
            "digest the bytes it points at do not have." % (uri, digest, snap["content_hash"]))
    if total != snap["byte_size"]:
        raise StepFailed(
            "byte_size mismatch: stored object is %d bytes, snapshot.byte_size says %d."
            % (total, snap["byte_size"]))
    expected_key = "sha256/%s/%s" % (digest[:2], digest)
    if key != expected_key:
        raise StepFailed(
            "content-addressing broken: object is stored at key %r but its own digest\n"
            "says it belongs at %r." % (key, expected_key))
    return "re-hashed %s bytes from %s -- digest, byte_size and content-addressed key all match" % (
        "{:,}".format(total), uri)


# ---------------------------------------------------------------------------
# STEP 11 -- an immutable parcels snapshot to bind the load to
# ---------------------------------------------------------------------------

def step_parcels_snapshot(ctx):
    row = _one(_pg(ctx),
               "SELECT id, content_hash, byte_size, fetched_at FROM snapshot "
               "WHERE source_id = %s AND http_status BETWEEN 200 AND 299 "
               "ORDER BY fetched_at DESC LIMIT 1", (PARCELS_SOURCE_ID,))
    _pg(ctx).rollback()
    if row is None:
        raise StepFailed(
            "no successful parcels snapshot exists in the smoke database.\n"
            "--phase d must bind to an immutable snapshot row (P45 Fix 1); it will\n"
            "not guess one, and this target will not fetch the full parcels GeoJSON\n"
            "on your behalf -- that is the same file --phase e reads, and downloading\n"
            "it is a deliberate, one-time act, not a smoke-test side effect.\n"
            "Run it once:\n"
            "    DATABASE_URL=%s %s scripts/ingest_parcels.py --phase b\n"
            "then re-run `make smoke-real`. Every later run reuses this snapshot."
            % (ctx["smoke_url"], sys.executable))
    sid, digest, byte_size, fetched_at = row
    ctx["parcels_snapshot_id"] = sid
    return "%s | %s bytes | fetched %s" % (sid, "{:,}".format(byte_size), fetched_at)


# ---------------------------------------------------------------------------
# STEP 12 -- load 20 parcels
# ---------------------------------------------------------------------------

def step_ingest(ctx):
    conn = _pg(ctx)
    n = _one(conn, "SELECT count(*) FROM parcel WHERE jurisdiction_id = %s",
             (JURISDICTION_ID,))[0]
    conn.rollback()
    if n >= TARGET_PARCELS:
        return (SKIP, "%d parcels already loaded -- --phase d is not re-run "
                      "(it is not idempotent: a second load now REFUSES via "
                      "load_parcels' own source_feature_identity check -- C10, P59; "
                      "corrected from an earlier claim citing "
                      "parcel_jurisdiction_id_apn_key, which 0034 dropped). "
                      "Steps 13-15 run against these rows."
                % n)
    if n != 0:
        raise StepFailed(
            "the smoke database has %d parcels -- neither empty nor a completed\n"
            "20-parcel load. Something wrote a partial state here. Inspect it before\n"
            "re-running; this target will not load on top of it." % n)

    argv = [sys.executable, os.path.join("scripts", "ingest_parcels.py"),
            "--phase", "d", "--snapshot-id", ctx["parcels_snapshot_id"]]
    print("       $ DATABASE_URL=<smoke> %s" % " ".join(argv[1:]))
    p = subprocess.Popen(argv, cwd=REPO_ROOT, env=ctx["child_env"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = p.communicate()
    text = (out or b"").decode("utf-8", "replace")
    for line in text.splitlines():
        print("       | %s" % line)
    if p.returncode != 0:
        raise StepFailed("ingest_parcels.py --phase d exited %d. Its output is above."
                         % p.returncode)
    n2 = _one(conn, "SELECT count(*) FROM parcel WHERE jurisdiction_id = %s",
              (JURISDICTION_ID,))[0]
    nf = _one(conn, "SELECT count(*) FROM fact f JOIN parcel p ON p.id = f.parcel_id "
                    "WHERE p.jurisdiction_id = %s", (JURISDICTION_ID,))[0]
    conn.rollback()
    if n2 < TARGET_PARCELS:
        raise StepFailed("expected at least %d parcels after the load, found %d."
                         % (TARGET_PARCELS, n2))
    return "loaded %d parcels carrying %d facts, all citing snapshot %s" % (
        n2, nf, ctx["parcels_snapshot_id"])


# ---------------------------------------------------------------------------
# STEP 13 -- query one parcel back, straight SQL
# ---------------------------------------------------------------------------

def step_query_sql(ctx):
    conn = _pg(ctx)
    row = _one(conn,
               "SELECT p.id, p.apn FROM parcel p WHERE p.jurisdiction_id = %s "
               "AND EXISTS (SELECT 1 FROM fact f WHERE f.parcel_id = p.id) "
               "ORDER BY p.apn NULLS LAST LIMIT 1", (JURISDICTION_ID,))
    if row is None:
        conn.rollback()
        raise StepFailed("no parcel with any fact exists in the smoke database.")
    parcel_id, apn = row
    facts = _all(conn,
                 "SELECT field_key, licence_id, source_id, snapshot_id, value "
                 "FROM current_fact_at(now()) WHERE parcel_id = %s ORDER BY field_key",
                 (str(parcel_id),))
    conn.rollback()
    if not facts:
        raise StepFailed(
            "parcel %s has fact rows but current_fact_at(now()) returns none for it.\n"
            "The current_fact materialized view is probably stale -- see db/README.md;\n"
            "the first refresh of a database must be a plain REFRESH MATERIALIZED VIEW,\n"
            "never CONCURRENTLY." % parcel_id)
    ctx["parcel_id"] = str(parcel_id)
    ctx["sql_facts"] = facts
    for fk, lic, src, snap, _v in facts:
        print("       %-28s licence=%-12s source=%s" % (fk, lic, src))
    return "parcel %s (apn %s) -> %d current fact(s)" % (parcel_id, apn, len(facts))


# ---------------------------------------------------------------------------
# STEP 14 -- query the same parcel back over HTTP, through the viewer
# ---------------------------------------------------------------------------

def step_query_viewer(ctx):
    import requests
    url = "%s/v1/parcels/%s/facts" % (ctx["viewer"], ctx["parcel_id"])
    r = requests.get(url, timeout=20)
    if r.status_code == 404:
        raise StepFailed(
            "the viewer returned 404 for a parcel that demonstrably exists in SQL\n"
            "(step 13 just read it). That means the uvicorn process at %s is bound to a\n"
            "DIFFERENT database than SMOKE_DATABASE_URL -- almost certainly the one in\n"
            ".env, because api/main.py reaches Postgres through infra.env.get_db().\n"
            "Restart it against the smoke database:\n"
            "    DATABASE_URL=%s .venv-api/bin/python3 -m uvicorn api.main:app \\\n"
            "        --host 127.0.0.1 --port 8420"
            % (ctx["viewer"], ctx["smoke_url"]))
    if r.status_code != 200:
        raise StepFailed("GET %s returned %d\n%s" % (url, r.status_code, r.text[:600]))
    body = r.text
    try:
        doc = json.loads(body)
    except ValueError:
        raise StepFailed("viewer response was not JSON:\n%s" % body[:400])
    for key in ("parcel_id", "as_of", "channel", "facts", "omitted_for_rights"):
        if key not in doc:
            raise StepFailed("viewer response is missing %r -- expected the "
                             "ParcelFactsResponse shape." % key)
    if doc["parcel_id"] != ctx["parcel_id"]:
        raise StepFailed("viewer echoed parcel_id %r, asked for %r"
                         % (doc["parcel_id"], ctx["parcel_id"]))
    ctx["viewer_body"] = body
    ctx["viewer_doc"] = doc
    return "GET /v1/parcels/%s/facts -> 200 | channel=%s | %d permitted, %d omitted_for_rights" % (
        ctx["parcel_id"][:8] + "...", doc["channel"],
        len(doc["facts"]), len(doc["omitted_for_rights"]))


# ---------------------------------------------------------------------------
# STEP 15 -- the I6 rights gate, on real data (P55 Phase 2 Stage 4, re-scoped
# per prompts/P55-scoped-unblock.md §11 -- design there, implementation here,
# nothing invented that wasn't already decided)
# ---------------------------------------------------------------------------

def _ensure_blocked_fixture(conn, parcel_id):
    """Idempotently seeds ONE permanent, ca_san_jose-scoped fact -- licensed
    under a dedicated, always-blocked fixture licence -- on the SAME real
    parcel step 13 already selected. Modelled directly on
    scripts/seed_internal_test_licences.py's own P42 "blocked fixture fact"
    pattern (cite a real-shaped licence from a new fact row; nothing about
    any OTHER licence is touched), adapted to attach to a REAL ca_san_jose
    parcel rather than a synthetic internal_test.* one -- which is exactly
    why this needs its own licence/source/snapshot/field_definition, all
    namespaced smoke_fixture.*, rather than reusing internal_test.*'s.

    Permanent, like every other write this target makes (module docstring's
    own WRITES section) -- no separate opt-in gate, because this database is
    already scoped to SMOKE_DATABASE_URL by construction.

    WHERE NOT EXISTS for the fact row (P42's own reason: `fact` has no
    unique index this INSERT's own conflict target could lean on); ON
    CONFLICT DO NOTHING for the rows that do have real primary keys.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO licence (id, display_name, restriction, commercial_use, "
            "redistribution, attribution_text, observed_at, cleared_by, cleared_at, notes) "
            "VALUES (%s, 'smoke_real.py step 15 fixture -- always blocked', 'open', "
            "'allowed', 'allowed', NULL, now(), 'smoke_fixture_seed', now(), "
            "'P55 Phase 2 Stage 4 -- permanent smoke_real.py fixture, not a real licence. "
            "Every licence_channel row is deliberately allowed=false, forever, so step 15 "
            "always has a genuinely-blocked fact to prove the gate withholds, independent "
            "of which real licence the --phase d snapshot happens to load facts under.') "
            "ON CONFLICT (id) DO NOTHING",
            (SMOKE_FIXTURE_LICENCE_ID,),
        )
        cur.execute(
            "INSERT INTO licence_channel (licence_id, channel, allowed, rationale) "
            "SELECT %s, c, false, "
            "'P55 Phase 2 Stage 4 smoke_real.py fixture -- deliberately, permanently "
            "blocked on every channel. Not a real rights decision.' "
            "FROM unnest(enum_range(NULL::output_channel)) AS c "
            "ON CONFLICT (licence_id, channel) DO NOTHING",
            (SMOKE_FIXTURE_LICENCE_ID,),
        )
        cur.execute(
            "INSERT INTO source (id, jurisdiction_id, display_name, steward, steward_class, method, "
            "phase_status, phase_status_reason, endpoint_url, licence_id, active) "
            "VALUES (%s, %s, 'smoke_real.py step 15 fixture source', 'smoke_real.py', 'unknown', "
            "'bulk', 'active', 'P55 Phase 2 Stage 4 fixture -- not a real ingest source; "
            "method=bulk (not manual) so I13 does not forbid this fact from existing.', "
            "'https://smoke-fixture.invalid/p55', %s, false) ON CONFLICT (id) DO NOTHING",
            (SMOKE_FIXTURE_SOURCE_ID, JURISDICTION_ID, SMOKE_FIXTURE_LICENCE_ID),
        )
        digest = hashlib.sha256(SMOKE_FIXTURE_SENTINEL.encode()).hexdigest()
        snapshot_id = "%s:sha256:%s" % (SMOKE_FIXTURE_SOURCE_ID, digest)
        cur.execute(
            "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, "
            "byte_size, request, http_status, fetched_at, licence_observed_id) "
            "VALUES (%s, %s, 's3://smoke-fixture/p55/blocked', %s, 'application/json', 1, "
            "'{}'::jsonb, 200, now(), %s) ON CONFLICT (id) DO NOTHING",
            (snapshot_id, SMOKE_FIXTURE_SOURCE_ID, digest, SMOKE_FIXTURE_LICENCE_ID),
        )
        cur.execute(
            "INSERT INTO field_definition (field_key, display_name, claim, value_type, "
            "category, description) VALUES (%s, 'smoke_real.py fixture marker', "
            "'public_record', 'string', 'parcel', "
            "'P55 Phase 2 Stage 4 fixture field -- not a real field.') "
            "ON CONFLICT (field_key) DO NOTHING",
            (SMOKE_FIXTURE_FIELD_KEY,),
        )
        now_ts = datetime.datetime.now(datetime.timezone.utc)
        cur.execute(
            "INSERT INTO fact (parcel_id, jurisdiction_id, field_key, value, method, "
            "source_id, snapshot_id, retrieved_at, source_url, licence_id, confidence, "
            "confidence_rule_id, effective_from, pack_version) "
            "SELECT %s, %s, %s, %s, 'bulk', %s, %s, %s, "
            "'https://smoke-fixture.invalid/p55', %s, 'high', 'smoke_fixture.rule', %s, "
            "'v1.0' "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM fact WHERE parcel_id = %s AND field_key = %s AND licence_id = %s"
            ")",
            (
                parcel_id, JURISDICTION_ID, SMOKE_FIXTURE_FIELD_KEY,
                json.dumps(SMOKE_FIXTURE_SENTINEL), SMOKE_FIXTURE_SOURCE_ID, snapshot_id,
                now_ts, SMOKE_FIXTURE_LICENCE_ID, now_ts,
                parcel_id, SMOKE_FIXTURE_FIELD_KEY, SMOKE_FIXTURE_LICENCE_ID,
            ),
        )
    conn.commit()


def step_rights_gate(ctx):
    """The I6 rights gate, on real data, both directions (§11 of
    prompts/P55-scoped-unblock.md):

    BLOCKED side: this step seeds (idempotently, permanently) ONE fact on
    the real parcel step 13 selected, under a dedicated fixture licence that
    is allowed=false on every channel forever -- so this half of the proof
    no longer depends on which real licence happens to be blocked today.
    The response must carry that field_key under omitted_for_rights, must
    carry no fixture-licensed fact under `facts`, and -- the assertion that
    actually matters -- the fixture value must not appear in the response
    bytes at all.

    ALLOWED side (new, P55): every OTHER current fact on this parcel -- the
    real, --phase d-ingested ones -- must be reported under `facts`, and
    its value must actually appear in the response bytes. Proven nowhere
    at smoke level before this pass.

    Both checked against ONE fresh fetch, not step 14's: the fixture fact
    is inserted by THIS step, after step 14 already ran, so reusing step
    14's response would make the blocked-side byte-absence check trivially
    true for the wrong reason (the fact didn't exist yet when that request
    was made) rather than because the gate withheld it.

    Byte-level, not dict-level, for the reason scripts/test_viewer_rights_gate.py
    already argues: a value absent from a parsed structure but present in the
    serialized body has still left the building. Scoped to scalar values
    (str/int/float/bool) -- found live during Stage 5's own smoke rehearsal:
    a dict/list value's (e.g. parcel.geometry) own re-serialization here is
    not guaranteed to byte-match Pydantic/FastAPI's actual wire encoding
    (key order, separators), so a substring search against it would prove
    nothing reliable either way. Dict/list values still get the
    parsed-structure guarantee (leaked/missing/present_keys, below) -- only
    the EXTRA byte-level check is scoped to what it can actually prove.

    No SKIP on either side (§11.4): this step controls whether the blocked
    fact exists (it seeds it itself), so an empty match there means the
    seeding broke, not "nothing to block" -- FAIL, naming that specifically.
    An empty match on the allowed side means a --phase d-loaded parcel
    (step 13's own WHERE EXISTS already required it to carry a fact) lost
    every non-fixture fact, which is itself a reportable inconsistency, not
    a routine skip.
    """
    conn = _pg(ctx)
    parcel_id = ctx["parcel_id"]
    _ensure_blocked_fixture(conn, parcel_id)

    # Fresh SQL read (step 13's own ctx["sql_facts"] predates the fixture)
    # and fresh HTTP fetch (step 14's own ctx["viewer_doc"]/["viewer_body"]
    # predates it too) -- see the docstring above for why reusing either
    # would be the wrong proof.
    all_facts = _all(
        conn,
        "SELECT field_key, licence_id, value FROM current_fact_at(now()) "
        "WHERE parcel_id = %s ORDER BY field_key",
        (parcel_id,),
    )
    conn.rollback()

    import requests
    url = "%s/v1/parcels/%s/facts" % (ctx["viewer"], parcel_id)
    r = requests.get(url, timeout=20)
    if r.status_code != 200:
        raise StepFailed("GET %s returned %d (after seeding the blocked fixture)\n%s"
                         % (url, r.status_code, r.text[:600]))
    body = r.text
    doc = json.loads(body)

    # Generalized per §11.3, not hardcoded to SMOKE_FIXTURE_LICENCE_ID alone:
    # "blocked" means this fact's own licence has no allowed=true row for
    # VIEWER_CHANNEL, checked live -- the same default-deny I6 itself
    # applies. This sweeps in the fixture AND, for free, any other fact
    # that happens to be genuinely blocked, without this step needing to
    # know its licence id by name.
    channel_allowed = {
        lic: allowed
        for lic, allowed in _all(
            conn,
            "SELECT licence_id, bool_or(allowed) FROM licence_channel "
            "WHERE channel = %s AND licence_id = ANY(%s) GROUP BY licence_id",
            (VIEWER_CHANNEL, list({lic for _fk, lic, _v in all_facts})),
        )
    }
    conn.rollback()
    blocked_sql = [(fk, lic, val) for fk, lic, val in all_facts
                   if not channel_allowed.get(lic, False)]
    allowed_sql = [(fk, lic, val) for fk, lic, val in all_facts
                   if channel_allowed.get(lic, False)]

    if not blocked_sql:
        raise StepFailed(
            "no blocked fact found on parcel %s after _ensure_blocked_fixture ran -- the "
            "fixture-seeding step itself is broken (or licence_channel for %r was somehow "
            "changed to allowed=true). This names the seeding, not the gate, as what to "
            "fix -- see this step's own docstring." % (parcel_id, SMOKE_FIXTURE_LICENCE_ID))
    if not allowed_sql:
        raise StepFailed(
            "parcel %s carries no fact besides the blocked fixture. Step 13's own query "
            "already required this parcel to carry a fact before the fixture was ever "
            "seeded -- a real, reportable inconsistency, not something to skip past."
            % parcel_id)

    leaked = [f for f in doc["facts"] if not channel_allowed.get(f.get("licence_id"), False)]
    if leaked:
        raise StepFailed(
            "I6 BREACH: %d blocked fact(s) appear under `facts` (permitted) in the viewer "
            "response: %s\nThe gate that produced this is core.rights.evaluate_rights_gate "
            "-- the same function the composer calls."
            % (len(leaked), ", ".join(f.get("field_key", "?") for f in leaked)))

    omitted_keys = set(o["field_key"] for o in doc["omitted_for_rights"])
    missing = [fk for fk, _l, _v in blocked_sql if fk not in omitted_keys]
    if missing:
        raise StepFailed(
            "%d blocked fact(s) are in neither `facts` nor `omitted_for_rights`: %s\n"
            "A fact silently vanishing is not the gate working -- I6 requires the\n"
            "refusal to be reported, not the row to be dropped."
            % (len(missing), ", ".join(missing)))

    def _sentinel_text(val):
        # Scalars only (str/int/float/bool) -- a dict/list value's own
        # re-serialization here (key order, separators) is not guaranteed
        # to byte-match the actual wire response's serialization (Pydantic/
        # FastAPI's own encoder), so a substring search against it proves
        # nothing reliable either way. Found live, not theoretically: a
        # geometry value on the ALLOWED side (P55's own new check) failed
        # this way -- present, correctly, in both `doc["facts"]` and the
        # raw body, just not as this function's own sort_keys=True text.
        # The parsed-structure checks (leaked/missing/present_keys, all
        # above and below) still cover dict/list values; only the extra
        # byte-level guarantee is scoped down to what it can actually prove.
        if isinstance(val, (dict, list)):
            return None
        text = json.dumps(val, default=str)
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return text if len(text) >= 6 else None

    blocked_sentinels = [(fk, t) for fk, _l, v in blocked_sql
                         for t in [_sentinel_text(v)] if t]
    hits = [fk for fk, text in blocked_sentinels if text in body]
    if hits:
        raise StepFailed(
            "I6 BREACH: the value of %d rights-blocked fact(s) appears in the raw response "
            "body even though the fact is reported as omitted: %s\n"
            "Absent from the parsed structure is not absent from the wire."
            % (len(hits), ", ".join(hits)))

    present_keys = set(f["field_key"] for f in doc["facts"])
    missing_allowed = [fk for fk, _l, _v in allowed_sql if fk not in present_keys]
    if missing_allowed:
        raise StepFailed(
            "%d fact(s) whose licence permits channel %r are NOT under `facts` in the "
            "viewer response: %s\nEither the rebuild's licence_channel row is missing/"
            "false, or the gate is over-blocking."
            % (len(missing_allowed), VIEWER_CHANNEL, ", ".join(missing_allowed)))

    allowed_sentinels = [(fk, t) for fk, _l, v in allowed_sql
                         for t in [_sentinel_text(v)] if t]
    allowed_misses = [fk for fk, text in allowed_sentinels if text not in body]
    if allowed_misses:
        raise StepFailed(
            "%d permitted fact(s) are reported under `facts` but their own value is "
            "missing from the raw response body: %s"
            % (len(allowed_misses), ", ".join(allowed_misses)))

    return ("%d allowed fact(s) (present under `facts`, values on the wire) and "
            "%d blocked fact(s) (none under `facts`, all under omitted_for_rights, "
            "values absent from the %d-byte response body)"
            % (len(allowed_sql), len(blocked_sql), len(body)))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

STEPS = [
    ("tooling and interpreter", step_tooling),
    ("environment binding", step_env),
    ("service: Docker daemon", step_docker),
    ("service: PostgreSQL + PostGIS", step_postgres),
    ("service: object store and bucket", step_object_store),
    ("service: viewer on :8420", step_viewer),
    ("network: San Jose source reachable", step_internet),
    ("smoke database: migrated and seeded", step_schema),
    ("real fetch -> hash -> upload -> snapshot", step_fetch),
    ("independent SHA-256 re-verification", step_verify_hash),
    ("parcels snapshot available to bind to", step_parcels_snapshot),
    ("ingest %d parcels (--phase d)" % TARGET_PARCELS, step_ingest),
    ("query one parcel back (SQL)", step_query_sql),
    ("query one parcel back (viewer HTTP)", step_query_viewer),
    ("I6 rights gate on real data", step_rights_gate),
]

NOT_PROVEN = """\
  - the invariant suite (`make db-test`), the pack (`make conformance`),
    the golden fixtures (`make golden`), core/'s unit suite (`make test`)
  - that the gate permits the SPECIFIC real licence ids P55 named
    (cc_by_4_0_api_2026_08/cc0_api_2026_08) rather than whatever licence the
    loaded parcel's own facts happen to carry -- step 15's allowed side
    checks the shape, not the id by name; scripts/test_scoped_unblock.py's
    T1 is what pins the real ids. `make viewer-test` remains the OTHER
    both-outcomes proof (against scripts/seed_internal_test_licences.py's
    own synthetic fixture, needing SEED_INTERNAL_TEST_LICENCES=1 run
    deliberately first -- a separate, permanent, un-deletable write this
    target still will not make for you).
  - anything about the full ~225k-parcel load (--phase e), which never runs
  - that the HTML viewer renders correctly; only one JSON route was called
  - any source other than the permits CSV and the parcels snapshot reused"""


def main():
    print("=" * 78)
    print("make smoke-real -- local end-to-end check")
    print("started %s" % datetime.datetime.now().isoformat(timespec="seconds"))
    print("=" * 78)

    runner = Runner()
    stopped_at = None
    for i, (name, fn) in enumerate(STEPS, start=1):
        if not runner.run(i, name, fn):
            stopped_at = i
            break

    conn = runner.ctx.get("conn")
    if conn is not None:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for number, name, status, detail in runner.results:
        print("  %-4s [%02d] %s" % (status, number, name))
        print("            %s" % detail.splitlines()[0])
    if stopped_at is not None:
        remaining = len(STEPS) - stopped_at
        if remaining:
            print("  ---- %d later step(s) not run: each depends on the one that failed."
                  % remaining)

    failed = [r for r in runner.results if r[2] == FAIL]
    skipped = [r for r in runner.results if r[2] == SKIP]

    print("\nNOT PROVEN by this target, green or red:")
    print(NOT_PROVEN)

    print("\n" + "=" * 78)
    if failed:
        print("RESULT: FAIL -- step %d (%s)" % (failed[0][0], failed[0][1]))
        print("=" * 78)
        return 1
    print("RESULT: PASS -- %d step(s) passed, %d skipped" % (
        len(runner.results) - len(skipped), len(skipped)))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
