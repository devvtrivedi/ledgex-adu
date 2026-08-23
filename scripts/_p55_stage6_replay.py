#!/usr/bin/env python3
"""P55 Phase 2 Stage 6 replay -- one-off utility (not wired into any make
target). Executes the SEVEN-operation replay list against the REPLACEMENT
bar §12.11 sets (§12.6-owner-decided, 2026-08-23), ONE OPERATION AT A TIME.

CORRECTED 2026-08-23 (§12.12, second Stage 6 recovery): historical operation
4 (parcels, b98138f0...) is EXCLUDED from replay -- not a code fix, an input
fix. b98138f0's own historical rows_out=25 was an artifact of migration
0043 (source_feature_identity) landing AFTER the original 0216d539 wave had
already ingested -- the tracking table was empty by construction when
b98138f0 ran historically, not because it was a genuine small delta. In this
rebuild, 0216d539 correctly populates 225,039 identities before b98138f0
would run, so replaying it via --phase e's full reconciliation would (does,
confirmed live) report 225,014 real parcels as falsely "disappeared." All 25
of b98138f0's own APNs were checked directly against the rebuilt parcel
table after 0216d539 loads and confirmed already present -- exclusion costs
zero real parcels. Its SNAPSHOT ROW is still registered by scripts/
_p55_stage6_prep.py (the fetch genuinely happened; provenance is honest to
keep) -- only the LOAD is excluded. TARGET_SNAPSHOT_COUNT stays 6.

  - PARCELS operations (--phase e): rows_in/rows_out must match the
    historical job_run row EXACTLY. A mismatch halts. This bar's own
    original justification ("no cross-row matching logic for a bug fix to
    have changed") was WRONG -- phase_e's own Phase B reconciliation has
    real cross-row logic (new/changed/disappeared against the full
    source_feature_identity ledger), and it is exactly that logic which
    caught b98138f0's own deviation. Kept exact because a parcels mismatch
    is diagnosable and rare, not because the code path is simple.

  - ZONING/PERMITS operations: the historical rows_in/rows_out are PRINTED
    (informational -- §12.10 already explains why they will not match:
    contaminated historical parcel set + evolved matching code, both
    additive to the real fact count) but NEVER used as a pass/fail gate.
    Instead, PARTITION INVARIANTS read from persisted, independently-
    queryable outcome data (facts + parcel_exception, never a second call
    into classify_zoning_candidates()) -- see verify_zoning_partition() and
    verify_no_contamination() below. A FAILED invariant halts.

  - After all seven operations: the FINAL fact count must be STRICTLY
    GREATER than 1,135,140 (§12.11's own binding directional stop condition
    -- a result at or below contradicts both of §12.10's named mechanisms
    and halts, is not folded into a delta-explained close-out) and the
    final snapshot count must be exactly 6.

No origin fetch anywhere in this file: every operation below is
`ingest_parcels.py --phase e` or `ingest_zoning_permits.py --phase load`,
both bound exclusively to `verified_snapshot_file()` (reads snapshot.
object_uri -- s3://ledgex-snapshots-locked/..., never a San Jose endpoint).

Usage (note `set -o pipefail` -- REQUIRED if piping through `tee`; without
it, a halted script's own sys.exit(1) is masked by tee's own exit 0, and a
background-task summary reporting "exit code 0" reads as success when the
script actually stopped on a real deviation -- this nearly cost the Stage 6
recovery investigation its own most important finding, 2026-08-23):
  set -o pipefail
  DATABASE_URL=<fresh, post-rename, post-migrate, post-seed,
  post-_p55_stage6_prep.py-register ledgex_schema_check> \
    .venv-ingest/bin/python3 scripts/_p55_stage6_replay.py 2>&1 | tee <logfile>
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from infra.env import get_db  # noqa: E402

PARCELS_SID_A = "ca_san_jose.parcels:sha256:0216d539a3995ccc88e4b6542ad8aa936fb6078e74ea39402444a96c5b172fe2"
ZONING_SID = "ca_san_jose.zoning_districts:sha256:699ec193384d4894d68d04b91df2f2531c4587e65488de560087be925adf451b"
ZONING_SID_A = "ca_san_jose.zoning_districts:sha256:eae7823a22e72537d5738d473c6c8289e0e2af78e76be782ea5e432fdd5d04ba"
PERMITS_SID = "ca_san_jose.building_permits_active:sha256:70bf19c13dadebe65321d0d56efce66ded036f0022be1dcef7972330c7c72640"
PERMITS_SID_A = "ca_san_jose.building_permits_active:sha256:8f3328b5cb9845228bb6bb11aac4a0b33289105a4134d5d2c42af78d2d6afffb"

TARGET_FACT_COUNT = 1135140
TARGET_SNAPSHOT_COUNT = 6

# op_num is the ORIGINAL historical operation number (1-8, per prompts/
# P55-scoped-unblock.md §12.3) -- kept as an explicit label, not re-derived
# from list position, precisely BECAUSE operation 4 is missing from this
# list on purpose (§12.12). Renumbering 1-7 would silently discard the
# traceability back to job_run's own historical numbering; op_num keeps it.
# kind in {"parcels", "zoning", "permits"}. historical rows_in/rows_out are
# always the ORIGINAL job_run figures -- reproduced literally, never retyped.
REPLAY = [
    (1, "parcels", "ingest_parcels_full", PARCELS_SID_A, 225039, 225039,
     [sys.executable, "scripts/ingest_parcels.py", "--phase", "e", "--snapshot-id", PARCELS_SID_A]),
    (2, "zoning", "ingest_zoning", ZONING_SID_A, 225042, 214892,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "zoning", "--phase", "load",
      "--snapshot-id", ZONING_SID_A]),
    (3, "permits", "ingest_permits", PERMITS_SID_A, 17499, 8322,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "permits", "--phase", "load",
      "--snapshot-id", PERMITS_SID_A]),
    # op_num 4 (parcels, b98138f0...) EXCLUDED -- §12.12. Snapshot row still
    # registered by scripts/_p55_stage6_prep.py; the LOAD is what's excluded.
    (5, "zoning", "ingest_zoning", ZONING_SID, 225088, 522,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "zoning", "--phase", "load",
      "--snapshot-id", ZONING_SID]),
    (6, "permits", "ingest_permits", PERMITS_SID, 2, 0,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "permits", "--phase", "load",
      "--snapshot-id", PERMITS_SID]),
    (7, "zoning", "ingest_zoning", ZONING_SID, 225088, 443,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "zoning", "--phase", "load",
      "--snapshot-id", ZONING_SID]),
    (8, "permits", "ingest_permits", PERMITS_SID, 3, 0,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "permits", "--phase", "load",
      "--snapshot-id", PERMITS_SID]),
]
TOTAL_OPS = len(REPLAY)  # 7


def latest_job_run_since(conn, job_key, snapshot_id, since_ts):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, status, rows_in, rows_out, started_at FROM job_run "
            "WHERE job_key = %s AND snapshot_id = %s AND started_at > %s "
            "ORDER BY started_at DESC LIMIT 1",
            (job_key, snapshot_id, since_ts),
        )
        return cur.fetchone()


def verify_no_contamination(conn):
    """Every ca_san_jose parcel must trace to the real ca_san_jose.parcels
    source. Zero is the only acceptable count -- named risk in §12.11:
    check_golden.py's own make_fixture_parcel_and_fact() creates exactly
    this contamination; must not have run against this database.

    STAGE 6 RECOVERY (2026-08-23): the original `NOT IN` form here is
    PATHOLOGICAL, found live -- pid 97239 + 2 parallel workers ran the
    literal query below for 44+ minutes on operation 3's own post-check,
    zero locks, zero idle-in-transaction, pure CPU/IO on a materialized
    SubPlan re-probed per outer row. `fact.parcel_id` is NOT NULL
    (confirmed, db/schema.sql:284), so `NOT IN`/`NOT EXISTS` are
    semantically identical here -- Postgres just doesn't rewrite an
    uncorrelated `NOT IN` into an anti-join the way it does `NOT EXISTS`.
    Proven, not assumed: EXPLAIN on the old form costs 4,713,162,723;
    EXPLAIN on the NOT EXISTS form below costs 101,573 (a Parallel Hash
    Right Anti Join, not a SubPlan) -- a ~46,000x reduction -- and the
    corrected form actually ran in 0.817s against this same live database
    while the old one was still stuck. Old form, for the record, never
    executed to a diff -- EXPLAIN and the rewrite's own correctness
    (NOT IN -> NOT EXISTS, both text-book equivalent given NOT NULL) are
    the proof, not a side-by-side run of the pathological query."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM parcel p WHERE p.jurisdiction_id = 'ca_san_jose' "
            "AND NOT EXISTS (SELECT 1 FROM fact f WHERE f.parcel_id = p.id "
            "AND f.source_id = 'ca_san_jose.parcels')"
        )
        return cur.fetchone()[0]


def verify_zoning_partition(conn):
    """matched + ambiguous + zero_match == real-source parcel count,
    exactly. Reason strings read directly from ingest_zoning_permits.py's
    own REASON_NO_CONTAINING_DISTRICT/REASON_MULTIPLE_CONTAINING_DISTRICTS
    constants (duplicated here as literals -- both files are one-off/
    scripts, no shared import between them by this repo's own convention)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM parcel WHERE jurisdiction_id = 'ca_san_jose' AND centroid IS NOT NULL"
        )
        real_source_count = cur.fetchone()[0]

        cur.execute(
            "SELECT count(DISTINCT parcel_id) FROM current_fact_at(now()) "
            "WHERE field_key = 'zoning.district' AND source_id = 'ca_san_jose.zoning_districts'"
        )
        matched = cur.fetchone()[0]

        cur.execute(
            "SELECT count(DISTINCT parcel_id) FROM parcel_exception "
            "WHERE detector_key = 'zoning_spatial_join_unresolvable' "
            "AND detail->>'reason' = 'no_containing_district' AND outcome = 'open'"
        )
        zero_match = cur.fetchone()[0]

        cur.execute(
            "SELECT count(DISTINCT parcel_id) FROM parcel_exception "
            "WHERE detector_key = 'zoning_spatial_join_unresolvable' "
            "AND detail->>'reason' = 'multiple_containing_districts' AND outcome = 'open'"
        )
        ambiguous = cur.fetchone()[0]
    conn.rollback()
    total = matched + zero_match + ambiguous
    return real_source_count, matched, zero_match, ambiguous, total


def parse_start_at(argv):
    """--start-at N, EXPLICIT only -- no default resume behaviour. N is the
    ORIGINAL historical operation number (1-8), matching op_num above, NOT
    a position in this (now seven-entry) list -- so "--start-at 5" means
    "skip op_num 1-4" regardless of where op_num 5 sits in REPLAY. Absent
    entirely means the full replay (the ordinary case).

    Hard to invoke by accident, by construction: requires the literal flag
    with a value; there is no short form, no environment variable fallback,
    and the value is validated against the real op_num range below before
    anything runs. A bare `python3 _p55_stage6_replay.py` (no flags) always
    means "run everything in REPLAY" -- the single most damaging possible
    mistake this recovery could make is a silent partial-start reading as a
    full run, so the banner below prints the skip list LOUDLY, unmissably,
    before the first subprocess ever launches."""
    start_at = 1
    if "--start-at" in argv:
        idx = argv.index("--start-at")
        try:
            start_at = int(argv[idx + 1])
        except (IndexError, ValueError):
            raise SystemExit("--start-at requires an integer operation number (1-8), e.g. --start-at 5")
    max_op_num = max(op_num for op_num, *_ in REPLAY)
    if not (1 <= start_at <= max_op_num):
        raise SystemExit(f"--start-at {start_at} out of range -- historical operations run 1-{max_op_num}")
    return start_at


def main():
    start_at = parse_start_at(sys.argv)

    print("=" * 78)
    print("REPLACEMENT BAR (prompts/P55-scoped-unblock.md §12.11): parcels exact-"
          "match; zoning/permits structural (partition invariants, historical "
          "counts informational only); final count > %d (binding); final "
          "snapshot count == %d. %d operations (op_num 4 EXCLUDED, §12.12)."
          % (TARGET_FACT_COUNT, TARGET_SNAPSHOT_COUNT, TOTAL_OPS))
    print("=" * 78)
    for op_num, kind, job_key, sid, pin, pout, _argv in REPLAY:
        gate = "EXACT" if kind == "parcels" else "structural (informational counts below)"
        skip = "  <-- SKIPPED (already committed, per approved recovery)" if op_num < start_at else ""
        print(f"  [op {op_num}] {kind:8s} {job_key:22s} rows_in={pin:>7} rows_out={pout:>7}  [{gate}]  {sid}{skip}")
    print()
    if start_at > 1:
        print("!" * 78)
        print(f"!! RESUMING AT HISTORICAL OPERATION {start_at} -- operations before it above are")
        print("!! SKIPPED, not re-run, because they are already committed to this database.")
        print("!! This is only correct if you are resuming an interrupted replay against")
        print("!! the SAME database those operations already ran against. If this is a")
        print("!! fresh database, the skipped operations were NEVER run and this will")
        print("!! produce a wrong, incomplete database. STOP now if you are not certain.")
        print("!" * 78)
        print()

    conn = get_db()
    done = 0

    for op_num, kind, job_key, sid, predicted_in, predicted_out, argv in REPLAY:
        if op_num < start_at:
            continue
        done += 1
        print("=" * 78)
        print(f"[op {op_num}, {done}/{TOTAL_OPS} run] RUNNING ({kind}): {' '.join(argv)}")
        print("=" * 78)
        with conn.cursor() as cur:
            cur.execute("SELECT now()")
            before_ts = cur.fetchone()[0]
        conn.rollback()

        result = subprocess.run(argv, cwd=REPO_ROOT)
        if result.returncode != 0:
            print(f"\nSTOP: operation [op {op_num}] exited {result.returncode}. Not continuing.")
            sys.exit(1)

        row = latest_job_run_since(conn, job_key, sid, before_ts)
        conn.rollback()
        if row is None:
            print(f"\nSTOP: operation [op {op_num}] produced no new job_run row for "
                  f"({job_key!r}, {sid!r}) after {before_ts}. Cannot verify.")
            sys.exit(1)
        _id, status, actual_in, actual_out, started_at = row
        print(f"  historical: rows_in={predicted_in} rows_out={predicted_out}")
        print(f"  actual:     rows_in={actual_in} rows_out={actual_out} status={status}")

        if status != "succeeded":
            print(f"\nSTOP: operation [op {op_num}] job_run status={status!r}, not 'succeeded'.")
            sys.exit(1)

        if kind == "parcels":
            if actual_in == predicted_in and actual_out == predicted_out:
                print(f"  [op {op_num}] EXACT MATCH (parcels keeps the exact-count bar)")
            else:
                print(f"\nSTOP: operation [op {op_num}] (parcels) DEVIATED from the historical "
                      f"figure. delta rows_in={actual_in - predicted_in} "
                      f"rows_out={actual_out - predicted_out}. Diagnose before proceeding -- "
                      f"§12.12 already found one real, non-code cause (schema-vs-data ordering) "
                      f"for exactly this shape; do not assume this is the same one without "
                      f"checking.")
                sys.exit(1)
        elif kind == "zoning":
            delta_out = actual_out - predicted_out
            print(f"  delta vs history: rows_in={actual_in - predicted_in} rows_out={delta_out} "
                  f"(informational -- §12.10: contaminated historical parcel set + evolved "
                  f"matching code, both explain this, neither requires zero)")
            real_count, matched, zero_match, ambiguous, total = verify_zoning_partition(conn)
            print(f"  partition check: real_source_parcels={real_count} matched={matched} "
                  f"zero_match={zero_match} ambiguous={ambiguous} sum={total}")
            if total != real_count:
                print(f"\nSTOP: operation [op {op_num}] (zoning) partition invariant FAILED: "
                      f"matched+zero_match+ambiguous={total} != real_source_parcel_count="
                      f"{real_count} (off by {total - real_count}). A parcel fell through, "
                      f"or landed in more than one bucket. This is a structural defect, not "
                      f"an explainable delta.")
                sys.exit(1)
            contamination = verify_no_contamination(conn)
            if contamination != 0:
                print(f"\nSTOP: operation [op {op_num}] (zoning) found {contamination} "
                      f"non-real-source ca_san_jose parcel(s) -- contamination should be "
                      f"impossible in this clean rebuild (was make golden run against it?).")
                sys.exit(1)
            print(f"  [op {op_num}] STRUCTURAL CHECKS PASS")
        elif kind == "permits":
            delta_out = actual_out - predicted_out
            print(f"  delta vs history: rows_in={actual_in - predicted_in} rows_out={delta_out} "
                  f"(informational -- §12.10)")
            contamination = verify_no_contamination(conn)
            if contamination != 0:
                print(f"\nSTOP: operation [op {op_num}] (permits) found {contamination} "
                      f"non-real-source ca_san_jose parcel(s).")
                sys.exit(1)
            print(f"  [op {op_num}] STRUCTURAL CHECKS PASS")
        print()

    print("=" * 78)
    print(f"ALL {TOTAL_OPS} OPERATIONS COMPLETE (op_num 4 excluded, §12.12). FINAL ACCEPTANCE (§12.11).")
    print("=" * 78)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM fact")
        final_fact_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM snapshot")
        final_snapshot_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM fact WHERE licence_id IN ('cc_by_4_0', 'cc0')")
        old_licence_count = cur.fetchone()[0]
    conn.rollback()

    print(f"  final fact count:     {final_fact_count:,}  (target: > {TARGET_FACT_COUNT:,}, binding)")
    print(f"  final snapshot count: {final_snapshot_count}  (target: exactly {TARGET_SNAPSHOT_COUNT})")
    print(f"  facts under old licence ids (cc_by_4_0/cc0): {old_licence_count}  (target: exactly 0)")

    halted = False
    if final_fact_count <= TARGET_FACT_COUNT:
        print(f"\nSTOP: final fact count {final_fact_count:,} is NOT strictly greater than "
              f"{TARGET_FACT_COUNT:,} -- contradicts BOTH §12.10 mechanisms (both additive-"
              f"only). This is a binding stop condition, not a delta to explain.")
        halted = True
    if final_snapshot_count != TARGET_SNAPSHOT_COUNT:
        print(f"\nSTOP: final snapshot count {final_snapshot_count} != predicted "
              f"{TARGET_SNAPSHOT_COUNT}.")
        halted = True
    if old_licence_count != 0:
        print(f"\nSTOP: {old_licence_count} fact(s) still cite the old licence ids.")
        halted = True

    if halted:
        sys.exit(1)
    print("\nALL ACCEPTANCE CRITERIA MET.")


if __name__ == "__main__":
    main()
