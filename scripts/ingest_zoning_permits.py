#!/usr/bin/env python3
"""Second and third ingestions: zoning_districts and building_permits_active.

A SEPARATE script from scripts/ingest_parcels.py, not a shared module --
core/connectors doesn't exist yet and module boundaries should be
extracted from three working ingests, not designed after one (this is
the second and third). The plumbing below is COPIED from
ingest_parcels.py, not imported, deliberately: fetch_and_hash,
start_job_run/fail_job_run/finish_job_run, the snapshot exists/insert/
dedupe-proof pattern inside run_one_fetch, the client-generated-UUID
batch-insert shape, and the geojson_geom_param half of the GeoJSON-
coordinates pair. That list is the real input for what core/connectors
eventually factors out; recording it here rather than reconstructing it
later.

env, get_db, is_blank and the decimal_default half of the GeoJSON pair
are no longer part of that copied list -- extracted to infra/ (see
infra/__init__.py for why that's not core/) once the same-four-scripts
copy audit confirmed they were genuinely byte-identical everywhere and
needed no design decision to move. Imported from there now, not
copied.

Nor is the execute_values fact/parcel_exception insert shape itself --
core/store.insert_facts and core/exceptions.insert_exceptions now own
that (§2 places both at their real layer, L4 and L6, and real code
agrees). insert_facts() takes list[core.model.Fact] now, not a
positional tuple (P22) -- this script builds Fact(...) with named
fields at every fact_rows.append() site; insert_exceptions() still
takes a positional tuple, a deliberate, separate decision (see core/
exceptions.py's own docstring for why that adoption was deferred, not
forgotten). What still lives here either way, deliberately: the mapping
into whichever shape each function takes (ZONING/ZONINGABBREV ->
zoning.district/zoning.district_verbatim, ASSESSORS_PARCEL_NUMBER -> the
permits join key). That mapping is San-José-source-specific and belongs
outside core/ (I1) -- it stays in this script for this slice rather than
moving
to a not-yet-created jurisdictions/ca_san_jose/, a bigger step this
slice doesn't take.

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
  multi-match parcels (measured for real, v2 ambiguity rule -- distinct
  non-blank ZONING values, not candidate row count, see
  DETECTOR_VERSION_ZONING_UNRESOLVABLE below: 10,138 zero, 1 genuinely
  ambiguous, out of 225,042; 11 more resolve to one real classification
  despite multiple candidate rows and get both a fact and a non-blocking
  anomaly exception) get a coverage_gap parcel_exception instead of (or,
  for the 11, alongside) a fact -- they DO have an existing parcel row to
  attach to, unlike permits' unmatched case below, so the 0034 pattern
  applies directly.

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
import hashlib
import json
import os
import resource
import sys
import tempfile
import time
import uuid

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
from core.exceptions import insert_exceptions, close_resolved_exceptions, relink_reopened_exceptions, close_exceptions_for_parcels  # noqa: E402

JURISDICTION_ID = "ca_san_jose"

SOURCE_ID_ZONING = "ca_san_jose.zoning_districts"
LICENCE_ID_ZONING = "cc_by_4_0_api_2026_08"  # P55: repointed from 'cc_by_4_0' -- see
                                              # prompts/P55-scoped-unblock.md §4.1/§4.5 step 9
ENDPOINT_URL_ZONING = (
    "https://gisdata-csj.opendata.arcgis.com/api/download/v1/items/"
    "adf17ae739214787ad42945c5f72ccd8/geojson?layers=401"
)

SOURCE_ID_PERMITS = "ca_san_jose.building_permits_active"
LICENCE_ID_PERMITS = "cc0_api_2026_08"  # P55: repointed from 'cc0' -- see
                                         # prompts/P55-scoped-unblock.md §4.1/§4.5 step 9
ENDPOINT_URL_PERMITS = (
    "https://data.sanjoseca.gov/dataset/fd9ceb0c-75e0-402e-9fe3-3f6e04f2c23f/"
    "resource/761b7ae8-3be1-4ad6-923d-c7af6404a904/download/buildingpermitsactive.csv"
)

SCRATCHPAD = "/tmp/ledgex_ingest_scratch"

CHUNK_SIZE = 8 * 1024 * 1024

FACT_CONFIDENCE = "high"
# C24.14 (P59, annex): this used to be one constant, FACT_CONFIDENCE_RULE_ID
# = "bulk_direct_from_assessor_gis" -- copy-pasted from ingest_parcels.py,
# where that label is accurate (parcels really do come direct from the
# assessor GIS layer). Applied unchanged to every fact this file writes
# too, including zoning.district/zoning.district_verbatim (from
# ca_san_jose.zoning_districts, a different GIS layer, not the assessor's)
# and permits.active/permits.series_earliest (from
# ca_san_jose.building_permits_active, a bulk CSV export, not a GIS layer
# at all) -- confidence_rule_id is a free-text provenance label (core/
# model.py's Fact.confidence_rule_id, no enum constraint), and every fact
# either function here wrote carried a false claim about which source
# actually produced it. Split into two correctly-labeled constants, one
# per real source.
FACT_CONFIDENCE_RULE_ID_ZONING = "bulk_direct_from_zoning_districts_gis"
FACT_CONFIDENCE_RULE_ID_PERMITS = "bulk_direct_from_building_permits_csv"
FACT_PACK_VERSION = "v1.0"

DETECTOR_KEY_ZONING_UNRESOLVABLE = "zoning_spatial_join_unresolvable"
# v2.0: ambiguity is determined by DISTINCT NON-BLANK ZONING values among a
# parcel's containing polygons, not by the raw candidate ROW count. v1.0
# counted rows: a parcel intersecting both a real district polygon and the
# one zoning polygon with no recorded classification at all (FACILITYID
# 30392, ZONING and ZONINGABBREV both null) got row-count=2 and was
# recorded ambiguous, even though there was exactly one real answer.
# Measured for real against the live dataset: 10 parcels hit exactly that
# shape, plus 1 more (parcel 5072c848) that intersects two DIFFERENT real
# polygons (FACILITYID 6206 and 6207) which independently carry the
# identical ZONING value 'A' -- a second, distinct source-data artifact
# (overlapping/adjacent polygons agreeing on classification), also
# miscounted as ambiguous by row counting. v1.0's exception rows meant "row
# count > 1"; v2.0's mean "distinct real classification count != 1" -- a
# genuinely different rule, so the version bumps: a detector_version that
# didn't change under a changed rule would make historical exception rows
# unfalsifiable later (no way to tell which rule actually produced a given
# row).
DETECTOR_VERSION_ZONING_UNRESOLVABLE = "2.0"

REASON_NO_CONTAINING_DISTRICT = "no_containing_district"
REASON_MULTIPLE_CONTAINING_DISTRICTS = "multiple_containing_districts"
# Non-blocking: the parcel DID resolve to exactly one real ZONING value,
# but more than one candidate polygon row contributed to that answer.
# Written ALONGSIDE the resolved fact, never instead of it -- resolving
# the value and recording the underlying polygon-overlap anomaly are
# separate obligations. Measured for real: 11 occurrences, all row_count=2
# (10 the null-polygon shape, 1 the two-real-polygons-agree shape above).
REASON_MULTIPLE_POLYGONS_AGREE = "multiple_containing_polygons_agree"

# C1 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): the join point used below
# (parcel.centroid) must be guaranteed INTERIOR to its own parcel --
# ST_Centroid alone is not (a concave, L-shaped or multi-part parcel's
# centroid can fall in a neighbor's polygon), and a stray point landing in
# the wrong district got NO anomaly at all: a single containing polygon
# with one distinct zoning value is indistinguishable from a clean match in
# classify_zoning_candidates. This detector records the rare residual case
# where even the ST_PointOnSurface fallback (populate_interior_centroids,
# below) is not interior -- geometrically possible only for an invalid
# polygon (ST_PointOnSurface guarantees an interior point for a VALID
# geometry; see C4 for validity handling at the source). Distinct from
# DETECTOR_KEY_ZONING_UNRESOLVABLE: that one is about the JOIN finding zero
# or multiple districts for a good point; this one is about the POINT
# itself not being trustworthy, before the join ever runs.
DETECTOR_KEY_CENTROID_NOT_INTERIOR = "parcel_centroid_not_interior"
DETECTOR_VERSION_CENTROID_NOT_INTERIOR = "1.0"
REASON_CENTROID_NOT_INTERIOR = "centroid_not_interior_after_fallback"

# C2 (P59): load_permits' replacement for the old fabricated-false write --
# see load_permits' own inline comment for the full argument.
DETECTOR_KEY_PERMIT_ATTRIBUTION_LOST = "permit_attribution_lost"
DETECTOR_VERSION_PERMIT_ATTRIBUTION_LOST = "1.0"
REASON_PERMIT_ATTRIBUTION_LOST = "no_fresh_apn_match_this_run"


def populate_interior_centroids(cur):
    """C1: replaces the old unconditional `UPDATE parcel SET centroid =
    ST_Centroid(geom) WHERE geom IS NOT NULL AND centroid IS NULL`, which had
    two independent defects. First, ST_Centroid is not guaranteed interior --
    fixed here by preferring it only when it verifiably IS interior
    (ST_Contains(geom, ST_Centroid(geom))) and falling back to
    ST_PointOnSurface(geom) (interior-guaranteed for valid geometry)
    otherwise. Second, `WHERE centroid IS NULL` recomputed a point only
    once, ever -- an already-stored non-interior point (from before this
    fix, or from a future geometry update that lands centroid outside geom
    again for some other reason) was silently wrong forever, and the
    zoning join's own diff-every-run reconciliation (see load_zoning's own
    docstring: "no same-snapshot short-circuit") would then keep
    re-deriving the SAME wrong district from the SAME wrong point on every
    run, reading as stable/confirmed. Re-deriving here on
    `centroid IS NULL OR NOT ST_Contains(geom, centroid)` instead means any
    already-stored bad point is corrected before the join below ever reads
    it, and load_zoning's existing full-reclassification-every-run
    behavior (not touched by this function) then supersedes -- never
    updates, I4 -- any zoning.district fact that was derived from the old,
    wrong point, through the same diff-and-supersede path every other
    zoning reclassification already goes through. No separate supersession
    code is needed for that reason.

    Returns the count of parcels whose stored centroid was NOT interior
    (post-update) -- these get DETECTOR_KEY_CENTROID_NOT_INTERIOR exceptions
    from the caller; this only computes and returns the count/ids. Takes a
    cursor, not a connection -- called from inside load_zoning's own
    single-transaction `with conn.cursor() as cur:` block, same convention
    as insert_exceptions(cur, ...) and every other helper in this file.

    A-N4 (P59C): ST_Contains/ST_Centroid/ST_PointOnSurface can all raise a
    GEOS error on an INVALID polygon (self-intersecting etc.) -- this
    function had never executed against a database actually carrying
    invalid geometry (0057's geom_valid), and one raising row would abort
    the whole load_zoning transaction, discovered for the first time by
    C1's own remediation run. Guarded on 0057's geom_valid (a STORED
    generated column computed via ST_IsValid, which is itself safe on
    invalid input -- referencing it never calls the risky functions): the
    UPDATE below only ever touches geom_valid rows, so ST_Centroid/
    ST_PointOnSurface never see an invalid geometry; the residual SELECT
    uses a CASE (guaranteed short-circuit in Postgres, unlike a bare OR)
    so ST_Contains is never evaluated for a NOT geom_valid row either --
    those rows are routed straight into still_not_interior unconditionally,
    the same exception path a genuinely-non-interior point already takes.
    No remediation of the invalid geometry itself happens here -- P61's,
    under D-6.3, tracked separately via the parcel_geometry_invalid
    detector (C4)."""
    cur.execute("""
        UPDATE parcel
           SET centroid = CASE
                             WHEN ST_Contains(geom, ST_Centroid(geom)) THEN ST_Centroid(geom)
                             ELSE ST_PointOnSurface(geom)
                           END
         WHERE geom IS NOT NULL
           AND geom_valid
           AND (centroid IS NULL OR NOT ST_Contains(geom, centroid))
    """)
    recomputed = cur.rowcount

    # Residual check: even ST_PointOnSurface is not guaranteed interior
    # for an INVALID polygon (self-intersecting etc. -- C4's own
    # concern). Record a typed, non-blocking exception rather than
    # silently classifying against a point that still is not interior.
    # A-N4: NOT geom_valid rows are flagged unconditionally, via the CASE's
    # own short-circuit, without ever calling ST_Contains on them.
    cur.execute("""
        SELECT id FROM parcel
         WHERE geom IS NOT NULL
           AND CASE
                 WHEN NOT geom_valid THEN TRUE
                 ELSE (centroid IS NULL OR NOT ST_Contains(geom, centroid))
               END
    """)
    still_not_interior = [r[0] for r in cur.fetchall()]

    return recomputed, still_not_interior


def classify_zoning_candidates(candidates):
    """candidates: list of (facilityid, zoning, zoning_verbatim) for ONE
    parcel's containing polygons (possibly empty -- zero-match).

    Returns (kind, data):
      ("zero_match", None)
      ("ambiguous", None)
      ("matched", {"zoning": str, "zoning_verbatim": str or None,
                    "anomaly": None or {"facility_ids": [...], "verbatim_conflict": [...] or None}})

    Ambiguity is decided from distinct non-blank ZONING values ONLY.
    zoning_verbatim (from ZONINGABBREV) is a second, independent source
    column despite the name -- it never drives the zero/matched/ambiguous
    decision. Multiple candidate ROWS that agree on ZONING are not
    ambiguous; that was v1.0's bug.
    """
    non_blank_zoning = {z for (fid, z, zv) in candidates if not is_blank(z)}
    if len(non_blank_zoning) == 0:
        return "zero_match", None
    if len(non_blank_zoning) >= 2:
        return "ambiguous", None

    resolved_zoning = next(iter(non_blank_zoning))
    # Only rows that actually contributed the resolved ZONING value get a
    # vote on zoning_verbatim -- a candidate row with a different (or
    # null) ZONING never had a say in the answer, so its ZONINGABBREV
    # isn't relevant to it either.
    verbatim_candidates = {zv for (fid, z, zv) in candidates if z == resolved_zoning}
    verbatim_conflict = None
    if len(verbatim_candidates) == 1:
        resolved_verbatim = next(iter(verbatim_candidates))
    else:
        # ZONINGABBREV disagrees among rows that agree on ZONING. Never
        # fetchone()/dict-overwrite an arbitrary pick here -- that is
        # exactly compose_property_file.py's collision bug wearing a
        # different hat (see Fix 3). Write the fact we ARE certain of
        # (zoning.district) and skip the one we're not
        # (zoning.district_verbatim); the disagreement is recorded in the
        # anomaly detail below, never silently resolved. Zero real
        # occurrences of this branch in the dataset this was verified
        # against -- this path is defensive, not exercised by real data.
        resolved_verbatim = None
        verbatim_conflict = sorted(v for v in verbatim_candidates if v is not None)

    anomaly = None
    if len(candidates) > 1:
        anomaly = {
            "facility_ids": sorted(fid for fid, z, zv in candidates),
            "verbatim_conflict": verbatim_conflict,
        }

    return "matched", {"zoning": resolved_zoning, "zoning_verbatim": resolved_verbatim, "anomaly": anomaly}


# ---------------------------------------------------------------------------
# COPIED from ingest_parcels.py (see module docstring for the full list and
# why it is copied, not imported). env, get_db, is_blank and
# decimal_default are imported from infra/ instead -- see module docstring.
# ---------------------------------------------------------------------------

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


def geojson_geom_param(geom):
    return json.dumps(geom, default=decimal_default)


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


def finish_job_run(conn, job_run_id, status, snapshot_id, rows_in=None, rows_out=None, metrics=None):
    # clock_timestamp(), not now() -- see ingest_parcels.py's
    # finish_job_run_full for the full story: now() returns the current
    # TRANSACTION's start time, not the time this statement executes, and
    # is silently wrong whenever meaningful work happens earlier in the
    # same transaction (exactly the load phases below).
    #
    # metrics (0051, README findings #12/#16): was schema_drift before
    # this migration, stretched by load_permits()/load_zoning() to carry
    # per-row match-outcome breakdowns that were never schema drift in
    # its literal sense (0012: "fields expected but missing") -- see each
    # call site for the shape it writes. metrics is the real column for
    # that now; schema_drift is untouched by this function going forward.
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
    """README finding #10: ON CONFLICT (id) DO NOTHING, not a bare INSERT --
    id = snapshot_id_for(source_id, digest) is deterministic from content
    alone, so two concurrent fetches of identical new content compute the
    identical id and would otherwise race a bare INSERT into a raw PK
    violation (an unhandled exception, not a clean no-op). ON CONFLICT (id)
    alone is sufficient: id and the table's other uniqueness constraint,
    UNIQUE (content_hash, source_id), are both fully determined by the same
    (source_id, digest) pair in this script, so a conflict on one always
    means a conflict on the other for a row this code ever writes -- never
    two different code paths to satisfy.

    Returns (sid, inserted) -- inserted is True only when THIS call's own
    INSERT actually added the row (cur.rowcount == 1, read before commit()).
    False means another writer's INSERT (or an earlier already-committed
    run) got there first -- this call is a no-op, not a failure. The
    caller must use THIS return value, not snapshot_exists()'s earlier
    SELECT, to decide job_run's terminal status -- see snapshot_exists()'s
    own docstring."""
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
            ON CONFLICT (id) DO NOTHING
            """,
            (sid, source_id, uri, digest, media_type, byte_size, request_payload, http_status, fetched_at, licence_id),
        )
        inserted = cur.rowcount == 1
    conn.commit()
    return sid, inserted


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
            sid, inserted = insert_snapshot(conn, source_id, digest, byte_size, media_type, http_status, fetched_at, bucket, url, licence_id)
            if inserted:
                print(f"  snapshot inserted: {sid}")
            else:
                print(f"  snapshot {sid} already existed by the time of INSERT "
                      f"(lost a concurrent race) -- no-op, not re-inserted")

        status = "failed" if not ok else ("skipped_unchanged" if not inserted else "succeeded")
        finish_job_run(conn, job_run_id, status, sid)
        print(f"  job_run {job_run_id} -> {status}")
        # P45 Fix 2 (same fix as ingest_parcels.py's own run_one_fetch --
        # see prompts/P45-ingest-provenance.md): `ok` used to be discarded
        # after deciding job_run.status; now returned so phase_b can fail
        # the whole phase on a failed fetch, not just leave a `failed`
        # job_run row nobody read. C7 unaffected -- the snapshot above is
        # already recorded, unconditionally, regardless of this return.
        return digest, sid, http_status, ok
    except Exception as e:
        fail_job_run(conn, job_run_id, e)
        print(f"  job_run {job_run_id} -> failed: {e}")
        raise


def phase_b(source_id, url, path1, path2, label_prefix, licence_id, job_key):
    """P45 Fix 2: same fix as ingest_parcels.py's own phase_b -- both
    fetches always complete and get snapshotted (C7 unaffected); this now
    fails LOUDLY, via SystemExit, if either fetch was non-2xx, AFTER both
    snapshots are already durably recorded."""
    conn = get_db()
    s3 = get_s3()
    bucket = env("OBJECT_STORE_BUCKET")
    digest1, sid1, status1, ok1 = run_one_fetch(conn, s3, bucket, path1, f"{label_prefix} FETCH 1 (first ingest)", source_id, url, licence_id, job_key)
    digest2, sid2, status2, ok2 = run_one_fetch(conn, s3, bucket, path2, f"{label_prefix} FETCH 2 (dedupe proof)", source_id, url, licence_id, job_key)
    print(f"\n=== {label_prefix} PHASE B SUMMARY ===")
    digests_match = digest1 == digest2
    print(f"digests match: {digests_match}  (fetch 1: http_status={status1}, ok={ok1}; "
          f"fetch 2: http_status={status2}, ok={ok2})")
    # P45 STEP 0(d): same policy as ingest_parcels.py's own phase_b --
    # loud, not fatal. See that function's own comment for the full
    # argument.
    if not digests_match:
        print(f"\n{'!' * 78}\n"
              f"! SOURCE CHANGED BETWEEN FETCHES -- digests do not match.\n"
              f"!   fetch 1: {sid1}\n"
              f"!   fetch 2: {sid2}\n"
              f"! Both are recorded, independently, under their own true hashes (C7).\n"
              f"! A later --phase load must name exactly ONE of these two ids --\n"
              f"! it will never be guessed.\n"
              f"{'!' * 78}")
    conn.close()

    if not (ok1 and ok2):
        raise SystemExit(
            f"{label_prefix} phase b: at least one fetch was non-2xx (fetch 1 "
            f"http_status={status1}, fetch 2 http_status={status2}) -- both snapshots "
            f"are recorded (C7), but a phase that half-worked is not a phase that "
            f"worked. See the job_run rows above for detail."
        )


def parse_s3_uri(uri):
    """P45 Fix 3: copied from ingest_parcels.py's own parse_s3_uri, not
    imported -- see this file's own module docstring for why every piece
    of shared plumbing here is a deliberate copy, not a shared import,
    until core/connectors exists to factor it out for real."""
    from urllib.parse import urlparse
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise RuntimeError(f"snapshot.object_uri is not an s3:// URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def verified_snapshot_file(conn, snapshot_id, source_id):
    """P45 Fix 3: copied from ingest_parcels.py's own verified_snapshot_file,
    not imported -- same reasoning as parse_s3_uri above. Parameterized by
    source_id (unlike the parcels original, which closes over a single
    module-level SOURCE_ID): this file serves two sources -- zoning and
    permits -- with different media types (geo+json vs. CSV), which the
    parcels version never had to handle.

    Returns (path, snapshot row dict) for bytes read from
    snapshot.object_uri. The hash is computed over exactly the bytes the
    loader will parse -- raises on a content_hash OR byte_size mismatch,
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
    if snapshot["media_type"] == "application/geo+json":
        suffix = ".geojson"
    elif snapshot["media_type"] in ("text/csv", "application/csv"):
        suffix = ".csv"
    else:
        suffix = ".snapshot"
    tmp = tempfile.NamedTemporaryFile(prefix="ledgex-zoning-permits-", suffix=suffix, delete=False)
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
                    facilityid text,
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
                    props.get("FACILITYID"), props.get("ZONING"), props.get("ZONINGABBREV"),
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
                "INSERT INTO zoning_staging (facilityid, zoning, zoning_verbatim, geom) VALUES %s",
                rows,
                template="(%s, %s, %s, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3)))",
                page_size=2000,
            )
            cur.execute("CREATE INDEX ON zoning_staging USING gist (geom)")

            # Prerequisite: populate parcel.centroid. Data, not DDL -- the
            # column and its GiST index (parcel_centroid_gix) have existed
            # since 0004 and were simply never populated before this. C1:
            # populate_interior_centroids re-derives ANY non-interior stored
            # point (not just NULL ones -- see its own docstring) using an
            # interior-guaranteed fallback, and reports the (rare) residual
            # case where even that fallback isn't interior.
            centroid_recomputed, centroid_still_bad = populate_interior_centroids(cur)
            print(f"  parcel.centroid populated/corrected for {centroid_recomputed:,} rows "
                  f"({len(centroid_still_bad):,} still not interior after the interior-point fallback)")

            # A-N2 (P59C), D-6.6: a parcel whose derived point is
            # known-non-interior is EXCLUDED from zoning classification --
            # the join used to filter only on `centroid IS NOT NULL`, so
            # these parcels flowed through and received confidence-high
            # zoning.district facts derived from a point this same function
            # just proved sits outside the parcel. The exception type below
            # is `record_to_ground`, not `coverage_gap` (was `coverage_gap`
            # until this pass -- the same type flag_invalid_geometry.py
            # already uses for parcel_geometry_invalid, the sibling
            # data-quality detector): a `coverage_gap`-typed exception here
            # would be indistinguishable from a genuine "this parcel is in
            # no district" statement (the zoning_spatial_join_unresolvable
            # detector below, which IS a real coverage_gap) and would
            # launder a data-quality defect into a coverage claim.
            centroid_still_bad_set = set(centroid_still_bad)
            if centroid_still_bad:
                cur.execute("""
                    SELECT parcel_id FROM parcel_exception
                    WHERE detector_key = %s AND detector_version = %s AND outcome = 'open'
                """, (DETECTOR_KEY_CENTROID_NOT_INTERIOR, DETECTOR_VERSION_CENTROID_NOT_INTERIOR))
                existing_open_centroid = {r[0] for r in cur.fetchall()}
                centroid_exception_rows = [
                    ParcelException(
                        parcel_id=pid, jurisdiction_id=JURISDICTION_ID, type="record_to_ground", severity="warning",
                        detector_key=DETECTOR_KEY_CENTROID_NOT_INTERIOR, detector_version=DETECTOR_VERSION_CENTROID_NOT_INTERIOR,
                        detail={"reason": REASON_CENTROID_NOT_INTERIOR},
                    )
                    for pid in centroid_still_bad if pid not in existing_open_centroid
                ]
                if centroid_exception_rows:
                    insert_exceptions(cur, centroid_exception_rows)
                print(f"  parcel_centroid_not_interior exceptions: {len(centroid_exception_rows):,} new "
                      f"({len(centroid_still_bad) - len(centroid_exception_rows):,} already open)")

            # A-N8 (P59C): closure-by-exclusion, unconditional (runs even
            # when centroid_still_bad is empty -- close_resolved_exceptions'
            # own docstring: "empty still_true_pairs ... every currently-open
            # row ... is correctly closed"). populate_interior_centroids
            # (above) already does a FULL recompute of the still-bad set on
            # every load_zoning run -- the same precondition
            # close_resolved_exceptions requires (it's built for load_zoning's
            # own DETECTOR_KEY_ZONING_UNRESOLVABLE closure two blocks below;
            # this reuses it, not a second hand-rolled UPDATE). A parcel that
            # was open here and is no longer in centroid_still_bad_set (its
            # geometry was corrected, or centroid recomputed interior) closes
            # condition_cleared.
            centroid_still_true_pairs = {
                (pid, REASON_CENTROID_NOT_INTERIOR) for pid in centroid_still_bad_set
            }
            centroid_closed_count = close_resolved_exceptions(
                cur, DETECTOR_KEY_CENTROID_NOT_INTERIOR, DETECTOR_VERSION_CENTROID_NOT_INTERIOR,
                centroid_still_true_pairs,
            )
            print(f"  parcel_centroid_not_interior exceptions closed (condition_cleared): {centroid_closed_count:,}")

            # No count(*) OVER () here -- that counted candidate ROWS, which
            # is what made this ambiguity-detection wrong (see
            # DETECTOR_VERSION_ZONING_UNRESOLVABLE's comment above). Fetch
            # every (parcel, candidate) pair and classify per parcel in
            # Python via classify_zoning_candidates, which counts DISTINCT
            # non-blank ZONING values instead.
            #
            # A-N2: NOT (p.id = ANY(%s::uuid[])) excludes centroid_still_bad
            # parcels from the join's own candidate set -- an empty list
            # makes this clause always-true (no exclusion), same as before.
            t_join_start = time.monotonic()
            cur.execute("""
                SELECT p.id, z2.facilityid, z2.zoning, z2.zoning_verbatim
                FROM parcel p
                JOIN zoning_staging z2 ON ST_Contains(z2.geom, p.centroid)
                WHERE p.centroid IS NOT NULL
                  AND NOT (p.id = ANY(%s::uuid[]))
            """, (list(centroid_still_bad_set),))
            join_rows = cur.fetchall()
            print(f"  spatial join: {len(join_rows):,} (parcel, candidate zoning) pairs in {time.monotonic()-t_join_start:.1f}s")

        by_parcel = {}
        for parcel_id, facilityid, zoning, zoning_verbatim in join_rows:
            by_parcel.setdefault(parcel_id, []).append((facilityid, zoning, zoning_verbatim))

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM parcel WHERE centroid IS NOT NULL")
            all_parcel_ids = {r[0] for r in cur.fetchall()}

        matched = {}     # parcel_id -> classify_zoning_candidates() "matched" data
        ambiguous = set()
        zero_match = set()
        anomaly_count = 0
        for parcel_id in all_parcel_ids:
            if parcel_id in centroid_still_bad_set:
                # A-N2: excluded from classification entirely -- neither
                # matched, zero_match nor ambiguous. Stays out of
                # zoning_spatial_join_unresolvable's own coverage_gap
                # exception below; the record_to_ground exception above is
                # the one and only record. It remains in all_parcel_ids, so
                # the diff/supersede loop below still sees it: any
                # previously-live zoning.district/zoning.district_verbatim
                # fact for this parcel is superseded with NO successor,
                # through the exact same "matched -> zero-match" path a
                # genuine zero-match already uses (fresh_value is None
                # because parcel_id is never added to `matched`) -- not a
                # new code path, and not a silent no-op either.
                continue
            kind, data = classify_zoning_candidates(by_parcel.get(parcel_id, []))
            if kind == "zero_match":
                zero_match.add(parcel_id)
            elif kind == "ambiguous":
                ambiguous.add(parcel_id)
            else:
                matched[parcel_id] = data
                if data["anomaly"] is not None:
                    anomaly_count += 1

        print(f"  matched (exactly one real classification): {len(matched):,}")
        print(f"  zero-match: {len(zero_match):,}")
        print(f"  ambiguous (>=2 distinct real classifications): {len(ambiguous):,}")
        print(f"  matched WITH a polygon-overlap anomaly (non-blocking, both fact and exception written): {anomaly_count:,}")

        # --- Reconciliation, not blind insert. P5 finding: this classification
        # is a function of (zoning snapshot x current parcel set), not the
        # snapshot alone -- the parcel set can and does grow between zoning
        # runs (P3/P4 keep re-ingesting parcels independently), so "same
        # snapshot as last time" does NOT imply "no-op" the way it does for
        # parcels' own Phase B. There is deliberately no same-snapshot
        # short-circuit here: every run recomputes the full classification
        # above and diffs it against the live ledger. The spatial join is ~8s
        # at this scale -- not expensive enough to justify inventing a new
        # invalidation key whose own correctness would be one more thing to
        # get wrong, in exactly the direction that matters here: a run that
        # silently skips work it should have done.
        #
        # Reads fact WHERE superseded_at IS NULL directly, NOT current_fact --
        # same reasoning P3's own Phase B diff already established for
        # parcels (current_fact can be stale). Load-bearing, not a style
        # choice: P1 made current_fact's refresh best-effort and AFTER
        # commit (ingest_parcels.py's refresh_current_fact), specifically so
        # a refresh failure can never re-mark an already-succeeded job_run
        # failed. That means current_fact can legitimately lag a correct
        # ledger. Diffing against it in that state would read the OLD value,
        # classify it as "changed" relative to the fresh classification, and
        # supersede a fact that was already correct -- the exact fabricated-
        # supersession failure this package exists to prevent, arriving by a
        # different route than the one already closed.
        with conn.cursor() as cur:
            cur.execute("""
                SELECT parcel_id, field_key, id, value
                FROM fact
                WHERE field_key IN ('zoning.district','zoning.district_verbatim')
                  AND superseded_at IS NULL
                  AND source_id = %s
            """, (SOURCE_ID_ZONING,))
            live = {(pid, fk): (fid, val) for pid, fk, fid, val in cur.fetchall()}

        fact_ids_to_supersede = []
        fact_rows = []
        diff_counts = {
            "zoning.district": {"same": 0, "different": 0, "new": 0, "retired": 0},
            "zoning.district_verbatim": {"same": 0, "different": 0, "new": 0, "retired": 0},
        }

        def extract_district(d):
            return d["zoning"]

        def extract_verbatim(d):
            return d["zoning_verbatim"]

        for field_key, extract in (
            ("zoning.district", extract_district),
            ("zoning.district_verbatim", extract_verbatim),
        ):
            counts = diff_counts[field_key]
            for parcel_id in all_parcel_ids:
                live_entry = live.get((parcel_id, field_key))
                fresh_value = extract(matched[parcel_id]) if parcel_id in matched else None

                if live_entry is None:
                    if fresh_value is None:
                        continue  # absent stays absent -- no-op
                    # zero-match/ambiguous -> matched (or first-ever
                    # classification): a NEW fact, never a supersession --
                    # there is nothing live to supersede.
                    fact_rows.append(Fact(
                        parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                        field_key=field_key, value=json.dumps(fresh_value), method="bulk",
                        source_id=SOURCE_ID_ZONING, snapshot_id=snapshot_id, retrieved_at=retrieved_at,
                        source_url=ENDPOINT_URL_ZONING, licence_id=LICENCE_ID_ZONING,
                        confidence=FACT_CONFIDENCE, confidence_rule_id=FACT_CONFIDENCE_RULE_ID_ZONING,
                        effective_from=retrieved_at, pack_version=FACT_PACK_VERSION,
                    ))
                    counts["new"] += 1
                else:
                    live_fact_id, live_value = live_entry
                    if fresh_value is None:
                        # matched -> zero-match/ambiguous: supersede, NO
                        # successor. The exception (below) records why.
                        fact_ids_to_supersede.append(live_fact_id)
                        counts["retired"] += 1
                    elif live_value == fresh_value:
                        counts["same"] += 1  # no-op -- the whole point of this diff
                    else:
                        fact_ids_to_supersede.append(live_fact_id)
                        fact_rows.append(Fact(
                            parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                            field_key=field_key, value=json.dumps(fresh_value), method="bulk",
                            source_id=SOURCE_ID_ZONING, snapshot_id=snapshot_id, retrieved_at=retrieved_at,
                            source_url=ENDPOINT_URL_ZONING, licence_id=LICENCE_ID_ZONING,
                            confidence=FACT_CONFIDENCE, confidence_rule_id=FACT_CONFIDENCE_RULE_ID_ZONING,
                            effective_from=retrieved_at, pack_version=FACT_PACK_VERSION,
                            supersedes_fact_id=live_fact_id, supersession_reason="unknown",
                        ))
                        counts["different"] += 1

            print(f"  {field_key}: same={counts['same']:,} different={counts['different']:,} "
                  f"new={counts['new']:,} retired-no-successor={counts['retired']:,}")

        # Exception-writing is diff-aware too (P5 finding): insert_exceptions()
        # has no dedup and parcel_exception had no uniqueness (0045 now adds
        # one) -- an unconditional write here would re-open the same finding
        # on every single re-run. Only write when this (parcel, reason) is
        # not ALREADY a currently-open exception at this detector_version.
        with conn.cursor() as cur:
            cur.execute("""
                SELECT parcel_id, detail->>'reason' FROM parcel_exception
                WHERE detector_key = %s AND detector_version = %s AND outcome = 'open'
            """, (DETECTOR_KEY_ZONING_UNRESOLVABLE, DETECTOR_VERSION_ZONING_UNRESOLVABLE))
            existing_open = {(pid, reason) for pid, reason in cur.fetchall()}

        # P9 (prompts/P9-exception-resolution.md): the closure half of exception
        # resolution needs the same (parcel_id, reason) shape as existing_open
        # above, but for "still true this run", not "already open" -- every
        # zero_match/ambiguous/matched-with-anomaly parcel this run's full
        # classification actually found, regardless of whether it was already
        # open. Same three populations exception_rows is built from below.
        still_true_pairs = (
            {(parcel_id, REASON_NO_CONTAINING_DISTRICT) for parcel_id in zero_match}
            | {(parcel_id, REASON_MULTIPLE_CONTAINING_DISTRICTS) for parcel_id in ambiguous}
            | {
                (parcel_id, REASON_MULTIPLE_POLYGONS_AGREE)
                for parcel_id, data in matched.items()
                if data["anomaly"] is not None
            }
        )

        exception_rows = []
        exception_skipped = 0
        for parcel_id in zero_match:
            if (parcel_id, REASON_NO_CONTAINING_DISTRICT) in existing_open:
                exception_skipped += 1
                continue
            exception_rows.append(ParcelException(
                parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID, type="coverage_gap", severity="info",
                detector_key=DETECTOR_KEY_ZONING_UNRESOLVABLE, detector_version=DETECTOR_VERSION_ZONING_UNRESOLVABLE,
                detail={"reason": REASON_NO_CONTAINING_DISTRICT},
            ))
        for parcel_id in ambiguous:
            if (parcel_id, REASON_MULTIPLE_CONTAINING_DISTRICTS) in existing_open:
                exception_skipped += 1
                continue
            exception_rows.append(ParcelException(
                parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID, type="coverage_gap", severity="info",
                detector_key=DETECTOR_KEY_ZONING_UNRESOLVABLE, detector_version=DETECTOR_VERSION_ZONING_UNRESOLVABLE,
                detail={"reason": REASON_MULTIPLE_CONTAINING_DISTRICTS},
            ))
        # Non-blocking: written for a parcel that ALSO got a fact above.
        # Resolving the value and recording the polygon-overlap anomaly
        # are separate obligations -- see REASON_MULTIPLE_POLYGONS_AGREE.
        for parcel_id, data in matched.items():
            if data["anomaly"] is not None:
                if (parcel_id, REASON_MULTIPLE_POLYGONS_AGREE) in existing_open:
                    exception_skipped += 1
                    continue
                exception_rows.append(ParcelException(
                    parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID, type="coverage_gap", severity="info",
                    detector_key=DETECTOR_KEY_ZONING_UNRESOLVABLE, detector_version=DETECTOR_VERSION_ZONING_UNRESOLVABLE,
                    detail={
                        "reason": REASON_MULTIPLE_POLYGONS_AGREE,
                        "zoning": data["zoning"],
                        **data["anomaly"],
                    },
                ))
        print(f"  exceptions: {len(exception_rows):,} new, {exception_skipped:,} skipped "
              f"(already open at this detector_version)")

        with conn.cursor() as cur:
            # MUST run before insert_facts() below -- fact_one_current_per_source
            # is a plain unique index, checked immediately, no deferral. Same
            # order Phase E already established.
            if fact_ids_to_supersede:
                cur.execute(
                    "UPDATE fact SET superseded_at = clock_timestamp() WHERE id = ANY(%s::uuid[]) AND superseded_at IS NULL",
                    (fact_ids_to_supersede,),
                )
            print(f"  facts superseded: {len(fact_ids_to_supersede):,}")

            if fact_rows:
                insert_facts(cur, fact_rows)
            print(f"  fact rows submitted: {len(fact_rows):,}")

            # P9: closure before insert -- a (parcel_id, reason) key can never be
            # both "not still true" (closed below) and "freshly true, needs a new
            # open row" (inserted below) in the SAME run; still_true_pairs and the
            # exception_rows population above are complementary by construction,
            # not just sequenced this way for convenience.
            closed_count = close_resolved_exceptions(
                cur, DETECTOR_KEY_ZONING_UNRESOLVABLE, DETECTOR_VERSION_ZONING_UNRESOLVABLE, still_true_pairs
            )
            print(f"  exceptions closed (condition_cleared): {closed_count:,}")

            if exception_rows:
                insert_exceptions(cur, exception_rows)
                print(f"  parcel_exception rows submitted: {len(exception_rows):,}")
                relinked_count = relink_reopened_exceptions(
                    cur, DETECTOR_KEY_ZONING_UNRESOLVABLE, DETECTOR_VERSION_ZONING_UNRESOLVABLE
                )
                print(f"  exceptions relinked (reopened_from_id): {relinked_count:,}")

        rows_in = len(all_parcel_ids)
        rows_out = len(matched)
        finish_job_run(conn, job_run_id, "succeeded", snapshot_id, rows_in, rows_out, {
            "diff": diff_counts,
            "exceptions_written": len(exception_rows),
            "exceptions_skipped_already_open": exception_skipped,
        })
        print(f"\njob_run {job_run_id} -> succeeded (rows_in={rows_in:,}, rows_out={rows_out:,})")

    except Exception as e:
        conn.rollback()
        fail_job_run(conn, job_run_id, e)
        print(f"\njob_run {job_run_id} -> failed: {e}")
        raise

    conn.close()


def phase_zoning_load(snapshot_id):
    """P45 Fix 3 (see prompts/P45-ingest-provenance.md): no default "newest"
    guess and no fixed local path -- exactly ingest_parcels.py's phase_d,
    same fix, same reasoning. `verified_snapshot_file` proves the bytes
    are this snapshot's before `load_zoning` ever sees them."""
    conn = get_db()
    path, snapshot = verified_snapshot_file(conn, snapshot_id, SOURCE_ID_ZONING)
    retrieved_at = snapshot["fetched_at"]
    print(f"using verified snapshot: {snapshot_id}")
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
        by_apn = {}   # canonicalized apn -> list of date
        rows_in = 0
        blank_apn = 0
        non_active_status_rows = 0
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                rows_in += 1
                # C24.13 (P59, annex): this ingest hardcodes permits.active
                # = True (below) on the strength of an ASSUMPTION -- "every
                # row in the source file already carries Status='Active'"
                # (this module's own docstring) -- that was never actually
                # checked per-row; the Status column, when present, was
                # read by nothing in this function. Self-verifying now,
                # not a behavior change to the aggregation itself (which
                # column(s)/rows should drive permits.active if the
                # assumption ever breaks is a real design question, not
                # something to invent silently here -- reported, not
                # absorbed): if Status IS present in this file and any row
                # says something other than 'Active', refuse loudly rather
                # than continue silently trusting a premise that just
                # proved false. A file with no Status column at all (some
                # test fixtures; conceivably a differently-shaped future
                # export) is not checked -- absence of the column is a
                # different, pre-existing condition this fix does not
                # newly police.
                if "Status" in row and row["Status"] != "Active":
                    non_active_status_rows += 1
                # canonicalize_identifier, not a bare .strip(): a real row
                # carries a leading apostrophe (spreadsheet-export "force
                # text" artifact, ASSESSORS_PARCEL_NUMBER = "'67620002")
                # that never string-equalled parcel.apn's clean
                # '67620002' -- a real active permit silently dropped.
                # Fix 1; see infra/values.canonicalize_identifier.
                apn = canonicalize_identifier(row.get("ASSESSORS_PARCEL_NUMBER"))
                if is_blank(apn):
                    blank_apn += 1
                    continue
                by_apn.setdefault(apn, []).append(parse_issue_date(row["ISSUEDATE"]))
        if non_active_status_rows:
            raise RuntimeError(
                f"{non_active_status_rows} row(s) have Status != 'Active' -- this ingest's "
                f"permits.active=True is hardcoded on the assumption every row is already "
                f"Active (this module's own docstring); that assumption just proved false. "
                f"Refusing rather than silently computing permits.active from a premise that "
                f"no longer holds -- deciding how non-Active rows should affect the derived "
                f"value is a real design question, not something to invent here."
            )
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
        fresh_by_parcel = {}   # parcel_id -> (active_bool, series_earliest_iso_or_None)
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
            fresh_by_parcel[pid] = (True, min(dates).isoformat())

        print(f"  blank APN: {blank_apn:,} rows")
        print(f"  not-found APN: {not_found:,} distinct ({not_found_rows:,} rows)")
        print(f"  ambiguous (duplicated parcel APN): {ambiguous:,} distinct ({ambiguous_rows:,} rows)")
        print(f"  matched: {len(fresh_by_parcel):,} parcels ({matched_rows:,} rows)")
        total_unmatched_rows = blank_apn + not_found_rows + ambiguous_rows
        print(f"  TOTAL UNMATCHED ROWS: {total_unmatched_rows:,} / {rows_in:,} "
              f"({100*total_unmatched_rows/rows_in:.1f}%) -- no parcel to attach a "
              f"parcel_exception to; not silently dropped, just not persisted per-row. "
              f"See rows_in/rows_out AND metrics on this job_run for the durable record.")

        # PERSISTING the breakdown, not just printing it: rows_in/rows_out
        # already give the aggregate gap durably, but not the SHAPE of it
        # (blank vs not-found vs ambiguous), and that shape is what a
        # future reader needs to tell "the source stopped populating APN"
        # from "the parcel dataset doesn't cover these" from "APN reuse
        # made this one genuinely unresolvable" apart. Written to
        # job_run.metrics (0051, README findings #12/#16) -- this used to
        # be a documented reach into schema_drift, whose declared meaning
        # (0012: "fields expected but missing") never actually described
        # a per-row match-outcome distribution; that argument is now
        # historical, not live -- see 0051 for the full record of why the
        # reach existed and what replaced it.
        # --- Reconciliation, not blind insert. Same source-set-vs-parcel-set
        # dependency as zoning (P5 finding): the APN join is a function of the
        # CURRENT parcel set, not the permits snapshot alone -- no
        # same-snapshot short-circuit here either, for the identical reason.
        #
        # Reads fact WHERE superseded_at IS NULL, NOT current_fact -- same
        # reasoning as load_zoning above (see its comment for the full
        # argument): current_fact's refresh is best-effort and runs after
        # commit (P1), so it can legitimately lag a correct ledger, and
        # diffing against it while lagging would misclassify an already-
        # correct value as changed and supersede it -- the fabricated-
        # supersession failure this package exists to prevent.
        with conn.cursor() as cur:
            cur.execute("""
                SELECT parcel_id, field_key, id, value
                FROM fact
                WHERE field_key IN ('permits.active','permits.series_earliest')
                  AND superseded_at IS NULL
                  AND source_id = %s
            """, (SOURCE_ID_PERMITS,))
            live = {(pid, fk): (fid, val) for pid, fk, fid, val in cur.fetchall()}

        candidate_parcels = set(fresh_by_parcel) | {pid for (pid, fk) in live}

        fact_ids_to_supersede = []
        fact_rows = []
        diff_counts = {
            "permits.active": {"same": 0, "different": 0, "new": 0, "attribution_lost": 0},
            "permits.series_earliest": {"same": 0, "different": 0, "new": 0, "attribution_lost": 0},
        }
        # C2 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md). Real evidence
        # gathered before writing this fix, not assumed: the real permits
        # export's FOLDERNUMBER and FOLDERRSN columns are BOTH 100%
        # populated and 100% unique across all 17,467 real rows -- a
        # genuine, reliable per-permit identity exists in the SOURCE. But
        # nothing in this ledger has ever PERSISTED that identity alongside
        # a permits.active/series_earliest fact (Fact carries no such
        # column) -- the same structural gap source_feature_identity (0043)
        # closes for parcels is open, unclosed, for permits (new finding,
        # not one of the audit's 44 -- see this pass's own deliverable).
        # Without a persisted link from a live fact back to the specific
        # FOLDERNUMBER/FOLDERRSN that produced it, this run cannot tell "the
        # permit that produced this parcel's live fact is still in this
        # run's export, just with an unattributable (blank) APN cell" apart
        # from "that permit genuinely dropped off the export" -- both look
        # identical from here: the parcel has no fresh match this run.
        #
        # So: fresh_value is None (four routes -- blank APN, not-found APN,
        # ambiguous/duplicate APN, or genuinely absent) NEVER writes a false
        # successor, uniformly, for BOTH fields (the old
        # retire_with_false_successor split is gone -- series_earliest's own
        # "retired, no successor" branch was justified only by
        # permits.active's now-removed false-write: "a positive, confirmed
        # fact (permits.active=false already says so)" no longer holds once
        # that write is gone). "We can no longer attribute this" and "this
        # is now false" are different claims (CONVENTIONS) -- absence opens
        # a typed, non-blocking exception and leaves the live fact exactly
        # as it was; it never supersedes.
        #
        # COST, STATED EXPLICITLY, NOT GLOSSED OVER: a permit that
        # genuinely drops off the export now leaves a permits.active=true
        # fact standing indefinitely -- the ledger asserting "active" for a
        # permit that may no longer be. That is a real error in the
        # opposite direction from before. It is still the right trade: a
        # stale true is recoverable the moment a future pass builds
        # persisted permit identity (the new finding above) or a
        # product-level staleness policy notices; a fabricated false is an
        # immutable affirmative falsehood that has already superseded a
        # true fact and can never be taken back. The audit's own §3
        # reaches the same place independently: "the map should not surface
        # permits.active until the retire logic distinguishes absence from
        # unattributability" -- carried forward as an explicit map-phase
        # precondition in this pass's own report, not silently assumed
        # resolved by this fix.
        attribution_lost_parcels = set()
        attribution_confirmed_parcels = set()

        for parcel_id in candidate_parcels:
            fresh = fresh_by_parcel.get(parcel_id)  # (True, iso_date) or None
            fresh_active = True if fresh is not None else None
            fresh_earliest = fresh[1] if fresh is not None else None
            parcel_had_absence = False

            for field_key, fresh_value in (
                ("permits.active", fresh_active),
                ("permits.series_earliest", fresh_earliest),
            ):
                counts = diff_counts[field_key]
                live_entry = live.get((parcel_id, field_key))

                if live_entry is None:
                    if fresh_value is None:
                        continue  # never had one, still doesn't -- no-op
                    fact_rows.append(Fact(
                        parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                        field_key=field_key, value=json.dumps(fresh_value), method="bulk",
                        source_id=SOURCE_ID_PERMITS, snapshot_id=snapshot_id, retrieved_at=retrieved_at,
                        source_url=ENDPOINT_URL_PERMITS, licence_id=LICENCE_ID_PERMITS,
                        confidence=FACT_CONFIDENCE, confidence_rule_id=FACT_CONFIDENCE_RULE_ID_PERMITS,
                        effective_from=retrieved_at, pack_version=FACT_PACK_VERSION,
                    ))
                    counts["new"] += 1
                    continue

                live_fact_id, live_value = live_entry

                if fresh_value is None:
                    # Absence. Never a claim on its own -- leave the live
                    # fact exactly as it is, no supersession, and mark this
                    # parcel for a typed exception below.
                    counts["attribution_lost"] += 1
                    parcel_had_absence = True
                    continue

                if fresh_value == live_value:
                    counts["same"] += 1
                    attribution_confirmed_parcels.add(parcel_id)
                    continue

                # Genuine positive difference (e.g. reactivation: live=false
                # or absent, fresh=true; or a new, different earliest date)
                # -- real evidence, a real supersession.
                fact_ids_to_supersede.append(live_fact_id)
                fact_rows.append(Fact(
                    parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                    field_key=field_key, value=json.dumps(fresh_value), method="bulk",
                    source_id=SOURCE_ID_PERMITS, snapshot_id=snapshot_id, retrieved_at=retrieved_at,
                    source_url=ENDPOINT_URL_PERMITS, licence_id=LICENCE_ID_PERMITS,
                    confidence=FACT_CONFIDENCE, confidence_rule_id=FACT_CONFIDENCE_RULE_ID_PERMITS,
                    effective_from=retrieved_at, pack_version=FACT_PACK_VERSION,
                    supersedes_fact_id=live_fact_id, supersession_reason="world_change",
                ))
                counts["different"] += 1
                attribution_confirmed_parcels.add(parcel_id)

            if parcel_had_absence:
                attribution_lost_parcels.add(parcel_id)

        for field_key in ("permits.active", "permits.series_earliest"):
            c = diff_counts[field_key]
            print(f"  {field_key}: same={c['same']:,} different={c['different']:,} "
                  f"new={c['new']:,} attribution_lost-no-write={c['attribution_lost']:,}")

        metrics = {
            "unmatched_breakdown": {
                "blank_apn_rows": blank_apn,
                "not_found_apn_rows": not_found_rows,
                "not_found_apn_distinct": not_found,
                "ambiguous_apn_rows": ambiguous_rows,
                "ambiguous_apn_distinct": ambiguous,
            },
            "diff": diff_counts,
        }

        with conn.cursor() as cur:
            if fact_ids_to_supersede:
                cur.execute(
                    "UPDATE fact SET superseded_at = clock_timestamp() WHERE id = ANY(%s::uuid[]) AND superseded_at IS NULL",
                    (fact_ids_to_supersede,),
                )
            print(f"  facts superseded: {len(fact_ids_to_supersede):,}")

            if fact_rows:
                insert_facts(cur, fact_rows)
            print(f"  fact rows submitted: {len(fact_rows):,}")

            # C2: the typed, non-blocking exception that replaces the old
            # fabricated-false write. Dedup + closure follow the exact
            # pattern ingest_parcels.py already uses for the APN detector
            # (existing_open_parcels/close_exceptions_for_parcels above, in
            # this same file, for DETECTOR_KEY_ZONING_UNRESOLVABLE) -- reuse,
            # not a third hand-rolled variant.
            cur.execute(
                "SELECT parcel_id FROM parcel_exception WHERE detector_key = %s AND detector_version = %s AND outcome = 'open'",
                (DETECTOR_KEY_PERMIT_ATTRIBUTION_LOST, DETECTOR_VERSION_PERMIT_ATTRIBUTION_LOST),
            )
            existing_open_permit = {r[0] for r in cur.fetchall()}
            new_permit_exceptions = [
                ParcelException(
                    parcel_id=pid, jurisdiction_id=JURISDICTION_ID, type="coverage_gap", severity="info",
                    detector_key=DETECTOR_KEY_PERMIT_ATTRIBUTION_LOST, detector_version=DETECTOR_VERSION_PERMIT_ATTRIBUTION_LOST,
                    detail={"reason": REASON_PERMIT_ATTRIBUTION_LOST},
                )
                for pid in attribution_lost_parcels
                if pid not in existing_open_permit
            ]
            if new_permit_exceptions:
                insert_exceptions(cur, new_permit_exceptions)
            print(f"  permit_attribution_lost exceptions: {len(new_permit_exceptions):,} new, "
                  f"{len(attribution_lost_parcels) - len(new_permit_exceptions):,} already open")

            permit_closed_count = close_exceptions_for_parcels(
                cur, DETECTOR_KEY_PERMIT_ATTRIBUTION_LOST, DETECTOR_VERSION_PERMIT_ATTRIBUTION_LOST,
                attribution_confirmed_parcels,
            )
            print(f"  permit_attribution_lost exceptions closed (condition_cleared): {permit_closed_count:,}")

        finish_job_run(conn, job_run_id, "succeeded", snapshot_id, rows_in, matched_rows, metrics)
        print(f"\njob_run {job_run_id} -> succeeded (rows_in={rows_in:,}, rows_out={matched_rows:,})")

    except Exception as e:
        conn.rollback()
        fail_job_run(conn, job_run_id, e)
        print(f"\njob_run {job_run_id} -> failed: {e}")
        raise

    conn.close()


def phase_permits_load(snapshot_id):
    """P45 Fix 3: same fix as phase_zoning_load above."""
    conn = get_db()
    path, snapshot = verified_snapshot_file(conn, snapshot_id, SOURCE_ID_PERMITS)
    retrieved_at = snapshot["fetched_at"]
    print(f"using verified snapshot: {snapshot_id}")
    load_permits(conn, path, snapshot_id, retrieved_at)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["zoning", "permits"], required=True)
    parser.add_argument("--phase", choices=["b", "load"], required=True)
    parser.add_argument("--snapshot-id", help="snapshot id to load for --phase load")
    args = parser.parse_args()

    if args.source == "zoning":
        if args.phase == "b":
            path1 = os.path.join(SCRATCHPAD, "zoning_districts_fetch_1.geojson")
            path2 = os.path.join(SCRATCHPAD, "zoning_districts_fetch_2.geojson")
            phase_b(SOURCE_ID_ZONING, ENDPOINT_URL_ZONING, path1, path2, "ZONING", LICENCE_ID_ZONING, "ingest_zoning")
        else:
            # P45 Fix 3: no default "newest" guess -- matches
            # ingest_parcels.py's --phase d precondition exactly.
            if not args.snapshot_id:
                raise SystemExit("--phase load requires --snapshot-id; loads must bind to an immutable snapshot row")
            phase_zoning_load(args.snapshot_id)
    else:
        if args.phase == "b":
            path1 = os.path.join(SCRATCHPAD, "permits_fetch_1.csv")
            path2 = os.path.join(SCRATCHPAD, "permits_fetch_2.csv")
            phase_b(SOURCE_ID_PERMITS, ENDPOINT_URL_PERMITS, path1, path2, "PERMITS", LICENCE_ID_PERMITS, "ingest_permits")
        else:
            if not args.snapshot_id:
                raise SystemExit("--phase load requires --snapshot-id; loads must bind to an immutable snapshot row")
            phase_permits_load(args.snapshot_id)
