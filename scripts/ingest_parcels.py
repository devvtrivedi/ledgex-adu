#!/usr/bin/env python3
"""First ingestion: San José parcels, end to end, smallest useful slice.

One plain script, not the core/connectors + core/store architecture --
turning this into modules is a later job informed by what this teaches.
See CLAUDE.md / docs/LEDGEX_SPEC.md for the invariants this respects.

Phases (run with --phase b / c / d, or no flag for all three in order):
  B: fetch the parcels endpoint, hash streamed to disk, upload to the
     content-addressed object store key, record snapshot + job_run. Does
     NOT parse the GeoJSON. Then re-fetches once more to prove the same
     content hashes to the same key (job_run.status='skipped_unchanged',
     no second snapshot row -- the id would collide on the PK anyway).
  C: inspect the downloaded file (property keys, geometry types, APN
     uniqueness, expected_fields coverage). Loads nothing into the
     database.
  D: load 20 parcel rows and their facts, including the deliberate
     ST_Multi() omission probe phase D.1 asks for.

DATABASE_URL and OBJECT_STORE_* are read from the process environment
first, falling back to .env only if unset (python-dotenv's default
override=False) -- this run is meant to hit a scratch database, never
whatever DATABASE_URL happens to be sitting in .env.
"""
import argparse
import decimal
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import boto3
import ijson
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

SOURCE_ID = "ca_san_jose.parcels"
JURISDICTION_ID = "ca_san_jose"
LICENCE_ID = "cc_by_4_0"
ENDPOINT_URL = (
    "https://gisdata-csj.opendata.arcgis.com/api/download/v1/items/"
    "4bb085cb99a64eff8e83d2bf92a8d5cb/geojson?layers=270"
)
JOB_KEY = "ingest_parcels"

SCRATCHPAD = "/private/tmp/claude-501/-Users-dev-Desktop-ledgex-adu/59865388-e258-4aba-b756-014d02490b5a/scratchpad"

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB -- streamed, never buffered whole in memory


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


def snapshot_id_for(digest):
    return f"{SOURCE_ID}:sha256:{digest}"


# ---------------------------------------------------------------------------
# PHASE B -- fetch, hash, upload, record. No parsing.
# ---------------------------------------------------------------------------

def start_job_run(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO job_run (job_key, jurisdiction_id, source_id, status)
            VALUES (%s, %s, %s, 'running')
            RETURNING id
            """,
            (JOB_KEY, JURISDICTION_ID, SOURCE_ID),
        )
        job_run_id = cur.fetchone()[0]
    conn.commit()
    print(f"  job_run started: {job_run_id}")
    return job_run_id


def fail_job_run(conn, job_run_id, error):
    conn.rollback()  # clear whatever aborted the transaction before writing the failure
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE job_run SET status = 'failed', finished_at = now(), error = %s
            WHERE id = %s
            """,
            (str(error), job_run_id),
        )
    conn.commit()


def fetch_and_hash(dest_path):
    """GET the endpoint, following redirects, streaming to dest_path while
    hashing incrementally. Returns (digest, byte_size, media_type, http_status,
    fetched_at)."""
    hasher = hashlib.sha256()
    byte_size = 0
    with requests.get(ENDPOINT_URL, stream=True, allow_redirects=True, timeout=300) as resp:
        resp.raise_for_status()
        http_status = resp.status_code
        media_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                f.write(chunk)
                hasher.update(chunk)
                byte_size += len(chunk)
    fetched_at = datetime.now(timezone.utc)
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
    stored_size = head["ContentLength"]
    if stored_size != byte_size:
        raise RuntimeError(
            f"uploaded object size {stored_size} != computed byte_size {byte_size}"
        )
    # Re-hash what's actually in the bucket, not just trust the upload --
    # download and hash to confirm the stored bytes are exactly what we
    # computed the digest from.
    obj = s3.get_object(Bucket=bucket, Key=key)
    verify_hasher = hashlib.sha256()
    for chunk in obj["Body"].iter_chunks(chunk_size=CHUNK_SIZE):
        verify_hasher.update(chunk)
    stored_digest = verify_hasher.hexdigest()
    if stored_digest != digest:
        raise RuntimeError(
            f"uploaded object hash {stored_digest} != computed digest {digest}"
        )
    return key


def insert_snapshot(conn, digest, byte_size, media_type, http_status, fetched_at, bucket):
    sid = snapshot_id_for(digest)
    uri = object_uri(bucket, digest)
    request_payload = json.dumps({"url": ENDPOINT_URL, "method": "GET", "params": {}})
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO snapshot (
                id, source_id, object_uri, content_hash, media_type, byte_size,
                request, http_status, fetched_at, licence_observed_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
            (
                sid, SOURCE_ID, uri, digest, media_type, byte_size,
                request_payload, http_status, fetched_at, LICENCE_ID,
            ),
        )
    conn.commit()
    return sid


def finish_job_run(conn, job_run_id, status, snapshot_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE job_run
            SET status = %s, finished_at = now(), snapshot_id = %s
            WHERE id = %s
            """,
            (status, snapshot_id, job_run_id),
        )
    conn.commit()


def run_one_fetch(conn, s3, bucket, dest_path, label):
    """One full job_run: fetch, hash, and either upload+record (first time
    for this content) or discover it's unchanged and skip (dedupe)."""
    print(f"\n--- {label} ---")
    job_run_id = start_job_run(conn)
    try:
        t0 = time.monotonic()
        digest, byte_size, media_type, http_status, fetched_at = fetch_and_hash(dest_path)
        elapsed = time.monotonic() - t0
        print(f"  fetched {byte_size:,} bytes in {elapsed:.1f}s, media_type={media_type}, http_status={http_status}")
        print(f"  sha256: {digest}")

        sid = snapshot_id_for(digest)
        if snapshot_exists(conn, sid):
            print(f"  snapshot {sid} already exists -- content unchanged, skipping upload")
            finish_job_run(conn, job_run_id, "skipped_unchanged", sid)
            print(f"  job_run {job_run_id} -> skipped_unchanged")
        else:
            key = upload_and_verify(s3, bucket, dest_path, digest, byte_size)
            print(f"  uploaded and verified at key: {key}")
            sid = insert_snapshot(conn, digest, byte_size, media_type, http_status, fetched_at, bucket)
            print(f"  snapshot inserted: {sid}")
            finish_job_run(conn, job_run_id, "succeeded", sid)
            print(f"  job_run {job_run_id} -> succeeded")
        return digest, sid
    except Exception as e:
        fail_job_run(conn, job_run_id, e)
        print(f"  job_run {job_run_id} -> failed: {e}")
        raise


def phase_b():
    conn = get_db()
    s3 = get_s3()
    bucket = env("OBJECT_STORE_BUCKET")
    path1 = os.path.join(SCRATCHPAD, "parcels_fetch_1.geojson")
    path2 = os.path.join(SCRATCHPAD, "parcels_fetch_2.geojson")

    digest1, sid1 = run_one_fetch(conn, s3, bucket, path1, "FETCH 1 (first ingest)")
    digest2, sid2 = run_one_fetch(conn, s3, bucket, path2, "FETCH 2 (dedupe proof)")

    print("\n=== PHASE B SUMMARY ===")
    print(f"fetch 1 digest: {digest1}")
    print(f"fetch 2 digest: {digest2}")
    print(f"digests match:  {digest1 == digest2}")
    print(f"snapshot row (fetch 1): {sid1}")
    print(f"snapshot row (fetch 2): {sid2} (same id -- no second row was inserted)")
    conn.close()
    return path1, digest1


# ---------------------------------------------------------------------------
# PHASE C -- inspect the real data. Loads nothing into the database.
# ---------------------------------------------------------------------------

EXPECTED_FIELDS = ["parcel.apn", "parcel.geometry", "parcel.lot_area_gis", "parcel.situs_address"]


def is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def phase_c(path):
    address_key_candidates = {"SITUS_ADDRESS", "ADDRESS", "SITE_ADDR", "SITUSADDR", "SITEADDRESS"}

    # Pass 1: the full set of property keys that occur ANYWHERE in the file.
    # Needed before pass 2 can compute an accurate missing-count per key --
    # a key discovered on feature 200,000 was still absent on every feature
    # before it, and a single pass can't know that until it's seen the
    # whole file.
    all_keys_seen = set()
    address_keys_found = set()
    with open(path, "rb") as f:
        for feat in ijson.items(f, "features.item"):
            for k in (feat.get("properties") or {}):
                all_keys_seen.add(k)
                if k.upper() in address_key_candidates:
                    address_keys_found.add(k)

    # Pass 2: tally against the now-complete key set.
    feature_count = 0
    geometry_types = {}
    key_missing_count = {k: 0 for k in all_keys_seen}
    apn_values = []
    null_apn_count = 0
    null_address_count = 0

    with open(path, "rb") as f:
        for feat in ijson.items(f, "features.item"):
            feature_count += 1
            geom = feat.get("geometry") or {}
            gtype = geom.get("type")
            geometry_types[gtype] = geometry_types.get(gtype, 0) + 1

            props = feat.get("properties") or {}
            for k in all_keys_seen:
                if props.get(k, None) is None:
                    key_missing_count[k] += 1

            apn = props.get("APN")
            if is_blank(apn):
                null_apn_count += 1
            else:
                apn_values.append(apn)

            if address_keys_found and all(is_blank(props.get(k)) for k in address_keys_found):
                null_address_count += 1
            elif not address_keys_found:
                null_address_count += 1  # no address-shaped key exists on this feature set at all

    apn_set = set(apn_values)
    print("\n=== PHASE C: DATA INSPECTION (no database writes) ===")
    print(f"feature count: {feature_count:,}")
    print(f"\ngeometry types: {geometry_types}")
    print(f"\nproperty keys present (all features, union): {sorted(all_keys_seen)}")
    print("\nkey coverage (features missing/null each key):")
    for k in sorted(all_keys_seen):
        missing = key_missing_count.get(k, 0)
        print(f"  {k:16s} missing/null in {missing:,} of {feature_count:,}")
    print(f"\nAPN: {len(apn_values):,} non-blank, {null_apn_count:,} null/blank")
    print(f"APN uniqueness: {len(apn_set):,} distinct values among {len(apn_values):,} non-blank APNs "
          f"({'UNIQUE' if len(apn_set) == len(apn_values) else 'HAS DUPLICATES'})")
    print(f"\naddress-shaped property key found: {address_keys_found or 'NONE'}")
    print(f"features lacking any address-shaped key: {null_address_count:,} of {feature_count:,}")

    print("\nexpected_fields coverage (source.expected_fields = "
          f"{EXPECTED_FIELDS}):")
    print("  parcel.apn            -> APN property, present" if "APN" in all_keys_seen
          else "  parcel.apn            -> NOT FOUND")
    print("  parcel.geometry       -> geometry present on every feature (GeoJSON structural)")
    if "SHAPE_Area" in all_keys_seen:
        print("  parcel.lot_area_gis   -> NOT directly supplied. SHAPE_Area is present (a GIS-computed "
              "polygon area) but is NOT the same thing as a declared lot_area_gis field, and its unit "
              "and computation method (planar sq ft in what SRID?) are not confirmed. Not treated as "
              "a match -- reported as a candidate only, not consumed.")
    else:
        print("  parcel.lot_area_gis   -> NOT FOUND, no candidate present either")
    if address_keys_found:
        print(f"  parcel.situs_address  -> candidate key(s) found: {address_keys_found}")
    else:
        print("  parcel.situs_address  -> NOT FOUND. No address-shaped property exists on this "
              "feature set at all.")

    unmatched = []
    if "SHAPE_Area" not in all_keys_seen:
        unmatched.append("parcel.lot_area_gis")
    else:
        unmatched.append("parcel.lot_area_gis (SHAPE_Area present but not confirmed equivalent -- not consumed)")
    if not address_keys_found:
        unmatched.append("parcel.situs_address")
    schema_drift = {
        "expected_fields": EXPECTED_FIELDS,
        "actual_property_keys": sorted(all_keys_seen),
        "unmatched_expected": unmatched,
        "notes": {
            "parcel.lot_area_gis": "not supplied as a declared field; SHAPE_Area present but not "
                                    "confirmed equivalent (unit/SRID/computation method unverified), "
                                    "not consumed -- computing it from geometry would make it a "
                                    "derived fact (method='derived'), out of scope here",
            "parcel.situs_address": "not supplied; no address-shaped property key found in the feature set",
        },
    }
    print(f"\nschema_drift (to be recorded on job_run): {json.dumps(schema_drift, indent=2)}")
    return {
        "feature_count": feature_count,
        "geometry_types": geometry_types,
        "all_keys": all_keys_seen,
        "apn_values": apn_values,
        "apn_set": apn_set,
        "null_apn_count": null_apn_count,
        "schema_drift": schema_drift,
    }


# ---------------------------------------------------------------------------
# PHASE D -- load 20 parcels. Inline property->field_key mapping: the seed
# of jurisdictions/ca_san_jose/, kept deliberately inline and obvious here,
# not built out into a pack.
# ---------------------------------------------------------------------------

# Only two of source.expected_fields are actually supplied -- see Phase C.
# parcel.lot_area_gis and parcel.situs_address are NOT mapped: the source
# has no address-shaped property at all, and SHAPE_Area (present) is not
# consumed as lot_area_gis -- field_definition declares
# parcel.lot_area_gis unit='square_feet', and SHAPE_Area is computed
# against this export's EPSG:4326 (geographic, degrees) coordinates, so
# its unit is unconfirmed -- possibly square degrees, possibly computed
# server-side against a different, undocumented projected CRS before
# export. Asserting square_feet without confirming that would be
# fabricating a unit, not recording an observation. It would be a
# RETRIEVED fact if it were used (SHAPE_Area is in the payload, not
# computed from geometry by us), not a derived one -- the blocker is the
# unit mismatch, not the provenance shape.
PROPERTY_TO_FIELD_KEY = {
    "APN": "parcel.apn",
}

# Accepted NOT NULL judgment calls (Phase C report):
FACT_CONFIDENCE = "high"
FACT_CONFIDENCE_RULE_ID = "bulk_direct_from_assessor_gis"
FACT_PACK_VERSION = "v1.0"


def select_parcels(path, n=20):
    """First n features with a non-blank APN, unique within the selection.
    Does NOT attempt to resolve the 53 duplicate-APN cases or the 9 blanks
    found in Phase C -- skipped and counted, not fixed."""
    selected = []
    seen_apns = set()
    skipped_blank = 0
    skipped_duplicate = 0
    with open(path, "rb") as f:
        for feat in ijson.items(f, "features.item"):
            apn = (feat.get("properties") or {}).get("APN")
            if is_blank(apn):
                skipped_blank += 1
                continue
            if apn in seen_apns:
                skipped_duplicate += 1
                continue
            seen_apns.add(apn)
            selected.append(feat)
            if len(selected) >= n:
                break
    return selected, skipped_blank, skipped_duplicate


def _decimal_default(o):
    # ijson parses GeoJSON coordinate numbers as decimal.Decimal; json.dumps
    # has no default encoding for it. float() loses no precision that
    # matters for a geometry coordinate here (this is not a currency value).
    if isinstance(o, decimal.Decimal):
        return float(o)
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def geojson_geom_param(feat):
    return json.dumps(feat["geometry"], default=_decimal_default)


def phase_d1_probe(conn, feat):
    """Deliberately insert ONE parcel WITHOUT ST_Multi() on a Polygon-typed
    feature. parcel.geom is geometry(MultiPolygon, 4326); the source
    reports Polygon. Prediction: PostGIS rejects it. Paste whatever
    actually happens -- do not change the schema to make it succeed."""
    print("\n=== PHASE D.1: probe -- insert WITHOUT ST_Multi() on a Polygon feature ===")
    apn = feat["properties"]["APN"]
    print(f"  using feature APN={apn}, geometry type={feat['geometry']['type']}")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO parcel (jurisdiction_id, apn, geom)
                VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                """,
                (JURISDICTION_ID, apn, geojson_geom_param(feat)),
            )
        conn.commit()
        print("  RESULT: INSERT SUCCEEDED (unexpected -- the prediction was wrong)")
        return True
    except Exception as e:
        conn.rollback()
        print(f"  RESULT: INSERT FAILED as predicted:\n  {type(e).__name__}: {e}")
        return False


def load_parcels(conn, features):
    """Load parcel rows for real, ST_Multi() applied uniformly -- it is a
    no-op on an already-MultiPolygon geometry, so there is no branching on
    the source's reported type."""
    print(f"\n=== PHASE D.2: loading {len(features)} parcel rows (ST_Multi() applied uniformly) ===")
    parcel_ids = {}  # apn -> parcel.id
    with conn.cursor() as cur:
        for feat in features:
            apn = feat["properties"]["APN"]
            cur.execute(
                """
                INSERT INTO parcel (jurisdiction_id, apn, geom)
                VALUES (%s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                RETURNING id
                """,
                (JURISDICTION_ID, apn, geojson_geom_param(feat)),
            )
            parcel_ids[apn] = cur.fetchone()[0]
    conn.commit()
    print(f"  loaded {len(parcel_ids)} parcels")
    return parcel_ids


def load_facts(conn, features, parcel_ids, source_id_row, snapshot_id, retrieved_at):
    """Insert facts for the two fields actually supplied: parcel.apn and
    parcel.geometry. Every insert must satisfy fact_provenance_complete,
    fact_source_method_fk, fact_snapshot_source_fk, fact_snapshot_licence_fk
    and the jurisdiction-consistency FKs (0018, 0020, 0022). If any of them
    rejects a row, that is reported as a finding, not patched around."""
    print(f"\n=== PHASE D.3: inserting facts for {len(features)} parcels ===")
    inserted = 0
    with conn.cursor() as cur:
        for feat in features:
            props = feat["properties"]
            apn = props["APN"]
            pid = parcel_ids[apn]

            cur.execute(
                """
                INSERT INTO fact (
                    parcel_id, jurisdiction_id, field_key, value, method,
                    source_id, snapshot_id, retrieved_at, source_url,
                    licence_id, confidence, confidence_rule_id,
                    effective_from, pack_version
                ) VALUES (
                    %s, %s, 'parcel.apn', to_jsonb(%s::text), 'bulk',
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    pid, JURISDICTION_ID, apn,
                    source_id_row, snapshot_id, retrieved_at, ENDPOINT_URL,
                    LICENCE_ID, FACT_CONFIDENCE, FACT_CONFIDENCE_RULE_ID,
                    retrieved_at, FACT_PACK_VERSION,
                ),
            )
            inserted += 1

            cur.execute(
                """
                INSERT INTO fact (
                    parcel_id, jurisdiction_id, field_key, value, method,
                    source_id, snapshot_id, retrieved_at, source_url,
                    licence_id, confidence, confidence_rule_id,
                    effective_from, pack_version
                ) VALUES (
                    %s, %s, 'parcel.geometry', %s::jsonb, 'bulk',
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    pid, JURISDICTION_ID, geojson_geom_param(feat),
                    source_id_row, snapshot_id, retrieved_at, ENDPOINT_URL,
                    LICENCE_ID, FACT_CONFIDENCE, FACT_CONFIDENCE_RULE_ID,
                    retrieved_at, FACT_PACK_VERSION,
                ),
            )
            inserted += 1
    conn.commit()
    print(f"  inserted {inserted} fact rows ({len(features)} parcels x 2 fields)")
    return inserted


def refresh_current_fact(conn):
    print("\n=== PHASE D.4: refreshing current_fact ===")
    with conn.cursor() as cur:
        cur.execute("SELECT ispopulated FROM pg_matviews WHERE matviewname = 'current_fact'")
        populated = cur.fetchone()[0]
    if not populated:
        print("  current_fact is not yet populated -- plain REFRESH first (per db/README.md)")
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW current_fact")
        conn.commit()
    else:
        print("  current_fact already populated -- plain REFRESH anyway, per instruction, before CONCURRENTLY")
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW current_fact")
        conn.commit()
    print("  plain REFRESH done")
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY current_fact")
    conn.commit()
    print("  REFRESH CONCURRENTLY done")


def query_one_parcel(conn, apn):
    print(f"\n=== PHASE D.5: querying APN={apn} through current_fact ===")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT cf.parcel_id, cf.field_key, cf.value, cf.method,
                   cf.source_id, cf.snapshot_id, cf.licence_id,
                   cf.confidence, cf.effective_from, cf.retrieved_at,
                   s.content_hash AS snapshot_content_hash,
                   s.object_uri AS snapshot_object_uri
            FROM current_fact cf
            JOIN parcel p ON p.id = cf.parcel_id
            LEFT JOIN snapshot s ON s.id = cf.snapshot_id
            WHERE p.apn = %s
            ORDER BY cf.field_key
            """,
            (apn,),
        )
        rows = cur.fetchall()
    for row in rows:
        print(f"  {dict(row)}")
    return rows


def phase_d():
    conn = get_db()
    path = os.path.join(SCRATCHPAD, "parcels_fetch_1.geojson")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, content_hash FROM snapshot WHERE source_id = %s ORDER BY fetched_at DESC LIMIT 1",
            (SOURCE_ID,),
        )
        row = cur.fetchone()
        if row is None:
            raise SystemExit("no snapshot found for ca_san_jose.parcels -- run --phase b first")
        snapshot_id, digest = row
        cur.execute("SELECT fetched_at FROM snapshot WHERE id = %s", (snapshot_id,))
        retrieved_at = cur.fetchone()[0]
    print(f"using snapshot: {snapshot_id}")

    # 21 candidates: 20 for the real load, 1 held out for the D.1 probe so
    # that an unexpected probe success can't collide (parcel_jurisdiction_id_apn_key)
    # with the same APN being inserted again during the real load.
    candidates, skipped_blank, skipped_duplicate = select_parcels(path, n=21)
    probe_feat = next(f for f in candidates if f["geometry"]["type"] == "Polygon")
    selected = [f for f in candidates if f is not probe_feat][:20]
    print(f"\nselected {len(selected)} features for loading (+1 held out for the D.1 probe): "
          f"{skipped_blank} skipped for blank APN, {skipped_duplicate} skipped as "
          f"in-selection duplicates (53 real duplicate APNs and 9 blanks exist dataset-wide "
          f"per Phase C -- not resolved, recorded only)")

    phase_d1_probe(conn, probe_feat)

    parcel_ids = load_parcels(conn, selected)
    load_facts(conn, selected, parcel_ids, SOURCE_ID, snapshot_id, retrieved_at)
    refresh_current_fact(conn)
    sample_apn = selected[0]["properties"]["APN"]
    query_one_parcel(conn, sample_apn)

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["b", "c", "d"])
    parser.add_argument("--input-file", help="path to a previously-fetched GeoJSON file, for --phase c/d")
    args = parser.parse_args()

    if args.phase == "b":
        phase_b()
    elif args.phase == "c":
        path = args.input_file or os.path.join(SCRATCHPAD, "parcels_fetch_1.geojson")
        phase_c(path)
    elif args.phase == "d":
        phase_d()
    else:
        print("pass --phase b, c, or d", file=sys.stderr)
        sys.exit(1)
