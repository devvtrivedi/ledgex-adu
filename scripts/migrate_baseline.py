#!/usr/bin/env python3
"""One-time adoption of a pre-ledger database into scripts/migrate.py's
schema_migrations ledger -- for a database that already has some migrations
applied by hand, from before the ledger existed (exactly ledgex_schema_check's
situation this session).

Never guesses which migrations already ran. Builds a fresh, disposable
reference database on the same server, applies EVERY migration to it from
empty via the same apply_one() logic migrate.py itself uses, dumps both
schemas with pg_dump --schema-only (target and reference, both with
schema_migrations excluded from the comparison -- the target doesn't have it
yet and the reference's rows would differ trivially by timestamp anyway),
strips the same pg_dump build-string / restrict-key noise the Makefile's own
`make schema-dump` target already strips, and diffs the rest byte for byte.

Only on an EXACT match does it record schema_migrations rows for every
migration except its own (0046, which is applied for real, not baselined --
the table has to actually exist) -- each row carries baselined=true and that
migration's CURRENT file hash, an assertion that the schema is EQUIVALENT to
having run it, not a claim that it literally did.

If the dumps differ at all, refuses and prints the diff. Resolving that is a
human decision -- apply whatever's actually missing, or investigate why a
database claiming to be "just migrations, no seed" isn't -- not something
this script decides for you.

Requires CREATE DATABASE / DROP DATABASE privilege on the same server
DATABASE_URL points at, to create and discard the disposable reference.
"""
import os
import pathlib
import subprocess
import sys
import urllib.parse

import psycopg2

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from infra.env import env  # noqa: E402
from migrate import (  # noqa: E402
    LEDGER_MIGRATION_NAME, MIGRATIONS_DIR, all_migrations, apply_one,
    file_sha256, ledger_exists, other_tables_exist, version_of,
)

REF_SUFFIX = "_migrate_baseline_ref"


def parsed_url():
    return urllib.parse.urlparse(env("DATABASE_URL"))


def admin_connect(dbname):
    u = parsed_url()
    conn = psycopg2.connect(
        host=u.hostname, port=u.port or 5432, user=u.username, password=u.password,
        dbname=dbname,
    )
    conn.autocommit = True
    return conn


def target_dbname():
    return parsed_url().path.lstrip("/")


def strip_dump_noise(text):
    lines = [
        ln for ln in text.splitlines()
        if not ln.startswith("-- Dumped by pg_dump version")
        and not ln.startswith("-- Dumped from database version")
        and not ln.startswith("\\restrict")
        and not ln.startswith("\\unrestrict")
    ]
    return "\n".join(lines)


def dump_schema(dbname, exclude_table=None):
    u = parsed_url()
    # Matches the Makefile's own PG_DUMP ?= pg_dump: CI pins this to a
    # specific version (/usr/lib/postgresql/16/bin/pg_dump) to avoid the
    # false-diff trap a mismatched client version produces (see db.yml's own
    # comment) -- an unqualified "pg_dump" here would silently use whatever
    # happens to be first on PATH instead.
    pg_dump = os.environ.get("PG_DUMP", "pg_dump")
    args = [pg_dump, "-h", u.hostname, "-p", str(u.port or 5432), "-U", u.username,
            "-d", dbname, "--schema-only", "--no-owner", "--no-privileges"]
    if exclude_table:
        args += ["--exclude-table", exclude_table]
    env_vars = {"PGPASSWORD": u.password} if u.password else {}
    result = subprocess.run(args, capture_output=True, text=True,
                             env={**os.environ, **env_vars})
    if result.returncode != 0:
        raise SystemExit(f"pg_dump failed for {dbname}:\n{result.stderr}")
    return strip_dump_noise(result.stdout)


def main():
    target = target_dbname()
    ref = f"{target}{REF_SUFFIX}"

    admin = admin_connect("postgres")
    with admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (ref,))
        if cur.fetchone():
            print(f"dropping stale reference database {ref} from a prior run")
            cur.execute(f'DROP DATABASE "{ref}"')
        print(f"creating disposable reference database {ref}")
        cur.execute(f'CREATE DATABASE "{ref}"')
    admin.close()

    try:
        target_conn = psycopg2.connect(env("DATABASE_URL"))
        target_conn.autocommit = False
        with target_conn.cursor() as cur:
            if ledger_exists(cur):
                print(f"{target} already has a schema_migrations table -- nothing to baseline. "
                      "Run scripts/migrate.py directly.")
                target_conn.close()
                return
            if not other_tables_exist(cur):
                print(f"{target} is empty -- nothing to baseline. Run scripts/migrate.py directly.")
                target_conn.close()
                return
        target_conn.close()

        u = parsed_url()
        ref_conn = psycopg2.connect(
            host=u.hostname, port=u.port or 5432, user=u.username, password=u.password,
            dbname=ref,
        )
        ref_conn.autocommit = False
        print("applying every migration to the reference database, from empty")
        migrations = all_migrations()
        ledger_path = MIGRATIONS_DIR / LEDGER_MIGRATION_NAME
        apply_one(ref_conn, ledger_path, version_of(ledger_path))
        for path in migrations:
            if path.name == LEDGER_MIGRATION_NAME:
                continue
            apply_one(ref_conn, path, version_of(path))
        ref_conn.close()

        print("dumping and comparing schemas (schema_migrations excluded from both)")
        target_schema = dump_schema(target, exclude_table="public.schema_migrations")
        ref_schema = dump_schema(ref, exclude_table="public.schema_migrations")

        if target_schema != ref_schema:
            print("REFUSING: schema does not match a fresh full-migration build exactly.",
                  file=sys.stderr)
            print("Resolve this by hand -- apply whatever's actually missing, or "
                  "investigate the divergence -- before re-running this script.",
                  file=sys.stderr)
            import difflib
            diff = difflib.unified_diff(
                ref_schema.splitlines(), target_schema.splitlines(),
                fromfile="reference (fresh, all migrations)", tofile=f"{target} (current)",
                lineterm="",
            )
            print("\n".join(list(diff)[:200]), file=sys.stderr)
            sys.exit(1)

        print("MATCH -- schema is equivalent to a fresh full-migration build. Baselining.")
        target_conn = psycopg2.connect(env("DATABASE_URL"))
        target_conn.autocommit = False
        apply_one(target_conn, ledger_path, version_of(ledger_path))
        for path in migrations:
            if path.name == LEDGER_MIGRATION_NAME:
                continue
            digest = file_sha256(path)
            with target_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO schema_migrations (version, file_sha256, baselined) "
                    "VALUES (%s, %s, true)",
                    (version_of(path), digest),
                )
            target_conn.commit()
        target_conn.close()
        print(f"baselined {len(migrations)} migration(s) into {target}'s schema_migrations")

    finally:
        admin = admin_connect("postgres")
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (ref,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{ref}"')
        admin.close()
        print(f"dropped disposable reference database {ref}")


if __name__ == "__main__":
    main()
