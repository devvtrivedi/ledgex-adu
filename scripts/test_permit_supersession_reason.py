#!/usr/bin/env python3
"""Narrow regression fixture for D4 (P63B, LEDGEX-P63A-PREDESIGN-PROVENANCE-SIMPLIFICATION.txt
§12 B4; P63A packet §12 item 5): load_permits()'s genuine-difference branch
(scripts/ingest_zoning_permits.py, the "real evidence, a real supersession" comment) must
write supersession_reason='unknown', not 'world_change' -- the diff observes that the
source's rendering changed, not why it changed, and 'world_change' claimed knowledge the
code does not have. This is the ONLY thing this test checks; it is not a general
supersession-reason suite.

Two runs, same APN, DIFFERENT issue dates -- min(dates) (permits.series_earliest) genuinely
differs between the two runs while permits.active stays true=true (a same, not a diff) --
this isolates the genuine-difference branch at :1475 without touching the absence/
attribution-lost path at all (see scripts/test_load_permits_attribution.py for that,
separate, fixture).

Requires DATABASE_URL for a database with db/seeds/day4_sources.sql already applied (needs
the real ca_san_jose.building_permits_active source + cc0_api_2026_08 licence rows). Writes
permanent rows under a TEST-D4- prefixed APN (matches db/tests/teardown.sql's
`apn ILIKE 'test-%'` cleanup convention), same as this suite's siblings.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_permit_supersession_reason.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import csv
import hashlib
import datetime
import os
import sys
import tempfile
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
from ingest_zoning_permits import load_permits, SOURCE_ID_PERMITS, LICENCE_ID_PERMITS  # noqa: E402

JURISDICTION_ID = "ca_san_jose"

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _seed_parcel(conn, apn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (JURISDICTION_ID, apn),
        )
        parcel_id = cur.fetchone()[0]
    conn.commit()
    return parcel_id


def _write_permits_csv(apn, issue_date_str):
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
    writer = csv.writer(tmp)
    writer.writerow(["ASSESSORS_PARCEL_NUMBER", "ISSUEDATE"])
    writer.writerow([apn, issue_date_str])
    tmp.close()
    return tmp.name


def _make_snapshot(conn, suffix):
    digest = hashlib.sha256(f"test-d4-{suffix}".encode()).hexdigest()
    snapshot_id = f"{SOURCE_ID_PERMITS}:sha256:{digest}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, "
            "byte_size, request, http_status, fetched_at, licence_observed_id) "
            "VALUES (%s, %s, 's3://test-d4/fixture', %s, 'text/csv', 1, "
            "'{}'::jsonb, 200, now(), %s) ON CONFLICT (id) DO NOTHING",
            (snapshot_id, SOURCE_ID_PERMITS, digest, LICENCE_ID_PERMITS),
        )
    conn.commit()
    return snapshot_id, datetime.datetime.now(datetime.timezone.utc)


def _latest_earliest_fact(conn, parcel_id):
    """(id, value, superseded_at, supersedes_fact_id, supersession_reason) for the
    CURRENT permits.series_earliest fact, most recent first."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, value, superseded_at, supersedes_fact_id, supersession_reason "
            "FROM fact WHERE parcel_id = %s AND field_key = 'permits.series_earliest' "
            "AND source_id = %s ORDER BY recorded_at DESC LIMIT 1",
            (parcel_id, SOURCE_ID_PERMITS),
        )
        return cur.fetchone()


def main():
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    apn = f"TEST-D4-{suffix}"
    parcel_id = _seed_parcel(conn, apn)
    snap1, retrieved_at1 = _make_snapshot(conn, "run1")

    # Run 1: establishes permits.series_earliest = 2026-06-01.
    path1 = _write_permits_csv(apn, "6/1/2026 12:00:00 AM")
    load_permits(conn, path1, snap1, retrieved_at1)
    os.unlink(path1)

    conn = get_db()
    row1 = _latest_earliest_fact(conn, parcel_id)
    check("run 1: permits.series_earliest fact written", row1 is not None, f"got {row1}")
    snap2, retrieved_at2 = _make_snapshot(conn, "run2")

    # Run 2: SAME apn, EARLIER issue date -> min(dates) genuinely differs
    # (2026-01-01 < 2026-06-01). permits.active stays true=true (a "same", not a diff) --
    # this isolates the :1475 genuine-difference branch on series_earliest alone, with no
    # absence/attribution-lost path involved at all.
    path2 = _write_permits_csv(apn, "1/1/2026 12:00:00 AM")
    load_permits(conn, path2, snap2, retrieved_at2)
    os.unlink(path2)

    conn = get_db()
    row2 = _latest_earliest_fact(conn, parcel_id)
    check("run 2: a NEW permits.series_earliest fact was written (genuine difference)",
          row2 is not None and row1 is not None and row2[0] != row1[0],
          f"run1={row1}, run2={row2}")
    if row2 is not None and row1 is not None:
        check("run 2: the new fact supersedes run 1's fact",
              row2[3] == row1[0], f"got supersedes_fact_id={row2[3]!r}, run1 fact id={row1[0]!r}")
        check("D4 FIX: supersession_reason is 'unknown', not 'world_change'",
              row2[4] == "unknown", f"got supersession_reason={row2[4]!r}")

    conn.close()
    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
