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

     Phase B reconciliation (same function, same transaction discipline):
     a snapshot that differs from previous_successful_snapshot() no longer
     makes phase_e refuse. It classifies every incoming feature as new,
     changed (>=1 of apn/geometry differs from the live fact), or
     disappeared (a previously-live source_feature_id absent from this
     snapshot) via a TEMP staging table + SQL diff against the live fact
     table, and reconciles each case for real -- see phase_e()'s own
     docstring for the write shape and NEXT_PROMPTS.md's Phase B report
     for the design.

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
import tempfile
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import boto3
import ijson
import psycopg2
import psycopg2.extras
import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from infra.env import env, get_db  # noqa: E402
from infra.values import is_blank, decimal_default, canonicalize_identifier  # noqa: E402
from core.model import Fact, ParcelException  # noqa: E402
from core.store import insert_facts  # noqa: E402
from core.exceptions import insert_exceptions, close_exceptions_for_parcels, relink_reopened_exceptions  # noqa: E402

SOURCE_ID = "ca_san_jose.parcels"
JURISDICTION_ID = "ca_san_jose"
LICENCE_ID = "cc_by_4_0_api_2026_08"  # P55: repointed from 'cc_by_4_0' (licence immutable,
                                       # facts cite THIS constant at write time -- see
                                       # prompts/P55-scoped-unblock.md §4.1/§4.5 step 9)
ENDPOINT_URL = (
    "https://gisdata-csj.opendata.arcgis.com/api/download/v1/items/"
    "4bb085cb99a64eff8e83d2bf92a8d5cb/geojson?layers=270"
)
JOB_KEY = "ingest_parcels"

SCRATCHPAD = "/tmp/ledgex_ingest_scratch"

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


def parse_s3_uri(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise RuntimeError(f"snapshot.object_uri is not an s3:// URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def verified_snapshot_file(conn, snapshot_id):
    """Return (path, snapshot row dict) for bytes read from snapshot.object_uri.
    The hash is computed over exactly the bytes the loader will parse."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, source_id, object_uri, content_hash, media_type,
                   byte_size, fetched_at
            FROM snapshot
            WHERE id = %s AND source_id = %s
            """,
            (snapshot_id, SOURCE_ID),
        )
        snapshot = cur.fetchone()
    if snapshot is None:
        raise SystemExit(f"no snapshot {snapshot_id} found for {SOURCE_ID}")

    bucket, key = parse_s3_uri(snapshot["object_uri"])
    s3 = get_s3()
    hasher = hashlib.sha256()
    byte_size = 0
    suffix = ".geojson" if snapshot["media_type"] == "application/geo+json" else ".snapshot"
    tmp = tempfile.NamedTemporaryFile(prefix="ledgex-parcels-", suffix=suffix, delete=False)
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


def previous_successful_snapshot(conn, source_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT snapshot_id
            FROM job_run
            WHERE source_id = %s
              AND status = 'succeeded'
              AND snapshot_id IS NOT NULL
            ORDER BY finished_at DESC, started_at DESC
            LIMIT 1
            """,
            (source_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


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
    """OPTIMIZATION ONLY (README finding #10) -- lets the caller skip a
    redundant upload_and_verify() round-trip when this content is already
    stored. NOT the authority on whether snapshot.id = sid is actually
    live right now: two concurrent fetches of identical new content both
    call this before either has inserted, so both see False here. The
    authoritative answer -- whether THIS run is the one that durably
    wrote the row -- comes from insert_snapshot()'s own INSERT rowcount,
    not this SELECT. Do not "simplify" run_one_fetch() by reading
    already_had_snapshot for both the upload-skip AND the job_run status
    decision again -- that reintroduces the race this comment exists to
    prevent."""
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
    """README finding #10: ON CONFLICT (id) DO NOTHING, not a bare INSERT --
    id = snapshot_id_for(digest) is deterministic from content alone, so two
    concurrent fetches of identical new content compute the identical id and
    would otherwise race a bare INSERT into a raw PK violation (an
    unhandled exception, not a clean no-op). ON CONFLICT (id) alone is
    sufficient: id and the table's other uniqueness constraint,
    UNIQUE (content_hash, source_id), are both fully determined by the same
    (source_id, digest) pair in this script, so a conflict on one always
    means a conflict on the other for a row this code ever writes -- never
    two different code paths to satisfy.

    Returns (sid, inserted) -- inserted is True only when THIS call's own
    INSERT actually added the row (cur.rowcount == 1, read before commit()
    per this function's own docstring elsewhere in this codebase's
    convention -- rowcount does not depend on commit having happened, but
    reading it first keeps the ordering unambiguous). False means another
    writer's INSERT (or an earlier already-committed run) got there first
    -- this call is a no-op, not a failure. The caller must use THIS
    return value, not snapshot_exists()'s earlier SELECT, to decide
    job_run's terminal status -- see snapshot_exists()'s own docstring."""
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
            ON CONFLICT (id) DO NOTHING
            """,
            (
                sid, SOURCE_ID, uri, digest, media_type, byte_size,
                request_payload, http_status, fetched_at, LICENCE_ID,
            ),
        )
        inserted = cur.rowcount == 1
    conn.commit()
    return sid, inserted


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
        # already_had_snapshot is an upload-skipping OPTIMIZATION only
        # (README finding #10, see snapshot_exists()'s own docstring) --
        # job_run's terminal status below is decided from insert_snapshot()'s
        # own INSERT rowcount (`inserted`), never from this earlier SELECT.
        already_had_snapshot = snapshot_exists(conn, sid)
        if already_had_snapshot:
            print(f"  snapshot {sid} already exists -- content unchanged, skipping upload")
            inserted = False
        else:
            key = upload_and_verify(s3, bucket, dest_path, digest, byte_size)
            print(f"  uploaded and verified at key: {key}")
            sid, inserted = insert_snapshot(conn, digest, byte_size, media_type, http_status, fetched_at, bucket, url=url)
            if inserted:
                print(f"  snapshot inserted: {sid}")
            else:
                print(f"  snapshot {sid} already existed by the time of INSERT "
                      f"(lost a concurrent race) -- no-op, not re-inserted")

        if not ok:
            status = "failed"
        elif inserted:
            status = "succeeded"
        else:
            status = "skipped_unchanged"
        finish_job_run(conn, job_run_id, status, sid)
        print(f"  job_run {job_run_id} -> {status}")
        # P45 Fix 2 (README finding, see prompts/P45-ingest-provenance.md):
        # `ok` used to decide job_run.status above and then be discarded --
        # the function returned normally either way, so phase_b (the only
        # caller) never learned what this call already knew. Now returned
        # to the caller so a failed fetch can fail the PHASE, not just the
        # one job_run row. C7 is unaffected: the snapshot above is already
        # recorded, unconditionally, regardless of what happens with this
        # return value from here on.
        return digest, sid, http_status, ok
    except Exception as e:
        fail_job_run(conn, job_run_id, e)
        print(f"  job_run {job_run_id} -> failed: {e}")
        raise


def phase_b():
    """P45 Fix 2: both fetches ALWAYS complete and get snapshotted (C7 --
    unchanged, see run_one_fetch's own docstring); phase_b now fails LOUDLY
    if either one was a non-2xx response, AFTER both snapshot rows are
    already durably recorded -- recording first, failing second, is the
    order that keeps C7 intact. One failed fetch out of two fails the
    phase: a phase that half-worked is not a phase that worked, and a
    silent exit 0 with a `failed` job_run already in the database (the
    pre-fix behavior) is exactly the shape that let a failure go unnoticed.
    SystemExit, not a bare non-zero sys.exit() or an uncaught exception --
    matches phase_d/phase_e's own existing convention for a fatal,
    caller-facing condition in this file."""
    conn = get_db()
    s3 = get_s3()
    bucket = env("OBJECT_STORE_BUCKET")
    path1 = os.path.join(SCRATCHPAD, "parcels_fetch_1.geojson")
    path2 = os.path.join(SCRATCHPAD, "parcels_fetch_2.geojson")

    digest1, sid1, status1, ok1 = run_one_fetch(conn, s3, bucket, path1, "FETCH 1 (first ingest)")
    digest2, sid2, status2, ok2 = run_one_fetch(conn, s3, bucket, path2, "FETCH 2 (dedupe proof)")

    print("\n=== PHASE B SUMMARY ===")
    print(f"fetch 1 digest: {digest1}  (http_status={status1}, ok={ok1})")
    print(f"fetch 2 digest: {digest2}  (http_status={status2}, ok={ok2})")
    digests_match = digest1 == digest2
    print(f"digests match:  {digests_match}")
    print(f"snapshot row (fetch 1): {sid1}")
    print(f"snapshot row (fetch 2): {sid2} (same id -- no second row was inserted)")
    # P45 STEP 0(d): a mismatch is no longer a silent provenance risk after
    # Fix 1 -- any later load binds to one explicit, verified snapshot id,
    # never a guess -- but it is still a real fact about the source (it
    # changed between two fetches seconds apart) worth a human noticing,
    # not just a line in a scrolling log. Loud, not fatal: this does NOT
    # raise or change phase_b's exit code by itself.
    if not digests_match:
        print(f"\n{'!' * 78}\n"
              f"! SOURCE CHANGED BETWEEN FETCHES -- digests do not match.\n"
              f"!   fetch 1: {sid1}\n"
              f"!   fetch 2: {sid2}\n"
              f"! Both are recorded, independently, under their own true hashes (C7).\n"
              f"! A later --phase d/e load must name exactly ONE of these two ids --\n"
              f"! it will never be guessed.\n"
              f"{'!' * 78}")
    conn.close()

    if not (ok1 and ok2):
        raise SystemExit(
            f"phase b: at least one fetch was non-2xx (fetch 1 http_status={status1}, "
            f"fetch 2 http_status={status2}) -- both snapshots are recorded (C7), but a "
            f"phase that half-worked is not a phase that worked. See the job_run rows "
            f"above for detail."
        )
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


def load_parcels(conn, features, snapshot_id, retrieved_at):
    """Load parcel rows for real, ST_Multi() applied uniformly -- it is a
    no-op on an already-MultiPolygon geometry, so there is no branching on
    the source's reported type.

    C10 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): three fixes over the
    original version.

    (1) apn is canonicalized (canonicalize_identifier), matching phase E --
    Phase D used to insert feat["properties"]["APN"] verbatim, the one
    real divergence from phase E's own canonicalization Phase D never had
    a reason to skip.

    (2) source_feature_identity rows are written here now, keyed on
    PARCELID (phase E's own identity key) -- Phase D used to write none at
    all, so a LATER `--phase e` run on the SAME database found no identity
    row for these features, classified every one of them as NEW (phase
    E's own test is exactly "no identity row exists"), and minted a
    SECOND, duplicate parcel per feature -- legal since 0034 dropped
    jurisdiction+APN uniqueness. Writing the identity row here closes that
    gap the same way phase E's own NEW-feature branch does it, not a
    second, different mechanism.

    (3) REFUSES (raises, no parcel written) if a source_feature_identity
    row already exists for a feature's PARCELID -- this is exactly the
    "phase D re-run" collision the (now-corrected, see phase_d's own
    comment) belief in parcel_jurisdiction_id_apn_key used to describe.
    That constraint was dropped by 0034; nothing else in this schema would
    stop a second load_parcels call from silently duplicate-minting.
    Refusing loudly here, rather than writing a second, real
    accidental-collision code path (a "resolve the collision" mechanism
    Phase D -- a small demonstration/probe tool, per its own module
    comment, not the production bulk loader -- has no design for), is the
    acceptance-offered choice: pick one and say why. Phase E remains the
    only path that legitimately re-processes an already-identified
    feature (its own reconcile, changed/reappeared branches)."""
    print(f"\n=== PHASE D.2: loading {len(features)} parcel rows (ST_Multi() applied uniformly, canonicalized APN) ===")
    parcel_ids = {}  # apn -> parcel.id
    with conn.cursor() as cur:
        for feat in features:
            apn_raw = feat["properties"]["APN"]
            apn = canonicalize_identifier(apn_raw)
            source_feature_id = feat["properties"]["PARCELID"]

            cur.execute(
                "SELECT 1 FROM source_feature_identity WHERE source_id = %s AND source_feature_id = %s",
                (SOURCE_ID, source_feature_id),
            )
            if cur.fetchone() is not None:
                raise RuntimeError(
                    f"load_parcels: source_feature_identity already exists for "
                    f"source_id={SOURCE_ID!r}, source_feature_id={source_feature_id!r} "
                    f"(apn={apn!r}) -- this looks like a re-run of Phase D against a "
                    f"database that already loaded this feature. Phase D is a small "
                    f"demonstration/probe tool, not the production bulk loader (that is "
                    f"Phase E, whose own reconcile logic handles a re-observed feature "
                    f"correctly) -- refusing rather than minting a duplicate parcel "
                    f"(0034 dropped the jurisdiction+APN uniqueness constraint that used "
                    f"to make this impossible)."
                )

            cur.execute(
                """
                INSERT INTO parcel (jurisdiction_id, apn, geom)
                VALUES (%s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                RETURNING id
                """,
                (JURISDICTION_ID, apn, geojson_geom_param(feat)),
            )
            pid = cur.fetchone()[0]
            parcel_ids[apn] = pid

            cur.execute(
                """
                INSERT INTO source_feature_identity (
                    source_id, source_feature_id, parcel_id,
                    first_seen_snapshot_id, first_seen_at,
                    last_seen_snapshot_id, last_seen_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (SOURCE_ID, source_feature_id, pid, snapshot_id, retrieved_at, snapshot_id, retrieved_at),
            )
    # C10: NOT committed here -- see phase_d's own call site. Parcels,
    # their identity rows and their facts (load_facts, next) now land in
    # ONE transaction; a load_facts failure no longer strands committed,
    # fact-less parcels (I2's spirit, and 0017 forbids removing them once
    # committed).
    print(f"  loaded {len(parcel_ids)} parcels (not yet committed)")
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
            # C10: canonicalized, matching load_parcels' own key (and
            # phase E) -- the raw APN is no longer what parcel_ids is
            # keyed on.
            apn = canonicalize_identifier(props["APN"])
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
    # C10: NOT committed here either -- see load_parcels' own docstring.
    # phase_d does the single commit for parcels+identity+facts together,
    # right after this call returns.
    print(f"  inserted {inserted} fact rows ({len(features)} parcels x 2 fields), not yet committed")
    return inserted


def refresh_current_fact(conn):
    print("\n=== PHASE D.4: refreshing current_fact ===")
    conn.commit()
    old_autocommit = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT ispopulated FROM pg_matviews WHERE matviewname = 'current_fact'")
            populated = cur.fetchone()[0]
            if not populated:
                print("  current_fact is not yet populated -- plain REFRESH first (per db/README.md)")
                cur.execute("REFRESH MATERIALIZED VIEW current_fact")
                print("  plain REFRESH done")
            else:
                print("  current_fact already populated -- REFRESH CONCURRENTLY")
                cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY current_fact")
                print("  REFRESH CONCURRENTLY done")
    finally:
        conn.autocommit = old_autocommit


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


def phase_d(snapshot_id):
    """P45 Fix 1 (README finding, see prompts/P45-ingest-provenance.md).

    Before this fix: the bytes came from a FIXED path naming fetch 1
    (parcels_fetch_1.geojson) while the snapshot was WHICHEVER row was
    newest (`ORDER BY fetched_at DESC LIMIT 1`) -- two independent choices
    that silently diverge exactly when phase_b's two fetches disagree (a
    source that changed mid-run, a truncated response, an error body).
    `content_hash` was read into `digest` and never used to check anything.

    After: matches phase_e's own precedent exactly (that function's own
    docstring: "the loader is bound to the supplied snapshot_id... and
    refuses if those bytes do not match content_hash"). `--snapshot-id` is
    now REQUIRED (see this file's own __main__ block) -- no default
    "newest" guess, the same discipline phase_e already enforces. The path
    is no longer a fixed guess either: `verified_snapshot_file` reads the
    bytes FROM `snapshot.object_uri`, hashes them, and raises on a
    content_hash OR byte_size mismatch before this function ever touches
    them -- "run phase d with no arguments" is no longer a thing that
    works, the same cost `--phase e` already pays."""
    conn = get_db()
    path, snapshot = verified_snapshot_file(conn, snapshot_id)
    retrieved_at = snapshot["fetched_at"]
    print(f"using verified snapshot: {snapshot_id}")

    # 21 candidates: 20 for the real load, 1 held out for the D.1 probe so
    # that an unexpected probe success can't collide with the same APN
    # being inserted again during the real load. CORRECTED (C10, P59):
    # this used to cite parcel_jurisdiction_id_apn_key as the collision
    # protection -- 0034 dropped that constraint; load_parcels' own
    # source_feature_identity check-and-refuse (see its docstring) is
    # the real protection now, and it would refuse loudly rather than
    # collide silently either way.
    candidates, skipped_blank, skipped_duplicate = select_parcels(path, n=21)
    probe_feat = next(f for f in candidates if f["geometry"]["type"] == "Polygon")
    selected = [f for f in candidates if f is not probe_feat][:20]
    print(f"\nselected {len(selected)} features for loading (+1 held out for the D.1 probe): "
          f"{skipped_blank} skipped for blank APN, {skipped_duplicate} skipped as "
          f"in-selection duplicates (53 real duplicate APNs and 9 blanks exist dataset-wide "
          f"per Phase C -- not resolved, recorded only)")

    phase_d1_probe(conn, probe_feat)

    # C10: parcels, their source_feature_identity rows and their facts land
    # in ONE transaction -- committed together here, explicitly, rather
    # than relying only on refresh_current_fact's own internal commit()
    # (which would still merge them correctly, but implicitly). A
    # load_facts failure now rolls back the parcels load_parcels just
    # wrote too, instead of stranding committed, fact-less parcels 0017
    # would then forbid ever removing.
    parcel_ids = load_parcels(conn, selected, snapshot_id, retrieved_at)
    load_facts(conn, selected, parcel_ids, SOURCE_ID, snapshot_id, retrieved_at)
    conn.commit()
    print("  committed: parcels + source_feature_identity + facts together")

    refresh_current_fact(conn)
    # C10: parcel.apn is now stored canonicalized (load_parcels' own fix) --
    # query with the same canonical form, not the raw source value, or a
    # feature whose raw APN needed canonicalizing (leading apostrophe/
    # whitespace) would look up nothing.
    sample_apn = canonicalize_identifier(selected[0]["properties"]["APN"])
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

# Phase B (P4 revision): raised once for every parcel that disappears from
# the bulk parcels snapshot (its source_feature_identity is retired) --
# unconditionally, not only when it happens to carry a zoning.district
# fact. A parcel absent from its own identity source is worth flagging
# whether or not any other source has ever observed it; the exception's
# detail lists whatever other-source facts are currently live so a reader
# can see what's riding on an identity no longer confirmed, without this
# pass touching a single one of them (P4: it used to, wrongly -- see
# NEXT_PROMPTS.md). Distinct detector from
# ingest_zoning_permits.py's zoning_spatial_join_unresolvable: that one
# describes a join-quality problem found DURING a zoning ingest; this one
# describes a parcels-identity problem found during a parcels reconcile,
# with no zoning (or permits) re-ingest involved at all.
#
# version stays "1.0": this detector was never pushed/run for real under
# the P4-revised meaning or the pre-revision one (Phase B, commit 62cf90f,
# was local-only) -- there is no real historical exception data whose
# interpretation this change could make ambiguous, so there is nothing a
# version bump would protect here.
DETECTOR_KEY_PARCEL_DISAPPEARED = "parcel_disappeared_from_source"
DETECTOR_VERSION_PARCEL_DISAPPEARED = "1.0"

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
#
# A THIRD shape exists and is NOT handled here: 5 features carry a
# literal 'XX' prefix (e.g. 'XX000230') -- not a '?' character, so
# is_unresolvable_apn (both before and after routing through
# canonicalize_identifier below) does not catch it; these are stored as
# ordinary resolvable APNs today. Found while measuring Fix 1's real APN
# shapes; recorded here as a finding, deliberately not acted on --
# canonicalize_identifier only strips a leading apostrophe and
# surrounding whitespace (both confirmed raw/canonical representation
# artifacts of the SAME identifier), and 'XX' is a different kind of
# problem (an apparent placeholder token, like '?', not a formatting
# artifact) that wasn't asked for and would need its own investigation
# before a rule is written for it.
#
# is_unresolvable_apn now classifies the CANONICALIZED string, not the
# raw one -- canonicalize_identifier only strips whitespace/apostrophe,
# neither of which changes a real APN into '?'-shaped or blank, or vice
# versa. Confirmed against all 225,039 real features, not assumed: zero
# features' resolvable/unresolvable classification changed.
def is_unresolvable_apn(apn_raw):
    """True if apn_raw cannot be recorded as a resolvable public_record
    observation, once canonicalized. Returns (bool, reason) where reason
    is 'blank' or 'placeholder'."""
    canon = canonicalize_identifier(apn_raw)
    if is_blank(canon):
        return True, "blank"
    if "?" in canon:
        return True, "placeholder"
    return False, None


def finish_job_run_full(conn, job_run_id, status, snapshot_id, rows_in, rows_out, metrics=None):
    # Does NOT commit -- the caller (phase_e) commits this UPDATE together
    # with the ledger rows it describes, in one transaction, so job_run's
    # terminal status can never be observed (or, after a crash, left stuck
    # at 'running') without the facts it claims. See phase_e's own call
    # site and NEXT_PROMPTS.md P1 for why this changed from an
    # independent commit.
    #
    # metrics (0051, README findings #12/#16): phase_e's new/changed/
    # reappeared/disappeared and resolvable/unresolvable-APN breakdowns
    # were computed and printed every run but never persisted -- see the
    # call site below for the exact shape written.
    #
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
                rows_in = %s, rows_out = %s, metrics = %s
            WHERE id = %s
            """,
            (status, snapshot_id, rows_in, rows_out,
             json.dumps(metrics) if metrics is not None else None, job_run_id),
        )


def phase_e(snapshot_id):
    """Full-scale Phase A reconcile. The loader is bound to the supplied
    snapshot_id: it reads snapshot.object_uri, hashes the exact bytes it
    will parse, and refuses if those bytes do not match content_hash.

    One transaction for the entire ledger write (parcel + identity + fact
    + parcel_exception inserts, PLUS job_run's own terminal status update):
    any failure anywhere rolls back everything, leaving no partial state to
    repair. 0017 blocks fact deletion, so a bug discovered after a partial
    COMMIT would be permanent -- the discipline here is to never partially
    commit in the first place, not to clean up afterward. On failure
    (before this commit), the job_run row (already committed by
    start_job_run, a separate transaction) is marked 'failed' -- the
    attempt itself is provenance, C7's policy for Phase B applied here to a
    load, not just a fetch.

    current_fact's refresh runs AFTER this commit and deliberately does
    NOT participate in job_run's status: a refresh failure is read-model
    staleness, not a ledger problem, and must never re-mark a job_run
    'failed' whose ledger write already succeeded. An earlier version of
    this function refreshed current_fact and marked job_run 'succeeded' as
    two separate later steps -- a refresh failure between them left facts
    permanently committed under a job_run stuck at 'failed', which
    previous_successful_snapshot() (status='succeeded' only) then could
    never see as the anchor, permanently wedging every later run against
    the same snapshot. Fixed in this pass; see NEXT_PROMPTS.md P1.

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
    previous_snapshot_id = previous_successful_snapshot(conn, SOURCE_ID)
    path, snapshot = verified_snapshot_file(conn, snapshot_id)
    retrieved_at = snapshot["fetched_at"]
    same_as_previous = previous_snapshot_id == snapshot_id
    print(f"using verified snapshot: {snapshot_id}")
    print(f"previous successful snapshot: {previous_snapshot_id or '(none)'}")
    print(f"same as immediately previous successful observation: {same_as_previous}")

    job_run_id = start_job_run(conn, job_key=JOB_KEY_FULL)

    # Captured once, explicitly, and reused for every "this reconciliation
    # happened now" timestamp below (fact.superseded_at,
    # source_feature_identity.retired_at) -- not a separate clock_timestamp()
    # per write. retrieved_at (the SNAPSHOT's own fetch time, set once when
    # the snapshot row was inserted) is never reused for this: it can be
    # long past, and source_feature_identity_retired_after_seen requires
    # retired_at >= last_seen_at, which retrieved_at cannot be trusted to
    # satisfy.
    with conn.cursor() as cur:
        cur.execute("SELECT clock_timestamp()")
        reconcile_at = cur.fetchone()[0]

    t_parse_start = time.monotonic()

    parcel_rows = []
    fact_rows = []
    exception_rows = []
    rows_in = 0
    resolvable_count = 0
    unresolvable_count = 0
    reason_counts = {"blank": 0, "placeholder": 0}
    identity_by_feature_id = {}
    identity_rows_to_insert = []

    # Phase B additions -- populated only on the reconciliation path
    # (same_as_previous is False). See ingest_parcels.py's Phase B report
    # (NEXT_PROMPTS.md) for the design this implements.
    fact_ids_to_supersede = []              # bulk UPDATE target, retired BEFORE any successor INSERT
    parcel_apn_cache_updates = []           # (parcel_id, new_apn) -- parcel.apn cache (0034)
    parcel_geom_cache_updates = []          # (parcel_id, geometry_json) -- parcel.geom/centroid cache
    identity_retirements = []               # (source_id, source_feature_id, retired_snapshot_id, retired_at, retirement_reason)
    identity_touch_updates = []             # (source_id, source_feature_id, last_seen_snapshot_id, last_seen_at, was_reappearing)
    apn_resolved_parcel_ids = []            # P13: parcels whose APN just became resolvable -- close their open parcel_apn_unresolvable exception
    reappeared_parcel_ids = []              # C5 (P59): parcels un-retired this run -- close their open parcel_disappeared_from_source exception
    changed_count = 0
    changed_field_counts = {"parcel.apn": 0, "parcel.geometry": 0}
    new_count = 0
    reappeared_count = 0
    disappeared_count = 0

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_feature_id, parcel_id
                FROM source_feature_identity
                WHERE source_id = %s
                  AND retired_at IS NULL
                """,
                (SOURCE_ID,),
            )
            identity_by_feature_id = {source_feature_id: str(parcel_id) for source_feature_id, parcel_id in cur.fetchall()}

        if same_as_previous:
            # Identical bytes to the last successfully-reconciled snapshot
            # (previous_successful_snapshot() confirmed it, per the P1 fix,
            # durably and correctly). Same bytes in can only mean the same
            # facts out -- verifying identity presence is sufficient to
            # prove that without paying for a full value-by-value database
            # diff. This is the ONLY case that still skips the Phase B
            # reconciliation pass below; any genuine snapshot change goes
            # through it.
            #
            # C19 (P59): this loop used to check only is_blank(pid_raw) --
            # identity_by_feature_id (queried above) was built and never
            # read, so the comment's claim ("verifying identity presence")
            # was not actually being checked; a feature with a real,
            # non-blank PARCELID but no matching active identity row would
            # silently pass. Now checked directly: every feature's PARCELID
            # must resolve to an active source_feature_identity row, since
            # same_as_previous means this exact content already went
            # through a successful reconciliation that would have written
            # one. Only one direction needs checking -- byte-identical
            # content already guarantees the reverse (an identity row with
            # no matching feature here) can't happen.
            with open(path, "rb") as f:
                for feat in ijson.items(f, "features.item"):
                    rows_in += 1
                    props = feat.get("properties") or {}
                    pid_raw = props.get("PARCELID")
                    if is_blank(pid_raw):
                        raise RuntimeError(f"feature {rows_in} has blank PARCELID; cannot reconcile identity")
                    source_feature_id = str(pid_raw)
                    if source_feature_id not in identity_by_feature_id:
                        raise RuntimeError(
                            f"feature {rows_in} (PARCELID {source_feature_id!r}) has no active "
                            f"source_feature_identity row, but same_as_previous claims this "
                            f"snapshot is byte-identical to the last successfully-reconciled one -- "
                            f"every feature in a successfully-reconciled snapshot must already have "
                            f"one. Refusing rather than silently skipping the identity verification "
                            f"this fast path exists to perform."
                        )
                    if rows_in % 25000 == 0:
                        print(f"  ...verified unchanged identity for {rows_in:,} features")
            t_parse_end = time.monotonic()
            print(f"\nparse complete: {rows_in:,} features in {t_parse_end - t_parse_start:.1f}s "
                  f"(same_as_previous -- verified identity only, no reconciliation needed)")

        else:
            # Phase B reconciliation. Stage every incoming feature and let
            # Postgres compute the changed/new/disappeared sets -- "set
            # difference must run in the database, not in Python" (report
            # 1(d)). staging is a TEMP TABLE inside this same transaction,
            # same precedent as ingest_zoning_permits.py's zoning_staging:
            # holds no durable domain truth, rolls back for free with
            # everything else if this transaction never commits.
            staging_rows = []
            with open(path, "rb") as f:
                for feat in ijson.items(f, "features.item"):
                    rows_in += 1
                    props = feat.get("properties") or {}
                    apn_raw = props.get("APN")
                    pid_raw = props.get("PARCELID")
                    if is_blank(pid_raw):
                        raise RuntimeError(f"feature {rows_in} has blank PARCELID; cannot reconcile identity")
                    source_feature_id = str(pid_raw)
                    staging_rows.append((
                        source_feature_id, apn_raw, canonicalize_identifier(apn_raw),
                        geojson_geom_param(feat), feat,
                    ))
                    if rows_in % 25000 == 0:
                        print(f"  ...parsed {rows_in:,} features")

            staging_by_feature_id = {r[0]: r for r in staging_rows}
            t_parse_end = time.monotonic()
            print(f"\nparse complete: {rows_in:,} features in {t_parse_end - t_parse_start:.1f}s")

            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TEMP TABLE parcels_incoming_staging (
                        source_feature_id text PRIMARY KEY,
                        apn_canonical      text,
                        geometry_json      jsonb
                    )
                """)
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO parcels_incoming_staging (source_feature_id, apn_canonical, geometry_json) VALUES %s",
                    [(r[0], r[2], r[3]) for r in staging_rows],
                    template="(%s, %s, %s::jsonb)",
                    page_size=2000,
                )

                # NEW: incoming features with NO identity row at all, ever
                # (not "no LIVE row" -- source_feature_identity's primary
                # key is (source_id, source_feature_id), so a feature that
                # disappeared and reappeared already owns a row, just a
                # retired one; INSERTing a second row for it would violate
                # that PK. That case is EXISTING_OR_REAPPEARING below, not
                # NEW.)
                cur.execute("""
                    SELECT s.source_feature_id FROM parcels_incoming_staging s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM source_feature_identity sfi
                        WHERE sfi.source_id = %s AND sfi.source_feature_id = s.source_feature_id
                    )
                """, (SOURCE_ID,))
                new_feature_ids = {r[0] for r in cur.fetchall()}

                # DISAPPEARED: live identity rows with no incoming feature.
                cur.execute("""
                    SELECT sfi.source_feature_id, sfi.parcel_id FROM source_feature_identity sfi
                    WHERE sfi.source_id = %s AND sfi.retired_at IS NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM parcels_incoming_staging s
                          WHERE s.source_feature_id = sfi.source_feature_id
                      )
                """, (SOURCE_ID,))
                disappeared_rows = cur.fetchall()

                # EXISTING_OR_REAPPEARING: any identity row (live OR
                # retired) matching an incoming feature. sfi.retired_at is
                # selected so Python can tell a plain value-change apart
                # from a reappearance that also needs the identity
                # un-retired. parcel.apn/geometry facts are never touched
                # on disappearance (see the DISAPPEARED write section
                # below), so they're still there, un-superseded, to
                # compare against even for a currently-retired identity.
                #
                # fa (parcel.apn) is a LEFT JOIN -- P13 (findings #17/#22):
                # a feature with no live parcel.apn fact (every currently-
                # unresolvable parcel) used to be dropped by an INNER JOIN
                # here entirely, silently losing its GEOMETRY changes too
                # and making a resolvability flip back to a real value
                # undetectable. fg (parcel.geometry) stays INNER: every
                # parcel gets a parcel.geometry fact unconditionally (NEW
                # branch above), resolvable or not, so it is never absent.
                #
                # The apn-changed predicate is NOT the same expression as
                # before for fa IS NULL rows -- worked out for all four
                # (fact present/absent x incoming resolvable/unresolvable)
                # combinations, not assumed:
                #   fact present,  incoming resolvable:   plain value compare (unchanged from before)
                #   fact present,  incoming unresolvable:  fa.value (a real string) is never NULL nor
                #                                           equal to a placeholder/blank -- always
                #                                           IS DISTINCT FROM -- correctly TRUE (degrade
                #                                           detected, #22)
                #   fact absent,   incoming resolvable:    apn_canonical NOT NULL and not a '?'-shaped
                #                                           placeholder -- TRUE (resolve detected, #17)
                #   fact absent,   incoming unresolvable:  FALSE, explicitly -- a bare `fa.value (NULL)
                #                                           IS DISTINCT FROM to_jsonb(s.apn_canonical)`
                #                                           would be TRUE here (NULL is always distinct
                #                                           from non-NULL) and wrongly flag an unchanged,
                #                                           still-unresolvable parcel as changed on every
                #                                           run it merely happens to also match this
                #                                           query for (e.g. a real geometry change) --
                #                                           the CASE below exists specifically to make
                #                                           this fourth combination FALSE.
                cur.execute("""
                    SELECT s.source_feature_id, sfi.parcel_id, sfi.retired_at,
                           fa.id, fa.value, s.apn_canonical,
                           fg.id, fg.value, s.geometry_json
                    FROM parcels_incoming_staging s
                    JOIN source_feature_identity sfi
                      ON sfi.source_id = %s AND sfi.source_feature_id = s.source_feature_id
                    LEFT JOIN fact fa ON fa.parcel_id = sfi.parcel_id AND fa.field_key = 'parcel.apn' AND fa.superseded_at IS NULL AND fa.source_id = %s
                    JOIN fact fg ON fg.parcel_id = sfi.parcel_id AND fg.field_key = 'parcel.geometry' AND fg.superseded_at IS NULL AND fg.source_id = %s
                    WHERE sfi.retired_at IS NOT NULL
                       OR (CASE WHEN fa.id IS NOT NULL
                                THEN fa.value IS DISTINCT FROM to_jsonb(s.apn_canonical)
                                ELSE s.apn_canonical IS NOT NULL AND s.apn_canonical NOT LIKE '%%?%%'
                           END)
                       OR fg.value IS DISTINCT FROM s.geometry_json
                """, (SOURCE_ID, SOURCE_ID, SOURCE_ID))
                changed_rows = cur.fetchall()

            reappeared_count_query = sum(1 for r in changed_rows if r[2] is not None)
            print(f"  new: {len(new_feature_ids):,}  disappeared: {len(disappeared_rows):,}  "
                  f"changed-or-reappeared: {len(changed_rows):,} (of which reappeared: {reappeared_count_query:,})")

            # --- NEW: parcel + source_feature_identity + initial facts. No supersession. ---
            for source_feature_id in new_feature_ids:
                _, apn_raw, canon_apn, geometry_json, feat = staging_by_feature_id[source_feature_id]
                unresolvable, reason = is_unresolvable_apn(apn_raw)
                parcel_id = str(uuid.uuid4())
                stored_apn = None if unresolvable else canon_apn

                parcel_rows.append((parcel_id, JURISDICTION_ID, stored_apn, geojson_geom_param(feat)))
                identity_rows_to_insert.append((
                    SOURCE_ID, source_feature_id, parcel_id,
                    snapshot_id, retrieved_at, snapshot_id, retrieved_at,
                ))
                fact_rows.append(Fact(
                    parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                    field_key="parcel.geometry", value=geojson_geom_param(feat), method="bulk",
                    source_id=SOURCE_ID, snapshot_id=snapshot_id, retrieved_at=retrieved_at,
                    source_url=ENDPOINT_URL, licence_id=LICENCE_ID, confidence=FACT_CONFIDENCE,
                    confidence_rule_id=FACT_CONFIDENCE_RULE_ID, effective_from=retrieved_at,
                    pack_version=FACT_PACK_VERSION,
                ))
                fact_rows.append(Fact(
                    parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                    field_key="parcel.source_parcel_id", value=json.dumps(source_feature_id), method="bulk",
                    source_id=SOURCE_ID, snapshot_id=snapshot_id, retrieved_at=retrieved_at,
                    source_url=ENDPOINT_URL, licence_id=LICENCE_ID, confidence=FACT_CONFIDENCE,
                    confidence_rule_id=FACT_CONFIDENCE_RULE_ID, effective_from=retrieved_at,
                    pack_version=FACT_PACK_VERSION,
                ))
                if unresolvable:
                    unresolvable_count += 1
                    reason_counts[reason] += 1
                    exception_rows.append(ParcelException(
                        parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID, type="coverage_gap", severity="info",
                        detector_key=DETECTOR_KEY_APN_UNRESOLVABLE, detector_version=DETECTOR_VERSION_APN_UNRESOLVABLE,
                        detail={"raw_apn": apn_raw, "reason": reason},
                    ))
                else:
                    resolvable_count += 1
                    fact_rows.append(Fact(
                        parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                        field_key="parcel.apn", value=json.dumps(canon_apn), method="bulk",
                        source_id=SOURCE_ID, snapshot_id=snapshot_id, retrieved_at=retrieved_at,
                        source_url=ENDPOINT_URL, licence_id=LICENCE_ID, confidence=FACT_CONFIDENCE,
                        confidence_rule_id=FACT_CONFIDENCE_RULE_ID, effective_from=retrieved_at,
                        pack_version=FACT_PACK_VERSION, local_verbatim=apn_raw,
                    ))
                new_count += 1

            # --- CHANGED: supersede current fact(s), insert successor(s) with
            # supersedes_fact_id + supersession_reason='unknown' (0042's
            # parcel/field-match and target-retirement checks apply and were
            # verified directly -- see the Phase B report). Only the field(s)
            # that actually differ get superseded; a feature with the same
            # apn but a moved geometry is one row here but only ONE field
            # changes. ---
            for (source_feature_id, parcel_id, sfi_retired_at, apn_fact_id, apn_current_value, apn_incoming,
                 geom_fact_id, geom_current_value, geom_incoming) in changed_rows:
                _, apn_raw, canon_apn, geometry_json, feat = staging_by_feature_id[source_feature_id]

                # A feature that disappeared and reappeared owns its
                # original identity row (PK is (source_id, source_feature_id),
                # so it can't be re-INSERTed) -- un-retire it and refresh
                # last_seen, reusing the SAME parcel_id and SAME un-superseded
                # apn/geometry facts it always had. Every row reaching this
                # loop gets its last_seen_snapshot_id/last_seen_at bumped,
                # reappearing or not -- it was just freshly observed in this
                # snapshot. (A truly unchanged, never-retired feature that
                # ISN'T in changed_rows at all does NOT get last_seen bumped
                # by this pass -- a known, deliberate scope limit; see the
                # Phase B report.)
                identity_touch_updates.append((
                    SOURCE_ID, source_feature_id, snapshot_id, retrieved_at,
                    sfi_retired_at is not None,
                ))
                if sfi_retired_at is not None:
                    reappeared_count += 1
                    reappeared_parcel_ids.append(parcel_id)

                # psycopg2 hands back jsonb columns already decoded to a
                # Python value (apn_current_value is a plain str, not a
                # '"..."'-quoted JSON string) -- compare decoded-to-decoded,
                # not string forms.
                #
                # P13 (findings #17/#22): apn_fact_id is None whenever this
                # parcel currently has no live parcel.apn fact (LEFT JOIN
                # above) -- the plain != compare below only makes sense when
                # a real fa.value exists to compare against. Mirrors the
                # SQL CASE in the query above exactly, combination for
                # combination -- see that comment for the four-way
                # derivation.
                had_live_apn_fact = apn_fact_id is not None
                incoming_unresolvable, incoming_unresolvable_reason = is_unresolvable_apn(apn_raw)
                if had_live_apn_fact:
                    apn_changed = (apn_current_value != apn_incoming)
                else:
                    apn_changed = not incoming_unresolvable
                geom_changed = (geom_current_value != geom_incoming)

                if apn_changed:
                    changed_field_counts["parcel.apn"] += 1
                    if had_live_apn_fact and incoming_unresolvable:
                        # Degrade: resolvable -> '?'-placeholder or blank
                        # (#22). Supersede with NO successor -- db/README.md:
                        # "Ingest code must not write a parcel.apn fact for
                        # either case." -- and raise the same
                        # coverage_gap/parcel_apn_unresolvable exception the
                        # NEW branch already raises for a feature that was
                        # never resolvable, reusing its detector_key/version
                        # rather than inventing a second detector for the
                        # same condition. parcel.apn cache -> NULL (0034: no
                        # fact means no cache value), via the same
                        # parcel_apn_cache_updates UPDATE every other cache
                        # write already goes through -- no second write path.
                        fact_ids_to_supersede.append(apn_fact_id)
                        parcel_apn_cache_updates.append((parcel_id, None))
                        exception_rows.append(ParcelException(
                            parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID, type="coverage_gap", severity="info",
                            detector_key=DETECTOR_KEY_APN_UNRESOLVABLE, detector_version=DETECTOR_VERSION_APN_UNRESOLVABLE,
                            detail={"raw_apn": apn_raw, "reason": incoming_unresolvable_reason},
                        ))
                        unresolvable_count += 1
                        reason_counts[incoming_unresolvable_reason] += 1
                    elif had_live_apn_fact:
                        # Ordinary resolvable -> different resolvable value.
                        # Unchanged from before P13.
                        fact_ids_to_supersede.append(apn_fact_id)
                        fact_rows.append(Fact(
                            parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                            field_key="parcel.apn", value=json.dumps(canon_apn), method="bulk",
                            source_id=SOURCE_ID, snapshot_id=snapshot_id, retrieved_at=retrieved_at,
                            source_url=ENDPOINT_URL, licence_id=LICENCE_ID, confidence=FACT_CONFIDENCE,
                            confidence_rule_id=FACT_CONFIDENCE_RULE_ID, effective_from=retrieved_at,
                            pack_version=FACT_PACK_VERSION, local_verbatim=apn_raw,
                            supersedes_fact_id=apn_fact_id, supersession_reason="unknown",
                        ))
                        parcel_apn_cache_updates.append((parcel_id, canon_apn))
                        resolvable_count += 1
                    else:
                        # Resolve (#17): no live fact to supersede -- this is
                        # a NEW fact (supersedes_fact_id/supersession_reason
                        # both NULL), not a successor. The parcel may be
                        # resolving for the first time ever, or resolving
                        # again after a prior degrade; either way there is
                        # nothing live to retire. Collected here, closed in
                        # one batch after the write loop (targeted close, not
                        # close_resolved_exceptions' full-recompute sweep --
                        # see that call site's own comment for why).
                        fact_rows.append(Fact(
                            parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                            field_key="parcel.apn", value=json.dumps(canon_apn), method="bulk",
                            source_id=SOURCE_ID, snapshot_id=snapshot_id, retrieved_at=retrieved_at,
                            source_url=ENDPOINT_URL, licence_id=LICENCE_ID, confidence=FACT_CONFIDENCE,
                            confidence_rule_id=FACT_CONFIDENCE_RULE_ID, effective_from=retrieved_at,
                            pack_version=FACT_PACK_VERSION, local_verbatim=apn_raw,
                        ))
                        parcel_apn_cache_updates.append((parcel_id, canon_apn))
                        apn_resolved_parcel_ids.append(parcel_id)
                        resolvable_count += 1

                if geom_changed:
                    fact_ids_to_supersede.append(geom_fact_id)
                    fact_rows.append(Fact(
                        parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                        field_key="parcel.geometry", value=geojson_geom_param(feat), method="bulk",
                        source_id=SOURCE_ID, snapshot_id=snapshot_id, retrieved_at=retrieved_at,
                        source_url=ENDPOINT_URL, licence_id=LICENCE_ID, confidence=FACT_CONFIDENCE,
                        confidence_rule_id=FACT_CONFIDENCE_RULE_ID, effective_from=retrieved_at,
                        pack_version=FACT_PACK_VERSION,
                        supersedes_fact_id=geom_fact_id, supersession_reason="unknown",
                    ))
                    parcel_geom_cache_updates.append((parcel_id, geojson_geom_param(feat)))
                    changed_field_counts["parcel.geometry"] += 1

                # 1(c)'s definition is "at least one field's value differs" --
                # a row that's here ONLY because it reappeared (identity was
                # retired, but apn/geometry are byte-identical to before)
                # does not count as changed.
                if apn_changed or geom_changed:
                    changed_count += 1

            # --- DISAPPEARED: retire identity; raise ONE exception. That is
            # ALL. P4 finding: the previous version of this pass also wrote
            # a permits.active=false successor and superseded zoning.district
            # -- both carrying SOURCE_ID/snapshot_id/ENDPOINT_URL/LICENCE_ID
            # from ca_san_jose.parcels. A parcel absent from the PARCELS
            # snapshot is not evidence about permit status and not evidence
            # about zoning; it is only evidence that the parcels source no
            # longer confirms this parcel. The comment that used to sit here
            # already said as much about geometry/apn/source_parcel_id --
            # this pass now applies the same reasoning to every other-source
            # field, not just this source's own.
            #
            # Type/reason, argued: exception_type has no dedicated "identity
            # no longer confirmed" bucket. coverage_gap (used elsewhere in
            # this file) means "we lack a value" -- wrong here, values exist,
            # some from other sources, and are not being touched. cross_source
            # means sources disagree -- wrong, nothing here conflicts with
            # anything. record_to_ground is the fit: whether a ledger record
            # still corresponds to a real, currently-observable thing is
            # exactly what "record to ground" asks, and losing the
            # authoritative identity source's confirmation is precisely
            # that question going unanswered. severity='warning', not 'info'
            # (coverage_gap's usual level elsewhere in this file): unlike an
            # unresolved APN or an unmatched zoning join, this parcel may
            # still have LIVE facts from other sources that a consumer could
            # mistake for still-current-and-confirmed if this exception goes
            # unnoticed.
            if disappeared_rows:
                disappeared_parcel_ids = [pid for _, pid in disappeared_rows]
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT parcel_id, field_key, source_id FROM fact
                        WHERE parcel_id = ANY(%s::uuid[]) AND superseded_at IS NULL
                    """, (disappeared_parcel_ids,))
                    live_facts_by_parcel = {}
                    for pid, field_key, source_id in cur.fetchall():
                        live_facts_by_parcel.setdefault(pid, []).append(
                            {"field_key": field_key, "source_id": source_id})

                    # C5 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): first
                    # disappearance opened this exception with NO existing-
                    # open dedup guard at all. A parcel that disappears,
                    # reappears, then disappears again (a real flap, not a
                    # hypothetical -- the phase-B acceptance suite's own
                    # A->B->A sequence produces exactly this shape) hits
                    # this branch a second time while its first exception
                    # is STILL open (nothing ever closed it -- see the
                    # reappearance-closure fix below), and the bare INSERT
                    # in core.exceptions.insert_exceptions violates 0045/
                    # 0049's partial unique index on open exceptions --
                    # UniqueViolation, rolling back the ENTIRE single-
                    # transaction reconcile (all 225k parcels' updates) and
                    # failing the job_run, on every retry, until a human
                    # closes the row by hand. Dedup here, consistent with
                    # 0045/0049's own partial unique index shape (parcel_id,
                    # detector_key, detector_version, COALESCE(detail->>
                    # 'reason', '')) -- NOT a broadened index (this repo's
                    # own CLAUDE.md/CONVENTIONS position: never change a
                    # constraint to make something pass).
                    cur.execute("""
                        SELECT parcel_id FROM parcel_exception
                        WHERE parcel_id = ANY(%s::uuid[])
                          AND detector_key = %s AND detector_version = %s
                          AND outcome = 'open'
                    """, (disappeared_parcel_ids, DETECTOR_KEY_PARCEL_DISAPPEARED, DETECTOR_VERSION_PARCEL_DISAPPEARED))
                    existing_open_disappeared = {r[0] for r in cur.fetchall()}

                for source_feature_id, parcel_id in disappeared_rows:
                    identity_retirements.append((
                        SOURCE_ID, source_feature_id, snapshot_id, reconcile_at,
                        "parcel_absent_from_bulk_parcels_snapshot",
                    ))
                    disappeared_count += 1

                    if parcel_id in existing_open_disappeared:
                        continue

                    exception_rows.append(ParcelException(
                        parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID, type="record_to_ground", severity="warning",
                        detector_key=DETECTOR_KEY_PARCEL_DISAPPEARED, detector_version=DETECTOR_VERSION_PARCEL_DISAPPEARED,
                        detail={
                            "reason": "parcel_absent_from_source_snapshot",
                            "source_feature_id": source_feature_id,
                            "live_facts_from_other_sources": live_facts_by_parcel.get(parcel_id, []),
                        },
                    ))

        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_rss_mb = peak_rss / (1024 * 1024) if sys.platform == "darwin" else peak_rss / 1024
        print(f"  peak RSS {peak_rss_mb:.1f} MB")
        print(f"  new: {new_count:,}  changed: {changed_count:,} "
              f"(apn={changed_field_counts['parcel.apn']:,}, geometry={changed_field_counts['parcel.geometry']:,})  "
              f"reappeared: {reappeared_count:,}  "
              f"disappeared: {disappeared_count:,} (record_to_ground exception raised, no cross-source writes)")
        print(f"  resolvable APN: {resolvable_count:,}  unresolvable: {unresolvable_count:,} "
              f"(blank={reason_counts['blank']}, placeholder={reason_counts['placeholder']})")
        print(f"  parcel rows to insert: {len(parcel_rows):,}")
        print(f"  fact rows to insert: {len(fact_rows):,}")
        print(f"  parcel_exception rows to insert: {len(exception_rows):,}")
        print(f"  fact ids to supersede: {len(fact_ids_to_supersede):,}")

        # cur.rowcount after execute_values reflects only the LAST internal
        # page (execute_values splits page_size-row chunks into separate
        # statements), not the cumulative total -- confirmed directly, not
        # assumed: a 2,020-row smoketest insert reported cur.rowcount == 20
        # (the trailing partial page) while count(*) in the database showed
        # the correct 2,020. Report len() of the Python lists we already
        # built instead; they are what was actually submitted.
        t_load_start = time.monotonic()
        with conn.cursor() as cur:
            if parcel_rows:
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO parcel (id, jurisdiction_id, apn, geom) VALUES %s",
                    parcel_rows,
                    template="(%s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))",
                    page_size=2000,
                )
            print(f"  parcel rows submitted: {len(parcel_rows):,}")

            if identity_rows_to_insert:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO source_feature_identity (
                        source_id, source_feature_id, parcel_id,
                        first_seen_snapshot_id, first_seen_at,
                        last_seen_snapshot_id, last_seen_at
                    ) VALUES %s
                    """,
                    identity_rows_to_insert,
                    page_size=2000,
                )
            print(f"  source_feature_identity rows submitted: {len(identity_rows_to_insert):,}")

            # MUST run before insert_facts() below: fact_one_current_per_source
            # is a plain unique INDEX (not a deferrable constraint -- checked
            # immediately, per statement, no deferral available), so a
            # successor row with the same (parcel_id, field_key, source_id,
            # method_version) key as one of these targets would violate it
            # if its predecessor weren't already retired. This is one single
            # UPDATE statement -- by the time it returns, every targeted row
            # is retired in this transaction, before the INSERT below runs.
            # Verified directly (Phase B report 1(b)): this order succeeds;
            # the reverse order raises fact_one_current_per_source for real.
            if fact_ids_to_supersede:
                cur.execute(
                    "UPDATE fact SET superseded_at = %s WHERE id = ANY(%s::uuid[]) AND superseded_at IS NULL",
                    (reconcile_at, fact_ids_to_supersede),
                )
            print(f"  facts superseded: {len(fact_ids_to_supersede):,}")

            if fact_rows:
                insert_facts(cur, fact_rows)
            print(f"  fact rows submitted: {len(fact_rows):,}")

            # P13: close before insert, same reasoning as P9's load_zoning
            # call site -- a given parcel_id can never be both "just
            # resolved" (closed here) and "freshly unresolvable, needs a
            # new open row" (inserted below) in the SAME run, since each
            # parcel_id appears at most once in changed_rows, but closing
            # first keeps the write order consistent with how it's reasoned
            # about regardless.
            if apn_resolved_parcel_ids:
                apn_closed_count = close_exceptions_for_parcels(
                    cur, DETECTOR_KEY_APN_UNRESOLVABLE, DETECTOR_VERSION_APN_UNRESOLVABLE, apn_resolved_parcel_ids
                )
                print(f"  parcel_apn_unresolvable exceptions closed (condition_cleared): {apn_closed_count:,}")

            # C5 (P59): the other half of the dedup guard above -- a
            # reappeared parcel's open parcel_disappeared_from_source
            # exception is closed here, using the SAME helper the APN
            # detector just used two lines up, not a second hand-rolled
            # closure. Without this, the dedup guard alone would leave a
            # reappeared-then-disappeared-again parcel's FIRST exception
            # open forever (skipped by the guard, never replaced), silently
            # under-reporting a second, real disappearance.
            if reappeared_parcel_ids:
                disappeared_closed_count = close_exceptions_for_parcels(
                    cur, DETECTOR_KEY_PARCEL_DISAPPEARED, DETECTOR_VERSION_PARCEL_DISAPPEARED, reappeared_parcel_ids
                )
                print(f"  parcel_disappeared_from_source exceptions closed (condition_cleared): {disappeared_closed_count:,}")

            if exception_rows:
                insert_exceptions(cur, exception_rows)
                print(f"  parcel_exception rows submitted: {len(exception_rows):,}")
                # Only ever touches rows at DETECTOR_KEY_APN_UNRESOLVABLE
                # (filtered by detector_key/version internally) -- safe to
                # call even though exception_rows may also carry
                # record_to_ground (DISAPPEARED) or NEW-branch coverage_gap
                # rows for other parcels in the same batch.
                apn_relinked_count = relink_reopened_exceptions(
                    cur, DETECTOR_KEY_APN_UNRESOLVABLE, DETECTOR_VERSION_APN_UNRESOLVABLE
                )
                print(f"  parcel_apn_unresolvable exceptions relinked (reopened_from_id): {apn_relinked_count:,}")

            # parcel.apn / parcel.geom / parcel.centroid are non-authoritative
            # caches of the fact ledger (0034) -- kept in sync here so a
            # later zoning spatial join (parcel.centroid IS NULL trigger in
            # load_zoning) recomputes against the new geometry rather than
            # silently joining on stale coordinates. centroid is reset to
            # NULL, not recomputed here -- that recomputation is
            # load_zoning's own job, unchanged by this pass.
            if parcel_apn_cache_updates:
                psycopg2.extras.execute_values(
                    cur,
                    "UPDATE parcel AS p SET apn = v.apn FROM (VALUES %s) AS v(id, apn) WHERE p.id = v.id::uuid",
                    parcel_apn_cache_updates,
                    template="(%s::uuid, %s)",
                    page_size=2000,
                )
            if parcel_geom_cache_updates:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    UPDATE parcel AS p SET geom = ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(v.geom), 4326)), centroid = NULL
                    FROM (VALUES %s) AS v(id, geom)
                    WHERE p.id = v.id::uuid
                    """,
                    parcel_geom_cache_updates,
                    template="(%s::uuid, %s)",
                    page_size=2000,
                )
            print(f"  parcel cache columns updated: apn={len(parcel_apn_cache_updates):,} geom={len(parcel_geom_cache_updates):,}")

            # DISAPPEARED identities retired last -- order doesn't matter
            # relative to the writes above (no shared unique index), but
            # doing it after the cascade facts/exceptions that reference
            # these parcel_ids keeps the transaction's writes in the same
            # order they were reasoned about.
            if identity_retirements:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    UPDATE source_feature_identity AS sfi
                    SET retired_snapshot_id = v.retired_snapshot_id,
                        retired_at = v.retired_at,
                        retirement_reason = v.retirement_reason
                    FROM (VALUES %s) AS v(source_id, source_feature_id, retired_snapshot_id, retired_at, retirement_reason)
                    WHERE sfi.source_id = v.source_id AND sfi.source_feature_id = v.source_feature_id
                    """,
                    identity_retirements,
                    template="(%s, %s, %s, %s::timestamptz, %s)",
                    page_size=2000,
                )
            print(f"  source_feature_identity rows retired: {len(identity_retirements):,}")

            # EXISTING_OR_REAPPEARING identities: refresh last_seen always;
            # un-retire (clear retired_snapshot_id/retired_at/retirement_reason
            # together, per source_feature_identity_retirement_pairing --
            # 0043 -- all three or none) only for rows that were actually
            # retired. A plain CASE keeps this one statement instead of two
            # separate UPDATEs branching on was_reappearing.
            if identity_touch_updates:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    UPDATE source_feature_identity AS sfi
                    SET last_seen_snapshot_id = v.last_seen_snapshot_id,
                        last_seen_at = v.last_seen_at,
                        retired_snapshot_id = CASE WHEN v.was_reappearing THEN NULL ELSE sfi.retired_snapshot_id END,
                        retired_at = CASE WHEN v.was_reappearing THEN NULL ELSE sfi.retired_at END,
                        retirement_reason = CASE WHEN v.was_reappearing THEN NULL ELSE sfi.retirement_reason END
                    FROM (VALUES %s) AS v(source_id, source_feature_id, last_seen_snapshot_id, last_seen_at, was_reappearing)
                    WHERE sfi.source_id = v.source_id AND sfi.source_feature_id = v.source_feature_id
                    """,
                    identity_touch_updates,
                    template="(%s, %s, %s, %s::timestamptz, %s)",
                    page_size=2000,
                )
            print(f"  source_feature_identity rows touched (last_seen refreshed, {reappeared_count:,} un-retired): "
                  f"{len(identity_touch_updates):,}")
        t_load_end = time.monotonic()
        print(f"  bulk insert wall-clock: {t_load_end - t_load_start:.1f}s")

        # One ledger transaction: parcel/identity/fact/exception writes AND
        # job_run's terminal status commit together, in this one
        # conn.commit() below. This is the fix for the refresh-failure hole
        # (NEXT_PROMPTS.md P1): previously, job_run was marked 'succeeded'
        # in its own commit AFTER current_fact's refresh, so a refresh
        # failure left the ledger permanently committed (0017 forbids
        # deletion) under a job_run stuck at 'failed' -- previous_
        # successful_snapshot() would then never see this snapshot as the
        # anchor, and the next run on the same snapshot would misread
        # already-correct, already-committed data as "changed since the
        # last successful observation" and refuse to proceed, forever.
        # Folding the status UPDATE into this same commit means
        # previous_successful_snapshot() reflects the ledger the instant it
        # is durable, regardless of what happens to the read-model refresh
        # afterward.
        metrics = {
            "new": new_count,
            "changed": changed_count,
            "changed_fields": changed_field_counts,
            "reappeared": reappeared_count,
            "disappeared": disappeared_count,
            "apn_resolvable": resolvable_count,
            "apn_unresolvable": unresolvable_count,
            "apn_unresolvable_reasons": reason_counts,
        }
        finish_job_run_full(conn, job_run_id, "succeeded", snapshot_id, rows_in, len(parcel_rows), metrics)
        conn.commit()
        print(f"\njob_run {job_run_id} -> succeeded (ledger committed)")

    except Exception as e:
        conn.rollback()
        fail_job_run(conn, job_run_id, e)
        print(f"\njob_run {job_run_id} -> failed: {e}")
        raise
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    # Ledger and job_run status are durably committed above. current_fact's
    # refresh is now a separate, best-effort step: its failure is a
    # read-model staleness problem, not a ledger problem, and must NEVER
    # flip job_run back to 'failed' -- doing that is exactly the bug this
    # fix closes. Report it loudly and exit non-zero so an operator
    # notices and retries; re-running phase_e against this same
    # snapshot_id is safe when that happens -- source_feature_identity
    # already has these features recorded, previous_successful_snapshot()
    # already points at this snapshot, so the rerun verifies everything as
    # unchanged (no ledger writes) and simply retries the refresh.
    try:
        refresh_current_fact(conn)
    except Exception as e:
        print(f"\ncurrent_fact refresh FAILED after job_run {job_run_id} succeeded "
              f"(ledger is complete and correct; only the read model is stale -- "
              f"re-run phase_e against this snapshot_id to retry the refresh): {e}",
              file=sys.stderr)
        conn.close()
        raise

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["b", "c", "d", "e"])
    parser.add_argument("--input-file", help="path to a previously-fetched GeoJSON file, for --phase c")
    parser.add_argument("--snapshot-id", help="snapshot id to load for --phase d/e")
    args = parser.parse_args()

    if args.phase == "b":
        phase_b()
    elif args.phase == "c":
        path = args.input_file or os.path.join(SCRATCHPAD, "parcels_fetch_1.geojson")
        phase_c(path)
    elif args.phase == "d":
        # P45 Fix 1: no default "newest" guess -- matches --phase e's own
        # existing precondition exactly. See phase_d()'s own docstring.
        if not args.snapshot_id:
            raise SystemExit("--phase d requires --snapshot-id; loads must bind to an immutable snapshot row")
        phase_d(args.snapshot_id)
    elif args.phase == "e":
        if not args.snapshot_id:
            raise SystemExit("--phase e requires --snapshot-id; loads must bind to an immutable snapshot row")
        phase_e(args.snapshot_id)
    else:
        print("pass --phase b, c, d, or e", file=sys.stderr)
        sys.exit(1)
