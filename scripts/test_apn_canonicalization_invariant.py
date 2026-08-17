#!/usr/bin/env python3
"""Invariant test for APN canonicalisation across the parcels/permits join
(Fix 1).

Invariant under test: a permit CSV row whose ASSESSORS_PARCEL_NUMBER
carries a spreadsheet-export leading-apostrophe artifact (e.g.
"'67620002") must still match the parcel whose apn is the clean digit
string ('67620002') -- a real active permit must not be silently dropped
because of a formatting artifact neither side previously normalized.

Runs the REAL scripts/ingest_zoning_permits.py load_permits() end to end
against a real database -- real CSV parse, real matching, real fact
inserts. The permit source is a tiny, synthetic, one-row CSV reproducing
the exact real-world defect found in
ca_san_jose.building_permits_active.csv (1 of 17,499 rows: "'67620002")
-- not a mock of load_permits' matching logic, a real file it parses
itself.

Requires DATABASE_URL for a scratch database (this test commits real fact
rows; 0017 forbids deleting them, so use a disposable database, never a
shared one).

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_apn_canonicalization_invariant.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import datetime
import os
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import ingest_zoning_permits as izp  # noqa: E402 -- module under test, imported, not reimplemented
from infra.env import get_db  # noqa: E402


def seed_reference_rows(conn):
    with conn.cursor() as cur:
        cur.execute(
            # observed_at/cleared_by/cleared_at match db/seeds/day4_sources.sql's own
            # values exactly (not now()/'test'/now()) -- see _p5_setup.py's identical
            # comment: counsel/owner sign-off is genuinely still Pending, and this
            # insert must not fabricate it on whatever database it first reaches.
            """
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, observed_at, cleared_by, cleared_at)
            VALUES (%s, 'CC0', 'open', 'allowed', 'allowed', NULL,
                    '2026-07-31'::timestamptz, NULL, NULL)
            ON CONFLICT (id) DO NOTHING
            """,
            (izp.LICENCE_ID_PERMITS,),
        )
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES (%s, 'City of San Jose', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """,
            (izp.JURISDICTION_ID,),
        )
        cur.execute(
            """
            INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status,
                                 phase_status_reason, endpoint_url, licence_id, active)
            VALUES (%s, %s, 'Building permits active', 'City of San Jose', 'bulk', 'active', 'test fixture',
                    %s, %s, false)
            ON CONFLICT (id) DO NOTHING
            """,
            (izp.SOURCE_ID_PERMITS, izp.JURISDICTION_ID, izp.ENDPOINT_URL_PERMITS, izp.LICENCE_ID_PERMITS),
        )
        cur.execute(
            """
            INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description)
            VALUES
              ('permits.active', 'Active permit', 'public_record', 'boolean', 'permits', 'Has an active permit'),
              ('permits.series_earliest', 'Earliest active permit date', 'public_record', 'date', 'permits', 'Earliest issue date')
            ON CONFLICT (field_key) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size,
                                   request, http_status, fetched_at, licence_observed_id)
            VALUES (%s, %s, 's3://test/fixture', %s, 'text/csv', 1,
                    '{}'::jsonb, 200, now(), %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (izp.snapshot_id_for(izp.SOURCE_ID_PERMITS, "1" * 64), izp.SOURCE_ID_PERMITS, "1" * 64, izp.LICENCE_ID_PERMITS),
        )
    conn.commit()


def make_test_parcel(conn, apn):
    """A parcel whose apn is the CLEAN digit string -- what phase_e now
    stores after canonicalization (Fix 1's parcels-side half)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (izp.JURISDICTION_ID, apn),
        )
        parcel_id = cur.fetchone()[0]
    conn.commit()
    return parcel_id


def make_fixture_csv_path(scratchpad, apn_field_value):
    path = os.path.join(scratchpad, f"permits_apn_fixture_{uuid.uuid4().hex}.csv")
    with open(path, "w", newline="") as f:
        f.write("ASSESSORS_PARCEL_NUMBER,ISSUEDATE,Status\n")
        f.write(f'"{apn_field_value}",1/1/2026 12:00:00 AM,Active\n')
    return path


def run():
    scratchpad = "/private/tmp/claude-501/-Users-dev-Desktop-ledgex-adu/59865388-e258-4aba-b756-014d02490b5a/scratchpad"
    os.makedirs(scratchpad, exist_ok=True)

    apn = "67620002"
    conn = get_db()
    seed_reference_rows(conn)
    parcel_id = make_test_parcel(conn, apn)
    # The exact real-world defect: a leading apostrophe, the spreadsheet
    # "force text" artifact -- measured for real in
    # ca_san_jose.building_permits_active.csv (1 of 17,499 rows).
    permit_apn_raw = "'" + apn
    path = make_fixture_csv_path(scratchpad, permit_apn_raw)
    print(f"[test] parcel {parcel_id} apn={apn!r}, permit fixture row APN={permit_apn_raw!r}, path={path}")

    retrieved_at = datetime.datetime.now(datetime.timezone.utc)
    izp.load_permits(conn, path, izp.snapshot_id_for(izp.SOURCE_ID_PERMITS, "1" * 64), retrieved_at)

    check_conn = get_db()
    with check_conn.cursor() as cur:
        cur.execute(
            "SELECT field_key, value FROM fact WHERE parcel_id = %s AND field_key LIKE 'permits.%%' AND superseded_at IS NULL",
            (parcel_id,),
        )
        facts = dict(cur.fetchall())
    check_conn.close()
    conn.close()

    print(f"[test] facts for parcel: {facts}")

    if facts.get("permits.active") is not True:
        print("[test] FAIL:")
        print(f"  - expected fact permits.active=true, got {facts.get('permits.active')!r} -- "
              f"the permit row (APN with a leading apostrophe) was not matched to the parcel "
              f"(APN without one). A real active permit was silently dropped.")
        return 1

    print("[test] PASS: permit APN with a leading apostrophe matched the parcel's clean APN.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
