#!/usr/bin/env python3
"""make migrate -- P6's ledger-aware migration runner.

Applies only migrations not yet recorded in schema_migrations (0046), each
as one atomic unit: a migration's SQL and its own schema_migrations row are
executed in the same transaction and committed together, so a failure
partway through a migration leaves neither the schema change nor the ledger
row -- never one without the other. `make schema` is unchanged by this and
keeps its own contract ("clean apply" against an empty database, what CI
uses); this is the separate tool for a database that already has some
migrations applied, which `make schema` was never able to do at all.

Three things this script checks every run, not just once:

  1. Is a migration in the repo but not in the ledger? Apply it.
  2. Is a migration in the ledger with a file_sha256 that no longer matches
     the file on disk? Refuse outright -- migrations are forward-only and
     immutable once merged (CLAUDE.md), so a changed file after recording is
     itself a violation, not a normal thing to reconcile automatically.
  3. Does schema_migrations not exist, but the database is not empty either?
     Refuse outright -- that is a pre-ledger database (exactly what
     ledgex_schema_check was), and there is no way to tell "already applied,
     unrecorded" from "never applied" without a real schema comparison, not
     a guess. See migrate_baseline.py for that one-time adoption path.
"""
import hashlib
import pathlib
import sys

import psycopg2

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from infra.env import env, refuse_remote  # noqa: E402

MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
LEDGER_MIGRATION_NAME = "0046_schema_migrations_ledger.sql"


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def all_migrations():
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def version_of(path):
    return path.name.split("_", 1)[0]


def ledger_exists(cur):
    cur.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
    return cur.fetchone()[0]


def other_tables_exist(cur):
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name <> 'schema_migrations'
        )
    """)
    return cur.fetchone()[0]


def applied_versions(cur):
    cur.execute("SELECT version, file_sha256 FROM schema_migrations")
    return dict(cur.fetchall())


def apply_one(conn, path, version, baselined=False):
    """Runs path's SQL and inserts its own ledger row in ONE transaction,
    committed together. baselined=True is used only by migrate_baseline.py,
    which has already verified the schema matches without literally running
    this SQL here -- so it inserts the ledger row alone, still atomically,
    still in its own transaction, just without cur.execute(sql) first."""
    digest = file_sha256(path)
    with conn.cursor() as cur:
        if not baselined:
            cur.execute(path.read_text(encoding="utf-8"))
        cur.execute(
            "INSERT INTO schema_migrations (version, file_sha256, baselined) VALUES (%s, %s, %s)",
            (version, digest, baselined),
        )
    conn.commit()


def bootstrap_ledger(conn):
    """Truly empty database, no ledger yet: create schema_migrations first,
    out of band from the normal ordered loop below. Safe regardless of
    migration order -- schema_migrations has no FK to anything else."""
    ledger_path = MIGRATIONS_DIR / LEDGER_MIGRATION_NAME
    if not ledger_path.exists():
        raise SystemExit(f"expected {LEDGER_MIGRATION_NAME} in {MIGRATIONS_DIR}, not found")
    print(f"bootstrapping {ledger_path.name} (empty database, no ledger yet)")
    apply_one(conn, ledger_path, version_of(ledger_path))


def main():
    # P56a: this script applies DDL directly via env("DATABASE_URL"),
    # bypassing infra.env.get_db()'s own remote-host refusal entirely --
    # confirmed live (DATABASE_URL=postgresql://nonexistent.invalid/x make
    # migrate reached a raw psycopg2.OperationalError, not this refusal).
    # Called once, before the only connection this script makes.
    refuse_remote(env("DATABASE_URL"))
    conn = psycopg2.connect(env("DATABASE_URL"))
    conn.autocommit = False

    with conn.cursor() as cur:
        has_ledger = ledger_exists(cur)
        if not has_ledger:
            if other_tables_exist(cur):
                print(
                    "REFUSING: schema_migrations does not exist, but this database "
                    "already has other tables. This looks like a pre-ledger database "
                    "(migrations applied by hand before this ledger existed) -- "
                    "adopting it needs a real schema comparison, not a guess in "
                    "either direction. Run scripts/migrate_baseline.py against it "
                    "first, then re-run this.",
                    file=sys.stderr,
                )
                sys.exit(1)

    if not has_ledger:
        bootstrap_ledger(conn)

    with conn.cursor() as cur:
        already = applied_versions(cur)

    pending = []
    for path in all_migrations():
        version = version_of(path)
        digest = file_sha256(path)
        if version in already:
            recorded_digest = already[version]
            if recorded_digest != digest:
                print(
                    f"REFUSING: {path.name} (version {version}) was recorded with "
                    f"file_sha256={recorded_digest}, but its current content hashes "
                    f"to {digest}. Migrations are forward-only -- this file changed "
                    "after being applied, which is itself a violation, not something "
                    "to reconcile automatically. Nothing further will be applied "
                    "until a human resolves this.",
                    file=sys.stderr,
                )
                sys.exit(1)
            continue
        pending.append((path, version))

    if not pending:
        print("up to date -- nothing to apply")
        return

    for path, version in pending:
        print(f"applying {path.name}")
        apply_one(conn, path, version)
    print(f"applied {len(pending)} migration(s)")


if __name__ == "__main__":
    main()
