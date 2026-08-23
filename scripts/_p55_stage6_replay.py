#!/usr/bin/env python3
"""P55 Phase 2 Stage 6 replay -- one-off utility (not wired into any make
target). Executes the 8-operation replay list scripts/_p55_stage6_prep.py
already generated (prompts/P55-scoped-unblock.md §12.3/§12.9), ONE OPERATION
AT A TIME, against the REPLACEMENT bar §12.11 sets (§12.6-owner-decided,
2026-08-23):

  - PARCELS operations (--phase e, no cross-row matching logic -- §12.10's
    own structural argument for why this bar can stay exact): rows_in/
    rows_out must match the historical job_run row EXACTLY. A mismatch here
    halts -- there is no cross-row logic for a later bug fix to have
    changed, so a parcels deviation would mean something genuinely wrong,
    not code evolution.

  - ZONING/PERMITS operations: the historical rows_in/rows_out are PRINTED
    (informational -- §12.10 already explains why they will not match:
    contaminated historical parcel set + evolved matching code, both
    additive to the real fact count) but NEVER used as a pass/fail gate.
    Instead, PARTITION INVARIANTS read from persisted, independently-
    queryable outcome data (facts + parcel_exception, never a second call
    into classify_zoning_candidates()) -- see verify_zoning_partition() and
    verify_no_contamination() below. A FAILED invariant halts.

  - After all 8 operations: the FINAL fact count must be STRICTLY GREATER
    than 1,135,140 (§12.11's own binding directional stop condition -- a
    result at or below contradicts both of §12.10's named mechanisms and
    halts, is not folded into a delta-explained close-out) and the final
    snapshot count must be exactly 6 (§12.11's own prediction).

No origin fetch anywhere in this file: every operation below is
`ingest_parcels.py --phase e` or `ingest_zoning_permits.py --phase load`,
both bound exclusively to `verified_snapshot_file()` (reads snapshot.
object_uri -- s3://ledgex-snapshots-locked/..., never a San Jose endpoint).

Usage: DATABASE_URL=<fresh, post-rename, post-migrate, post-seed,
post-_p55_stage6_prep.py-register ledgex_schema_check> \
  .venv-ingest/bin/python3 scripts/_p55_stage6_replay.py
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from infra.env import get_db  # noqa: E402

PARCELS_SID_A = "ca_san_jose.parcels:sha256:0216d539a3995ccc88e4b6542ad8aa936fb6078e74ea39402444a96c5b172fe2"
PARCELS_SID_B = "ca_san_jose.parcels:sha256:b98138f01644b1b58c7161582c8f01ee2107e63eb6ce157737cea280c9655ce0"
ZONING_SID = "ca_san_jose.zoning_districts:sha256:699ec193384d4894d68d04b91df2f2531c4587e65488de560087be925adf451b"
ZONING_SID_A = "ca_san_jose.zoning_districts:sha256:eae7823a22e72537d5738d473c6c8289e0e2af78e76be782ea5e432fdd5d04ba"
PERMITS_SID = "ca_san_jose.building_permits_active:sha256:70bf19c13dadebe65321d0d56efce66ded036f0022be1dcef7972330c7c72640"
PERMITS_SID_A = "ca_san_jose.building_permits_active:sha256:8f3328b5cb9845228bb6bb11aac4a0b33289105a4134d5d2c42af78d2d6afffb"

TARGET_FACT_COUNT = 1135140
TARGET_SNAPSHOT_COUNT = 6

# kind in {"parcels", "zoning", "permits"}. historical rows_in/rows_out are
# always the ORIGINAL job_run figures -- reproduced literally from
# scripts/_p55_stage6_prep.py's own mechanical output, never retyped.
REPLAY = [
    ("parcels", "ingest_parcels_full", PARCELS_SID_A, 225039, 225039,
     [sys.executable, "scripts/ingest_parcels.py", "--phase", "e", "--snapshot-id", PARCELS_SID_A]),
    ("zoning", "ingest_zoning", ZONING_SID_A, 225042, 214892,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "zoning", "--phase", "load",
      "--snapshot-id", ZONING_SID_A]),
    ("permits", "ingest_permits", PERMITS_SID_A, 17499, 8322,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "permits", "--phase", "load",
      "--snapshot-id", PERMITS_SID_A]),
    ("parcels", "ingest_parcels_full", PARCELS_SID_B, 25, 25,
     [sys.executable, "scripts/ingest_parcels.py", "--phase", "e", "--snapshot-id", PARCELS_SID_B]),
    ("zoning", "ingest_zoning", ZONING_SID, 225088, 522,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "zoning", "--phase", "load",
      "--snapshot-id", ZONING_SID]),
    ("permits", "ingest_permits", PERMITS_SID, 2, 0,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "permits", "--phase", "load",
      "--snapshot-id", PERMITS_SID]),
    ("zoning", "ingest_zoning", ZONING_SID, 225088, 443,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "zoning", "--phase", "load",
      "--snapshot-id", ZONING_SID]),
    ("permits", "ingest_permits", PERMITS_SID, 3, 0,
     [sys.executable, "scripts/ingest_zoning_permits.py", "--source", "permits", "--phase", "load",
      "--snapshot-id", PERMITS_SID]),
]


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
    this contamination; must not have run against this database."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM parcel WHERE jurisdiction_id = 'ca_san_jose' "
            "AND id NOT IN (SELECT parcel_id FROM fact WHERE source_id = 'ca_san_jose.parcels')"
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


def main():
    print("=" * 78)
    print("REPLACEMENT BAR (prompts/P55-scoped-unblock.md §12.11): parcels exact-"
          "match; zoning/permits structural (partition invariants, historical "
          "counts informational only); final count > %d (binding); final "
          "snapshot count == %d" % (TARGET_FACT_COUNT, TARGET_SNAPSHOT_COUNT))
    print("=" * 78)
    for i, (kind, job_key, sid, pin, pout, _argv) in enumerate(REPLAY, start=1):
        gate = "EXACT" if kind == "parcels" else "structural (informational counts below)"
        print(f"  [{i}] {kind:8s} {job_key:22s} rows_in={pin:>7} rows_out={pout:>7}  [{gate}]  {sid}")
    print()

    conn = get_db()

    for i, (kind, job_key, sid, predicted_in, predicted_out, argv) in enumerate(REPLAY, start=1):
        print("=" * 78)
        print(f"[{i}/8] RUNNING ({kind}): {' '.join(argv)}")
        print("=" * 78)
        with conn.cursor() as cur:
            cur.execute("SELECT now()")
            before_ts = cur.fetchone()[0]
        conn.rollback()

        result = subprocess.run(argv, cwd=REPO_ROOT)
        if result.returncode != 0:
            print(f"\nSTOP: operation [{i}] exited {result.returncode}. "
                  f"Not continuing to operation [{i+1}].")
            sys.exit(1)

        row = latest_job_run_since(conn, job_key, sid, before_ts)
        conn.rollback()
        if row is None:
            print(f"\nSTOP: operation [{i}] produced no new job_run row for "
                  f"({job_key!r}, {sid!r}) after {before_ts}. Cannot verify.")
            sys.exit(1)
        _id, status, actual_in, actual_out, started_at = row
        print(f"  historical: rows_in={predicted_in} rows_out={predicted_out}")
        print(f"  actual:     rows_in={actual_in} rows_out={actual_out} status={status}")

        if status != "succeeded":
            print(f"\nSTOP: operation [{i}] job_run status={status!r}, not 'succeeded'.")
            sys.exit(1)

        if kind == "parcels":
            if actual_in == predicted_in and actual_out == predicted_out:
                print(f"  [{i}/8] EXACT MATCH (parcels keeps the exact-count bar)")
            else:
                print(f"\nSTOP: operation [{i}] (parcels) DEVIATED from the historical figure -- "
                      f"parcels has no cross-row matching logic for a bug fix to have changed "
                      f"(§12.10), so this is not explained by code evolution. delta "
                      f"rows_in={actual_in - predicted_in} rows_out={actual_out - predicted_out}. "
                      f"Diagnose before proceeding.")
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
                print(f"\nSTOP: operation [{i}] (zoning) partition invariant FAILED: "
                      f"matched+zero_match+ambiguous={total} != real_source_parcel_count="
                      f"{real_count} (off by {total - real_count}). A parcel fell through, "
                      f"or landed in more than one bucket. This is a structural defect, not "
                      f"an explainable delta.")
                sys.exit(1)
            contamination = verify_no_contamination(conn)
            if contamination != 0:
                print(f"\nSTOP: operation [{i}] (zoning) found {contamination} non-real-source "
                      f"ca_san_jose parcel(s) -- contamination should be impossible in this "
                      f"clean rebuild (was make golden run against this database?).")
                sys.exit(1)
            print(f"  [{i}/8] STRUCTURAL CHECKS PASS")
        elif kind == "permits":
            delta_out = actual_out - predicted_out
            print(f"  delta vs history: rows_in={actual_in - predicted_in} rows_out={delta_out} "
                  f"(informational -- §12.10)")
            contamination = verify_no_contamination(conn)
            if contamination != 0:
                print(f"\nSTOP: operation [{i}] (permits) found {contamination} non-real-source "
                      f"ca_san_jose parcel(s).")
                sys.exit(1)
            print(f"  [{i}/8] STRUCTURAL CHECKS PASS")
        print()

    print("=" * 78)
    print("ALL 8 OPERATIONS COMPLETE. FINAL ACCEPTANCE (§12.11).")
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
