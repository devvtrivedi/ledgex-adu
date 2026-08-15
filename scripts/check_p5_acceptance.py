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
    reasons = open_exceptions(cur, AMBIGUOUS_APN, ZONING_DETECTOR)
    # This parcel was zero-match under snapshot A (uncovered by any A
    # polygon) and got a no_containing_district exception then; B makes it
    # ambiguous instead, a DIFFERENT reason. Confirmed finding, not a bug:
    # nothing auto-resolves the now-stale A-era exception when the
    # underlying condition changes (P5 item 5 -- no outcome value cleanly
    # means "closed because new data superseded it", reported not fixed).
    # Both stay open simultaneously; this assertion documents that
    # deliberately, rather than assuming the stale one vanished.
    check(f"after B: {AMBIGUOUS_APN} has open multiple_containing_districts exception "
          "(NOT the same reason as zero-match), AND still carries its stale A-era "
          "no_containing_district exception -- confirmed unresolved, not a regression",
          {"multiple_containing_districts", "no_containing_district"} <= reasons,
          f"got {reasons}")


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
    # DIFFERENT reason from A2's (no_containing_district) -- both should now
    # be open simultaneously for the same parcel/detector, proving 0045's
    # index is scoped by reason, not just (parcel, detector).
    reasons = open_exceptions(cur, AMBIGUOUS_APN, ZONING_DETECTOR)
    check(f"after A2: {AMBIGUOUS_APN} still carries its B-era multiple_containing_districts "
          "exception, unresolved, alongside the new no_containing_district one",
          {"multiple_containing_districts", "no_containing_district"} <= reasons, f"got {reasons}")


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
