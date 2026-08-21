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
  15    the I6 rights gate, on REAL data: every fact those 20 parcels carry
        cites cc_by_4_0, whose licence_channel rows are all allowed=false
        (0030, pending LD-1 clearance). So the viewer MUST report them under
        omitted_for_rights and MUST NOT put their values in the response --
        and this step asserts the values are absent from the actual response
        BYTES, not from a parsed dict.

WHAT IT DOES NOT PROVE. Read this before quoting a PASS anywhere.
  - Not a substitute for `make db-test`, `make conformance`, `make golden`,
    `make test` or `make viewer-test`. It runs none of them. A green
    smoke-real means the machine is wired and one path works end to end; it
    says nothing about the invariant suite or the pack.
  - Step 15 proves the gate holds for cc_by_4_0 on channel 'api' on these
    parcels. It does NOT prove the gate PERMITS anything -- there is no
    permitted fixture here by construction, because the only permitted data
    in this project comes from scripts/seed_internal_test_licences.py, whose
    opt-in gate (SEED_INTERNAL_TEST_LICENCES=1) makes a PERMANENT,
    un-deletable licence/licence_channel write. This target will not trigger
    that as a side effect, for the same reason viewer-test does not.
    `make viewer-test` is the both-outcomes proof; run it separately, after
    running the seed deliberately.
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
BLOCKED_LICENCE = "cc_by_4_0"   # every licence_channel row allowed=false (0030)

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
               "SELECT snapshot_id, content_hash, byte_size, media_type, object_uri, "
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
               "SELECT snapshot_id, content_hash, byte_size, fetched_at FROM snapshot "
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
                      "(it is not idempotent: a second load collides on "
                      "parcel_jurisdiction_id_apn_key). Steps 13-15 run against these rows."
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
# STEP 15 -- the I6 rights gate, on real data
# ---------------------------------------------------------------------------

def step_rights_gate(ctx):
    """Every fact these 20 parcels carry cites cc_by_4_0, and 0030 leaves every
    licence_channel row allowed=false pending LD-1 clearance. So the correct
    behaviour of the gate here is total refusal, and that is checkable without
    seeding anything: the response must carry the field_keys under
    omitted_for_rights, must carry no cc_by_4_0 fact under facts, and -- the
    assertion that actually matters -- the fact VALUES must not appear in the
    response bytes at all.

    Byte-level, not dict-level, for the reason scripts/test_viewer_rights_gate.py
    already argues: a value absent from a parsed structure but present in the
    serialized body has still left the building.
    """
    doc = ctx["viewer_doc"]
    body = ctx["viewer_body"]

    blocked_sql = [(fk, lic, val) for fk, lic, _s, _sn, val in ctx["sql_facts"]
                   if lic == BLOCKED_LICENCE]
    if not blocked_sql:
        return (SKIP, "this parcel carries no %s fact, so there is nothing for the gate "
                      "to block here. Not a pass and not a failure -- rerun after a load "
                      "that includes one, or use `make viewer-test` for the seeded "
                      "both-outcomes fixture." % BLOCKED_LICENCE)

    leaked = [f for f in doc["facts"] if f.get("licence_id") == BLOCKED_LICENCE]
    if leaked:
        raise StepFailed(
            "I6 BREACH: %d fact(s) licensed %s appear under `facts` (permitted) in the\n"
            "viewer response: %s\n"
            "Every licence_channel row for that licence is allowed=false (0030). The\n"
            "gate that produced this is core.rights.evaluate_rights_gate -- the same\n"
            "function the composer calls."
            % (len(leaked), BLOCKED_LICENCE,
               ", ".join(f.get("field_key", "?") for f in leaked)))

    omitted_keys = set(o["field_key"] for o in doc["omitted_for_rights"]
                       if o.get("licence_id") == BLOCKED_LICENCE)
    missing = [fk for fk, _l, _v in blocked_sql if fk not in omitted_keys]
    if missing:
        raise StepFailed(
            "%d blocked fact(s) are in neither `facts` nor `omitted_for_rights`: %s\n"
            "A fact silently vanishing is not the gate working -- I6 requires the\n"
            "refusal to be reported, not the row to be dropped."
            % (len(missing), ", ".join(missing)))

    sentinels = []
    for fk, _lic, val in blocked_sql:
        text = json.dumps(val, sort_keys=True, default=str)
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        if len(text) >= 6:
            sentinels.append((fk, text))
    hits = [fk for fk, text in sentinels if text in body]
    if hits:
        raise StepFailed(
            "I6 BREACH: the value of %d rights-blocked fact(s) appears in the raw\n"
            "response body even though the fact is reported as omitted: %s\n"
            "Absent from the parsed structure is not absent from the wire."
            % (len(hits), ", ".join(hits)))

    return ("%d fact(s) licensed %s: none under `facts`, all %d reported under "
            "omitted_for_rights, and %d value sentinel(s) confirmed absent from the "
            "%d-byte response body" % (len(blocked_sql), BLOCKED_LICENCE,
                                       len(omitted_keys), len(sentinels), len(body)))


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
  - that the gate ever PERMITS a fact: no permitted fixture exists here by
    construction. `make viewer-test` is the both-outcomes proof, and it
    needs scripts/seed_internal_test_licences.py run deliberately first --
    a permanent, un-deletable write this target will not make for you.
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
