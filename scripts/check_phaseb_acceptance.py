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


APN_DETECTOR = "parcel_apn_unresolvable"


def live_apn_fact(cur, source_feature_id):
    cur.execute("""
        SELECT f.id, f.value, f.supersedes_fact_id, f.supersession_reason
        FROM source_feature_identity sfi
        JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'parcel.apn' AND f.superseded_at IS NULL
        WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
    """, (source_feature_id,))
    return cur.fetchone()


def apn_cache_column(cur, source_feature_id):
    cur.execute("""
        SELECT p.apn FROM source_feature_identity sfi
        JOIN parcel p ON p.id = sfi.parcel_id
        WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
    """, (source_feature_id,))
    row = cur.fetchone()
    return row[0] if row else "<no parcel row>"


def apn_exception_history(cur, source_feature_id):
    """Every parcel_apn_unresolvable exception (any outcome) for this
    source_feature_id, oldest first -- id, outcome, resolved_by,
    reopened_from_id, detail."""
    cur.execute("""
        SELECT pe.id, pe.outcome, pe.resolved_by, pe.reopened_from_id, pe.detail
        FROM source_feature_identity sfi
        JOIN parcel_exception pe ON pe.parcel_id = sfi.parcel_id
        WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
          AND pe.detector_key = %s
        ORDER BY pe.detected_at
    """, (source_feature_id, APN_DETECTOR))
    return cur.fetchall()


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

    # P13: was "exactly 3" (568, 509, 508) before the fixture extension.
    # Now 4, not 5 or 6 -- 99999003/99999004 (APN degrades) must NOT appear
    # here: a degrade supersedes with NO successor (db/README.md's rule),
    # so it contributes zero rows to this count, not one each. 99999005
    # (never-resolvable, geometry-only change) DOES newly appear -- its
    # geometry change was invisible before the INNER->LEFT JOIN fix (#17's
    # other half) and now correctly gets a successor. 99999006 (resolves
    # for the first time) also does NOT appear: its parcel.apn write is a
    # NEW fact (no supersedes_fact_id), not a supersession, so
    # supersession_reason IS NULL for it and this count -- which only
    # counts superseded successors -- correctly excludes it.
    cur.execute("""
        SELECT count(DISTINCT f.parcel_id) FROM fact f
        WHERE f.supersession_reason = 'unknown' AND f.snapshot_id = %s
          AND f.field_key IN ('parcel.apn', 'parcel.geometry')
    """, (B_SID,))
    changed_parcel_count = cur.fetchone()[0]
    check(cur, "after B: exactly 4 parcels got a changed-field successor fact "
               "(568, 509, 508 apn/geom + 99999005's newly-visible geometry change)",
          changed_parcel_count == 4, f"got {changed_parcel_count}")

    # --- P13: resolvable -> unresolvable degrade (findings #17/#22) ---
    for pid, reason, raw_apn in [("99999003", "placeholder", "99999003???"), ("99999004", "blank", None)]:
        d = live_apn_fact(cur, pid)
        check(cur, f"after B: source_feature_id {pid}: NO live parcel.apn fact "
                   f"(degrade supersedes with no successor, not a placeholder/null value)",
              d is None, f"got {d}")
        check(cur, f"after B: source_feature_id {pid}: parcel.apn cache column is NULL "
                   f"(0034: no fact means no cache value)",
              apn_cache_column(cur, pid) is None, f"got {apn_cache_column(cur, pid)!r}")
        history = apn_exception_history(cur, pid)
        check(cur, f"after B: source_feature_id {pid}: exactly one open parcel_apn_unresolvable "
                   f"exception, reason={reason!r}, raw_apn={raw_apn!r}",
              len(history) == 1 and history[0][1] == "open"
              and history[0][4].get("reason") == reason and history[0][4].get("raw_apn") == raw_apn,
              f"got {history}")

    # --- P13: never-resolvable, geometry-only change (#17's INNER->LEFT JOIN half) ---
    d = live_apn_fact(cur, "99999005")
    check(cur, "after B: source_feature_id 99999005: still no parcel.apn fact "
               "(never resolvable, unchanged -- APN side must stay untouched)",
          d is None, f"got {d}")
    history = apn_exception_history(cur, "99999005")
    check(cur, "after B: source_feature_id 99999005: still exactly ONE open exception "
               "(the original A-era one -- unchanged condition must not raise a duplicate)",
          len(history) == 1 and history[0][1] == "open", f"got {history}")
    cur.execute("""
        SELECT f.supersedes_fact_id, f.supersession_reason
        FROM source_feature_identity sfi
        JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'parcel.geometry' AND f.superseded_at IS NULL
        WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = '99999005'
    """)
    geom_row = cur.fetchone()
    check(cur, "after B: source_feature_id 99999005: parcel.geometry DID get superseded "
               "(the INNER JOIN would have silently dropped this before the fix -- #17's other half)",
          geom_row is not None and geom_row[0] is not None and geom_row[1] == "unknown", f"got {geom_row}")

    # --- P13: unresolvable -> resolvable for the FIRST time (the #17 direction itself) ---
    d = live_apn_fact(cur, "99999006")
    check(cur, "after B: source_feature_id 99999006: NEW parcel.apn fact = '99999006APN', "
               "NOT a supersession (nothing was live to supersede)",
          d is not None and d[1] == "99999006APN" and d[2] is None, f"got {d}")
    check(cur, "after B: source_feature_id 99999006: parcel.apn cache column = '99999006APN'",
          apn_cache_column(cur, "99999006") == "99999006APN", f"got {apn_cache_column(cur, '99999006')!r}")
    history = apn_exception_history(cur, "99999006")
    check(cur, "after B: source_feature_id 99999006: its A-era open exception is now "
               "condition_cleared, resolved_by the detector itself",
          len(history) == 1 and history[0][1] == "condition_cleared" and history[0][2] == APN_DETECTOR,
          f"got {history}")

    for pid in ("99999001", "99999002"):
        cur.execute("""
            SELECT parcel_id FROM source_feature_identity
            WHERE source_id = 'ca_san_jose.parcels' AND source_feature_id = %s AND retired_at IS NULL
        """, (pid,))
        row = cur.fetchone()
        check(cur, f"after B: source_feature_id {pid}: new parcel created, live identity", row is not None, f"got {row}")

    # P4: a parcel disappearing from PARCELS is not evidence about permits
    # or zoning. Neither fact should be touched AT ALL -- no supersession,
    # no successor, still exactly the fact that was there before B ran,
    # still carrying its OWN source's provenance (never ca_san_jose.parcels').
    # The only real observation here is that the parcels source no longer
    # confirms the parcel's identity -- one record_to_ground exception,
    # plus the identity retirement already asserted elsewhere.
    for pid in ("510", "11908"):
        cur.execute("""
            SELECT f.value, f.superseded_at, f.source_id FROM source_feature_identity sfi
            JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'permits.active'
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
        """, (pid,))
        permits_rows = cur.fetchall()
        check(cur, f"after B: source_feature_id {pid}: permits.active untouched -- exactly one fact row, "
                   f"still true, never superseded, still permits' own provenance",
              permits_rows == [(True, None, "ca_san_jose.building_permits_active")], f"got {permits_rows}")

        cur.execute("""
            SELECT f.value, f.superseded_at, f.source_id FROM source_feature_identity sfi
            JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'zoning.district'
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
        """, (pid,))
        zoning_rows = cur.fetchall()
        check(cur, f"after B: source_feature_id {pid}: zoning.district untouched -- exactly one fact row, "
                   f"never superseded, still zoning's own provenance",
              len(zoning_rows) == 1 and zoning_rows[0][1] is None
              and zoning_rows[0][2] == "ca_san_jose.zoning_districts",
              f"got {zoning_rows}")

        cur.execute("""
            SELECT pe.type, pe.severity, pe.detail FROM source_feature_identity sfi
            JOIN parcel_exception pe ON pe.parcel_id = sfi.parcel_id
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
              AND pe.detector_key = 'parcel_disappeared_from_source'
        """, (pid,))
        exc_rows = cur.fetchall()
        check(cur, f"after B: source_feature_id {pid}: exactly one record_to_ground/warning exception raised",
              len(exc_rows) == 1 and exc_rows[0][0] == "record_to_ground" and exc_rows[0][1] == "warning",
              f"got {exc_rows}")
        if len(exc_rows) == 1:
            live_facts = exc_rows[0][2].get("live_facts_from_other_sources", [])
            live_field_keys = {f["field_key"] for f in live_facts}
            check(cur, f"after B: source_feature_id {pid}: exception detail lists the live permits.active "
                       f"and zoning.district facts riding on this now-unconfirmed identity",
                  {"permits.active", "zoning.district"} <= live_field_keys, f"got {live_facts}")

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

        # P4: permits.active/zoning.district were never touched by B's
        # disappearance handling (see check_after_b) and reappearing in A2
        # doesn't touch them either -- reappearance is a parcels-identity
        # event, not a permits or zoning re-observation. Still exactly one
        # fact row each, from their OWN source, still their original value,
        # never superseded, through the entire A -> B -> A2 sequence.
        cur.execute("""
            SELECT f.value, f.superseded_at, f.source_id FROM source_feature_identity sfi
            JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'permits.active'
            WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = %s
        """, (pid,))
        permits_rows = cur.fetchall()
        check(cur, f"after A2: source_feature_id {pid}: permits.active STILL untouched -- one fact row, "
                   f"true, never superseded, still permits' own provenance",
              permits_rows == [(True, None, "ca_san_jose.building_permits_active")], f"got {permits_rows}")

    # --- P13: degrade-then-resolve, A2 restores the ORIGINAL A value (#17/#22) ---
    for pid, orig_value in [("99999003", "99999003APN"), ("99999004", "99999004APN")]:
        d = live_apn_fact(cur, pid)
        check(cur, f"after A2: source_feature_id {pid}: NEW parcel.apn fact = {orig_value!r}, "
                   f"NOT a supersession (nothing was live to supersede -- the degrade in B left none)",
              d is not None and d[1] == orig_value and d[2] is None, f"got {d}")
        check(cur, f"after A2: source_feature_id {pid}: parcel.apn cache column = {orig_value!r}",
              apn_cache_column(cur, pid) == orig_value, f"got {apn_cache_column(cur, pid)!r}")
        history = apn_exception_history(cur, pid)
        check(cur, f"after A2: source_feature_id {pid}: its B-era open exception is now "
                   f"condition_cleared, resolved_by the detector itself",
              len(history) == 1 and history[0][1] == "condition_cleared" and history[0][2] == APN_DETECTOR,
              f"got {history}")

    # --- P13: never-resolvable, geometry reverts to A's (still no APN activity) ---
    d = live_apn_fact(cur, "99999005")
    check(cur, "after A2: source_feature_id 99999005: still no parcel.apn fact",
          d is None, f"got {d}")
    history = apn_exception_history(cur, "99999005")
    check(cur, "after A2: source_feature_id 99999005: still exactly ONE open exception, "
               "the same original one -- never touched by either reconcile",
          len(history) == 1 and history[0][1] == "open", f"got {history}")
    cur.execute("""
        SELECT f.value, f.supersedes_fact_id, f.supersession_reason
        FROM source_feature_identity sfi
        JOIN fact f ON f.parcel_id = sfi.parcel_id AND f.field_key = 'parcel.geometry' AND f.superseded_at IS NULL
        WHERE sfi.source_id = 'ca_san_jose.parcels' AND sfi.source_feature_id = '99999005'
    """)
    geom_row = cur.fetchone()
    check(cur, "after A2: source_feature_id 99999005: parcel.geometry superseded AGAIN, back "
               "toward A's geometry (a real, second change, not a no-op)",
          geom_row is not None and geom_row[1] is not None and geom_row[2] == "unknown", f"got {geom_row}")

    # --- P13: resolves in B, degrades AGAIN in A2 -- the reopened_from_id test ---
    # A2 replays the exact same bytes as A, where this feature was blank --
    # so it degrades a second time. Its exception must link back to the
    # ORIGINAL A-era exception (same reason, 'blank'), proving
    # relink_reopened_exceptions matches on (parcel_id, reason) across a
    # real close-then-reopen cycle, not just "the last row for this parcel".
    d = live_apn_fact(cur, "99999006")
    check(cur, "after A2: source_feature_id 99999006: NO live parcel.apn fact "
               "(degraded again -- supersedes B's resolved fact, no successor)",
          d is None, f"got {d}")
    check(cur, "after A2: source_feature_id 99999006: parcel.apn cache column is NULL again",
          apn_cache_column(cur, "99999006") is None, f"got {apn_cache_column(cur, '99999006')!r}")
    history = apn_exception_history(cur, "99999006")
    check(cur, "after A2: source_feature_id 99999006: exactly two exceptions now -- the original "
               "A-era one (condition_cleared) and a fresh open one",
          len(history) == 2 and history[0][1] == "condition_cleared" and history[1][1] == "open",
          f"got {history}")
    if len(history) == 2:
        original_id = history[0][0]
        reopened_id, reopened_link = history[1][0], history[1][3]
        check(cur, "after A2: source_feature_id 99999006: the fresh open exception's "
                   "reopened_from_id links back to the ORIGINAL A-era exception "
                   "(not NULL, not itself)",
              reopened_link == original_id and reopened_id != original_id,
              f"reopened_from_id={reopened_link} original_id={original_id}")


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
