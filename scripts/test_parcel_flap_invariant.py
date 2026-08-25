#!/usr/bin/env python3
"""Three-run flap regression fixture for C5 (P59,
LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): a source feature that disappears,
reappears, and disappears again must not wedge phase_e's single-transaction
reconcile with a UniqueViolation on the 0045/0049 partial unique index.

Runs the REAL phase_e(snapshot_id) end to end, four times (A -> B -> A ->
B), against real snapshots uploaded to the object store -- not a unit-level
call, because the defect is in the interaction between insert_exceptions'
bare INSERT and the partial unique index, which only a real transaction
against a real database reproduces. Each snapshot's bytes differ (a
version marker in an unused GeoJSON property) so `same_as_previous` never
short-circuits the diff -- every run performs a real reconciliation.

MUST run against an otherwise-empty (schema + day4 seed only) scratch
database, not a database with real parcels data: phase_e reconciles the
ENTIRE `parcel` table under SOURCE_ID='ca_san_jose.parcels' against each
snapshot, and mixing in real production-scale data would both be slow and
would misrepresent 225k real parcels as "disappeared" the moment this
fixture's tiny synthetic snapshot doesn't include them (the exact
methodological trap this pass's own C2 test discovered and fixed).

Requires DATABASE_URL (schema + day4 seed) and the OBJECT_STORE_*
variables (real MinIO). Writes permanent rows.

Usage:
  DATABASE_URL=... OBJECT_STORE_URL=... OBJECT_STORE_ACCESS_KEY=... \\
  OBJECT_STORE_SECRET_KEY=... .venv-ingest/bin/python3 \\
  scripts/test_parcel_flap_invariant.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import hashlib
import json
import os
import sys
import tempfile
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import env, get_db  # noqa: E402
import ingest_parcels as ip  # noqa: E402

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _feature(apn, version_marker):
    # PARCELID is the stable source_feature_id phase_e reconciles identity
    # on (source_feature_identity's own key) -- APN is a separate value
    # property. PARCELID is fixed across all "present" runs (the same
    # real-world feature reappearing must carry the SAME identity, or this
    # would test a new/different feature, not a genuine reappearance).
    return {
        "type": "Feature",
        "properties": {"PARCELID": apn, "APN": apn, "_test_version_marker": version_marker},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-121.9, 37.3], [-121.9, 37.31], [-121.89, 37.31], [-121.89, 37.3], [-121.9, 37.3]]],
        },
    }


def _upload_snapshot(bucket, s3, features, version_marker):
    # version_marker is embedded both in each feature's own properties
    # (_feature()) AND as a top-level marker -- the latter is what makes
    # two "disappeared" (empty features list) runs produce DIFFERENT
    # content hashes / snapshot ids, so B1 and B2 are genuinely distinct
    # observations, not a same_as_previous replay of one snapshot row.
    # ijson.items(f, "features.item") (the real parser, used by phase_e)
    # only ever reads the "features" array -- an extra top-level member is
    # invisible to it, exactly like a real GeoJSON FeatureCollection's
    # optional members (bbox, crs) already are.
    body = json.dumps({
        "type": "FeatureCollection", "features": features,
        "_test_run_marker": version_marker,
    }).encode()
    digest = hashlib.sha256(body).hexdigest()
    tmp = tempfile.NamedTemporaryFile(suffix=".geojson", delete=False)
    tmp.write(body)
    tmp.close()
    ip.upload_and_verify(s3, bucket, tmp.name, digest, len(body))
    os.unlink(tmp.name)
    return digest, len(body)


def _run(conn, bucket, s3, apn, present, run_label):
    """conn here is ONLY for insert_snapshot -- phase_e(snapshot_id) opens
    and closes its own connection internally (same contract as
    load_zoning/load_permits elsewhere in this codebase)."""
    features = [_feature(apn, run_label)] if present else []
    digest, byte_size = _upload_snapshot(bucket, s3, features, run_label)
    sid, inserted = ip.insert_snapshot(conn, digest, byte_size, "application/geo+json", 200,
                                        __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                                        bucket)
    conn.commit()
    print(f"\n--- run {run_label}: present={present}, snapshot={sid} ---")
    ip.phase_e(sid)
    return sid


def _exception_outcome(conn, apn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pe.outcome FROM parcel_exception pe "
            "JOIN parcel p ON p.id = pe.parcel_id "
            "WHERE p.apn = %s AND pe.detector_key = %s "
            "ORDER BY pe.detected_at DESC LIMIT 1",
            (apn, ip.DETECTOR_KEY_PARCEL_DISAPPEARED),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _exception_count(conn, apn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM parcel_exception pe JOIN parcel p ON p.id = pe.parcel_id "
            "WHERE p.apn = %s AND pe.detector_key = %s",
            (apn, ip.DETECTOR_KEY_PARCEL_DISAPPEARED),
        )
        return cur.fetchone()[0]


def main():
    bucket = env("OBJECT_STORE_BUCKET")
    s3 = ip.get_s3()
    apn = f"TEST-C5-{uuid.uuid4().hex[:8]}"

    conn = get_db()
    try:
        # Run A: feature present -- parcel created, no exception.
        _run(conn, bucket, s3, apn, present=True, run_label="A1")
        conn = get_db()
        check("run A1: no parcel_disappeared_from_source exception yet",
              _exception_outcome(conn, apn) is None, f"got {_exception_outcome(conn, apn)!r}")

        # Run B: feature disappears -- exception opens (first disappearance).
        conn = get_db()
        _run(conn, bucket, s3, apn, present=False, run_label="B1")
        conn = get_db()
        check("run B1: exception OPEN after first disappearance",
              _exception_outcome(conn, apn) == "open", f"got {_exception_outcome(conn, apn)!r}")

        # Run A again: feature reappears -- exception must CLOSE (the fix).
        conn = get_db()
        _run(conn, bucket, s3, apn, present=True, run_label="A2")
        conn = get_db()
        check("run A2: exception CLOSED (condition_cleared) after reappearance",
              _exception_outcome(conn, apn) == "condition_cleared", f"got {_exception_outcome(conn, apn)!r}")

        # Run B again: feature disappears a SECOND time -- THE WEDGE. Pre-fix,
        # this UniqueViolations on 0045/0049's partial index (the first
        # exception was never closed) and rolls back the entire reconcile,
        # failing the job_run. Post-fix, the first exception is already
        # condition_cleared (not 'open'), so a fresh open row is legal.
        conn = get_db()
        try:
            _run(conn, bucket, s3, apn, present=False, run_label="B2")
            flap_survived = True
        except Exception as e:
            flap_survived = False
            print(f"  FLAP CRASHED: {type(e).__name__}: {e}")
        check("run B2 (second disappearance): completes WITHOUT UniqueViolation "
              "(the wedge itself)", flap_survived)

        if flap_survived:
            conn = get_db()
            check("run B2: exactly 2 parcel_disappeared_from_source rows exist "
                  "(one per real disappearance, not a duplicate/conflict)",
                  _exception_count(conn, apn) == 2, f"got {_exception_count(conn, apn)}")
            check("run B2: the SECOND exception is OPEN",
                  _exception_outcome(conn, apn) == "open", f"got {_exception_outcome(conn, apn)!r}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
