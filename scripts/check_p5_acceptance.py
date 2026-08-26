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
if CHECKPOINT not in ("after-b", "after-a2", "after-source-scope"):
    raise SystemExit("usage: check_p5_acceptance.py <after-b|after-a2|after-source-scope>")

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


def fact_by_source(cur, apn, field_key, source_id):
    """Like live_fact(), but scoped to one source_id -- for asserting what
    finding #21's fix must hold: a run reconciling one source's own facts must
    neither miss its own supersession nor touch a different source's live
    fact for the same (parcel, field), even when both are live at once."""
    cur.execute("""
        SELECT f.id, f.value, f.superseded_at IS NOT NULL
        FROM fact f JOIN parcel p ON p.id = f.parcel_id
        WHERE p.apn = %s AND f.field_key = %s AND f.source_id = %s
        ORDER BY f.recorded_at DESC LIMIT 1
    """, (apn, field_key, source_id))
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
    # Corrected (P60-2): this pair of checks previously asserted the OLD
    # retire_with_false_successor behavior -- a permit disappearing from the
    # source file used to supersede permits.active to false. C2 (P59,
    # LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md; see ingest_zoning_permits.py's own
    # extensive comment right above its attribution_lost handling) deliberately
    # removed that write: without a persisted per-permit identity, "genuinely
    # dropped off the export" and "just unattributable this run" look
    # identical, so absence now leaves the live fact untouched and opens a
    # typed, non-blocking permit_attribution_lost exception instead of ever
    # fabricating a false value. These checks never got updated when C2
    # landed -- first caught when db.yml's p5-acceptance job ran in CI for
    # the first time ever (P60-1); 23717099 is in db/fixtures/p5/
    # p5_permits_A.csv but genuinely absent from p5_permits_B.csv.
    d_active = live_fact(cur, "23717099", "permits.active")
    check("after B: 23717099 permits.active unchanged (still true, no supersession -- "
          "C2: absence never fabricates a false)",
          d_active is not None and d_active[1] is True and d_active[2] is None,
          f"got {d_active}")
    d_earliest = live_fact(cur, "23717099", "permits.series_earliest")
    check("after B: 23717099 permits.series_earliest unchanged (still 2026-01-01, no supersession)",
          d_earliest is not None and d_earliest[1] == "2026-01-01" and d_earliest[2] is None,
          f"got {d_earliest}")
    active_reasons = open_exceptions(cur, "23717099", "permit_attribution_lost")
    check("after B: 23717099 has open permit_attribution_lost exception "
          "(no_fresh_apn_match_this_run)",
          "no_fresh_apn_match_this_run" in active_reasons, f"got {active_reasons}")

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
    # Corrected (P60-2): see check_permits_after_b's identical correction --
    # since B never touched 23717099's permits.active/series_earliest (C2),
    # reloading A again just re-confirms the SAME unchanged live fact
    # (fresh == live, the "same" branch) -- nothing to flip "back", because
    # nothing was ever flipped forward. The attribution-lost exception opened
    # after B is what actually changes here: 23717099 is present in A again,
    # so it closes (condition_cleared).
    d_active = live_fact(cur, "23717099", "permits.active")
    check("after A2: 23717099 permits.active STILL unchanged (still true, no supersession -- "
          "never touched by B or by this reload)",
          d_active is not None and d_active[1] is True and d_active[2] is None,
          f"got {d_active}")
    d_earliest = live_fact(cur, "23717099", "permits.series_earliest")
    check("after A2: 23717099 permits.series_earliest STILL unchanged (still 2026-01-01, "
          "no supersession)",
          d_earliest is not None and d_earliest[1] == "2026-01-01" and d_earliest[2] is None,
          f"got {d_earliest}")
    active_history = exception_history(cur, "23717099", "permit_attribution_lost")
    check("after A2: 23717099's permit_attribution_lost exception is now closed "
          "(condition_cleared) -- attribution confirmed again",
          bool(active_history) and active_history[-1][2] == "condition_cleared",
          f"got {active_history}")

    d_earliest = live_fact(cur, "58705049", "permits.series_earliest")
    check("after A2: 58705049 permits.series_earliest back to 2026-01-02, superseded",
          d_earliest is not None and d_earliest[1] == "2026-01-02" and d_earliest[2] is not None,
          f"got {d_earliest}")

    # Corrected (P60-2): this block previously asserted the OLD
    # retire_with_false_successor behavior for 23712112 (absent from
    # p5_permits_A.csv, so A2's reload sees it vanish, same as 23717099 does
    # after B -- see check_permits_after_b's identical correction and C2's
    # own comment in ingest_zoning_permits.py). Under C2, absence never
    # fabricates a false: the live fact B wrote (true, NEW, no supersession)
    # stays exactly as it is, and a permit_attribution_lost exception opens
    # instead of a second fact row ever existing.
    d_active = live_fact(cur, "23712112", "permits.active")
    check("after A2: 23712112 permits.active STILL unchanged (still true, no supersession -- "
          "C2: absence never fabricates a false)",
          d_active is not None and d_active[1] is True and d_active[2] is None,
          f"got {d_active}")
    d_earliest = live_fact(cur, "23712112", "permits.series_earliest")
    check("after A2: 23712112 permits.series_earliest STILL unchanged (still 2026-02-01, "
          "no supersession)",
          d_earliest is not None and d_earliest[1] == "2026-02-01" and d_earliest[2] is None,
          f"got {d_earliest}")
    active_reasons = open_exceptions(cur, "23712112", "permit_attribution_lost")
    check("after A2: 23712112 has open permit_attribution_lost exception "
          "(no_fresh_apn_match_this_run)",
          "no_fresh_apn_match_this_run" in active_reasons, f"got {active_reasons}")

    # This checkpoint runs twice in run_p5_acceptance.sh: once right after
    # A2's reconcile, once more after the deliberate same-snapshot re-run at
    # the end of the script (identical fixture, no new data). Since C2 never
    # writes a fact on absence, 23712112 permits.active has exactly ONE total
    # fact row throughout -- B's original NEW true -- whether or not the
    # re-run happened; a same-snapshot re-run only re-opens (or leaves open)
    # the same attribution_lost exception, never touches the fact table.
    n = total_fact_rows(cur, "23712112", "permits.active")
    check("after A2: 23712112 permits.active has exactly 1 total fact row "
          "(B's original true; C2 never adds a fabricated successor)",
          n == 1, f"got {n}")


SOURCE_ID_ZONING = "ca_san_jose.zoning_districts"
SOURCE_ID_PERMITS = "ca_san_jose.building_permits_active"


def check_source_scope_conflict(cur):
    """Finding #21: load_zoning's live-fact reconciliation map was built
    without a source_id filter. run_p5_acceptance.sh's SOURCE-SCOPE CONFLICT
    stage plants a second, foreign-source live fact for 58705049's
    zoning.district (same field, different source_id) before reloading
    fixture B -- proven RED against pre-fix code (see
    prompts/P15-source-scope-reconciliation-reads.md): the foreign row won
    the plain dict-comprehension overwrite, the real zoning source's own
    'R-2' fact was wrongly read back as already 'R-3' and never superseded.
    """
    real = fact_by_source(cur, "58705049", "zoning.district", SOURCE_ID_ZONING)
    check("after source-scope conflict: 58705049 zoning.district (real source) "
          "= 'R-3', live -- reconciled against its OWN prior fact, not left "
          "stale at 'R-2' by a foreign-source arbitrary pick",
          real is not None and real[1] == "R-3" and real[2] is False, f"got {real}")

    foreign = fact_by_source(cur, "58705049", "zoning.district", SOURCE_ID_PERMITS)
    check("after source-scope conflict: 58705049 zoning.district (planted "
          "foreign-source row) untouched -- still live, still 'R-3'",
          foreign is not None and foreign[1] == "R-3" and foreign[2] is False, f"got {foreign}")

    cur.execute("""
        SELECT f.value FROM fact f JOIN parcel p ON p.id = f.parcel_id
        WHERE p.apn = %s AND f.field_key = 'zoning.district' AND f.source_id = %s
              AND f.superseded_at IS NOT NULL
        ORDER BY f.recorded_at DESC LIMIT 1
    """, ("58705049", SOURCE_ID_ZONING))
    prior = cur.fetchone()
    check("after source-scope conflict: 58705049 zoning.district (real source) "
          "prior fact = 'R-2', now superseded -- a real supersession happened, "
          "not a coincidence of 'R-3' already being live",
          prior is not None and prior[0] == "R-2", f"got {prior}")


def main():
    conn = get_db()
    cur = conn.cursor()
    if CHECKPOINT == "after-b":
        check_zoning_after_b(cur)
        check_permits_after_b(cur)
    elif CHECKPOINT == "after-source-scope":
        check_source_scope_conflict(cur)
    else:
        check_zoning_after_a2(cur)
        check_permits_after_a2(cur)
    conn.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
