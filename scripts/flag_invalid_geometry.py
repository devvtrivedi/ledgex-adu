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

P59 (C4, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): this script is now wired
into `make flag-invalid-geometry` and db.yml (after the day4 seed step --
start_job_run() needs the real source rows). Migration 0057 added
`parcel.geom_valid boolean GENERATED ALWAYS AS (ST_IsValid(geom)) STORED`
plus a partial GiST index `parcel_geom_valid_gix ON parcel USING gist
(geom) WHERE geom_valid` -- the per-parcel geometry-quality representation
this file's own exception rows previously had no counterpart for. A
closure path was added too (flag_parcel_geometry now calls the same
core.exceptions.close_exceptions_for_parcels ingest_parcels.py already
uses for the APN detector): a source-side republish with a corrected
shape now closes the exception, rather than leaving it open forever.

READ-TIME POLICY for a future geometry-serving path (no such path exists
yet -- §4 of the audit confirms the API serves no `geom` today; this is
written down for whoever builds it first, so the decision is not
rediscovered under deadline pressure). Repair stays banned AT REST (the
paragraph above, unchanged) AND at read time: reproduced for real against
this pass's own 28 known-invalid parcels, ST_Intersection raises a genuine
GEOS TopologyException on an actual invalid polygon from this database --
repairing it only at render time (ST_MakeValid wrapped around a tile
query) would make the crash go away by rendering a shape the source never
published, in the exact same visual treatment as a genuinely published lot
line. That is I9 (a derived conclusion must never render in the treatment
reserved for a retrieved fact) and it is this audit's own C4 failure
scenario verbatim ("renders a self-intersecting boundary a user takes as a
lot line") with the fabrication merely moved from ingest time to render
time, not removed.

Policy: (1) a geometry-serving query filters `WHERE geom_valid` (NOT
`IS NOT FALSE` -- confirmed by EXPLAIN that only the bare `geom_valid`
spelling matches parcel_geom_valid_gix's own partial-index predicate; the
`IS NOT FALSE` spelling silently falls back to the full geometry index,
which still contains the 28 invalid rows). (2) exclusion must not be
silent: the parcel is not simply dropped from a bbox/feature response --
it is carried as present-but-unrenderable (driven by parcel.geom_valid),
so a caller can render "boundary flagged, not shown" rather than a
same-looking hole where a real address sits. Any visual placeholder
(envelope, centroid marker) must stay visually distinct from a published
lot line (I9) -- left as a map-phase design choice, not decided here. (3)
this reaches beyond tiles: every derived-intelligence computation the map
phase plans (setbacks, buildable envelopes, ADU placement) is
ST_Intersection/ST_Buffer/ST_Difference over parcel.geom, the exact
operation family that crashes. Per I8, any such consumer meeting
geom_valid = false must return a typed refusal, never let a GEOS
exception propagate uncaught; whether an existing §9 code fits or a new
one is needed is a decision for whoever builds that consumer (a new
refusal code is its own spec §9 change + qa_check sync, its own pause
point, not decided here).

SEPARATE, NOT-YET-CATEGORIZED FINDING (recorded, not one of the audit's
44): ST_AsMVTGeom -- the actual MVT tile-serving function, not
ST_Intersection -- does NOT crash on these 28 parcels, but silently
returns NULL for a geometry-dependent subset of them (reproduced: some of
the 28 return a real tile geometry, others NULL, against the same bbox).
NULL from ST_AsMVTGeom is not exclusive to invalid input either (a valid
geometry can also collapse to NULL at low zoom) -- so a future tile path
must treat a NULL result as its own logged, investigated condition, never
silently read it as "no parcel here." See the P59 deliverable's section
(f) for the reproduction transcript and parcel ids.

No schema changes IN THIS FILE (0057 is a separate migration). One
transaction for each of the two exception-raising passes.
"""
import hashlib
import json
import os
import sys
import tempfile
import time

import boto3
import ijson
import psycopg2
import psycopg2.extras

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from infra.env import env, get_db  # noqa: E402
from infra.values import decimal_default  # noqa: E402
from core.model import ParcelException  # noqa: E402
from core.exceptions import insert_exceptions, close_exceptions_for_parcels  # noqa: E402

JURISDICTION_ID = "ca_san_jose"
SOURCE_ID_PARCELS = "ca_san_jose.parcels"
SOURCE_ID_ZONING = "ca_san_jose.zoning_districts"

CHUNK_SIZE = 8 * 1024 * 1024

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


def finish_job_run(conn, job_run_id, status, rows_in, rows_out, metrics=None):
    # metrics (0051, README findings #12/#16): exception_skipped (already-
    # open, deduped, at both call sites below) was printed every run but
    # never persisted.
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE job_run SET status = %s, finished_at = clock_timestamp(), "
            "rows_in = %s, rows_out = %s, metrics = %s WHERE id = %s",
            (status, rows_in, rows_out,
             json.dumps(metrics) if metrics is not None else None, job_run_id),
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


def existing_open_parcels(cur, detector_key, detector_version):
    """P9 (prompts/P9-exception-resolution.md), dedup guard only, not
    closure -- see that file's section 4. Keyed on parcel_id ALONE, not
    (parcel_id, reason) the way load_zoning's existing_open is: neither
    detector below ever writes more than one open exception per parcel per
    run (a parcel's own geometry is valid or it isn't; it is classified via
    one zoning polygon or none), so parcel_id alone is a correct dedup key
    for both -- and it is also the ONLY correct key for
    zoning_source_geometry_invalid specifically, whose detail carries no
    'reason' key at all (zoning_source_reason/zoning_value_assigned/note
    instead). detail->>'reason' evaluates SQL NULL for every one of that
    detector's rows, and NULL never equals NULL in a unique index -- 0045's
    partial unique index silently never fires for it. Confirmed directly
    before writing this: a second real run of flag_zoning_source_geometry
    against unchanged data did not raise UniqueViolation the way
    flag_parcel_geometry does -- it silently doubled 157 rows to 314. A
    (parcel_id, reason) key here would not have caught that; parcel_id
    alone does, for both."""
    cur.execute(
        "SELECT parcel_id FROM parcel_exception WHERE detector_key = %s AND detector_version = %s AND outcome = 'open'",
        (detector_key, detector_version),
    )
    return {r[0] for r in cur.fetchall()}


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

            existing_open = existing_open_parcels(cur, DETECTOR_KEY_PARCEL_GEOM, DETECTOR_VERSION)
            invalid_ids = {pid for pid, jid, reason in invalid}
            exception_rows = [
                ParcelException(
                    parcel_id=pid, jurisdiction_id=jid, type="record_to_ground", severity="warning",
                    detector_key=DETECTOR_KEY_PARCEL_GEOM, detector_version=DETECTOR_VERSION,
                    detail={"reason": reason},
                )
                for pid, jid, reason in invalid
                if pid not in existing_open
            ]
            exception_skipped = len(invalid) - len(exception_rows)
            if exception_rows:
                insert_exceptions(cur, exception_rows, page_size=500)
            print(f"  parcel_exception rows submitted: {len(exception_rows)}, "
                  f"{exception_skipped} skipped (already open at this detector_version)")

            # C4 (P59): closure path. A parcel with a currently-open
            # parcel_geometry_invalid exception whose geometry is no longer
            # in the invalid set this run (a source-side republish with a
            # corrected shape, or a parcel_exception left open from a
            # geometry that has since been superseded) is genuinely
            # resolved -- close it via the SAME targeted-close helper
            # ingest_parcels.py already uses for the APN detector
            # (core.exceptions.close_exceptions_for_parcels), not a second
            # hand-rolled UPDATE. Without this, a source-side fix leaves the
            # flag open forever (exactly the audit's own C4 complaint).
            resolved_parcel_ids = existing_open - invalid_ids
            closed_count = close_exceptions_for_parcels(
                cur, DETECTOR_KEY_PARCEL_GEOM, DETECTOR_VERSION, resolved_parcel_ids
            )
            print(f"  parcel_geometry_invalid exceptions closed (condition_cleared): {closed_count}")

        metrics = {
            "exceptions_written": len(exception_rows),
            "exceptions_skipped_already_open": exception_skipped,
            "exceptions_closed": closed_count,
        }
        finish_job_run(conn, job_run_id, "succeeded", rows_in, len(exception_rows), metrics)
        print(f"  job_run {job_run_id} -> succeeded (rows_in={rows_in:,}, rows_out={len(exception_rows)})")
    except Exception as e:
        conn.rollback()
        fail_job_run(conn, job_run_id, e)
        print(f"  job_run {job_run_id} -> failed: {e}")
        raise


def parse_s3_uri(uri):
    """C17 (P59): copied from ingest_zoning_permits.py's own parse_s3_uri
    (itself copied from ingest_parcels.py, P45 Fix 3) -- not imported, same
    reasoning as every other piece of shared plumbing across these scripts:
    core/connectors doesn't exist yet to factor it out for real, and this
    repo's own established convention (three scripts already do this) is a
    deliberate copy, not an inter-script import."""
    from urllib.parse import urlparse
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise RuntimeError(f"snapshot.object_uri is not an s3:// URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=env("OBJECT_STORE_URL"),
        aws_access_key_id=env("OBJECT_STORE_ACCESS_KEY"),
        aws_secret_access_key=env("OBJECT_STORE_SECRET_KEY"),
    )


def verified_snapshot_file(conn, snapshot_id, source_id):
    """C17 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): copied from
    ingest_zoning_permits.py's own verified_snapshot_file, not imported --
    same convention as parse_s3_uri above. This closes register findings
    #46/#47's own class (unverified snapshot bytes) at THIS detection site
    too -- flag_zoning_source_geometry used to open
    SCRATCHPAD/zoning_districts_fetch_1.geojson directly: no snapshot id,
    no hash check against snapshot.content_hash, so a newer fetch
    overwriting that mutable scratch file silently fed this detector
    polygons that never produced the zoning facts it was reasoning about.

    Returns (path, snapshot row dict) for bytes read from
    snapshot.object_uri. The hash is computed over exactly the bytes the
    caller will parse -- raises on a content_hash OR byte_size mismatch,
    before the caller ever touches the bytes."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, source_id, object_uri, content_hash, media_type,
                   byte_size, fetched_at
            FROM snapshot
            WHERE id = %s AND source_id = %s
            """,
            (snapshot_id, source_id),
        )
        snapshot = cur.fetchone()
    if snapshot is None:
        raise SystemExit(f"no snapshot {snapshot_id} found for {source_id}")

    bucket, key = parse_s3_uri(snapshot["object_uri"])
    s3 = get_s3()
    hasher = hashlib.sha256()
    byte_size = 0
    suffix = ".geojson" if snapshot["media_type"] == "application/geo+json" else ".snapshot"
    tmp = tempfile.NamedTemporaryFile(prefix="ledgex-flag-geom-", suffix=suffix, delete=False)
    tmp_path = tmp.name
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        with tmp:
            for chunk in obj["Body"].iter_chunks(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                tmp.write(chunk)
                hasher.update(chunk)
                byte_size += len(chunk)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    digest = hasher.hexdigest()
    if digest != snapshot["content_hash"]:
        os.unlink(tmp_path)
        raise RuntimeError(
            f"snapshot byte hash mismatch for {snapshot_id}: "
            f"object_uri bytes sha256={digest}, snapshot.content_hash={snapshot['content_hash']}"
        )
    if byte_size != snapshot["byte_size"]:
        os.unlink(tmp_path)
        raise RuntimeError(
            f"snapshot byte_size mismatch for {snapshot_id}: "
            f"object_uri bytes={byte_size}, snapshot.byte_size={snapshot['byte_size']}"
        )
    return tmp_path, snapshot


def flag_zoning_source_geometry(conn, snapshot_id):
    """Indirect case: a zoning polygon that classified real parcels was
    itself invalid. Re-derives the same repair-then-contains join
    ingest_zoning_permits.py performs, since no persisted reference
    connects a fact back to the raw zoning feature that produced it."""
    job_run_id = start_job_run(conn, "flag_invalid_geometry_zoning", SOURCE_ID_ZONING)
    # C17 (P59): verified_snapshot_file, not a direct open() of the mutable
    # scratch file -- raises before any bytes are parsed if content_hash or
    # byte_size disagrees with what snapshot_id's own row claims.
    path, snapshot = verified_snapshot_file(conn, snapshot_id, SOURCE_ID_ZONING)
    try:
        t0 = time.monotonic()
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE zoning_raw (id serial PRIMARY KEY, zoning text, geom geometry(MultiPolygon, 4326))")

        rows = []
        with open(path, "rb") as f:
            for feat in ijson.items(f, "features.item"):
                props = feat.get("properties") or {}
                rows.append((props.get("ZONING"), json.dumps(feat["geometry"], default=decimal_default)))
        print(f"  parsed {len(rows):,} zoning features in {time.monotonic()-t0:.1f}s (snapshot_id={snapshot_id})")

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

            # C17 (P59): ST_Contains(z.geom, p.centroid) evaluates SQL NULL,
            # never TRUE, for any parcel whose centroid IS NULL -- silently
            # absent from `affected` above, a false-clean (the same NULL-
            # inside-a-predicate shape as 0038/0045's own history in this
            # repo). Genuinely possible mid-reconcile (a parcel row can
            # exist with geom set and centroid not yet (re)computed -- see
            # C1's own populate_interior_centroids). Reported explicitly
            # here, not silently dropped: a looser ST_Intersects(z.geom,
            # p.geom) test (geometry, not centroid -- centroid doesn't
            # exist to test) over the SAME invalid-zoning-polygon set names
            # every such parcel, even though point-in-polygon classification
            # cannot be determined for them without a centroid.
            cur.execute("""
                SELECT p.id FROM zoning_repaired z
                JOIN parcel p ON p.centroid IS NULL AND p.geom IS NOT NULL
                              AND ST_Intersects(z.geom, p.geom)
                WHERE z.id = ANY(%s)
            """, (invalid_ids,))
            null_centroid_candidates = [r[0] for r in cur.fetchall()]
            print(f"  candidates with NULL centroid near an invalid zoning polygon "
                  f"(EXCLUDED from affected-set above -- cannot determine "
                  f"classification without a centroid): {len(null_centroid_candidates):,}"
                  + (f" -- {null_centroid_candidates}" if null_centroid_candidates else ""))

            existing_open = existing_open_parcels(cur, DETECTOR_KEY_ZONING_SOURCE_GEOM, DETECTOR_VERSION)
            exception_rows = [
                ParcelException(
                    parcel_id=parcel_id, jurisdiction_id=jid, type="record_to_ground", severity="info",
                    detector_key=DETECTOR_KEY_ZONING_SOURCE_GEOM, detector_version=DETECTOR_VERSION,
                    detail={
                        "zoning_source_reason": reason_by_id[zid],
                        "zoning_value_assigned": zoning_by_id[zid],
                        "note": "parcel's own geometry is valid; its zoning.district fact was derived using ST_MakeValid's repaired copy of an invalid source polygon, not the polygon as published",
                    },
                )
                for zid, parcel_id, jid in affected
                if parcel_id not in existing_open
            ]
            exception_skipped = len(affected) - len(exception_rows)
            if exception_rows:
                insert_exceptions(cur, exception_rows, page_size=500)
            print(f"  parcel_exception rows submitted: {len(exception_rows)}, "
                  f"{exception_skipped} skipped (already open at this detector_version)")

        metrics = {
            "exceptions_written": len(exception_rows),
            "exceptions_skipped_already_open": exception_skipped,
        }
        finish_job_run(conn, job_run_id, "succeeded", rows_in, len(exception_rows), metrics)
        print(f"  job_run {job_run_id} -> succeeded (rows_in={rows_in:,}, rows_out={len(exception_rows)})")
    except Exception as e:
        conn.rollback()
        fail_job_run(conn, job_run_id, e)
        print(f"  job_run {job_run_id} -> failed: {e}")
        raise
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


if __name__ == "__main__":
    # C4 (P59): --skip-zoning-source lets CI (db.yml) run the parcel-geometry
    # detector, which needs only the live `parcel` table, without also
    # requiring flag_zoning_source_geometry's own snapshot dependency.
    # Default (no flag) runs both, same as every local invocation to date --
    # but flag_zoning_source_geometry now REQUIRES --snapshot-id (C17): no
    # more silent fallback to a mutable scratch path.
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-zoning-source", action="store_true",
                         help="Run only flag_parcel_geometry (no snapshot dependency); for CI.")
    parser.add_argument("--snapshot-id",
                         help="ca_san_jose.zoning_districts snapshot id for flag_zoning_source_geometry "
                              "(C17: required unless --skip-zoning-source is given -- no fallback to a "
                              "raw scratch-file path).")
    args = parser.parse_args()
    if not args.skip_zoning_source and not args.snapshot_id:
        parser.error("--snapshot-id is required unless --skip-zoning-source is given (C17)")

    conn = get_db()
    print("=== flagging invalid parcel geometry ===")
    flag_parcel_geometry(conn)
    conn.close()

    if not args.skip_zoning_source:
        conn = get_db()
        print("\n=== flagging parcels affected by invalid zoning source geometry ===")
        flag_zoning_source_geometry(conn, args.snapshot_id)
        conn.close()
