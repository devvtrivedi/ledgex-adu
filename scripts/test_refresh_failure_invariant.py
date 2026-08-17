#!/usr/bin/env python3
"""Invariant test for the refresh-failure hole (NEXT_PROMPTS.md P1).

Invariant under test: a current_fact refresh failure must never make
previous_successful_snapshot() blind to a snapshot whose ledger rows
(parcel/source_feature_identity/fact) already committed. The refresh is
still allowed to fail -- this does not test that refreshes are infallible,
only that a failed one leaves the next run able to reason correctly.

Runs the REAL scripts/ingest_parcels.py phase_e() end to end -- real
database, real S3-compatible object store, real GeoJSON parse, real
parcel/fact/source_feature_identity inserts. The only thing faked is
forcing current_fact's refresh to fail: refresh_current_fact is
monkeypatched to always raise, injecting the fault at exactly the boundary
the reported bug is about, rather than reimplementing phase_e's logic
here. Same fault-injection idea as the manual reproduction (an ACCESS
EXCLUSIVE lock forcing a real LockNotAvailable there); this version is a
deterministic, fast, repeatable substitute suitable for a test run.

A fresh, uniquely-content-hashed snapshot is created on every run, so
running this test repeatedly against the same scratch database never
collides with a prior run's permanently-committed rows (0017 forbids
deleting them) -- each run gets its own clean "previous_successful_snapshot
is NULL going in" starting condition.

Requires the same environment as ingest_parcels.py itself: DATABASE_URL
(a scratch database -- this test commits real, permanent fact rows) and
OBJECT_STORE_*. Never point this at a shared or production database.

Usage:
  DATABASE_URL=... OBJECT_STORE_URL=... OBJECT_STORE_ACCESS_KEY=... \\
  OBJECT_STORE_SECRET_KEY=... OBJECT_STORE_BUCKET=... \\
    .venv-ingest/bin/python3 scripts/test_refresh_failure_invariant.py

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
from infra.env import env, get_db  # noqa: E402


def seed_reference_rows(conn):
    """Idempotent -- ON CONFLICT DO NOTHING, same convention as
    db/tests/invariants.sql. Reuses the real ids ingest_parcels.py hardcodes
    (SOURCE_ID/JURISDICTION_ID/LICENCE_ID are module globals, not
    parameters) -- this test is meant to run against a dedicated scratch
    database, the same way db-test's suite is, not against shared data."""
    with conn.cursor() as cur:
        cur.execute(
            # observed_at/cleared_by/cleared_at match db/seeds/day4_sources.sql's own
            # values exactly (not now()/'test'/now()) -- see _p5_setup.py's identical
            # comment: counsel/owner sign-off is genuinely still Pending, and this
            # insert must not fabricate it on whatever database it first reaches.
            """
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, observed_at, cleared_by, cleared_at)
            VALUES (%s, 'CC BY 4.0', 'attribution', 'allowed', 'allowed', 'City of San Jose',
                    '2026-07-31'::timestamptz, NULL, NULL)
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.LICENCE_ID,),
        )
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES (%s, 'City of San Jose', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.JURISDICTION_ID,),
        )
        cur.execute(
            """
            INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status,
                                 phase_status_reason, endpoint_url, licence_id, active)
            VALUES (%s, %s, 'Parcels', 'City of San Jose', 'bulk', 'active', 'test fixture',
                    'https://example.com/parcels', %s, false)
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.SOURCE_ID, ip.JURISDICTION_ID, ip.LICENCE_ID),
        )
        cur.execute(
            """
            INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description)
            VALUES
              ('parcel.apn', 'APN', 'public_record', 'string', 'parcel', 'Assessor parcel number'),
              ('parcel.geometry', 'Geometry', 'public_record', 'geometry', 'parcel', 'Parcel geometry'),
              ('parcel.source_parcel_id', 'Source parcel id', 'public_record', 'string', 'parcel', 'Source-native feature id')
            ON CONFLICT (field_key) DO NOTHING
            """
        )
    conn.commit()


def make_fresh_snapshot(conn, s3, bucket):
    """A tiny, uniquely-content-hashed GeoJSON fixture (one feature, a
    fresh uuid baked into PARCELID/APN so every run's bytes -- and
    therefore its content_hash / snapshot_id -- are new). Uploaded for
    real and recorded as a real snapshot row, same as phase_b would."""
    token = uuid.uuid4().hex
    body = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"APN": f"TEST-{token}", "PARCELID": f"TEST-{token}"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [-121.90, 37.33], [-121.89, 37.33], [-121.89, 37.34], [-121.90, 37.34], [-121.90, 37.33]
            ]]},
        }],
    }
    payload = json.dumps(body).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    key = ip.object_key(digest)
    s3.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="application/geo+json")

    sid = ip.snapshot_id_for(digest)
    uri = ip.object_uri(bucket, digest)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size,
                                   request, http_status, fetched_at, licence_observed_id)
            VALUES (%s, %s, %s, %s, 'application/geo+json', %s,
                    %s::jsonb, 200, now(), %s)
            """,
            (sid, ip.SOURCE_ID, uri, digest, len(payload),
             json.dumps({"url": ip.ENDPOINT_URL, "method": "GET", "params": {}}), ip.LICENCE_ID),
        )
    conn.commit()
    return sid


def run():
    setup_conn = get_db()
    seed_reference_rows(setup_conn)
    s3 = ip.get_s3()
    bucket = env("OBJECT_STORE_BUCKET")
    snapshot_id = make_fresh_snapshot(setup_conn, s3, bucket)
    setup_conn.close()

    print(f"[test] fresh snapshot for this run: {snapshot_id}")

    precondition = get_db()
    anchor_before = ip.previous_successful_snapshot(precondition, ip.SOURCE_ID)
    precondition.close()
    assert anchor_before != snapshot_id, (
        "precondition violated: previous_successful_snapshot() already points at this "
        "brand-new snapshot before phase_e has even run once -- the fresh-snapshot "
        "isolation above failed."
    )

    # Fault injection: force the refresh -- and only the refresh -- to fail.
    # Real phase_e(), real ledger writes, real job_run bookkeeping; this is
    # the one deliberately-broken collaborator.
    real_refresh = ip.refresh_current_fact

    def broken_refresh(conn):
        raise RuntimeError("synthetic refresh failure (test fault injection)")

    ip.refresh_current_fact = broken_refresh
    try:
        raised = None
        try:
            ip.phase_e(snapshot_id)
        except Exception as e:  # noqa: BLE001 -- phase_e is expected to raise here
            raised = e
    finally:
        ip.refresh_current_fact = real_refresh

    if raised is None:
        print("[test] FAIL: phase_e did not raise even though refresh_current_fact "
              "was forced to fail -- the fault injection itself is broken.")
        return 1
    if "synthetic refresh failure" not in str(raised):
        print(f"[test] FAIL: phase_e raised, but not the injected fault: {type(raised).__name__}: {raised}")
        return 1
    print(f"[test] phase_e raised as expected (refresh CAN still fail): {type(raised).__name__}: {raised}")

    check_conn = get_db()
    anchor_after = ip.previous_successful_snapshot(check_conn, ip.SOURCE_ID)
    with check_conn.cursor() as cur:
        cur.execute(
            "SELECT status, snapshot_id FROM job_run WHERE job_key = %s ORDER BY started_at DESC LIMIT 1",
            (ip.JOB_KEY_FULL,),
        )
        job_status, job_snapshot_id = cur.fetchone()
        cur.execute("SELECT count(*) FROM fact WHERE snapshot_id = %s", (snapshot_id,))
        fact_count = cur.fetchone()[0]
    check_conn.close()

    print(f"[test] job_run.status={job_status!r} job_run.snapshot_id={job_snapshot_id!r} "
          f"fact_count={fact_count} previous_successful_snapshot()={anchor_after!r}")

    failures = []
    if fact_count == 0:
        failures.append("no facts were committed at all -- the ledger write itself didn't happen; "
                         "this test's premise (facts commit before the refresh) is not being exercised")
    if job_status != "succeeded":
        failures.append(f"job_run.status={job_status!r}, expected 'succeeded' -- the ledger committed "
                         f"but job_run does not durably reflect that")
    if anchor_after != snapshot_id:
        failures.append(f"previous_successful_snapshot() returned {anchor_after!r}, expected {snapshot_id!r} -- "
                         f"the reconciliation anchor does not see this snapshot as the anchor even though "
                         f"{fact_count} facts are permanently committed under it. This is the refresh-failure "
                         f"hole: the next run cannot reason correctly about what already happened.")

    if failures:
        print("[test] FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("[test] PASS: ledger committed, job_run reflects it as 'succeeded', and "
          "previous_successful_snapshot() correctly anchors on this snapshot despite "
          "the refresh having failed.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
