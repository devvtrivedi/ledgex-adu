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
from infra.env import env  # noqa: E402
from migrate import LEDGER_MIGRATION_NAME, MIGRATIONS_DIR, apply_one, ledger_exists, version_of  # noqa: E402
from migrate_baseline import admin_connect, dump_schema, parsed_url, target_dbname  # noqa: E402

REF_SUFFIX = "_migrate_verify_ref"


def main():
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
        ref_url = env("DATABASE_URL").rsplit("/", 1)[0] + f"/{ref}"
        ref_conn = psycopg2.connect(ref_url)
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
