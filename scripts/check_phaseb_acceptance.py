#!/usr/bin/env python3
"""Assertions for the Phase B A->B->A acceptance run, checked at the two
points the acceptance test actually specifies: immediately after B, and
immediately after the second A. Call with "after-b" or "after-a2".

Exit 0 = every assertion for that checkpoint passed. Exit 1 = at least one
failed (details printed).
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from infra.env import get_db  # noqa: E402

A_SID = os.environ["A_SID"]
B_SID = os.environ["B_SID"]

failures = []


def check(cur_or_conn, label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def check_after_b(conn):
    cur = conn.cursor()

    for pid, expect_value in [("568", "23712199"), ("509", "23717188")]:
        cur.execute("""
            SELECT f.value, f.supersedes_fact_id, f.supersession_reason
            FROM source_feature_identity sfi
            JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'parcel.apn' AND f.superseded_at IS NULL
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
        """, (pid,))
        row = cur.fetchone()
        check(cur, f"after B: source_feature_id {pid}: current parcel.apn = {expect_value!r}",
              row is not None and row[0] == expect_value, f"got {row}")
        check(cur, f"after B: source_feature_id {pid}: has supersedes_fact_id + reason='unknown'",
              row is not None and row[1] is not None and row[2] == "unknown", f"got {row}")

    for pid in ("508", "509"):
        cur.execute("""
            SELECT f.supersedes_fact_id, f.supersession_reason
            FROM source_feature_identity sfi
            JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'parcel.geometry' AND f.superseded_at IS NULL
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
        """, (pid,))
        row = cur.fetchone()
        check(cur, f"after B: source_feature_id {pid}: current parcel.geometry superseded a prior fact",
              row is not None and row[0] is not None and row[1] == "unknown", f"got {row}")

    cur.execute("""
        SELECT count(DISTINCT f.parcel_id) FROM fact f
        WHERE f.supersession_reason = 'unknown' AND f.snapshot_id = %s
          AND f.field_key IN ('parcel.apn', 'parcel.geometry')
    """, (B_SID,))
    changed_parcel_count = cur.fetchone()[0]
    check(cur, "after B: exactly 3 parcels got a changed-field successor fact (matches 1(c)'s real count)",
          changed_parcel_count == 3, f"got {changed_parcel_count}")

    for pid in ("99999001", "99999002"):
        cur.execute("""
            SELECT parcel_id FROM source_feature_identity
            WHERE source_id = 'ca_san_jose.parcels' AND source_feature_id = %s AND retired_at IS NULL
        """, (pid,))
        row = cur.fetchone()
        check(cur, f"after B: source_feature_id {pid}: new parcel created, live identity", row is not None, f"got {row}")

    for pid in ("510", "11908"):
        cur.execute("""
            SELECT f.value FROM source_feature_identity sfi
            JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'permits.active' AND f.superseded_at IS NULL
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
        """, (pid,))
        row = cur.fetchone()
        check(cur, f"after B: source_feature_id {pid}: permits.active is now false (explicit successor)",
              row is not None and row[0] is False, f"got {row}")

        cur.execute("""
            SELECT count(*) FROM source_feature_identity sfi
            JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'zoning.district' AND f.superseded_at IS NULL
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
        """, (pid,))
        live_zoning_count = cur.fetchone()[0]
        check(cur, f"after B: source_feature_id {pid}: zoning.district superseded, NO successor",
              live_zoning_count == 0, f"got {live_zoning_count}")

        cur.execute("""
            SELECT count(*) FROM source_feature_identity sfi
            JOIN parcel_exception pe ON pe.parcel_id = sfi.parcel_id
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
              AND pe.detector_key = 'parcel_disappeared_from_source'
        """, (pid,))
        exc_count = cur.fetchone()[0]
        check(cur, f"after B: source_feature_id {pid}: coverage_gap exception raised",
              exc_count == 1, f"got {exc_count}")

        cur.execute("""
            SELECT retired_at, retired_snapshot_id, retirement_reason FROM source_feature_identity
            WHERE source_id = 'ca_san_jose.parcels' AND source_feature_id = %s
        """, (pid,))
        ident_row = cur.fetchone()
        check(cur, f"after B: source_feature_id {pid}: identity retired (all three retirement fields set)",
              ident_row is not None and all(v is not None for v in ident_row), f"got {ident_row}")


def check_after_a2(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT status, snapshot_id FROM job_run WHERE job_key = 'ingest_parcels_full' ORDER BY started_at
    """)
    runs = cur.fetchall()
    check(cur, "three ingest_parcels_full job_runs exist", len(runs) == 3, f"got {len(runs)}")
    if len(runs) == 3:
        check(cur, "all three job_runs succeeded", all(s == "succeeded" for s, _ in runs),
              f"statuses={[s for s, _ in runs]}")

    cur.execute("""
        SELECT f.id, f.value, f.supersedes_fact_id, f.supersession_reason
        FROM source_feature_identity sfi
        JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'parcel.apn' AND f.superseded_at IS NULL
        WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = '568'
    """)
    current_apn_row = cur.fetchone()
    check(cur, "after A2: source_feature_id 568's current parcel.apn is '23712112' again (A value)",
          current_apn_row is not None and current_apn_row[1] == "23712112", f"got {current_apn_row}")

    cur.execute("""
        SELECT count(*) FROM source_feature_identity sfi
        JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'parcel.apn'
        WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = '568'
    """)
    total_apn_facts_568 = cur.fetchone()[0]
    check(cur, "after A2: source_feature_id 568 has THREE parcel.apn fact rows (A -> B successor -> A2 successor)",
          total_apn_facts_568 == 3, f"got {total_apn_facts_568}")

    if current_apn_row is not None:
        cur.execute("""
            SELECT f.id FROM source_feature_identity sfi
            JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'parcel.apn'
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = '568'
              AND f.supersedes_fact_id IS NULL
        """)
        orig_row = cur.fetchone()
        check(cur, "after A2: the A2-current fact row's id differs from the ORIGINAL A fact's id "
                   "(a real new row, not a resurrection)",
              orig_row is not None and current_apn_row[0] != orig_row[0],
              f"current_id={current_apn_row[0]} original_id={orig_row}")

    for pid in ("510", "11908"):
        cur.execute("""
            SELECT retired_at, last_seen_snapshot_id FROM source_feature_identity
            WHERE source_id = 'ca_san_jose.parcels' AND source_feature_id = %s
        """, (pid,))
        row = cur.fetchone()
        check(cur, f"after A2: source_feature_id {pid}: reappeared, identity un-retired",
              row is not None and row[0] is None, f"got {row}")
        check(cur, f"after A2: source_feature_id {pid}: last_seen_snapshot_id updated to A's snapshot",
              row is not None and row[1] == A_SID, f"got {row}")

        cur.execute("""
            SELECT value FROM source_feature_identity sfi
            JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'permits.active' AND f.superseded_at IS NULL
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
        """, (pid,))
        permits_row = cur.fetchone()
        check(cur, f"after A2: source_feature_id {pid}: permits.active STILL false (not auto-restored by reappearing)",
              permits_row is not None and permits_row[0] is False, f"got {permits_row}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "after-a2"
    conn = get_db()
    if mode == "after-b":
        check_after_b(conn)
    else:
        check_after_a2(conn)
    conn.close()

    print()
    if failures:
        print(f"=== {len(failures)} ASSERTION(S) FAILED ({mode}) ===")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"=== ALL ASSERTIONS PASSED ({mode}) ===")
    sys.exit(0)
