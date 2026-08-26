#!/usr/bin/env python3
"""Regression fixture for B5 (P59C, LEDGEX-P59B-ENGINEERING-REPORT.md sec
3.2.2.5): a single feature with "geometry": null, or a non-polygonal
geometry type, used to abort phase_e's ENTIRE single-transaction reconcile
-- json.dumps(feat["geometry"]) feeds the literal text 'null' (or a
Point/LineString GeoJSON object) into ST_GeomFromGeoJSON via the bulk
parcel INSERT template, which errors, taking every other feature in the
same batch down with it. There was no geometry analogue of the existing
APN declared-gap handling (is_unresolvable_apn/DETECTOR_KEY_APN_
UNRESOLVABLE) -- one bad feature in a future export would block all
freshness until the source fixed it.

Runs the REAL phase_e(snapshot_id) end to end against a real snapshot
uploaded to the object store (not a unit-level call -- the defect is in
the bulk INSERT template, only reproducible against a real database), with
THREE features in the SAME batch: one ordinary valid-geometry feature, one
with "geometry": null, one with a non-polygonal (Point) geometry. Proves
the reconcile completes (does not abort, so the valid feature's own
parcel/facts land too) and that both bad features get a parcel row
(geom NULL, no parcel.geometry fact) plus a parcel_geometry_declared_gap
exception, correctly reasoned (null vs non_polygonal:Point).

MUST run against an otherwise-empty (schema + day4 seed only) scratch
database, not a database with real parcels data -- same reasoning
test_parcel_flap_invariant.py's own docstring states (phase_e reconciles
the ENTIRE parcel table under SOURCE_ID).

Requires DATABASE_URL (schema + day4 seed) and the OBJECT_STORE_*
variables (real MinIO). Writes permanent rows.

Usage:
  DATABASE_URL=... OBJECT_STORE_URL=... OBJECT_STORE_ACCESS_KEY=... \\
  OBJECT_STORE_SECRET_KEY=... .venv-ingest/bin/python3 \\
  scripts/test_geometry_declared_gap.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import datetime
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


def _upload_snapshot(bucket, s3, features):
    body = json.dumps({"type": "FeatureCollection", "features": features}).encode()
    digest = hashlib.sha256(body).hexdigest()
    tmp = tempfile.NamedTemporaryFile(suffix=".geojson", delete=False)
    tmp.write(body)
    tmp.close()
    ip.upload_and_verify(s3, bucket, tmp.name, digest, len(body))
    os.unlink(tmp.name)
    return digest, len(body)


def main():
    bucket = env("OBJECT_STORE_BUCKET")
    s3 = ip.get_s3()
    suffix = uuid.uuid4().hex[:8]

    apn_valid = f"TEST-B5-VALID-{suffix}"
    apn_null = f"TEST-B5-NULLGEOM-{suffix}"
    apn_point = f"TEST-B5-POINTGEOM-{suffix}"

    features = [
        {
            "type": "Feature",
            "properties": {"PARCELID": apn_valid, "APN": apn_valid},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-121.9, 37.3], [-121.9, 37.31], [-121.89, 37.31], [-121.89, 37.3], [-121.9, 37.3]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"PARCELID": apn_null, "APN": apn_null},
            "geometry": None,
        },
        {
            "type": "Feature",
            "properties": {"PARCELID": apn_point, "APN": apn_point},
            "geometry": {"type": "Point", "coordinates": [-121.9, 37.3]},
        },
    ]

    conn = get_db()
    digest, byte_size = _upload_snapshot(bucket, s3, features)
    sid, _ = ip.insert_snapshot(
        conn, digest, byte_size, "application/geo+json", 200,
        datetime.datetime.now(datetime.timezone.utc), bucket,
    )
    conn.commit()
    conn.close()

    print(f"\n--- running phase_e({sid}) against 3 features: 1 valid, 1 null-geometry, 1 Point-geometry ---")
    try:
        ip.phase_e(sid)
        reconcile_survived = True
    except Exception as e:
        reconcile_survived = False
        print(f"  RECONCILE CRASHED: {type(e).__name__}: {e}")
    check("B5 FIX: phase_e completes without aborting on the bad-geometry features "
          "(the wedge itself)", reconcile_survived)

    if not reconcile_survived:
        print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
        sys.exit(1 if failures else 0)

    conn = get_db()
    with conn.cursor() as cur:
        for apn, expect_geom, expect_reason in (
            (apn_valid, True, None),
            (apn_null, False, "null"),
            (apn_point, False, "non_polygonal:Point"),
        ):
            cur.execute(
                "SELECT id, geom IS NOT NULL FROM parcel WHERE apn = %s AND jurisdiction_id = %s",
                (apn, ip.JURISDICTION_ID),
            )
            row = cur.fetchone()
            check(f"{apn}: parcel row exists (0034: every feature becomes a parcel row)",
                  row is not None, f"got {row}")
            if row is None:
                continue
            parcel_id, has_geom = row
            check(f"{apn}: geom IS {'NOT ' if expect_geom else ''}NULL as expected",
                  has_geom == expect_geom, f"got has_geom={has_geom}")

            cur.execute(
                "SELECT count(*) FROM fact WHERE parcel_id = %s AND field_key = 'parcel.geometry' "
                "AND superseded_at IS NULL",
                (parcel_id,),
            )
            (fact_count,) = cur.fetchone()
            if expect_geom:
                check(f"{apn}: has a live parcel.geometry fact", fact_count == 1, f"got {fact_count}")
            else:
                check(f"{apn}: has NO parcel.geometry fact (mirrors stored_apn=None for an "
                      f"unresolvable APN)", fact_count == 0, f"got {fact_count}")

            cur.execute(
                "SELECT detail ->> 'reason' FROM parcel_exception WHERE parcel_id = %s "
                "AND detector_key = %s AND outcome = 'open'",
                (parcel_id, ip.DETECTOR_KEY_GEOMETRY_UNRESOLVABLE),
            )
            exc_row = cur.fetchone()
            if expect_reason is None:
                check(f"{apn}: no parcel_geometry_declared_gap exception", exc_row is None, f"got {exc_row}")
            else:
                check(f"{apn}: parcel_geometry_declared_gap exception with reason={expect_reason!r}",
                      exc_row is not None and exc_row[0] == expect_reason, f"got {exc_row}")
    conn.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
