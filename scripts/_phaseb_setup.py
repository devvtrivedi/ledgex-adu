#!/usr/bin/env python3
"""Self-contained setup for scripts/run_phaseb_acceptance.sh: hashes the
four db/fixtures/phaseb/* files, uploads them to OBJECT_STORE_*, inserts
the minimal reference rows phase_e/load_zoning/load_permits need (licence,
jurisdiction, source, field_definition -- ON CONFLICT DO NOTHING, so this
is safe against a database that already carries db/seeds/day4_sources.sql,
and sufficient against one that doesn't), and inserts the four snapshot
rows. Prints "<A snapshot id> <B snapshot id> <zoning snapshot id>
<permits snapshot id>" on stdout for the calling shell script to capture --
nothing else goes to stdout.

Not meant to be run standalone for its output; import-style reuse isn't
the point here either -- this is runner-glue for one script, kept out of
run_phaseb_acceptance.sh only because doing this in psql heredocs was
unreadable at this size.
"""
import hashlib
import os
import sys

import boto3
import psycopg2

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

    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            -- observed_at/cleared_by/cleared_at match db/seeds/day4_sources.sql's own
            -- values exactly (not now()/'test'/now()) -- see _p5_setup.py's identical
            -- comment for why: counsel/owner sign-off is genuinely still Pending, and
            -- this insert must not fabricate it on whatever database it first reaches.
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, observed_at, cleared_by, cleared_at, notes)
            VALUES
              ('cc_by_4_0', 'CC BY 4.0', 'attribution', 'allowed', 'allowed', 'City of San Jose',
               '2026-07-31'::timestamptz, NULL, NULL, NULL),
              ('cc0', 'CC0', 'open', 'allowed', 'allowed', NULL,
               '2026-07-31'::timestamptz, NULL, NULL, NULL),
              -- P55: see _p5_setup.py's identical comment -- the real ingest
              -- scripts this run shells out to now write facts citing these
              -- ids. notes carries the same SUCCESSION mitigation (P55 §12.6).
              -- Corrected (P60-2): this comment previously claimed the OLD
              -- 'cc_by_4_0' row above stays specifically for this script's
              -- own hand-written reconciliation-test INSERT (finding #21,
              -- run_phaseb_acceptance.sh) -- that INSERT plants a fact citing
              -- a real ca_san_jose.zoning_districts snapshot, and the real
              -- ingest now registers every such snapshot under
              -- 'cc_by_4_0_api_2026_08' (P55), so fact_snapshot_licence_fk
              -- (a composite FK on snapshot(id, licence_id)) rejected the old
              -- literal outright -- first observed when db.yml's
              -- phaseb-acceptance job ran in CI for the first time ever
              -- (P60-1). The INSERT was repointed to 'cc_by_4_0_api_2026_08'
              -- to match; the plain 'cc_by_4_0' row above is no longer read
              -- by anything in this script and is kept only as a harmless,
              -- pre-existing licence row (not a load-bearing fixture value).
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
            INSERT INTO source (id, jurisdiction_id, display_name, steward, steward_class, method, phase_status,
                                 phase_status_reason, endpoint_url, licence_id, active)
            VALUES
              ('ca_san_jose.parcels', 'ca_san_jose', 'Parcels', 'City of San Jose', 'governmental', 'bulk', 'active',
               'Phase B acceptance run', 'https://example.com/parcels', 'cc_by_4_0_api_2026_08', false),
              ('ca_san_jose.zoning_districts', 'ca_san_jose', 'Zoning', 'City of San Jose', 'governmental', 'bulk', 'active',
               'Phase B acceptance run', 'https://example.com/zoning', 'cc_by_4_0_api_2026_08', false),
              ('ca_san_jose.building_permits_active', 'ca_san_jose', 'Permits', 'City of San Jose', 'governmental', 'bulk', 'active',
               'Phase B acceptance run', 'https://example.com/permits', 'cc0_api_2026_08', false)
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

        a_sid = upload_and_snapshot(cur, s3, bucket, f"{fixtures_dir}/phaseb_A.geojson",
                                     "ca_san_jose.parcels", "cc_by_4_0_api_2026_08", "application/geo+json")
        b_sid = upload_and_snapshot(cur, s3, bucket, f"{fixtures_dir}/phaseb_B.geojson",
                                     "ca_san_jose.parcels", "cc_by_4_0_api_2026_08", "application/geo+json")
        zoning_sid = upload_and_snapshot(cur, s3, bucket, f"{fixtures_dir}/phaseb_zoning.geojson",
                                          "ca_san_jose.zoning_districts", "cc_by_4_0_api_2026_08", "application/geo+json")
        permits_sid = upload_and_snapshot(cur, s3, bucket, f"{fixtures_dir}/phaseb_permits.csv",
                                           "ca_san_jose.building_permits_active", "cc0_api_2026_08", "text/csv")

    conn.commit()
    conn.close()
    # P45 Fix 3: phase_zoning_load/phase_permits_load now require an
    # explicit --snapshot-id (no more guess-the-newest) -- the calling
    # shell script needs these two ids too, not just parcels' a_sid/b_sid.
    print(f"{a_sid} {b_sid} {zoning_sid} {permits_sid}")


if __name__ == "__main__":
    main()
