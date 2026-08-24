#!/usr/bin/env python3
"""P56 Phase 2 (B3, design doc sec 3): resolve and validate the dedicated
database variable for one of the two non-rerunnable acceptance suites
(run_p5_acceptance.sh / run_phaseb_acceptance.sh), print the validated URL
to stdout, and refuse loudly on stderr before anything connects.

Why a shared script parameterized by variable name, not two copies: the two
suites need the identical shape (no default, no fallback to DATABASE_URL,
refuse non-local/missing/unmigrated) under two DIFFERENT variable names
(P5_DATABASE_URL / PHASEB_DATABASE_URL) -- one implementation, called twice,
same reasoning infra.env.refuse_remote() was extracted for (P56a).

Why NO default, unlike GOLDEN_DATABASE_URL: make golden is read-mostly and
safe to re-run against the same database forever. These two suites are each
a real A->B->A state transition (P23, README finding #30) -- NOT SAFE TO
RERUN against an already-populated database, confirmed by both runners' own
headers. A fixed default would be correct on the first run against it and
silently wrong on every run after. Refusing when unset forces the caller to
name a database explicitly, every time.

Usage (from the runner, under set -euo pipefail so a nonzero exit here halts
the whole script via the failing command substitution):
    DATABASE_URL="$("$PYTHON" scripts/_acceptance_db_preflight.py P5_DATABASE_URL)"
    export DATABASE_URL
"""
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from infra.env import refuse_remote  # noqa: E402

SETUP_HELP = {
    "P5_DATABASE_URL": (
        "This suite is not safe to re-run against a populated database (P23, README\n"
        "finding #30) and it writes permanent rows (0021/0017). It has no default, on\n"
        "purpose: a default would be correct once and silently wrong every run after.\n"
        "Create a fresh database and name it explicitly:\n\n"
        "    createdb ledgex_p5_$(date +%Y%m%d_%H%M%S)\n"
        "    make schema DATABASE_URL=postgresql://localhost/<that database>\n"
        "    P5_DATABASE_URL=postgresql://localhost/<that database> "
        "bash scripts/run_p5_acceptance.sh"
    ),
    "PHASEB_DATABASE_URL": (
        "This suite is not safe to re-run against a populated database (P23, README\n"
        "finding #30) and it writes permanent rows (0021/0017). It has no default, on\n"
        "purpose: a default would be correct once and silently wrong every run after.\n"
        "Create a fresh database and name it explicitly:\n\n"
        "    createdb ledgex_phaseb_$(date +%Y%m%d_%H%M%S)\n"
        "    make schema DATABASE_URL=postgresql://localhost/<that database>\n"
        "    PHASEB_DATABASE_URL=postgresql://localhost/<that database> "
        "bash scripts/run_phaseb_acceptance.sh"
    ),
}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SETUP_HELP:
        raise SystemExit(
            f"usage: {sys.argv[0]} <P5_DATABASE_URL|PHASEB_DATABASE_URL>"
        )
    var_name = sys.argv[1]
    suite_name = "P5" if var_name == "P5_DATABASE_URL" else "Phase B"

    database_url = os.environ.get(var_name)
    if not database_url:
        raise SystemExit(
            f"refusing to run the {suite_name} acceptance suite: {var_name} is not "
            f"set.\n\n{SETUP_HELP[var_name]}\n\nIt reads {var_name}, never "
            f"DATABASE_URL -- P56 Phase 2, the same shape GOLDEN_DATABASE_URL and "
            f"SMOKE_DATABASE_URL already use."
        )

    # Reused, not reimplemented -- P56a extracted this specifically so there
    # would be one host-locality check, not a second one written here that
    # could drift from infra.env.get_db()'s own.
    refuse_remote(database_url)

    import psycopg2

    try:
        conn = psycopg2.connect(database_url)
    except Exception as e:
        raise SystemExit(
            f"cannot connect to the {suite_name} acceptance database "
            f"({type(e).__name__}: {str(e).strip()}).\n\n{SETUP_HELP[var_name]}"
        )
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT count(*) FROM schema_migrations")
                n_ledger = cur.fetchone()[0]
            except Exception:
                conn.rollback()
                raise SystemExit(
                    f"schema_migrations does not exist -- this database has never "
                    f"been migrated.\n\n{SETUP_HELP[var_name]}"
                )
            mig_dir = REPO_ROOT / "db" / "migrations"
            n_files = len([f for f in os.listdir(mig_dir) if f.endswith(".sql")])
            if n_ledger < n_files:
                conn.rollback()
                raise SystemExit(
                    f"schema_migrations has {n_ledger} row(s) but db/migrations/ has "
                    f"{n_files} .sql file(s) -- this database is behind. Run:\n"
                    f"    make migrate DATABASE_URL={database_url}"
                )
    finally:
        conn.close()

    # The ONLY thing on stdout -- the runner captures it directly into
    # DATABASE_URL via command substitution. Every diagnostic above goes to
    # stderr via SystemExit, never stdout, so a successful run's own stdout
    # is exactly the URL and nothing else.
    print(database_url)


if __name__ == "__main__":
    main()
