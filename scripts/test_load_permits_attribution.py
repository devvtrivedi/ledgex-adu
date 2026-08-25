#!/usr/bin/env python3
"""Two-run regression fixture for C2 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md):
load_permits must never write a fabricated permits.active=false when a
parcel's APN simply fails to resolve this run (blank/not-found/ambiguous),
only leave the live fact untouched and open a typed, closeable exception
(permit_attribution_lost). The pre-fix code wrote an affirmative,
immutable false successor on EXACTLY this condition.

load_permits() hardcodes JURISDICTION_ID='ca_san_jose' (not parameterized
per-call, unlike compose()) -- this test therefore writes under the REAL
ca_san_jose jurisdiction, with a TEST-C2- prefixed APN (matches
db/tests/teardown.sql's own `apn ILIKE 'test-%'` cleanup convention,
case-insensitive) and a synthetic snapshot row per run so
fact_provenance_complete's snapshot_id requirement is satisfied without
touching S3/MinIO -- load_permits() itself never calls
verified_snapshot_file (that is phase_permits_load's job, one layer up),
so a real CSV path plus a real snapshot row is sufficient here.

Requires DATABASE_URL for a database with db/seeds/day4_sources.sql
already applied (needs the real ca_san_jose.building_permits_active
source + cc0_api_2026_08 licence rows). Writes permanent rows (fact,
snapshot, parcel are not immutable in a way that blocks this, and permit
identity rows are namespaced/harmless, same convention as this suite's
siblings).

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_load_permits_attribution.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import csv
import datetime
import hashlib
import os
import sys
import tempfile
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
from ingest_zoning_permits import (  # noqa: E402
    load_permits, SOURCE_ID_PERMITS, LICENCE_ID_PERMITS,
    DETECTOR_KEY_PERMIT_ATTRIBUTION_LOST, DETECTOR_VERSION_PERMIT_ATTRIBUTION_LOST,
)

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


def _write_permits_csv(rows):
    """rows: list of (apn, issue_date_str) or () for an empty (blank-APN-
    only) run. Real header shape, minimal columns load_permits reads."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
    writer = csv.writer(tmp)
    writer.writerow(["ASSESSORS_PARCEL_NUMBER", "ISSUEDATE"])
    for apn, issue_date in rows:
        writer.writerow([apn, issue_date])
    tmp.close()
    return tmp.name


def _make_snapshot(conn, suffix):
    digest = hashlib.sha256(f"test-c2-{suffix}".encode()).hexdigest()
    snapshot_id = f"{SOURCE_ID_PERMITS}:sha256:{digest}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, "
            "byte_size, request, http_status, fetched_at, licence_observed_id) "
            "VALUES (%s, %s, 's3://test-c2/fixture', %s, 'text/csv', 1, "
            "'{}'::jsonb, 200, now(), %s) ON CONFLICT (id) DO NOTHING",
            (snapshot_id, SOURCE_ID_PERMITS, digest, LICENCE_ID_PERMITS),
        )
    conn.commit()
    return snapshot_id, datetime.datetime.now(datetime.timezone.utc)


def _live_permits_active(conn, parcel_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, value, superseded_at FROM fact WHERE parcel_id = %s "
            "AND field_key = 'permits.active' AND source_id = %s ORDER BY recorded_at DESC LIMIT 1",
            (parcel_id, SOURCE_ID_PERMITS),
        )
        return cur.fetchone()


def _exception_outcome(conn, parcel_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT outcome FROM parcel_exception WHERE parcel_id = %s AND detector_key = %s "
            "AND detector_version = %s ORDER BY detected_at DESC LIMIT 1",
            (parcel_id, DETECTOR_KEY_PERMIT_ATTRIBUTION_LOST, DETECTOR_VERSION_PERMIT_ATTRIBUTION_LOST),
        )
        row = cur.fetchone()
    return row[0] if row else None


def main():
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    apn = f"TEST-C2-{suffix}"
    parcel_id = _seed_parcel(conn, apn)
    snap1, retrieved_at1 = _make_snapshot(conn, "run1")

    # Run 1: the permit is present and resolves cleanly -- establishes a
    # live permits.active=true fact. load_permits() closes its OWN
    # connection when it returns (same contract as load_zoning) -- a fresh
    # get_db() is required before every call, not just the first.
    path1 = _write_permits_csv([(apn, "1/1/2026 12:00:00 AM")])
    load_permits(conn, path1, snap1, retrieved_at1)
    os.unlink(path1)

    conn = get_db()
    row = _live_permits_active(conn, parcel_id)
    check("run 1: permits.active=true fact written", row is not None and row[1] is True,
          f"got {row}")
    snap2, retrieved_at2 = _make_snapshot(conn, "run2")

    # Run 2: the SAME permit's APN cell is blank this run (the export's own
    # routine churn -- 6,815 of 17,499 real rows are blank). The old code
    # fabricated a false successor here; the fix must leave the live fact
    # untouched and open a typed exception instead.
    path2 = _write_permits_csv([("", "1/1/2026 12:00:00 AM")])  # blank APN row only
    load_permits(conn, path2, snap2, retrieved_at2)
    os.unlink(path2)

    conn = get_db()
    row_after_absence = _live_permits_active(conn, parcel_id)
    check("run 2: the TRUE fact from run 1 SURVIVES (no fabricated false successor)",
          row_after_absence is not None
          and row_after_absence[0] == row[0]
          and row_after_absence[1] is True
          and row_after_absence[2] is None,
          f"got {row_after_absence} (run 1 was {row})")
    check("run 2: a permit_attribution_lost exception was opened",
          _exception_outcome(conn, parcel_id) == "open",
          f"got outcome={_exception_outcome(conn, parcel_id)!r}")
    snap3, retrieved_at3 = _make_snapshot(conn, "run3")

    # Run 3: the permit reappears, cleanly attributable again -- the
    # exception should close.
    path3 = _write_permits_csv([(apn, "1/1/2026 12:00:00 AM")])
    load_permits(conn, path3, snap3, retrieved_at3)
    os.unlink(path3)

    conn = get_db()
    check("run 3: permit_attribution_lost exception CLOSED once re-attributed",
          _exception_outcome(conn, parcel_id) == "condition_cleared",
          f"got outcome={_exception_outcome(conn, parcel_id)!r}")

    conn.close()
    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
