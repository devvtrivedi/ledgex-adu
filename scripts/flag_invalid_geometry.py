#!/usr/bin/env python3
"""Flag invalid geometry as a measurable exception, not a silent load.

28 parcels and 4 zoning polygons carry self-intersecting geometry.
Loaded and unflagged until now -- discovered only because GEOS crashed
on a full-geometry ST_Intersects attempt during the zoning ingest's own
design pass, not because anything in the schema or the ingest scripts
noticed. This script closes that: it detects both populations and
raises a parcel_exception (type='record_to_ground', I12) for every
affected parcel, so the gap is a stored, queryable row, not tribal
knowledge in a commit message.

A SEPARATE, THIRD script, not added to ingest_parcels.py or
ingest_zoning_permits.py and not a shared module -- core/connectors
still doesn't exist, and this isn't "ingest a new source" the way those
two are; it's a quality-detection pass over data already loaded by
them. Copies the CREATE TEMP TABLE + repair staging approach from
ingest_zoning_permits.py's load_zoning -- because identifying which
parcels were classified by which raw zoning polygon requires redoing
that spatial join; the fact table itself never recorded a back-
reference to the specific zoning polygon that classified a parcel, only
the resulting zoning.district/zoning.district_verbatim VALUES. That is
itself worth naming as a design gap for whenever a real zoning ingest
module gets built: if it needs to answer "which raw feature produced
this fact" after the fact, it needs to persist that reference, because
the value alone doesn't carry it.

The parcel_exception execute_values shape is no longer copied either --
core/exceptions.insert_exceptions now owns it, same function
ingest_parcels.py and ingest_zoning_permits.py call. This file's two
call sites both passed page_size=500, not the 2000 the other two
scripts used -- no comment at either site said why. Preserved exactly
via insert_exceptions' page_size parameter rather than silently
unified to one number; see core/exceptions.py's own docstring.

get_db/env/decimal_default were previously copied from
ingest_parcels.py's pattern; imported from infra/ now instead -- see
infra/__init__.py for why that's not core/.

NOT repaired. ST_MakeValid was used at STAGING-load time for the zoning
side in ingest_zoning_permits.py -- a working copy, thrown away at the
end of that session, never written to any persisted table. Checked
directly for this script, not assumed: parcel.geom is written by
ingest_parcels.py's Phase E as
ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) with no ST_MakeValid
anywhere in that statement or anywhere else Phase E touches parcel.geom
-- grepped scripts/ingest_parcels.py for MakeValid: zero matches. No
repaired geometry has ever reached a stored table. The source published
these shapes; a repaired version would not be the observation anymore.

Two populations, two detector_keys, deliberately different severity:

  PARCEL's own geometry invalid (28 rows) -- severity 'warning'. The
  parcel's own recorded shape is malformed; detector_key
  'parcel_geometry_invalid', detail carries ST_IsValidReason(geom)
  verbatim.

  ZONING polygon invalid (4 rows) -- has no parcel of its own to
  attach to (it is not a parcel; parcel_exception.parcel_id is NOT
  NULL). Report says "where do these go, or nowhere, and why": not
  nowhere. Re-derived the same spatial join ingest_zoning_permits.py
  performed (repair-then-ST_Contains-against-centroid) and found 157
  parcels were classified into a zoning district using ST_MakeValid's
  repaired output for one of these 4 polygons, not their as-published
  shape. Those 157 parcels' OWN geometry is fine -- this is a lesser,
  once-removed concern than the direct case, hence severity 'info' --
  but their zoning.district fact rests on a repaired substitute for an
  invalid source shape, which is exactly the kind of thing a future
  reconstruction or dispute needs to be able to find. detector_key
  'zoning_source_geometry_invalid', detail carries which zoning value
  was assigned and the source polygon's own ST_IsValidReason.

Two job_run rows (parcels checked / zoning polygons checked have
different source_ids and different rows_in denominators; forcing them
into one row would blur which population rows_in/rows_out describes).

No schema changes. One transaction for each of the two exception-
raising passes.
"""
import json
import os
import sys
import time

import ijson
import psycopg2
import psycopg2.extras

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from infra.env import env, get_db  # noqa: E402
from infra.values import decimal_default  # noqa: E402
from core.exceptions import insert_exceptions  # noqa: E402

JURISDICTION_ID = "ca_san_jose"
SOURCE_ID_PARCELS = "ca_san_jose.parcels"
SOURCE_ID_ZONING = "ca_san_jose.zoning_districts"

SCRATCHPAD = "/private/tmp/claude-501/-Users-dev-Desktop-ledgex-adu/59865388-e258-4aba-b756-014d02490b5a/scratchpad"

DETECTOR_KEY_PARCEL_GEOM = "parcel_geometry_invalid"
DETECTOR_KEY_ZONING_SOURCE_GEOM = "zoning_source_geometry_invalid"
DETECTOR_VERSION = "1.0"


def start_job_run(conn, job_key, source_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO job_run (job_key, jurisdiction_id, source_id, status) VALUES (%s, %s, %s, 'running') RETURNING id",
            (job_key, JURISDICTION_ID, source_id),
        )
        job_run_id = cur.fetchone()[0]
    conn.commit()
    print(f"  job_run started: {job_run_id}")
    return job_run_id


def finish_job_run(conn, job_run_id, status, rows_in, rows_out):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE job_run SET status = %s, finished_at = clock_timestamp(), rows_in = %s, rows_out = %s WHERE id = %s",
            (status, rows_in, rows_out, job_run_id),
        )
    conn.commit()


def fail_job_run(conn, job_run_id, error):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE job_run SET status = 'failed', finished_at = clock_timestamp(), error = %s WHERE id = %s",
            (str(error), job_run_id),
        )
    conn.commit()


def flag_parcel_geometry(conn):
    """Direct case: the parcel's own stored geometry fails ST_IsValid."""
    job_run_id = start_job_run(conn, "flag_invalid_geometry_parcels", SOURCE_ID_PARCELS)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM parcel WHERE geom IS NOT NULL")
            rows_in = cur.fetchone()[0]

            cur.execute("""
                SELECT id, jurisdiction_id, ST_IsValidReason(geom) AS reason
                FROM parcel
                WHERE geom IS NOT NULL AND NOT ST_IsValid(geom)
            """)
            invalid = cur.fetchall()
            print(f"  {len(invalid)} parcels with invalid geometry (of {rows_in:,} checked)")

            exception_rows = [
                (pid, jid, "record_to_ground", "warning", DETECTOR_KEY_PARCEL_GEOM, DETECTOR_VERSION,
                 json.dumps({"reason": reason}))
                for pid, jid, reason in invalid
            ]
            if exception_rows:
                insert_exceptions(cur, exception_rows, page_size=500)
                print(f"  parcel_exception rows submitted: {len(exception_rows)}")

        finish_job_run(conn, job_run_id, "succeeded", rows_in, len(exception_rows))
        print(f"  job_run {job_run_id} -> succeeded (rows_in={rows_in:,}, rows_out={len(exception_rows)})")
    except Exception as e:
        conn.rollback()
        fail_job_run(conn, job_run_id, e)
        print(f"  job_run {job_run_id} -> failed: {e}")
        raise


def flag_zoning_source_geometry(conn):
    """Indirect case: a zoning polygon that classified real parcels was
    itself invalid. Re-derives the same repair-then-contains join
    ingest_zoning_permits.py performs, since no persisted reference
    connects a fact back to the raw zoning feature that produced it."""
    job_run_id = start_job_run(conn, "flag_invalid_geometry_zoning", SOURCE_ID_ZONING)
    path = os.path.join(SCRATCHPAD, "zoning_districts_fetch_1.geojson")
    try:
        t0 = time.monotonic()
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE zoning_raw (id serial PRIMARY KEY, zoning text, geom geometry(MultiPolygon, 4326))")

        rows = []
        with open(path, "rb") as f:
            for feat in ijson.items(f, "features.item"):
                props = feat.get("properties") or {}
                rows.append((props.get("ZONING"), json.dumps(feat["geometry"], default=decimal_default)))
        print(f"  parsed {len(rows):,} zoning features in {time.monotonic()-t0:.1f}s")

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO zoning_raw (zoning, geom) VALUES %s",
                rows,
                template="(%s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))",
                page_size=2000,
            )
            rows_in = len(rows)

            cur.execute("SELECT id, zoning, ST_IsValidReason(geom) FROM zoning_raw WHERE NOT ST_IsValid(geom)")
            invalid_zoning = cur.fetchall()
            print(f"  {len(invalid_zoning)} invalid zoning polygons (of {rows_in:,} checked)")

            cur.execute("""
                CREATE TEMP TABLE zoning_repaired AS
                SELECT id, zoning, ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) AS geom
                FROM zoning_raw
            """)
            cur.execute("CREATE INDEX ON zoning_repaired USING gist (geom)")

            invalid_ids = [r[0] for r in invalid_zoning]
            reason_by_id = {r[0]: r[2] for r in invalid_zoning}
            zoning_by_id = {r[0]: r[1] for r in invalid_zoning}

            cur.execute("""
                SELECT z.id, p.id AS parcel_id, p.jurisdiction_id
                FROM zoning_repaired z
                JOIN parcel p ON ST_Contains(z.geom, p.centroid)
                WHERE z.id = ANY(%s)
            """, (invalid_ids,))
            affected = cur.fetchall()
            print(f"  parcels classified via a repaired invalid zoning polygon: {len(affected):,}")

            exception_rows = [
                (parcel_id, jid, "record_to_ground", "info", DETECTOR_KEY_ZONING_SOURCE_GEOM, DETECTOR_VERSION,
                 json.dumps({
                     "zoning_source_reason": reason_by_id[zid],
                     "zoning_value_assigned": zoning_by_id[zid],
                     "note": "parcel's own geometry is valid; its zoning.district fact was derived using ST_MakeValid's repaired copy of an invalid source polygon, not the polygon as published",
                 }))
                for zid, parcel_id, jid in affected
            ]
            if exception_rows:
                insert_exceptions(cur, exception_rows, page_size=500)
                print(f"  parcel_exception rows submitted: {len(exception_rows)}")

        finish_job_run(conn, job_run_id, "succeeded", rows_in, len(exception_rows))
        print(f"  job_run {job_run_id} -> succeeded (rows_in={rows_in:,}, rows_out={len(exception_rows)})")
    except Exception as e:
        conn.rollback()
        fail_job_run(conn, job_run_id, e)
        print(f"  job_run {job_run_id} -> failed: {e}")
        raise


if __name__ == "__main__":
    conn = get_db()
    print("=== flagging invalid parcel geometry ===")
    flag_parcel_geometry(conn)
    conn.close()

    conn = get_db()
    print("\n=== flagging parcels affected by invalid zoning source geometry ===")
    flag_zoning_source_geometry(conn)
    conn.close()
