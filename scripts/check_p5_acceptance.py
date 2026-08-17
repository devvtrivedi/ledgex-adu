#!/usr/bin/env python3
"""Assertions for the P5 A->B->A acceptance run (zoning and permits,
separately), checked at the two points that matter: immediately after B,
and immediately after the second A. Call with "after-b" or "after-a2".

Written against what SHOULD be true, per the P5 investigation's own
transition table -- run against pre-P5 code first and shown red (see the
P5 session record), then made to pass by the reconciliation this file
was written to check, not the other way around.

Exit 0 = every assertion for that checkpoint passed. Exit 1 = at least
one failed (details printed).
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from infra.env import get_db  # noqa: E402

CHECKPOINT = sys.argv[1] if len(sys.argv) > 1 else None
if CHECKPOINT not in ("after-b", "after-a2"):
    raise SystemExit("usage: check_p5_acceptance.py <after-b|after-a2>")

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def live_fact(cur, apn, field_key):
    cur.execute("""
        SELECT f.id, f.value, f.supersedes_fact_id, f.supersession_reason
        FROM fact f JOIN parcel p ON p.id = f.parcel_id
        WHERE p.apn = %s AND f.field_key = %s AND f.superseded_at IS NULL
    """, (apn, field_key))
    return cur.fetchone()


def open_exceptions(cur, apn, detector_key):
    cur.execute("""
        SELECT pe.detail->>'reason' FROM parcel_exception pe JOIN parcel p ON p.id = pe.parcel_id
        WHERE p.apn = %s AND pe.detector_key = %s AND pe.outcome = 'open'
    """, (apn, detector_key))
    return {r[0] for r in cur.fetchall()}


def exception_history(cur, apn, detector_key):
    """Every parcel_exception row (any outcome) for (apn, detector_key), oldest
    first -- id, reason, outcome, resolved_by, reopened_from_id, detected_at.
    Used where open_exceptions()'s "just the open reasons" isn't enough: whether
    a since-closed row was closed for the right reason, and what a reopened
    row's reopened_from_id actually points at."""
    cur.execute("""
        SELECT pe.id, pe.detail->>'reason', pe.outcome, pe.resolved_by,
               pe.reopened_from_id, pe.detected_at
        FROM parcel_exception pe JOIN parcel p ON p.id = pe.parcel_id
        WHERE p.apn = %s AND pe.detector_key = %s
        ORDER BY pe.detected_at
    """, (apn, detector_key))
    return cur.fetchall()


def total_fact_rows(cur, apn, field_key):
    # Total row count (live + superseded), not just the live row -- a
    # same-snapshot re-run that supersedes a fact and writes an identical
    # successor leaves the live VALUE and the non-null supersedes_fact_id
    # both unchanged, which is all live_fact()'s callers ever check. A row
    # count catches the extra row without needing state carried across the
    # two separate CLI invocations that bracket the re-run (see call site).
    cur.execute("""
        SELECT COUNT(*) FROM fact f JOIN parcel p ON p.id = f.parcel_id
        WHERE p.apn = %s AND f.field_key = %s
    """, (apn, field_key))
    return cur.fetchone()[0]


CLUSTER1 = ["23712112", "23717101", "23717102", "23717099", "23711059", "23711066", "23711071"]
CLUSTER3_MINUS_AMBIGUOUS = ["23707063", "23707066", "23707075", "23707039", "23707019", "23707020"]
AMBIGUOUS_APN = "23707070"
CLUSTER2 = ["58705049", "58705050", "58705051", "58705052", "58705053", "58705054", "58705055",
            "58624001", "58624002", "58624003", "58624004"]

ZONING_DETECTOR = "zoning_spatial_join_unresolvable"


def check_zoning_after_b(cur):
    for apn in CLUSTER1:
        d = live_fact(cur, apn, "zoning.district")
        check(f"after B: {apn} zoning.district retired, no successor", d is None, f"got {d}")
        reasons = open_exceptions(cur, apn, ZONING_DETECTOR)
        check(f"after B: {apn} has open no_containing_district exception",
              "no_containing_district" in reasons, f"got {reasons}")

    for apn in CLUSTER2:
        d = live_fact(cur, apn, "zoning.district")
        check(f"after B: {apn} zoning.district = 'R-3', superseded, reason=unknown",
              d is not None and d[1] == "R-3" and d[2] is not None and d[3] == "unknown", f"got {d}")

    for apn in CLUSTER3_MINUS_AMBIGUOUS:
        d = live_fact(cur, apn, "zoning.district")
        check(f"after B: {apn} zoning.district = 'R-M', NEW fact (no supersession)",
              d is not None and d[1] == "R-M" and d[2] is None, f"got {d}")

    d = live_fact(cur, AMBIGUOUS_APN, "zoning.district")
    check(f"after B: {AMBIGUOUS_APN} zoning.district absent (ambiguous)", d is None, f"got {d}")
    # This parcel was zero-match under snapshot A (uncovered by any A polygon)
    # and got a no_containing_district exception then; B makes it ambiguous
    # instead, a DIFFERENT reason. P5 (this file, originally) asserted BOTH
    # reasons stayed open simultaneously -- true then: nothing closed a stale
    # exception when the underlying condition changed. P9
    # (db/migrations/0047, core/exceptions.close_resolved_exceptions,
    # 7c88d15) closed exactly that gap, on purpose, and load_zoning wires it
    # in. Updated here to match, not to make something pass: confirmed
    # against a live A1->B trace before this edit, not assumed from reading
    # the code -- see prompts/P12-p5-suite-blind-to-p9-and-ci-gap.md 1(a).
    # The A-era no_containing_district exception is no longer true this run
    # (this run's own classification is a DIFFERENT reason) so
    # close_resolved_exceptions closes it, condition_cleared, resolved_by
    # the detector itself; multiple_containing_districts is THIS run's own
    # finding and stays open.
    history = exception_history(cur, AMBIGUOUS_APN, ZONING_DETECTOR)
    by_reason = {row[1]: row for row in history}  # last occurrence per reason
    multiple = by_reason.get("multiple_containing_districts")
    no_containing = by_reason.get("no_containing_district")
    check(f"after B: {AMBIGUOUS_APN} has open multiple_containing_districts exception "
          "(this run's own finding, NOT the same reason as the A-era zero-match)",
          multiple is not None and multiple[2] == "open", f"got {multiple}")
    check(f"after B: {AMBIGUOUS_APN}'s A-era no_containing_district exception is closed "
          "(condition_cleared, resolved_by the detector itself) -- P9 closes a stale "
          "exception when the condition genuinely changed, it does not leave it open",
          no_containing is not None and no_containing[2] == "condition_cleared"
          and no_containing[3] == ZONING_DETECTOR,
          f"got {no_containing}")


def check_zoning_after_a2(cur):
    for apn in CLUSTER1:
        d = live_fact(cur, apn, "zoning.district")
        check(f"after A2: {apn} zoning.district = 'R-1', NEW fact (zero-match -> matched, not a supersession)",
              d is not None and d[1] == "R-1" and d[2] is None, f"got {d}")

    for apn in CLUSTER2:
        d = live_fact(cur, apn, "zoning.district")
        check(f"after A2: {apn} zoning.district = 'R-2' again, superseded",
              d is not None and d[1] == "R-2" and d[2] is not None, f"got {d}")

    for apn in CLUSTER3_MINUS_AMBIGUOUS + [AMBIGUOUS_APN]:
        d = live_fact(cur, apn, "zoning.district")
        check(f"after A2: {apn} zoning.district retired again, no successor", d is None, f"got {d}")
        reasons = open_exceptions(cur, apn, ZONING_DETECTOR)
        check(f"after A2: {apn} has open no_containing_district exception",
              "no_containing_district" in reasons, f"got {reasons}")

    # The ambiguous APN's B-era exception (multiple_containing_districts) is a
    # DIFFERENT reason from A2's (no_containing_district). P9's
    # close_resolved_exceptions closes multiple_containing_districts here --
    # it is no longer true this run -- and the loop above already confirmed
    # a fresh no_containing_district exception is open. What's left to check,
    # confirmed against a live A1->B->A2 trace before this edit (see
    # prompts/P12-p5-suite-blind-to-p9-and-ci-gap.md 1(a)): the fresh
    # no_containing_district row's reopened_from_id links back to the
    # ORIGINAL A1 exception with that same reason -- proving
    # relink_reopened_exceptions matches on (parcel_id, reason), not just
    # "whatever closed most recently for this parcel" (which would have
    # wrongly linked to the B-era multiple_containing_districts row instead).
    history = exception_history(cur, AMBIGUOUS_APN, ZONING_DETECTOR)
    by_reason = {row[1]: row for row in history}  # last occurrence per reason
    multiple = by_reason.get("multiple_containing_districts")
    no_containing_latest = by_reason.get("no_containing_district")
    original_no_containing = next(row for row in history if row[1] == "no_containing_district")
    check(f"after A2: {AMBIGUOUS_APN}'s B-era multiple_containing_districts exception is "
          "now closed (condition_cleared) -- no longer true this run",
          multiple is not None and multiple[2] == "condition_cleared"
          and multiple[3] == ZONING_DETECTOR,
          f"got {multiple}")
    check(f"after A2: {AMBIGUOUS_APN}'s fresh open no_containing_district exception's "
          "reopened_from_id links back to the ORIGINAL A1 exception with that reason "
          "(not the B-era row, not NULL)",
          no_containing_latest is not None and no_containing_latest[2] == "open"
          and no_containing_latest[4] == original_no_containing[0]
          and no_containing_latest[0] != original_no_containing[0],
          f"got {no_containing_latest}, original A1 row={original_no_containing}")


def check_permits_after_b(cur):
    d_active = live_fact(cur, "23717099", "permits.active")
    check("after B: 23717099 permits.active = false (last permit disappeared), superseded, world_change",
          d_active is not None and d_active[1] is False and d_active[2] is not None and d_active[3] == "world_change",
          f"got {d_active}")
    d_earliest = live_fact(cur, "23717099", "permits.series_earliest")
    check("after B: 23717099 permits.series_earliest retired, no successor",
          d_earliest is None, f"got {d_earliest}")

    d_active = live_fact(cur, "58705049", "permits.active")
    check("after B: 58705049 permits.active unchanged (still true, no-op)",
          d_active is not None and d_active[1] is True and d_active[2] is None, f"got {d_active}")
    d_earliest = live_fact(cur, "58705049", "permits.series_earliest")
    check("after B: 58705049 permits.series_earliest moved earlier to 2025-12-01, superseded",
          d_earliest is not None and d_earliest[1] == "2025-12-01" and d_earliest[2] is not None,
          f"got {d_earliest}")

    d_active = live_fact(cur, "23712112", "permits.active")
    check("after B: 23712112 permits.active = true, NEW fact (no supersession)",
          d_active is not None and d_active[1] is True and d_active[2] is None, f"got {d_active}")
    d_earliest = live_fact(cur, "23712112", "permits.series_earliest")
    check("after B: 23712112 permits.series_earliest = 2026-02-01, NEW fact",
          d_earliest is not None and d_earliest[1] == "2026-02-01" and d_earliest[2] is None,
          f"got {d_earliest}")


def check_permits_after_a2(cur):
    d_active = live_fact(cur, "23717099", "permits.active")
    check("after A2: 23717099 permits.active = true again (false -> true, superseded, world_change)",
          d_active is not None and d_active[1] is True and d_active[2] is not None and d_active[3] == "world_change",
          f"got {d_active}")
    d_earliest = live_fact(cur, "23717099", "permits.series_earliest")
    check("after A2: 23717099 permits.series_earliest = 2026-01-01, NEW fact (was absent after B)",
          d_earliest is not None and d_earliest[1] == "2026-01-01" and d_earliest[2] is None,
          f"got {d_earliest}")

    d_earliest = live_fact(cur, "58705049", "permits.series_earliest")
    check("after A2: 58705049 permits.series_earliest back to 2026-01-02, superseded",
          d_earliest is not None and d_earliest[1] == "2026-01-02" and d_earliest[2] is not None,
          f"got {d_earliest}")

    d_active = live_fact(cur, "23712112", "permits.active")
    check("after A2: 23712112 permits.active = false again (true -> false, superseded, world_change)",
          d_active is not None and d_active[1] is False and d_active[2] is not None and d_active[3] == "world_change",
          f"got {d_active}")
    d_earliest = live_fact(cur, "23712112", "permits.series_earliest")
    check("after A2: 23712112 permits.series_earliest retired again, no successor",
          d_earliest is None, f"got {d_earliest}")

    # This checkpoint runs twice in run_p5_acceptance.sh: once right after
    # A2's reconcile, once more after the deliberate same-snapshot re-run at
    # the end of the script (identical fixture, no new data). By then
    # 23712112 permits.active has exactly two total fact rows in its
    # history -- B's NEW true (23712112 has no row in p5_permits_A.csv, so
    # A1 wrote nothing) and A2's superseded false successor. A same-snapshot
    # re-run must not add a third: a live permits.active=false compared
    # against "still absent this run" is not a world change, it is the same
    # silence the false already recorded. The three PASS checks above
    # (value/supersession/reason) stay true whether the re-run added a
    # fabricated third row or not -- they were true after A2 and stay true
    # after the churn, because the churned row has the same shape as the
    # real A2 transition. Only a count (or an unchanged live id) sees it;
    # id-unchanged would need state persisted across the two separate CLI
    # invocations bracketing the re-run (nothing here provides that
    # channel), so a self-contained count against the fixture-determined
    # expected total is the one that doesn't need new plumbing to exist.
    n = total_fact_rows(cur, "23712112", "permits.active")
    check("after A2: 23712112 permits.active has exactly 2 total fact rows "
          "(B's true + A2's false; a same-snapshot re-run must not add a third)",
          n == 2, f"got {n}")


def main():
    conn = get_db()
    cur = conn.cursor()
    if CHECKPOINT == "after-b":
        check_zoning_after_b(cur)
        check_permits_after_b(cur)
    else:
        check_zoning_after_a2(cur)
        check_permits_after_a2(cur)
    conn.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
