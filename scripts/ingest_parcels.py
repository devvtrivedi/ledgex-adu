#!/usr/bin/env python3
"""First ingestion: San José parcels, end to end, smallest useful slice.

One plain script, not the core/connectors + core/store architecture --
turning this into modules is a later job informed by what this teaches.
See CLAUDE.md / docs/LEDGEX_SPEC.md for the invariants this respects.

Phases (run with --phase b / c / d / e). B/C/D are the smallest useful
slice this file's title describes. E is a later, separate addition: the
full-scale load, every feature in the file, not a 20-parcel sample.
  B: fetch the parcels endpoint, hash streamed to disk, upload to the
     content-addressed object store key, record snapshot + job_run. Does
     NOT parse the GeoJSON. Then re-fetches once more to prove the same
     content hashes to the same key (job_run.status='skipped_unchanged',
     no second snapshot row -- the id would collide on the PK anyway).
     C7 policy: a snapshot row is written for EVERY fetch, including a
     zero-result response and an HTTP error, with http_status recorded --
     run_one_fetch never raises on a non-2xx status, it snapshots the
     response anyway and marks job_run 'failed'; only a genuine exception
     (network failure, upload failure) skips writing the row. Verified
     against real requests, not simulated: a real 403 (365-byte XML error
     body) got hashed, uploaded and snapshotted with job_run='failed';
     a real 200 with a genuinely empty body produced
     sha256("")=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
     and job_run='succeeded' -- 0021's content_hash format CHECK and
     byte_size >= 0 both already permit this, no schema change needed.
  C: inspect the downloaded file (property keys, geometry types, APN
     uniqueness, expected_fields coverage). Loads nothing into the
     database.
  D: load 20 parcel rows and their facts, including the deliberate
     ST_Multi() omission probe phase D.1 asks for.
  E: full-scale load -- every feature in the file becomes exactly one
     parcel row, no skipping duplicates or blanks (0034 dropped apn's
     NOT NULL/UNIQUE specifically so this could happen without error).
     parcel.geometry and parcel.source_parcel_id facts (0035) are written
     for every parcel; parcel.apn only when the source's own APN value is
     resolvable (not blank, no '?' placeholder character anywhere in it
     -- both a trailing 'NNNNN???' and a leading '??NNNNNN' placeholder
     shape exist in the real data). An unresolvable APN gets no
     parcel.apn fact and one parcel_exception (type='coverage_gap')
     instead. One transaction for the entire load -- see phase_e()'s own
     docstring for why. Requires phase b to have already run against the
     target database (needs a real snapshot to cite).

DATABASE_URL and OBJECT_STORE_* are read from the process environment
first, falling back to .env only if unset (python-dotenv's default
override=False) -- this run is meant to hit a scratch database, never
whatever DATABASE_URL happens to be sitting in .env.
"""
import argparse
import hashlib
import json
import os
import resource
import sys
import time
import uuid
from datetime import datetime, timezone

import boto3
import ijson
import psycopg2
import psycopg2.extras
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from infra.env import env, get_db  # noqa: E402
from infra.values import is_blank, decimal_default  # noqa: E402

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

def start_job_run(conn, job_key=JOB_KEY):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO job_run (job_key, jurisdiction_id, source_id, status)
            VALUES (%s, %s, %s, 'running')
            RETURNING id
            """,
            (job_key, JURISDICTION_ID, SOURCE_ID),
        )
        job_run_id = cur.fetchone()[0]
    conn.commit()
    print(f"  job_run started: {job_run_id}")
    return job_run_id


def fail_job_run(conn, job_run_id, error):
    # clock_timestamp(), not now() -- see finish_job_run's own comment below.
    # This copy was missed when that one was fixed: now() returns the
    # CURRENT TRANSACTION's start time, frozen for its whole duration, so a
    # long-open failing transaction (a slow fetch or upload that ultimately
    # raises) would have finished_at silently discarding however long it
    # actually ran for. Same bug 0036 documented for now() vs.
    # clock_timestamp() in a different context.
    conn.rollback()  # clear whatever aborted the transaction before writing the failure
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE job_run SET status = 'failed', finished_at = clock_timestamp(), error = %s
            WHERE id = %s
            """,
            (str(error), job_run_id),
        )
    conn.commit()


def fetch_and_hash(dest_path, url=None):
    """GET the endpoint, following redirects, streaming to dest_path while
    hashing incrementally. Deliberately does NOT raise_for_status(): C7
    policy is to snapshot every fetch, including a zero-result response and
    an HTTP error, with http_status recorded -- a failed fetch is part of
    the provenance record, not something that skips writing a snapshot row.
    Returns (digest, byte_size, media_type, http_status, fetched_at)."""
    hasher = hashlib.sha256()
    byte_size = 0
    with requests.get(url or ENDPOINT_URL, stream=True, allow_redirects=True, timeout=300) as resp:
        http_status = resp.status_code
        # A non-2xx response (or one with no body) can arrive with no
        # Content-Type at all; snapshot_media_type_not_blank (0021) requires
        # a non-blank value, so an empty header falls back to a real,
        # honest placeholder rather than leaving it blank.
        media_type = resp.headers.get("Content-Type", "").split(";")[0].strip() or "application/octet-stream"
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


def insert_snapshot(conn, digest, byte_size, media_type, http_status, fetched_at, bucket, url=None):
    sid = snapshot_id_for(digest)
    uri = object_uri(bucket, digest)
    request_payload = json.dumps({"url": url or ENDPOINT_URL, "method": "GET", "params": {}})
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
    # clock_timestamp(), not now(): now() returns the CURRENT TRANSACTION's
    # start time, frozen for the whole transaction, not the time this
    # statement actually executes -- harmless here today, since nothing
    # slow happens between the last commit and this UPDATE in any current
    # caller, but see finish_job_run_full's header for where it is not
    # harmless.
    #
    # An earlier version of this comment claimed this was "fixed in both
    # places for the same reason, not just the one where it was observed."
    # That was false, and was never actually checked against the third
    # place before being written down: fail_job_run, above in this same
    # file, still used now() until it was found and fixed separately. All
    # three finished_at call sites in this file (here, fail_job_run,
    # finish_job_run_full) use clock_timestamp() now -- checked directly,
    # not assumed, this time.
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE job_run
            SET status = %s, finished_at = clock_timestamp(), snapshot_id = %s
            WHERE id = %s
            """,
            (status, snapshot_id, job_run_id),
        )
    conn.commit()


def run_one_fetch(conn, s3, bucket, dest_path, label, url=None):
    """One full job_run: fetch, hash, and ALWAYS record a snapshot row for
    whatever came back -- a successful response, an HTTP error, or an
    empty body (C7 policy). Content is stored and a snapshot row inserted
    the same way regardless of http_status; only job_run's terminal status
    differs: succeeded/skipped_unchanged for a 2xx response, failed for
    anything else -- the snapshot itself is written either way, because a
    failed fetch is part of the provenance record, not something to
    silently skip."""
    print(f"\n--- {label} ---")
    job_run_id = start_job_run(conn)
    try:
        t0 = time.monotonic()
        digest, byte_size, media_type, http_status, fetched_at = fetch_and_hash(dest_path, url=url)
        elapsed = time.monotonic() - t0
        ok = 200 <= http_status < 300
        print(f"  fetched {byte_size:,} bytes in {elapsed:.1f}s, media_type={media_type}, http_status={http_status}"
              + ("" if ok else " (non-2xx -- snapshotting anyway per C7)"))
        print(f"  sha256: {digest}")

        sid = snapshot_id_for(digest)
        already_had_snapshot = snapshot_exists(conn, sid)
        if already_had_snapshot:
            print(f"  snapshot {sid} already exists -- content unchanged, skipping upload")
        else:
            key = upload_and_verify(s3, bucket, dest_path, digest, byte_size)
            print(f"  uploaded and verified at key: {key}")
            sid = insert_snapshot(conn, digest, byte_size, media_type, http_status, fetched_at, bucket, url=url)
            print(f"  snapshot inserted: {sid}")

        if not ok:
            status = "failed"
        elif already_had_snapshot:
            status = "skipped_unchanged"
        else:
            status = "succeeded"
        finish_job_run(conn, job_run_id, status, sid)
        print(f"  job_run {job_run_id} -> {status}")
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


def geojson_geom_param(feat):
    return json.dumps(feat["geometry"], default=decimal_default)


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


# ---------------------------------------------------------------------------
# PHASE E -- the full-scale load. Every feature becomes a parcel row; no
# skipping duplicates or blanks the way Phase D's select_parcels does.
# 0034 dropped apn's NOT NULL/UNIQUE specifically so this could happen
# without error; 0035 added parcel.source_parcel_id as a fact-only field.
# ---------------------------------------------------------------------------

JOB_KEY_FULL = "ingest_parcels_full"
DETECTOR_KEY_APN_UNRESOLVABLE = "parcel_apn_unresolvable"
DETECTOR_VERSION_APN_UNRESOLVABLE = "1.0"

# Two placeholder shapes exist in the real data, discovered while writing
# this phase -- the parcel identity diagnostic's duplicate-only analysis
# only ever looked at APNs appearing more than once, so it only surfaced
# the 9 duplicated placeholder values (21 features). A full scan (this
# phase's own is_unresolvable_apn, run once over the whole file before
# writing the load below) found 45 features carrying a '?' somewhere in
# APN, not 21: 29 with the trailing 'NNNNN???' unresolved-suffix shape
# already documented in 0034, and 16 more split between a shorter
# trailing 'NNNNNN??' form and a LEADING '??NNNNNN' form (e.g.
# '??000008') the diagnostic never encountered, because none of those 24
# singly-occurring values were ever duplicated. Combined with the 9 blank
# features, 54 features -- not 30, not 18 -- get no parcel.apn fact.
# Detected on ANY '?' in the string, not a specific run length or
# position: a real APN is never expected to contain one.
def is_unresolvable_apn(apn):
    """True if apn cannot be recorded as a resolvable public_record
    observation. Returns (bool, reason) where reason is 'blank' or
    'placeholder'."""
    if is_blank(apn):
        return True, "blank"
    if "?" in apn:
        return True, "placeholder"
    return False, None


def finish_job_run_full(conn, job_run_id, status, snapshot_id, rows_in, rows_out):
    # clock_timestamp(), not now() -- found for real, not by inspection:
    # the first full-scale run reported job_run duration as 10.08s
    # (matching parse time alone) against a script-measured 10.0s parse +
    # 67.3s bulk insert, ~77s total. now() in Postgres returns the current
    # TRANSACTION's start time, constant for the whole transaction, not
    # the time a given statement actually runs. Nothing touches this
    # connection during the ~10s parse (pure Python, no DB calls), so the
    # transaction this UPDATE runs in does not begin until the first
    # execute_values call below -- meaning now() here returned "when the
    # bulk insert started," not "when it finished," silently discarding
    # the entire insert duration from the recorded finished_at. Confirmed
    # directly: BEGIN; SELECT now(); SELECT pg_sleep(2);
    # SELECT now(), clock_timestamp(); -- now() was identical both times,
    # clock_timestamp() had advanced by 2s. clock_timestamp() always
    # reflects actual current time, transaction or no.
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE job_run
            SET status = %s, finished_at = clock_timestamp(), snapshot_id = %s,
                rows_in = %s, rows_out = %s
            WHERE id = %s
            """,
            (status, snapshot_id, rows_in, rows_out, job_run_id),
        )
    conn.commit()


def phase_e():
    """Full-scale load. One transaction for the entire load (parcel +
    fact + parcel_exception inserts): any failure anywhere rolls back
    everything, leaving no partial state to repair. 0017 blocks fact
    deletion, so a bug discovered after a partial COMMIT would be
    permanent -- the discipline here is to never partially commit in the
    first place, not to clean up afterward. On failure, the job_run row
    (already committed by start_job_run, a separate transaction) is
    marked 'failed' -- the attempt itself is provenance, C7's policy for
    Phase B applied here to a load, not just a fetch.

    Every feature becomes exactly one parcel row (apn = the raw value if
    resolvable, else NULL -- 0034's documented cache-column policy: no
    fact means no cache value). parcel.geometry and
    parcel.source_parcel_id facts are written for every parcel (both
    fields the source supplies for all 225,039 features). parcel.apn is
    written only when resolvable; an unresolvable feature gets no
    parcel.apn fact and one parcel_exception (type='coverage_gap') instead
    -- verified in the previous pass to need no schema change (0010/0015
    already accept outcome='open' with resolved_at/resolved_by both
    NULL; see db/README.md).
    """
    conn = get_db()
    path = os.path.join(SCRATCHPAD, "parcels_fetch_1.geojson")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM snapshot WHERE source_id = %s ORDER BY fetched_at DESC LIMIT 1",
            (SOURCE_ID,),
        )
        row = cur.fetchone()
        if row is None:
            raise SystemExit("no snapshot found for ca_san_jose.parcels -- run --phase b first")
        snapshot_id = row[0]
        cur.execute("SELECT fetched_at FROM snapshot WHERE id = %s", (snapshot_id,))
        retrieved_at = cur.fetchone()[0]
    print(f"using snapshot: {snapshot_id}")

    job_run_id = start_job_run(conn, job_key=JOB_KEY_FULL)

    t_parse_start = time.monotonic()

    parcel_rows = []
    fact_rows = []
    exception_rows = []
    rows_in = 0
    resolvable_count = 0
    unresolvable_count = 0
    reason_counts = {"blank": 0, "placeholder": 0}

    try:
        with open(path, "rb") as f:
            for feat in ijson.items(f, "features.item"):
                rows_in += 1
                props = feat.get("properties") or {}
                apn_raw = props.get("APN")
                pid_raw = props.get("PARCELID")
                unresolvable, reason = is_unresolvable_apn(apn_raw)

                parcel_id = str(uuid.uuid4())
                stored_apn = None if unresolvable else apn_raw

                parcel_rows.append((parcel_id, JURISDICTION_ID, stored_apn, geojson_geom_param(feat)))

                fact_rows.append((
                    parcel_id, JURISDICTION_ID, "parcel.geometry", geojson_geom_param(feat), "bulk",
                    SOURCE_ID, snapshot_id, retrieved_at, ENDPOINT_URL,
                    LICENCE_ID, FACT_CONFIDENCE, FACT_CONFIDENCE_RULE_ID,
                    retrieved_at, FACT_PACK_VERSION,
                ))
                fact_rows.append((
                    parcel_id, JURISDICTION_ID, "parcel.source_parcel_id", json.dumps(str(pid_raw)), "bulk",
                    SOURCE_ID, snapshot_id, retrieved_at, ENDPOINT_URL,
                    LICENCE_ID, FACT_CONFIDENCE, FACT_CONFIDENCE_RULE_ID,
                    retrieved_at, FACT_PACK_VERSION,
                ))

                if unresolvable:
                    unresolvable_count += 1
                    reason_counts[reason] += 1
                    exception_rows.append((
                        parcel_id, JURISDICTION_ID, "coverage_gap", "info",
                        DETECTOR_KEY_APN_UNRESOLVABLE, DETECTOR_VERSION_APN_UNRESOLVABLE,
                        json.dumps({"raw_apn": apn_raw, "reason": reason}),
                    ))
                else:
                    resolvable_count += 1
                    fact_rows.append((
                        parcel_id, JURISDICTION_ID, "parcel.apn", json.dumps(apn_raw), "bulk",
                        SOURCE_ID, snapshot_id, retrieved_at, ENDPOINT_URL,
                        LICENCE_ID, FACT_CONFIDENCE, FACT_CONFIDENCE_RULE_ID,
                        retrieved_at, FACT_PACK_VERSION,
                    ))

                if rows_in % 25000 == 0:
                    print(f"  ...parsed {rows_in:,} features")

        t_parse_end = time.monotonic()
        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_rss_mb = peak_rss / (1024 * 1024) if sys.platform == "darwin" else peak_rss / 1024
        print(f"\nparse complete: {rows_in:,} features in {t_parse_end - t_parse_start:.1f}s, "
              f"peak RSS {peak_rss_mb:.1f} MB")
        print(f"  resolvable APN: {resolvable_count:,}  unresolvable: {unresolvable_count:,} "
              f"(blank={reason_counts['blank']}, placeholder={reason_counts['placeholder']})")
        print(f"  parcel rows to insert: {len(parcel_rows):,}")
        print(f"  fact rows to insert: {len(fact_rows):,}")
        print(f"  parcel_exception rows to insert: {len(exception_rows):,}")

        # cur.rowcount after execute_values reflects only the LAST internal
        # page (execute_values splits page_size-row chunks into separate
        # statements), not the cumulative total -- confirmed directly, not
        # assumed: a 2,020-row smoketest insert reported cur.rowcount == 20
        # (the trailing partial page) while count(*) in the database showed
        # the correct 2,020. Report len() of the Python lists we already
        # built instead; they are what was actually submitted.
        t_load_start = time.monotonic()
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO parcel (id, jurisdiction_id, apn, geom) VALUES %s",
                parcel_rows,
                template="(%s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))",
                page_size=2000,
            )
            print(f"  parcel rows submitted: {len(parcel_rows):,}")

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
        t_load_end = time.monotonic()
        print(f"  bulk insert wall-clock: {t_load_end - t_load_start:.1f}s")

        # finish_job_run_full's own commit is the ONE commit for this entire
        # phase -- it closes out the same transaction the parcel/fact/
        # exception inserts above are still pending in, so job_run only
        # ever reports 'succeeded' atomically with the data it describes.
        finish_job_run_full(conn, job_run_id, "succeeded", snapshot_id, rows_in, len(parcel_rows))
        print(f"\njob_run {job_run_id} -> succeeded")

    except Exception as e:
        conn.rollback()
        fail_job_run(conn, job_run_id, e)
        print(f"\njob_run {job_run_id} -> failed: {e}")
        raise

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["b", "c", "d", "e"])
    parser.add_argument("--input-file", help="path to a previously-fetched GeoJSON file, for --phase c/d")
    args = parser.parse_args()

    if args.phase == "b":
        phase_b()
    elif args.phase == "c":
        path = args.input_file or os.path.join(SCRATCHPAD, "parcels_fetch_1.geojson")
        phase_c(path)
    elif args.phase == "d":
        phase_d()
    elif args.phase == "e":
        phase_e()
    else:
        print("pass --phase b, c, d, or e", file=sys.stderr)
        sys.exit(1)
