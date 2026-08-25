#!/usr/bin/env python3
"""Regression fixture for C10 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md):
Phase D's load_parcels()/load_facts() must (1) canonicalize APN the same
way phase E does, (2) write source_feature_identity rows so a later
--phase e run does not classify these features as NEW and mint duplicates,
(3) REFUSE a re-run against the same identity rather than silently
duplicate-minting (0034 dropped the unique constraint that used to make
this impossible), and (4) commit parcels+identity+facts together, so a
load_facts failure does not strand fact-less parcels.

Calls load_parcels()/load_facts() directly (not through phase_d's own
snapshot-fetch machinery) -- they take a feature list plus snapshot_id/
retrieved_at as plain arguments, no S3 dependency. A real snapshot ROW is
still needed (fact_snapshot_source_fk) -- inserted directly here, matching
the pattern this suite's own scripts/test_compose_l0_gate.py already uses.

Requires DATABASE_URL for a database with db/seeds/day4_sources.sql
already applied (needs the real ca_san_jose.parcels source + its licence).
Writes permanent rows.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_load_parcels_identity.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import datetime
import hashlib
import os
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
import ingest_parcels as ip  # noqa: E402

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _make_snapshot(conn, suffix):
    digest = hashlib.sha256(f"test-c10-{suffix}".encode()).hexdigest()
    snapshot_id = f"{ip.SOURCE_ID}:sha256:{digest}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, "
            "byte_size, request, http_status, fetched_at, licence_observed_id) "
            "VALUES (%s, %s, 's3://test-c10/fixture', %s, 'application/geo+json', 1, "
            "'{}'::jsonb, 200, now(), %s) ON CONFLICT (id) DO NOTHING",
            (snapshot_id, ip.SOURCE_ID, digest, ip.LICENCE_ID),
        )
    conn.commit()
    return snapshot_id, datetime.datetime.now(datetime.timezone.utc)


def _feature(parcelid, apn_raw):
    return {
        "type": "Feature",
        "properties": {"PARCELID": parcelid, "APN": apn_raw},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-121.9, 37.3], [-121.9, 37.31], [-121.89, 37.31], [-121.89, 37.3], [-121.9, 37.3]]],
        },
    }


def main():
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    parcelid = f"TESTPID-C10-{suffix}"
    apn_raw = f"'{suffix}"  # leading apostrophe, the real spreadsheet-export artifact
    apn_canonical = suffix

    snap1, retrieved_at1 = _make_snapshot(conn, "run1")
    feat = _feature(parcelid, apn_raw)

    parcel_ids = ip.load_parcels(conn, [feat], snap1, retrieved_at1)
    ip.load_facts(conn, [feat], parcel_ids, ip.SOURCE_ID, snap1, retrieved_at1)
    conn.commit()

    check("(1) APN stored canonicalized (leading apostrophe stripped)",
          apn_canonical in parcel_ids and apn_raw not in parcel_ids,
          f"got keys {list(parcel_ids.keys())}")
    pid = parcel_ids[apn_canonical]

    with conn.cursor() as cur:
        cur.execute(
            "SELECT parcel_id FROM source_feature_identity WHERE source_id = %s AND source_feature_id = %s",
            (ip.SOURCE_ID, parcelid),
        )
        row = cur.fetchone()
    check("(2) source_feature_identity row written for this PARCELID",
          row is not None and row[0] == pid, f"got {row}")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM parcel WHERE id = %s", (pid,))
        parcel_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM fact WHERE parcel_id = %s AND superseded_at IS NULL", (pid,))
        fact_count = cur.fetchone()[0]
    check("(4) parcel + its 2 facts committed together",
          parcel_count == 1 and fact_count == 2, f"parcel_count={parcel_count} fact_count={fact_count}")

    # (3) Re-run: same PARCELID, same conn (fresh cursor) -- must REFUSE,
    # not silently mint a second parcel for the same feature.
    snap2, retrieved_at2 = _make_snapshot(conn, "run2")
    feat2 = _feature(parcelid, apn_raw)
    refused = False
    try:
        ip.load_parcels(conn, [feat2], snap2, retrieved_at2)
    except RuntimeError as e:
        refused = True
        conn.rollback()
        print(f"  correctly refused: {e}")
    check("(3) a re-run against the same PARCELID REFUSES, not duplicate-mints", refused)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM parcel WHERE apn = %s", (apn_canonical,))
        total_parcels_for_apn = cur.fetchone()[0]
    check("(3) still exactly ONE parcel for this APN after the refused re-run",
          total_parcels_for_apn == 1, f"got {total_parcels_for_apn}")

    conn.close()
    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
