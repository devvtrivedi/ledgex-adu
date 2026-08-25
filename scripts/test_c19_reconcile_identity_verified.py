#!/usr/bin/env python3
"""Regression test for C19 (P59): phase_e()'s same_as_previous fast path
queried identity_by_feature_id (an active source_feature_identity lookup
keyed by PARCELID) but never read it -- the loop's comment claimed
"verifying identity presence is sufficient to prove [the same facts]
without paying for a full value-by-value database diff", but the actual
check performed was only is_blank(pid_raw). A feature with a real,
non-blank PARCELID but NO matching active identity row would silently
pass the fast path, contradicting the claim.

Runs the REAL scripts/ingest_parcels.py phase_e() end to end against a
real database and a real MinIO-backed snapshot object -- not a mock of
the loop's logic. Fixture: two features, but only ONE gets an active
source_feature_identity row planted before the run (reproducing exactly
the case the dead code should have caught: a feature present in the
"unchanged" snapshot with no backing identity). A job_run row marks this
exact snapshot_id as the immediately-previous successful run, so
phase_e(snapshot_id) takes the same_as_previous=True fast path.

Requires DATABASE_URL for a scratch database (writes real job_run/
source_feature_identity/snapshot rows) with db/seeds/day4_sources.sql
already applied (needs ca_san_jose.parcels' real source/licence/
jurisdiction rows), and a reachable MinIO (OBJECT_STORE_* env vars).

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_c19_reconcile_identity_verified.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import hashlib
import json
import os
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import ingest_parcels as ip  # noqa: E402 -- module under test, imported, not reimplemented
from infra.env import get_db, env  # noqa: E402


def make_fixture_geojson():
    """Two trivial features -- their content doesn't matter to this test,
    only their PARCELID identity."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"PARCELID": "c19-has-identity", "APN": "123-45-678"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [0, 0], [0, 1], [1, 1], [1, 0], [0, 0]
                ]]},
            },
            {
                "type": "Feature",
                "properties": {"PARCELID": "c19-missing-identity", "APN": "987-65-432"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [2, 0], [2, 1], [3, 1], [3, 0], [2, 0]
                ]]},
            },
        ],
    }


def upload_snapshot_and_register(conn):
    body = json.dumps(make_fixture_geojson()).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    bucket = env("OBJECT_STORE_BUCKET")
    s3 = ip.get_s3()
    key = ip.object_key(digest)
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/geo+json")

    snapshot_id = ip.snapshot_id_for(digest)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, "
            "byte_size, request, http_status, fetched_at, licence_observed_id) "
            "VALUES (%s, %s, %s, %s, 'application/geo+json', %s, '{}'::jsonb, 200, now(), %s) "
            "ON CONFLICT (id) DO NOTHING",
            (snapshot_id, ip.SOURCE_ID, ip.object_uri(bucket, digest), digest, len(body), ip.LICENCE_ID),
        )
    conn.commit()
    return snapshot_id


def plant_one_identity_only(conn, snapshot_id, parcel_id_with_identity):
    """Only 'c19-has-identity' gets a live source_feature_identity row --
    'c19-missing-identity' deliberately does not, reproducing the gap the
    fast path must catch."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parcel (id, jurisdiction_id, apn, geom) VALUES "
            "(%s, %s, '123-45-678', ST_Multi(ST_SetSRID(ST_GeomFromText("
            "'POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))'), 4326)))",
            (parcel_id_with_identity, ip.JURISDICTION_ID),
        )
        cur.execute(
            "INSERT INTO source_feature_identity "
            "(source_id, source_feature_id, parcel_id, first_seen_snapshot_id, first_seen_at, "
            " last_seen_snapshot_id, last_seen_at) "
            "VALUES (%s, %s, %s, %s, now(), %s, now())",
            (ip.SOURCE_ID, "c19-has-identity", parcel_id_with_identity, snapshot_id, snapshot_id),
        )
    conn.commit()


def mark_previous_successful(conn, snapshot_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO job_run (job_key, jurisdiction_id, source_id, status, snapshot_id, "
            " started_at, finished_at) "
            "VALUES (%s, %s, %s, 'succeeded', %s, now(), now())",
            (ip.JOB_KEY_FULL, ip.JURISDICTION_ID, ip.SOURCE_ID, snapshot_id),
        )
    conn.commit()


def run():
    conn = get_db()
    snapshot_id = upload_snapshot_and_register(conn)
    plant_one_identity_only(conn, snapshot_id, str(uuid.uuid4()))
    mark_previous_successful(conn, snapshot_id)
    conn.close()

    print(f"[test] snapshot {snapshot_id}: 2 features, only 'c19-has-identity' has a live identity row")
    print("[test] calling phase_e() on the SAME snapshot_id -- must take the same_as_previous fast path")

    try:
        ip.phase_e(snapshot_id)
    except RuntimeError as e:
        if "no active source_feature_identity row" in str(e) and "c19-missing-identity" in str(e):
            print(f"[test] PASS: fast path correctly refused -- {e}")
            return 0
        print(f"[test] FAIL: refused, but not for the expected reason -- {e}")
        return 1
    except Exception as e:
        print(f"[test] FAIL: unexpected exception type {type(e).__name__}: {e}")
        return 1

    print("[test] FAIL: phase_e() completed without error -- the fast path silently accepted a "
          "feature ('c19-missing-identity') with no active source_feature_identity row, exactly "
          "the gap C19 exists to close.")
    return 1


if __name__ == "__main__":
    sys.exit(run())
