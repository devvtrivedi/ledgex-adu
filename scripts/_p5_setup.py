#!/usr/bin/env python3
"""Self-contained setup for scripts/run_p5_acceptance.sh -- same shape as
_phaseb_setup.py (P3), reused rather than duplicated in spirit: hashes the
five db/fixtures/p5/* + db/fixtures/phaseb/phaseb_A.geojson files, uploads
them to OBJECT_STORE_*, inserts the minimal reference rows phase_e/
load_zoning/load_permits need (ON CONFLICT DO NOTHING -- safe against a
database that already carries db/seeds/day4_sources.sql, and sufficient
against one that doesn't), and inserts the snapshot rows.

Prints "<parcels_sid> <zoning_A_sid> <zoning_B_sid> <permits_A_sid>
<permits_B_sid>" on stdout for the calling shell script to capture --
nothing else goes to stdout.
"""
import hashlib
import os
import sys

import boto3

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from infra.env import env, get_db  # noqa: E402


def upload_and_snapshot(cur, s3, bucket, path, source_id, licence_id, media_type):
    data = open(path, "rb").read()
    digest = hashlib.sha256(data).hexdigest()
    key = f"sha256/{digest[:2]}/{digest}"
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=media_type)
    sid = f"{source_id}:sha256:{digest}"
    uri = f"s3://{bucket}/{key}"
    cur.execute(
        """
        INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size,
                               request, http_status, fetched_at, licence_observed_id)
        VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb, 200, now(), %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (sid, source_id, uri, digest, media_type, len(data), licence_id),
    )
    return sid


def main():
    fixtures_dir = sys.argv[1]
    phaseb_fixtures_dir = sys.argv[2]

    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            -- observed_at/cleared_by/cleared_at match db/seeds/day4_sources.sql's own
            -- values exactly (not now()/'test'/now()) -- counsel/owner sign-off is
            -- genuinely still Pending (STANDING-BLOCKER.md), and this insert only ever
            -- fires (ON CONFLICT DO NOTHING) on a database the real seed hasn't reached
            -- yet, so it must assert the same honest position the seed does, not a
            -- fabricated clearance. See CLAUDE.md: an earlier, unnamespaced version of
            -- db/tests/invariants.sql did exactly this and permanently poisoned
            -- ledgex_schema_check.
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, observed_at, cleared_by, cleared_at, notes)
            VALUES
              ('cc_by_4_0', 'CC BY 4.0', 'attribution', 'allowed', 'allowed', 'City of San Jose',
               '2026-07-31'::timestamptz, NULL, NULL, NULL),
              ('cc0', 'CC0', 'open', 'allowed', 'allowed', NULL,
               '2026-07-31'::timestamptz, NULL, NULL, NULL),
              -- P55: the real ingest_parcels.py/ingest_zoning_permits.py this
              -- script's own caller shells out to now write facts citing
              -- these ids (LICENCE_ID/_ZONING/_PERMITS, repointed -- see
              -- prompts/P55-scoped-unblock.md §4.1/§4.5 step 9), so this
              -- disposable database needs them to exist too, or every real
              -- ingest call below raises a foreign_key_violation. notes
              -- carries the same SUCCESSION mitigation (P55 §12.6) as every
              -- other seeder of these ids -- real facts get written here too.
              -- Corrected (P60-2): this comment previously claimed the OLD
              -- rows above stay because run_p5_acceptance.sh's own finding
              -- #21 reconciliation-test INSERT cites them literally by hand
              -- -- that INSERT plants a fact citing a real
              -- ca_san_jose.building_permits_active snapshot, and the real
              -- ingest now registers every such snapshot under
              -- 'cc0_api_2026_08' (P55), so fact_snapshot_licence_fk
              -- rejected the old 'cc0' literal outright -- first observed
              -- when db.yml's p5-acceptance job ran in CI for the first time
              -- ever (P60-1). The INSERT was repointed to 'cc0_api_2026_08';
              -- the plain 'cc_by_4_0'/'cc0' rows above are no longer read by
              -- anything in this script and are kept only as harmless,
              -- pre-existing licence rows (not load-bearing fixture values).
              ('cc_by_4_0_api_2026_08', 'CC BY 4.0 (api channel, scoped 2026-08)',
               'attribution', 'allowed', 'allowed', 'City of San Jose',
               '2026-07-31'::timestamptz, NULL, NULL,
               'SUCCESSION (P55 §12.6): this id did not exist before 2026-08-22 -- minted then '
               'as a scoping decision under CC BY 4.0 terms observed 2026-07-31 (hence '
               'observed_at above, not today). A snapshot row citing this id under an earlier '
               'fetched_at records the terms under which the bytes are used, never that this id '
               'existed at fetch time.'),
              ('cc0_api_2026_08', 'CC0 1.0 (api channel, scoped 2026-08)',
               'open', 'allowed', 'allowed', NULL,
               '2026-07-31'::timestamptz, NULL, NULL,
               'SUCCESSION (P55 §12.6): this id did not exist before 2026-08-22 -- minted then '
               'as a scoping decision under CC0 1.0 terms observed 2026-07-31 (hence observed_at '
               'above, not today). A snapshot row citing this id under an earlier fetched_at '
               'records the terms under which the bytes are used, never that this id existed at '
               'fetch time.')
            ON CONFLICT (id) DO NOTHING
        """)
        cur.execute("""
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES ('ca_san_jose', 'City of San Jose', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
        """)
        cur.execute("""
            INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status,
                                 phase_status_reason, endpoint_url, licence_id, active)
            VALUES
              ('ca_san_jose.parcels', 'ca_san_jose', 'Parcels', 'City of San Jose', 'bulk', 'active',
               'P5 acceptance run', 'https://example.com/parcels', 'cc_by_4_0_api_2026_08', false),
              ('ca_san_jose.zoning_districts', 'ca_san_jose', 'Zoning', 'City of San Jose', 'bulk', 'active',
               'P5 acceptance run', 'https://example.com/zoning', 'cc_by_4_0_api_2026_08', false),
              ('ca_san_jose.building_permits_active', 'ca_san_jose', 'Permits', 'City of San Jose', 'bulk', 'active',
               'P5 acceptance run', 'https://example.com/permits', 'cc0_api_2026_08', false)
            ON CONFLICT (id) DO NOTHING
        """)
        cur.execute("""
            INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description)
            VALUES
              ('parcel.apn', 'APN', 'public_record', 'string', 'parcel', 'Assessor parcel number'),
              ('parcel.geometry', 'Geometry', 'public_record', 'geometry', 'parcel', 'Parcel geometry'),
              ('parcel.source_parcel_id', 'Source parcel id', 'public_record', 'string', 'parcel', 'Source-native feature id'),
              ('zoning.district', 'Zoning district', 'public_record', 'string', 'zoning', 'Zoning classification'),
              ('zoning.district_verbatim', 'Zoning district (verbatim)', 'public_record', 'string', 'zoning', 'Raw source abbreviation'),
              ('permits.active', 'Active permit', 'public_record', 'boolean', 'permits', 'Has an active permit'),
              ('permits.series_earliest', 'Earliest active permit date', 'public_record', 'date', 'permits', 'Earliest issue date')
            ON CONFLICT (field_key) DO NOTHING
        """)

        s3 = boto3.client(
            "s3",
            endpoint_url=env("OBJECT_STORE_URL"),
            aws_access_key_id=env("OBJECT_STORE_ACCESS_KEY"),
            aws_secret_access_key=env("OBJECT_STORE_SECRET_KEY"),
        )
        bucket = env("OBJECT_STORE_BUCKET")

        parcels_sid = upload_and_snapshot(cur, s3, bucket, f"{phaseb_fixtures_dir}/phaseb_A.geojson",
                                           "ca_san_jose.parcels", "cc_by_4_0_api_2026_08", "application/geo+json")
        zoning_a_sid = upload_and_snapshot(cur, s3, bucket, f"{fixtures_dir}/p5_zoning_A.geojson",
                                            "ca_san_jose.zoning_districts", "cc_by_4_0_api_2026_08", "application/geo+json")
        zoning_b_sid = upload_and_snapshot(cur, s3, bucket, f"{fixtures_dir}/p5_zoning_B.geojson",
                                            "ca_san_jose.zoning_districts", "cc_by_4_0_api_2026_08", "application/geo+json")
        permits_a_sid = upload_and_snapshot(cur, s3, bucket, f"{fixtures_dir}/p5_permits_A.csv",
                                             "ca_san_jose.building_permits_active", "cc0_api_2026_08", "text/csv")
        permits_b_sid = upload_and_snapshot(cur, s3, bucket, f"{fixtures_dir}/p5_permits_B.csv",
                                             "ca_san_jose.building_permits_active", "cc0_api_2026_08", "text/csv")

    conn.commit()
    conn.close()
    print(f"{parcels_sid} {zoning_a_sid} {zoning_b_sid} {permits_a_sid} {permits_b_sid}")


if __name__ == "__main__":
    main()
