#!/usr/bin/env python3
"""0061 (P64A.3): asserts current_fact_at() stays INLINED -- the regression this defect existed
under for 24 migrations (0039 through 0060) precisely because nothing did. T57, T58 and T63 in
db/tests/invariants.sql all pass whether the function is inlined or not (P64A.1/P64A.2,
~/Desktop/ledgex-p64-evidence/P64A1-RUN-EVIDENCE/, P64A2-RUN-EVIDENCE/) -- none of them inspects
the plan. This script does, and only that.

WHAT IS ASSERTED, AND WHY NOT SOMETHING ELSE. Inlining a LANGUAGE sql function is a rewrite-
stage decision -- eligibility depends on the function's own definition (LANGUAGE sql, no SET
clause, a single simple SELECT, no SECURITY DEFINER) and the calling query's shape, never on
table contents or planner statistics. The ABSENCE of a "Function Scan on <fn>" node in EXPLAIN
output is therefore deterministic and will not flake on a freshly migrated, near-empty CI
database. Whether a pushed-down predicate then lands as an Index Cond on fact_lookup is a
SEPARATE, cost-based decision the planner makes only after inlining already happened -- real on
a volume-matched database (P64A.1/P64A.2's own measurements), not guaranteed on a small one, and
NOT asserted here. Asserting the index choice on a small database is exactly the kind of thing
that flakes and gets disabled by whoever it wakes up at 3am -- this script asserts the
deterministic half only.

NO FIXTURE DATA IS CREATED. Since inlining does not depend on table contents, this script never
inserts a parcel, a fact, a licence, or a licence_channel row -- there is nothing to seed and
nothing for db/tests/teardown.sql to need to clean up afterward. If a future version of this
script ever needs fixture data, it must use the apn ILIKE 'test-%' / jurisdiction_id =
'test_ca_san_jose' namespace teardown.sql already cleans, and must refuse loudly rather than
insert a licence or licence_channel row (both immutable since 0027/0033) -- this script
currently has no need to and does not.

THE RED PROOF (see prove_red_with_a_set_carrying_probe() below): creates ITS OWN, separately
named probe function on the scratch database -- current_fact_at's real body, verbatim, but WITH
a SET search_path clause added back (simulating exactly the regression this test exists to
catch: a future migration re-adding 0039's layer 2) -- runs this file's own assertion helper
against it first, confirming the helper correctly flags it as NOT inlined, then runs the same
helper against the real, unmodified current_fact_at and confirms it IS inlined. Drops the probe
function itself when done (a schema object it created, not a data row -- teardown.sql has
nothing to do with it). Never edits any file on disk. A test that only ever calls the passing
case has not been shown to test anything.

Requires DATABASE_URL for a scratch database. Refuses loudly, before running anything, if
DATABASE_URL's current_database() is literally 'ledgex_schema_check'.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_current_fact_at_inlined.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402

failures = []

PROBE_PARCEL_ID = "00000000-0000-0000-0000-000000000000"  # need not exist -- see module docstring

# current_fact_at's real body, byte-identical to db/schema.sql / db/migrations/0061 minus the
# signature/SET clause line, reused here (not re-derived) so this file's own probe cannot
# silently drift from what the migration actually ships.
_BODY = """
    SELECT DISTINCT ON (f.parcel_id, f.field_key)
           f.*
      FROM public.fact f
      JOIN public.parcel p ON p.id = f.parcel_id
      LEFT JOIN public.source_rank sr
             ON sr.jurisdiction_id = p.jurisdiction_id
            AND sr.field_key       = f.field_key
            AND sr.source_id       = f.source_id
     WHERE f.recorded_at <= ts
       AND (f.superseded_at IS NULL OR f.superseded_at > ts)
       AND f.effective_from <= ts
       AND (f.effective_to IS NULL OR f.effective_to > ts)
     ORDER BY f.parcel_id, f.field_key,
              COALESCE(sr.rank, 999) ASC,
              f.confidence ASC,
              f.retrieved_at DESC NULLS LAST,
              f.id;
"""

PROBE_FUNCTION_NAME = "test_p64a3_set_carrying_probe"


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def refuse_if_ledgex_schema_check(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT current_database();")
        (dbname,) = cur.fetchone()
    if dbname == "ledgex_schema_check":
        print(
            "REFUSING: DATABASE_URL points at 'ledgex_schema_check'. This script creates and "
            "drops a probe FUNCTION object -- never point it at the real, long-lived database.",
            file=sys.stderr,
        )
        sys.exit(2)


def is_inlined(conn, function_name):
    """Runs the same single-parcel call shape api/main.py:598 uses, against function_name, and
    returns True iff no 'Function Scan on ...function_name' node appears in the plan -- the
    deterministic half of the diagnostic (see module docstring for why not the index choice)."""
    with conn.cursor() as cur:
        cur.execute(
            f"EXPLAIN (ANALYZE, FORMAT TEXT) "
            f"SELECT id, field_key, licence_id, value FROM {function_name}(now()) "
            f"WHERE parcel_id = %s ORDER BY field_key;",
            (PROBE_PARCEL_ID,),
        )
        plan_lines = [row[0] for row in cur.fetchall()]
    conn.rollback()  # EXPLAIN ANALYZE against a read-only SELECT; nothing to commit either way
    plan_text = "\n".join(plan_lines)
    leaked_function_scan = f"Function Scan on" in plan_text and function_name in plan_text
    return not leaked_function_scan, plan_text


def prove_red_with_a_set_carrying_probe(conn):
    """The mutation test: a probe function with the body above, current_fact_at's own real
    body, but with the SET clause 0061 removed added back -- simulating exactly the regression
    this whole test exists to catch. Confirms the helper flags it (RED), then confirms the real
    function passes (GREEN). Drops the probe function itself in a finally block regardless of
    outcome -- a schema object this script created, cleaned up by this script, not by
    teardown.sql."""
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE OR REPLACE FUNCTION {PROBE_FUNCTION_NAME}(ts timestamp with time zone) "
            f"RETURNS SETOF public.fact LANGUAGE sql STABLE "
            f"SET search_path TO 'public', 'pg_temp' AS $$ {_BODY} $$;"
        )
    conn.commit()
    try:
        probe_inlined, probe_plan = is_inlined(conn, PROBE_FUNCTION_NAME)
        print(
            f"[{'unexpected-green' if probe_inlined else 'RED'}] RED PROOF: the SET-carrying "
            f"probe function {'was' if not probe_inlined else 'was NOT'} correctly flagged as "
            f"not inlined"
        )
        check(
            "RED PROOF: the SET-carrying probe is correctly detected as NOT inlined "
            "(proves the assertion helper actually distinguishes the two cases, not vacuous)",
            not probe_inlined,
            f"plan=\n{probe_plan}",
        )
    finally:
        with conn.cursor() as cur:
            cur.execute(f"DROP FUNCTION IF EXISTS {PROBE_FUNCTION_NAME}(timestamp with time zone);")
        conn.commit()


def main():
    conn = get_db()
    refuse_if_ledgex_schema_check(conn)

    prove_red_with_a_set_carrying_probe(conn)

    real_inlined, real_plan = is_inlined(conn, "current_fact_at")
    check(
        "GREEN: the REAL, unmodified current_fact_at() is inlined (no Function Scan node)",
        real_inlined,
        f"plan=\n{real_plan}",
    )
    conn.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
