#!/usr/bin/env python3
"""P55 Phase 2 Stage 6 prep -- NOT a permanent script, a one-off utility for
this rebuild only (not wired into any make target). Two things, per the
owner's own item 5/6 instructions on 2026-08-23:

1. GENERATE THE REPLAY LIST MECHANICALLY from ledgex_schema_check's own live
   job_run table -- never from this pass's own prose, which is exactly what
   produced the ledgex_smoke permits-overreach bug this rebuild is correcting
   for. Discriminator (found live, during that bug's own diagnosis): a
   job_run row with rows_in/rows_out NULL is a --phase b fetch-only call and
   must NOT be replayed as a load; only rows with those columns populated are
   real loads that wrote facts.

2. VERIFY, don't type, every snapshot's own content_hash/byte_size: reads
   each needed snapshot's object_uri from the CURRENT (not yet renamed aside)
   ledgex_schema_check -- only to locate the bytes, not to trust the stored
   hash -- then independently downloads from S3/MinIO and re-hashes, the same
   mechanism scripts/ingest_parcels.py's own verified_snapshot_file() uses,
   reused here rather than re-implemented (imported directly).

Prints everything and does WRITE NOTHING by default. Pass --register to
actually INSERT the verified snapshot rows into DATABASE_URL (intended to be
run against the fresh, post-rename, post-migrate, post-seed ledgex_schema_check
-- the mass registration Stage 6 needs, done once, mechanically, not by hand
nine times).
"""
import hashlib
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
from ingest_parcels import get_s3, parse_s3_uri  # noqa: E402

JOB_KEYS = ("ingest_parcels", "ingest_parcels_full", "ingest_zoning", "ingest_permits")

# The three ingest constants this pass repointed (Stage 2) -- what a NEWLY
# written fact/snapshot row should cite, regardless of what the ORIGINAL row
# (queried below, read-only, from the source database) recorded historically.
LICENCE_FOR_SOURCE = {
    "ca_san_jose.parcels": "cc_by_4_0_api_2026_08",
    "ca_san_jose.zoning_districts": "cc_by_4_0_api_2026_08",
    "ca_san_jose.building_permits_active": "cc0_api_2026_08",
}


def generate_replay_list(conn):
    """Every REAL load, mechanically, in the order it actually happened.
    rows_in IS NOT NULL is the discriminator -- confirmed empirically against
    this exact database (see prompts/P55-scoped-unblock.md §12.2): every
    --phase b fetch-only job_run row here has rows_in/rows_out/metrics all
    NULL; every real --phase e/--phase load row has rows_in/rows_out
    populated. metrics is NULL even on real loads in this database's own
    history (an older column, not populated by ingest_parcels.py/
    ingest_zoning_permits.py at the time these ran) -- not used as the
    discriminator here for that reason; rows_in/rows_out alone is what this
    database's own real data actually supports."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT job_key, snapshot_id, rows_in, rows_out, started_at "
            "FROM job_run "
            "WHERE job_key = ANY(%s) AND rows_in IS NOT NULL AND rows_out IS NOT NULL "
            "ORDER BY started_at",
            (list(JOB_KEYS),),
        )
        return cur.fetchall()


def source_id_for_snapshot(snapshot_id):
    # snapshot.id format: "<source_id>:sha256:<hash>" (snapshot_id_format
    # CHECK) -- source_id is everything before the FIRST ":sha256:".
    return snapshot_id.split(":sha256:")[0]


def verify_snapshot_bytes(conn_readonly, snapshot_id):
    """Locate object_uri from the CURRENT (pre-rename) ledgex_schema_check's
    own existing row -- read-only, only to find WHERE the bytes live, never
    to trust the hash/byte_size it also carries. Independently re-downloads
    and re-hashes from S3/MinIO. Returns a dict ready to INSERT, with the
    licence_observed_id already repointed per LICENCE_FOR_SOURCE (Stage 2)."""
    with conn_readonly.cursor() as cur:
        cur.execute(
            "SELECT source_id, object_uri, media_type, http_status, fetched_at, request "
            "FROM snapshot WHERE id = %s",
            (snapshot_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise SystemExit(f"no existing snapshot row for {snapshot_id!r} in the source "
                          f"database -- cannot locate its bytes to verify.")
    source_id, object_uri, media_type, http_status, fetched_at, request = row

    bucket, key = parse_s3_uri(object_uri)
    s3 = get_s3()
    obj = s3.get_object(Bucket=bucket, Key=key)
    hasher = hashlib.sha256()
    byte_size = 0
    for chunk in obj["Body"].iter_chunks(chunk_size=8 * 1024 * 1024):
        if not chunk:
            continue
        hasher.update(chunk)
        byte_size += len(chunk)
    digest = hasher.hexdigest()

    expected_id = f"{source_id}:sha256:{digest}"
    if expected_id != snapshot_id:
        raise SystemExit(
            f"INTEGRITY FAILURE: {snapshot_id!r}'s own bytes at {object_uri!r} re-hash to "
            f"{digest!r} ({byte_size} bytes), which does not match the id's own embedded "
            f"hash. Refusing -- do not register this row.")

    licence_id = LICENCE_FOR_SOURCE.get(source_id)
    if licence_id is None:
        raise SystemExit(f"no LICENCE_FOR_SOURCE entry for source_id={source_id!r} -- "
                          f"add one before running this script.")

    return {
        "id": snapshot_id,
        "source_id": source_id,
        "object_uri": object_uri,
        "content_hash": digest,
        "media_type": media_type,
        "byte_size": byte_size,
        "request": request,
        "http_status": http_status,
        "fetched_at": fetched_at,
        "licence_observed_id": licence_id,
    }


def main():
    register = "--register" in sys.argv
    conn = get_db()

    replay = generate_replay_list(conn)
    print("=" * 78)
    print("MECHANICALLY-GENERATED REPLAY LIST (from job_run, not from prose)")
    print("=" * 78)
    for job_key, snapshot_id, rows_in, rows_out, started_at in replay:
        print(f"  {started_at}  {job_key:22s} rows_in={rows_in:>7} rows_out={rows_out:>7}  {snapshot_id}")
    print(f"\n{len(replay)} real load(s) found.\n")

    distinct_snapshots = sorted({r[1] for r in replay})
    print("=" * 78)
    print(f"VERIFYING {len(distinct_snapshots)} DISTINCT SNAPSHOT(S) AGAINST S3 (independent re-hash)")
    print("=" * 78)
    verified = {}
    for sid in distinct_snapshots:
        info = verify_snapshot_bytes(conn, sid)
        verified[sid] = info
        print(f"  OK  {sid}")
        print(f"      {info['byte_size']:,} bytes, licence_observed_id -> {info['licence_observed_id']}")
    conn.rollback()  # read-only throughout -- nothing written yet

    if not register:
        print("\n(dry run -- no rows written. Re-run with --register against the fresh, "
              "post-rename, post-migrate, post-seed ledgex_schema_check to actually insert.)")
        return

    print("\n" + "=" * 78)
    print(f"REGISTERING {len(verified)} SNAPSHOT ROW(S)")
    print("=" * 78)
    with conn.cursor() as cur:
        for sid, info in verified.items():
            cur.execute(
                "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, "
                "byte_size, request, http_status, fetched_at, licence_observed_id) "
                "VALUES (%(id)s, %(source_id)s, %(object_uri)s, %(content_hash)s, "
                "%(media_type)s, %(byte_size)s, %(request)s, %(http_status)s, "
                "%(fetched_at)s, %(licence_observed_id)s) "
                "ON CONFLICT (id) DO NOTHING",
                info,
            )
            print(f"  registered {sid}")
    conn.commit()
    print("\nDone. Replay list above is what to execute next, in that exact order.")


if __name__ == "__main__":
    main()
