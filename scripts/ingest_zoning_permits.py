#!/usr/bin/env python3
"""Second and third ingestions: zoning_districts and building_permits_active.

A SEPARATE script from scripts/ingest_parcels.py, not a shared module --
core/connectors doesn't exist yet and module boundaries should be
extracted from three working ingests, not designed after one (this is
the second and third). The plumbing below is COPIED from
ingest_parcels.py, not imported, deliberately: fetch_and_hash,
start_job_run/fail_job_run/finish_job_run, the snapshot exists/insert/
dedupe-proof pattern inside run_one_fetch, the execute_values +
client-generated-UUID batch-insert shape, is_blank, and the
_decimal_default/geojson_geom_param pair for GeoJSON coordinates. That
list is the real input for what core/connectors eventually factors out;
recording it here rather than reconstructing it later.

Two sources, deliberately different join shapes -- see the parcel
identity diagnostic and this ingest's own design report for the
evidence each decision below rests on:

  ZONING (GeoJSON, like parcels -- tests whether the ingest SHAPE
  generalises). zoning_districts has NO parcel identifier at all
  (properties: ZONING, ZONINGABBREV, FACILITYID, INTID, OBJECTID,
  PDDENSITY, PDUSE, REZONINGFILE, APPROVALDATE, COLORCODE, NOTES) --
  it is a geometric overlay, not a keyed dataset. Matched by spatial
  containment: parcel.centroid (declared since 0004, GiST-indexed,
  never populated until this ingest -- Phase E never set it) inside a
  zoning district polygon (ST_Contains(zoning.geom, parcel.centroid)).
  Point-in-polygon, not polygon-polygon: a full-geometry ST_Intersects
  fallback was tried and rejected -- it crashed outright on real data
  (GEOS: Invalid number of points in LinearRing found 3), because 28 of
  225,042 parcels and 4 of 13,691 zoning polygons have invalid
  (self-intersecting) geometry, a real source data-quality property,
  not a parsing bug. Point-in-polygon containment against a POINT
  doesn't invoke that code path and completed cleanly. Zero-match and
  multi-match parcels (measured for real: 10,138 zero, 12 multi, out of
  225,042) get a coverage_gap parcel_exception instead of a fact --
  they DO have an existing parcel row to attach to, unlike permits'
  unmatched case below, so the 0034 pattern applies directly.

  PERMITS (CSV -- tests whether the ingest SHAPE survives a genuinely
  different parse path). Matched by exact string equality on
  ASSESSORS_PARCEL_NUMBER against parcel.apn. Measured for real against
  17,499 permit rows: 6,815 have a blank APN, 2,359 have a non-blank
  APN matching no loaded parcel, 3 match a duplicated parcel APN (2-3
  candidate parcels -- ambiguous, not attributable without fabricating
  precision the parcel identity diagnostic already showed isn't there),
  8,322 match exactly one parcel cleanly. 52.4% of rows do not resolve
  to a single parcel -- the first operational consequence of the APN
  findings. Structural asymmetry from zoning's unmatched case: an
  unmatched PERMIT ROW usually has no parcel to attach a
  parcel_exception to at all (parcel_exception.parcel_id is NOT NULL) --
  not a choice, a consequence of the schema. Disposition is
  job_run.rows_in (all rows read) vs. rows_out (rows that contributed a
  fact); the gap is self-documenting the same way Phase E's already is,
  no new schema. Console output additionally breaks the gap into
  blank / not-found / ambiguous by exact count.

  Every row in the source file already carries Status='Active' (the
  file is the city's own pre-filtered "active permits" export), so
  permits.active=true is constant for any parcel this ingest matches at
  all; permits.series_earliest = MIN(ISSUEDATE) among that parcel's
  matched rows. First exercise of value_type='boolean' (native JSON
  true) and value_type='date' (ISO date string) for a fact.value -- no
  prior precedent in this codebase for either encoding; this ingest
  sets it.

No schema changes. parcel.centroid is populated by UPDATE (data, not
DDL) as a prerequisite for the zoning spatial join, using an index
(parcel_centroid_gix) that has existed since 0004 and was simply never
populated before. The zoning polygon staging table is a session-scoped
TEMP TABLE -- never part of db/schema.sql, never a migration.

DATABASE_URL and OBJECT_STORE_* follow ingest_parcels.py's own
convention: process environment first, .env only as fallback.
"""
import argparse
import csv
import datetime
import decimal
import hashlib
import json
import os
import resource
import sys
import time
import uuid

import boto3
import ijson
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

JURISDICTION_ID = "ca_san_jose"

SOURCE_ID_ZONING = "ca_san_jose.zoning_districts"
LICENCE_ID_ZONING = "cc_by_4_0"
ENDPOINT_URL_ZONING = (
    "https://gisdata-csj.opendata.arcgis.com/api/download/v1/items/"
    "adf17ae739214787ad42945c5f72ccd8/geojson?layers=401"
)

SOURCE_ID_PERMITS = "ca_san_jose.building_permits_active"
LICENCE_ID_PERMITS = "cc0"
ENDPOINT_URL_PERMITS = (
    "https://data.sanjoseca.gov/dataset/fd9ceb0c-75e0-402e-9fe3-3f6e04f2c23f/"
    "resource/761b7ae8-3be1-4ad6-923d-c7af6404a904/download/buildingpermitsactive.csv"
)

SCRATCHPAD = "/private/tmp/claude-501/-Users-dev-Desktop-ledgex-adu/59865388-e258-4aba-b756-014d02490b5a/scratchpad"

CHUNK_SIZE = 8 * 1024 * 1024

FACT_CONFIDENCE = "high"
FACT_CONFIDENCE_RULE_ID = "bulk_direct_from_assessor_gis"
FACT_PACK_VERSION = "v1.0"

DETECTOR_KEY_ZONING_UNRESOLVABLE = "zoning_spatial_join_unresolvable"
DETECTOR_VERSION_ZONING_UNRESOLVABLE = "1.0"


# ---------------------------------------------------------------------------
# COPIED from ingest_parcels.py (see module docstring for the full list and
# why it is copied, not imported).
# ---------------------------------------------------------------------------

def env(name):
    load_dotenv(override=False)
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"missing required environment variable: {name}")
    return val


def get_db():
    conn = psycopg2.connect(env("DATABASE_URL"))
    conn.autocommit = False
    return conn


def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=env("OBJECT_STORE_URL"),
        aws_access_key_id=env("OBJECT_STORE_ACCESS_KEY"),
        aws_secret_access_key=env("OBJECT_STORE_SECRET_KEY"),
    )


def object_key(digest):
    return f"sha256/{digest[:2]}/{digest}"


def object_uri(bucket, digest):
    return f"s3://{bucket}/{object_key(digest)}"


def snapshot_id_for(source_id, digest):
    return f"{source_id}:sha256:{digest}"


def is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def _decimal_default(o):
    if isinstance(o, decimal.Decimal):
        return float(o)
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def geojson_geom_param(geom):
    return json.dumps(geom, default=_decimal_default)


def start_job_run(conn, job_key, source_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO job_run (job_key, jurisdiction_id, source_id, status)
            VALUES (%s, %s, %s, 'running')
            RETURNING id
            """,
            (job_key, JURISDICTION_ID, source_id),
        )
        job_run_id = cur.fetchone()[0]
    conn.commit()
    print(f"  job_run started: {job_run_id}")
    return job_run_id


def fail_job_run(conn, job_run_id, error):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE job_run SET status = 'failed', finished_at = clock_timestamp(), error = %s WHERE id = %s",
            (str(error), job_run_id),
        )
    conn.commit()


def finish_job_run(conn, job_run_id, status, snapshot_id, rows_in=None, rows_out=None, schema_drift=None):
    # clock_timestamp(), not now() -- see ingest_parcels.py's
    # finish_job_run_full for the full story: now() returns the current
    # TRANSACTION's start time, not the time this statement executes, and
    # is silently wrong whenever meaningful work happens earlier in the
    # same transaction (exactly the load phases below).
    #
    # schema_drift is stretched by load_permits() to carry the unmatched
    # breakdown (blank/not-found/ambiguous), not schema drift in its
    # literal sense (0012: "fields expected but missing"). See that call
    # site for the reasoning -- recorded there, not assumed obvious here.
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE job_run
            SET status = %s, finished_at = clock_timestamp(), snapshot_id = %s,
                rows_in = %s, rows_out = %s, schema_drift = %s
            WHERE id = %s
            """,
            (status, snapshot_id, rows_in, rows_out,
             json.dumps(schema_drift) if schema_drift is not None else None, job_run_id),
        )
    conn.commit()


def fetch_and_hash(dest_path, url):
    """GET url, following redirects, streaming to dest_path while hashing
    incrementally. Same C7 policy as ingest_parcels.py: does not
    raise_for_status(); a non-2xx response is snapshotted anyway.
    Returns (digest, byte_size, media_type, http_status, fetched_at)."""
    hasher = hashlib.sha256()
    byte_size = 0
    with requests.get(url, stream=True, allow_redirects=True, timeout=300) as resp:
        http_status = resp.status_code
        media_type = resp.headers.get("Content-Type", "").split(";")[0].strip() or "application/octet-stream"
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                f.write(chunk)
                hasher.update(chunk)
                byte_size += len(chunk)
    fetched_at = datetime.datetime.now(datetime.timezone.utc)
    digest = hasher.hexdigest()
    return digest, byte_size, media_type, http_status, fetched_at


def snapshot_exists(conn, sid):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM snapshot WHERE id = %s", (sid,))
        return cur.fetchone() is not None


def upload_and_verify(s3, bucket, path, digest, byte_size):
    key = object_key(digest)
    s3.upload_file(path, bucket, key)
    head = s3.head_object(Bucket=bucket, Key=key)
    if head["ContentLength"] != byte_size:
        raise RuntimeError(f"uploaded object size {head['ContentLength']} != computed byte_size {byte_size}")
    obj = s3.get_object(Bucket=bucket, Key=key)
    verify_hasher = hashlib.sha256()
    for chunk in obj["Body"].iter_chunks(chunk_size=CHUNK_SIZE):
        verify_hasher.update(chunk)
    if verify_hasher.hexdigest() != digest:
        raise RuntimeError(f"uploaded object hash {verify_hasher.hexdigest()} != computed digest {digest}")
    return key


def insert_snapshot(conn, source_id, digest, byte_size, media_type, http_status, fetched_at, bucket, url, licence_id):
    sid = snapshot_id_for(source_id, digest)
    uri = object_uri(bucket, digest)
    request_payload = json.dumps({"url": url, "method": "GET", "params": {}})
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO snapshot (
                id, source_id, object_uri, content_hash, media_type, byte_size,
                request, http_status, fetched_at, licence_observed_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
            (sid, source_id, uri, digest, media_type, byte_size, request_payload, http_status, fetched_at, licence_id),
        )
    conn.commit()
    return sid


def run_one_fetch(conn, s3, bucket, dest_path, label, source_id, url, licence_id, job_key):
    """One full job_run: fetch, hash, always record a snapshot (C7)."""
    print(f"\n--- {label} ---")
    job_run_id = start_job_run(conn, job_key, source_id)
    try:
        t0 = time.monotonic()
        digest, byte_size, media_type, http_status, fetched_at = fetch_and_hash(dest_path, url)
        elapsed = time.monotonic() - t0
        ok = 200 <= http_status < 300
        print(f"  fetched {byte_size:,} bytes in {elapsed:.1f}s, media_type={media_type}, http_status={http_status}"
              + ("" if ok else " (non-2xx -- snapshotting anyway per C7)"))
        print(f"  sha256: {digest}")

        sid = snapshot_id_for(source_id, digest)
        already_had_snapshot = snapshot_exists(conn, sid)
        if already_had_snapshot:
            print(f"  snapshot {sid} already exists -- content unchanged, skipping upload")
        else:
            key = upload_and_verify(s3, bucket, dest_path, digest, byte_size)
            print(f"  uploaded and verified at key: {key}")
            sid = insert_snapshot(conn, source_id, digest, byte_size, media_type, http_status, fetched_at, bucket, url, licence_id)
            print(f"  snapshot inserted: {sid}")

        status = "failed" if not ok else ("skipped_unchanged" if already_had_snapshot else "succeeded")
        finish_job_run(conn, job_run_id, status, sid)
        print(f"  job_run {job_run_id} -> {status}")
        return digest, sid
    except Exception as e:
        fail_job_run(conn, job_run_id, e)
        print(f"  job_run {job_run_id} -> failed: {e}")
        raise


def phase_b(source_id, url, path1, path2, label_prefix, licence_id, job_key):
    conn = get_db()
    s3 = get_s3()
    bucket = env("OBJECT_STORE_BUCKET")
    digest1, sid1 = run_one_fetch(conn, s3, bucket, path1, f"{label_prefix} FETCH 1 (first ingest)", source_id, url, licence_id, job_key)
    digest2, sid2 = run_one_fetch(conn, s3, bucket, path2, f"{label_prefix} FETCH 2 (dedupe proof)", source_id, url, licence_id, job_key)
    print(f"\n=== {label_prefix} PHASE B SUMMARY ===")
    print(f"digests match: {digest1 == digest2}")
    conn.close()


def latest_snapshot(conn, source_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, fetched_at FROM snapshot WHERE source_id = %s ORDER BY fetched_at DESC LIMIT 1",
            (source_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise SystemExit(f"no snapshot found for {source_id} -- run --phase b first")
        return row[0], row[1]


# ---------------------------------------------------------------------------
# ZONING -- spatial join. See module docstring for the design.
# ---------------------------------------------------------------------------

def load_zoning(conn, path, snapshot_id, retrieved_at):
    """One transaction for the entire load, same discipline as Phase E:
    any failure rolls back everything. rows_in/rows_out are PARCELS
    attempted/classified, not zoning features read -- this is a
    classification job over the parcel set, not a per-feature load."""
    job_run_id = start_job_run(conn, "ingest_zoning", SOURCE_ID_ZONING)

    try:
        t0 = time.monotonic()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TEMP TABLE zoning_staging (
                    id serial PRIMARY KEY,
                    zoning text,
                    zoning_verbatim text,
                    geom geometry(MultiPolygon, 4326)
                )
            """)

        rows = []
        with open(path, "rb") as f:
            for feat in ijson.items(f, "features.item"):
                props = feat.get("properties") or {}
                rows.append((
                    props.get("ZONING"), props.get("ZONINGABBREV"),
                    geojson_geom_param(feat["geometry"]),
                ))
        print(f"  parsed {len(rows):,} zoning features in {time.monotonic()-t0:.1f}s")

        with conn.cursor() as cur:
            # ST_MakeValid at load time -- one-time cost over 13,691 rows,
            # not a per-pair cost. 4 of these polygons are self-intersecting
            # in the raw source; defends the join below without ever
            # touching parcel geometry (point-in-polygon doesn't need it).
            # ST_CollectionExtract(_, 3), found for real, not by inspection:
            # ST_MakeValid on a badly self-intersecting polygon does not
            # reliably return a (Multi)Polygon -- for a severe enough
            # self-intersection it returns a GeometryCollection mixing
            # point/line/polygon parts, which INSERT then rejects outright
            # ("Geometry type (GeometryCollection) does not match column
            # type (MultiPolygon)"). ST_CollectionExtract(geom, 3) keeps
            # only the polygonal parts of whatever ST_MakeValid produced;
            # ST_Multi guarantees the column's declared type regardless of
            # whether that leaves one polygon or several.
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO zoning_staging (zoning, zoning_verbatim, geom) VALUES %s",
                rows,
                template="(%s, %s, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3)))",
                page_size=2000,
            )
            cur.execute("CREATE INDEX ON zoning_staging USING gist (geom)")

            # Prerequisite: populate parcel.centroid. Data, not DDL -- the
            # column and its GiST index (parcel_centroid_gix) have existed
            # since 0004 and were simply never populated before this.
            cur.execute("UPDATE parcel SET centroid = ST_Centroid(geom) WHERE geom IS NOT NULL AND centroid IS NULL")
            print(f"  parcel.centroid populated for {cur.rowcount:,} rows newly")

            t_join_start = time.monotonic()
            cur.execute("""
                SELECT p.id, z.zoning, z.zoning_verbatim, n
                FROM parcel p
                JOIN LATERAL (
                    SELECT z2.zoning, z2.zoning_verbatim, count(*) OVER () AS n
                    FROM zoning_staging z2
                    WHERE ST_Contains(z2.geom, p.centroid)
                ) z ON true
                WHERE p.centroid IS NOT NULL
            """)
            join_rows = cur.fetchall()
            print(f"  spatial join: {len(join_rows):,} (parcel, candidate zoning) pairs in {time.monotonic()-t_join_start:.1f}s")

        matched = {}   # parcel_id -> (zoning, zoning_verbatim)
        ambiguous = set()
        for parcel_id, zoning, zoning_verbatim, n in join_rows:
            if n > 1:
                ambiguous.add(parcel_id)
            else:
                matched[parcel_id] = (zoning, zoning_verbatim)

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM parcel WHERE centroid IS NOT NULL")
            all_parcel_ids = {r[0] for r in cur.fetchall()}
        zero_match = all_parcel_ids - matched.keys() - ambiguous

        print(f"  matched (exactly one district): {len(matched):,}")
        print(f"  zero-match: {len(zero_match):,}")
        print(f"  ambiguous (multiple districts): {len(ambiguous):,}")

        fact_rows = []
        for parcel_id, (zoning, zoning_verbatim) in matched.items():
            fact_rows.append((
                parcel_id, JURISDICTION_ID, "zoning.district", json.dumps(zoning), "bulk",
                SOURCE_ID_ZONING, snapshot_id, retrieved_at, ENDPOINT_URL_ZONING,
                LICENCE_ID_ZONING, FACT_CONFIDENCE, FACT_CONFIDENCE_RULE_ID,
                retrieved_at, FACT_PACK_VERSION,
            ))
            fact_rows.append((
                parcel_id, JURISDICTION_ID, "zoning.district_verbatim", json.dumps(zoning_verbatim), "bulk",
                SOURCE_ID_ZONING, snapshot_id, retrieved_at, ENDPOINT_URL_ZONING,
                LICENCE_ID_ZONING, FACT_CONFIDENCE, FACT_CONFIDENCE_RULE_ID,
                retrieved_at, FACT_PACK_VERSION,
            ))

        exception_rows = []
        for parcel_id in zero_match:
            exception_rows.append((
                parcel_id, JURISDICTION_ID, "coverage_gap", "info",
                DETECTOR_KEY_ZONING_UNRESOLVABLE, DETECTOR_VERSION_ZONING_UNRESOLVABLE,
                json.dumps({"reason": "no_containing_district"}),
            ))
        for parcel_id in ambiguous:
            exception_rows.append((
                parcel_id, JURISDICTION_ID, "coverage_gap", "info",
                DETECTOR_KEY_ZONING_UNRESOLVABLE, DETECTOR_VERSION_ZONING_UNRESOLVABLE,
                json.dumps({"reason": "multiple_containing_districts"}),
            ))

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO fact (
                    parcel_id, jurisdiction_id, field_key, value, method,
                    source_id, snapshot_id, retrieved_at, source_url,
                    licence_id, confidence, confidence_rule_id,
                    effective_from, pack_version
                ) VALUES %s
                """,
                fact_rows,
                template="(%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                page_size=2000,
            )
            print(f"  fact rows submitted: {len(fact_rows):,}")

            if exception_rows:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO parcel_exception (
                        parcel_id, jurisdiction_id, type, severity,
                        detector_key, detector_version, detail
                    ) VALUES %s
                    """,
                    exception_rows,
                    template="(%s, %s, %s, %s, %s, %s, %s::jsonb)",
                    page_size=2000,
                )
                print(f"  parcel_exception rows submitted: {len(exception_rows):,}")

        rows_in = len(all_parcel_ids)
        rows_out = len(matched)
        finish_job_run(conn, job_run_id, "succeeded", snapshot_id, rows_in, rows_out)
        print(f"\njob_run {job_run_id} -> succeeded (rows_in={rows_in:,}, rows_out={rows_out:,})")

    except Exception as e:
        conn.rollback()
        fail_job_run(conn, job_run_id, e)
        print(f"\njob_run {job_run_id} -> failed: {e}")
        raise

    conn.close()


def phase_zoning_load():
    conn = get_db()
    snapshot_id, retrieved_at = latest_snapshot(conn, SOURCE_ID_ZONING)
    print(f"using snapshot: {snapshot_id}")
    path = os.path.join(SCRATCHPAD, "zoning_districts_fetch_1.geojson")
    load_zoning(conn, path, snapshot_id, retrieved_at)


# ---------------------------------------------------------------------------
# PERMITS -- APN string join + per-parcel aggregation. See module
# docstring for the design and the measured unmatched breakdown.
# ---------------------------------------------------------------------------

def parse_issue_date(s):
    """'7/7/2026 12:00:00 AM' -> date(2026, 7, 7). ISSUEDATE is never
    blank in the real file (confirmed before writing this), so no
    blank-handling branch here -- if that assumption is ever wrong, this
    raises and the whole load rolls back, which is correct: silently
    treating a missing date as "no date" would misrepresent it as
    genuinely absent rather than a parse failure."""
    dt = datetime.datetime.strptime(s.strip(), "%m/%d/%Y %I:%M:%S %p")
    return dt.date()


def load_permits(conn, path, snapshot_id, retrieved_at):
    job_run_id = start_job_run(conn, "ingest_permits", SOURCE_ID_PERMITS)

    try:
        t0 = time.monotonic()
        by_apn = {}   # apn -> list of date
        rows_in = 0
        blank_apn = 0
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                rows_in += 1
                apn = (row.get("ASSESSORS_PARCEL_NUMBER") or "").strip()
                if is_blank(apn):
                    blank_apn += 1
                    continue
                by_apn.setdefault(apn, []).append(parse_issue_date(row["ISSUEDATE"]))
        print(f"  parsed {rows_in:,} permit rows ({len(by_apn):,} distinct non-blank APNs) in {time.monotonic()-t0:.1f}s")

        with conn.cursor() as cur:
            cur.execute("SELECT apn, id FROM parcel WHERE apn IS NOT NULL")
            parcel_by_apn = {}
            dup_apns = set()
            for apn, pid in cur.fetchall():
                if apn in parcel_by_apn:
                    dup_apns.add(apn)
                parcel_by_apn.setdefault(apn, pid)

        not_found = 0
        ambiguous = 0
        not_found_rows = 0
        ambiguous_rows = 0
        matched_rows = 0
        fact_rows = []
        for apn, dates in by_apn.items():
            n_rows = len(dates)
            if apn in dup_apns:
                ambiguous += 1
                ambiguous_rows += n_rows
                continue
            pid = parcel_by_apn.get(apn)
            if pid is None:
                not_found += 1
                not_found_rows += n_rows
                continue
            matched_rows += n_rows
            earliest = min(dates).isoformat()
            fact_rows.append((
                pid, JURISDICTION_ID, "permits.active", json.dumps(True), "bulk",
                SOURCE_ID_PERMITS, snapshot_id, retrieved_at, ENDPOINT_URL_PERMITS,
                LICENCE_ID_PERMITS, FACT_CONFIDENCE, FACT_CONFIDENCE_RULE_ID,
                retrieved_at, FACT_PACK_VERSION,
            ))
            fact_rows.append((
                pid, JURISDICTION_ID, "permits.series_earliest", json.dumps(earliest), "bulk",
                SOURCE_ID_PERMITS, snapshot_id, retrieved_at, ENDPOINT_URL_PERMITS,
                LICENCE_ID_PERMITS, FACT_CONFIDENCE, FACT_CONFIDENCE_RULE_ID,
                retrieved_at, FACT_PACK_VERSION,
            ))

        print(f"  blank APN: {blank_apn:,} rows")
        print(f"  not-found APN: {not_found:,} distinct ({not_found_rows:,} rows)")
        print(f"  ambiguous (duplicated parcel APN): {ambiguous:,} distinct ({ambiguous_rows:,} rows)")
        print(f"  matched: {len(fact_rows)//2:,} parcels ({matched_rows:,} rows)")
        total_unmatched_rows = blank_apn + not_found_rows + ambiguous_rows
        print(f"  TOTAL UNMATCHED ROWS: {total_unmatched_rows:,} / {rows_in:,} "
              f"({100*total_unmatched_rows/rows_in:.1f}%) -- no parcel to attach a "
              f"parcel_exception to; not silently dropped, just not persisted per-row. "
              f"See rows_in/rows_out AND schema_drift on this job_run for the durable record.")

        # PERSISTING the breakdown, not just printing it: rows_in/rows_out
        # already give the aggregate gap durably, but not the SHAPE of it
        # (blank vs not-found vs ambiguous), and that shape is what a
        # future reader needs to tell "the source stopped populating APN"
        # from "the parcel dataset doesn't cover these" from "APN reuse
        # made this one genuinely unresolvable" apart.
        #
        # job_run has exactly four candidate slots: rows_in, rows_out
        # (both used above), schema_drift jsonb, error text. Considered
        # both remaining options rather than assuming:
        #   - error: wrong on its face. This run is status='succeeded';
        #     using the error column to carry a non-error would misreport
        #     a healthy run as having failed to anyone reading status
        #     alongside a populated error, and the column has no shape
        #     contract beyond "text", so it invites exactly this kind of
        #     misuse for the next thing that wants a slot, too.
        #   - schema_drift jsonb: declared purpose (0012) is "fields
        #     expected but missing" -- a source dropping an expected
        #     COLUMN, not a per-row match outcome. This is a real reach:
        #     the unmatched breakdown is a distribution over ROWS, not a
        #     statement about the SOURCE's schema. Used anyway, because
        #     the hard rule for this pass is no schema changes, and this
        #     is closer to the real thing than error is -- both describe
        #     an anomaly discovered while processing the source, jsonb
        #     with no fixed shape either way. Flagged here, explicitly,
        #     rather than silently treated as the column's real job.
        #
        # The honest long-term answer is job_run needs a general metrics
        # jsonb column (rows_in/rows_out cover exactly one axis -- total
        # attempted vs. total succeeded -- and every ingest job so far has
        # wanted a different SECOND axis: Phase E's blank/placeholder
        # split, zoning's zero/multi-match split, this one's
        # blank/not-found/ambiguous split. A metrics column would hold
        # all of them uniformly instead of each one arguing its way into
        # a column named for something else.) Not added here -- that is a
        # schema change, out of scope for this pass -- reported instead.
        schema_drift = {
            "unmatched_breakdown": {
                "blank_apn_rows": blank_apn,
                "not_found_apn_rows": not_found_rows,
                "not_found_apn_distinct": not_found,
                "ambiguous_apn_rows": ambiguous_rows,
                "ambiguous_apn_distinct": ambiguous,
            },
            "_note": "stretched beyond schema_drift's literal 'fields expected but missing' meaning -- see ingest_zoning_permits.py load_permits() for why",
        }

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO fact (
                    parcel_id, jurisdiction_id, field_key, value, method,
                    source_id, snapshot_id, retrieved_at, source_url,
                    licence_id, confidence, confidence_rule_id,
                    effective_from, pack_version
                ) VALUES %s
                """,
                fact_rows,
                template="(%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                page_size=2000,
            )
            print(f"  fact rows submitted: {len(fact_rows):,}")

        finish_job_run(conn, job_run_id, "succeeded", snapshot_id, rows_in, matched_rows, schema_drift)
        print(f"\njob_run {job_run_id} -> succeeded (rows_in={rows_in:,}, rows_out={matched_rows:,})")

    except Exception as e:
        conn.rollback()
        fail_job_run(conn, job_run_id, e)
        print(f"\njob_run {job_run_id} -> failed: {e}")
        raise

    conn.close()


def phase_permits_load():
    conn = get_db()
    snapshot_id, retrieved_at = latest_snapshot(conn, SOURCE_ID_PERMITS)
    print(f"using snapshot: {snapshot_id}")
    path = os.path.join(SCRATCHPAD, "permits_fetch_1.csv")
    load_permits(conn, path, snapshot_id, retrieved_at)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["zoning", "permits"], required=True)
    parser.add_argument("--phase", choices=["b", "load"], required=True)
    args = parser.parse_args()

    if args.source == "zoning":
        if args.phase == "b":
            path1 = os.path.join(SCRATCHPAD, "zoning_districts_fetch_1.geojson")
            path2 = os.path.join(SCRATCHPAD, "zoning_districts_fetch_2.geojson")
            phase_b(SOURCE_ID_ZONING, ENDPOINT_URL_ZONING, path1, path2, "ZONING", LICENCE_ID_ZONING, "ingest_zoning")
        else:
            phase_zoning_load()
    else:
        if args.phase == "b":
            path1 = os.path.join(SCRATCHPAD, "permits_fetch_1.csv")
            path2 = os.path.join(SCRATCHPAD, "permits_fetch_2.csv")
            phase_b(SOURCE_ID_PERMITS, ENDPOINT_URL_PERMITS, path1, path2, "PERMITS", LICENCE_ID_PERMITS, "ingest_permits")
        else:
            phase_permits_load()
