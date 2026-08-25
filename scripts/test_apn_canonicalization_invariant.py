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
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import ingest_zoning_permits as izp  # noqa: E402 -- module under test, imported, not reimplemented
from infra.env import get_db  # noqa: E402
from infra.values import canonicalize_identifier  # noqa: E402


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


def make_test_parcel(conn, raw_apn):
    """A parcel whose apn is run through the REAL canonicalize_identifier
    (infra/values.py) -- the same function ingest_parcels.py's phase_e
    calls at ingest time -- rather than a hand-typed value the test author
    believes to already be canonical. raw_apn carries the OTHER real
    observed parcels-side artifact (trailing whitespace, per
    canonicalize_identifier's own docstring: 3 of 225,039 real
    ca_san_jose.parcels features), so this test exercises canonicalization
    on BOTH sides of the join it's proving -- parcels-side whitespace,
    permits-side leading apostrophe -- through the one real function,
    instead of bypassing it on the parcels side."""
    stored_apn = canonicalize_identifier(raw_apn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (izp.JURISDICTION_ID, stored_apn),
        )
        parcel_id = cur.fetchone()[0]
    conn.commit()
    return parcel_id, stored_apn


def make_fixture_csv_path(apn_field_value):
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
    tmp.write("ASSESSORS_PARCEL_NUMBER,ISSUEDATE,Status\n")
    tmp.write(f'"{apn_field_value}",1/1/2026 12:00:00 AM,Active\n')
    tmp.close()
    return tmp.name


def run():
    # Ground truth the real identifier both sides must independently
    # arrive back at -- NOT chained through each other's output, so a
    # broken canonicalize_identifier can't cancel itself out by applying
    # identically-wrong logic to both sides (a real risk if the permit
    # side's raw value were derived from the parcel side's stored,
    # already-canonicalized value instead of from this constant).
    apn_clean = "67620002"
    raw_parcel_apn = apn_clean + " "  # real observed artifact: trailing whitespace
    conn = get_db()
    seed_reference_rows(conn)
    parcel_id, apn = make_test_parcel(conn, raw_parcel_apn)
    # The exact real-world defect: a leading apostrophe, the spreadsheet
    # "force text" artifact -- measured for real in
    # ca_san_jose.building_permits_active.csv (1 of 17,499 rows).
    permit_apn_raw = "'" + apn_clean
    path = make_fixture_csv_path(permit_apn_raw)
    print(f"[test] parcel {parcel_id} raw_apn={raw_parcel_apn!r} canonicalized-and-stored apn={apn!r}, "
          f"permit fixture row APN={permit_apn_raw!r}, path={path}")

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
