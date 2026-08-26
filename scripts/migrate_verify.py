#!/usr/bin/env python3
"""P6: verify a database's live schema actually matches what its own
schema_migrations ledger claims -- the check that catches both remaining
failure modes migrate.py's own read-the-ledger logic cannot see by
construction:

  - recorded but not applied: a ledger row exists (by hand, bypassing this
    tool, or by any other tampering) for a migration whose DDL never
    actually ran here.
  - applied but not recorded: a migration's DDL ran here (by hand, bypassing
    this tool) but no ledger row exists for it.

migrate.py's apply_one() makes both states impossible to produce THROUGH the
tool itself (DDL and ledger row commit together, atomically, always both or
neither) -- these are states someone or something else creates by touching
the database directly. Detecting them needs an independent source of truth,
not another read of the same ledger that could itself be wrong.

Builds a disposable reference database from empty, applying ONLY the
migrations this target's ledger currently claims are applied (not every
file on disk -- deliberately, so a recorded-but-not-applied row still gets
built into the reference and shows up as a real diff, and an
applied-but-unrecorded change in the target shows up as the target having
something the reference does not). Dumps both schemas (schema_migrations
excluded from the comparison -- timestamps differ trivially) and diffs them
byte for byte. Any difference is reported and this exits non-zero; an exact
match exits 0.
"""
import pathlib
import subprocess
import sys

import psycopg2

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from infra.env import env, refuse_remote, resolved_host  # noqa: E402
from migrate import LEDGER_MIGRATION_NAME, MIGRATIONS_DIR, apply_one, ledger_exists, version_of  # noqa: E402
from migrate_baseline import admin_connect, dump_schema, parsed_url, target_dbname  # noqa: E402

REF_SUFFIX = "_migrate_verify_ref"


def main():
    # P56a: connects directly via env("DATABASE_URL") (target) and, through
    # migrate_baseline's admin_connect()/dump_schema(), to an admin/reference
    # database on the SAME host -- confirmed live, neither path went through
    # infra.env.get_db()'s own remote-host refusal. One call here, before the
    # first connection, covers both: admin_connect() always re-derives its
    # own host from this same DATABASE_URL, so it cannot point anywhere this
    # check did not already clear.
    refuse_remote(env("DATABASE_URL"))

    target = target_dbname()
    ref = f"{target}{REF_SUFFIX}"

    target_conn = psycopg2.connect(env("DATABASE_URL"))
    target_conn.autocommit = False
    with target_conn.cursor() as cur:
        if not ledger_exists(cur):
            print(f"REFUSING: {target} has no schema_migrations table -- nothing to verify "
                  "against. Run scripts/migrate.py or scripts/migrate_baseline.py first.",
                  file=sys.stderr)
            sys.exit(1)
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        recorded_versions = [r[0] for r in cur.fetchall()]
    target_conn.close()

    by_version = {version_of(p): p for p in MIGRATIONS_DIR.glob("*.sql")}
    missing_files = [v for v in recorded_versions if v not in by_version]
    if missing_files:
        print(f"REFUSING: schema_migrations records version(s) {missing_files} with no "
              "matching file in db/migrations/ -- cannot build a reference without them.",
              file=sys.stderr)
        sys.exit(1)

    admin = admin_connect("postgres")
    with admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (ref,))
        if cur.fetchone():
            cur.execute(f'DROP DATABASE "{ref}"')
        cur.execute(f'CREATE DATABASE "{ref}"')
    admin.close()

    try:
        # P47 (README finding #44, closed): a FOURTH occurrence of the exact
        # same host=u.hostname mistake -- NOT inherited via the imported
        # admin_connect()/dump_schema() (finding #44's own text named only
        # those two, believing this file's bug was entirely inherited
        # through them), but this file's own independent copy of
        # migrate_baseline.py's main() reference-database connection logic.
        # Found while fixing the other three, confirming this file had no
        # occurrence of its own left unfixed -- it did. Same fix, same reuse.
        u = parsed_url()
        host = resolved_host(env("DATABASE_URL"))
        if host is None:
            raise SystemExit(
                f"main: DATABASE_URL could not be parsed into a host -- "
                f"refusing to guess. See infra.env.resolved_host's own docstring."
            )
        # P60-4: options="-c timezone=UTC" -- this connection replays every
        # migration file (apply_one() below), bare timestamptz literals
        # included, to build the reference database this script diffs
        # against. Same fix as migrate.py's own (see that script's own
        # comment) -- without it, this reference build is exposed to the
        # identical hazard, on whatever cluster this script happens to run.
        ref_conn = psycopg2.connect(
            host=host, port=u.port or 5432, user=u.username, password=u.password,
            dbname=ref, options="-c timezone=UTC",
        )
        ref_conn.autocommit = False
        print(f"building reference from exactly the {len(recorded_versions)} migration(s) "
              f"{target}'s own ledger claims are applied")
        # 0046 (schema_migrations' own creation) first if recorded, out of
        # band, same reason migrate.py's bootstrap_ledger does this -- every
        # apply_one() call inserts its own ledger row, which needs the table
        # to already exist, and 0046 has no FK dependency on anything else
        # so applying it out of numeric order is safe.
        ledger_version = version_of(MIGRATIONS_DIR / LEDGER_MIGRATION_NAME)
        if ledger_version in recorded_versions:
            apply_one(ref_conn, by_version[ledger_version], ledger_version)
        for v in recorded_versions:
            if v == ledger_version:
                continue
            apply_one(ref_conn, by_version[v], v)
        ref_conn.close()

        target_schema = dump_schema(target, exclude_table="public.schema_migrations")
        ref_schema = dump_schema(ref, exclude_table="public.schema_migrations")

        if target_schema == ref_schema:
            print(f"MATCH -- {target}'s live schema is exactly what its ledger claims. "
                  f"{len(recorded_versions)} migration(s) verified.")
            return
        print(f"MISMATCH -- {target}'s live schema does NOT match what its ledger claims "
              f"({len(recorded_versions)} migration(s) recorded). This means at least one "
              "of: a recorded migration whose DDL isn't actually live, or DDL that's live "
              "but has no ledger row.", file=sys.stderr)
        import difflib
        diff = difflib.unified_diff(
            ref_schema.splitlines(), target_schema.splitlines(),
            fromfile=f"reference (built from {target}'s ledger)", tofile=f"{target} (live)",
            lineterm="",
        )
        print("\n".join(list(diff)[:200]), file=sys.stderr)
        sys.exit(1)
    finally:
        admin = admin_connect("postgres")
        with admin.cursor() as cur:
            # Terminate any lingering session first -- a mid-loop failure
            # above can leave ref_conn open, and DROP DATABASE refuses while
            # any session still holds it.
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (ref,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{ref}"')
        admin.close()


if __name__ == "__main__":
    main()
