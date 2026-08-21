#!/usr/bin/env python3
"""P45: does a fact's stated provenance hold up, or has something already
gone wrong? This script answers by measurement, never by argument.

For every row in `snapshot`, it re-reads the actual bytes at object_uri from
the object store, hashes them, and compares against content_hash/byte_size
-- the identical check verified_snapshot_file() (ingest_parcels.py,
ingest_zoning_permits.py) makes at load time, run here independently and
after the fact, over every snapshot ever recorded rather than only the one
a given load happens to bind to. It also reports every snapshot whose
http_status was not 2xx (or was never recorded at all), and for every
flagged snapshot -- hash mismatch, size mismatch, unreadable object, or
non-2xx status -- joins through to `fact` to report exactly which facts and
which parcels cite it.

READ ONLY. Every statement below is a SELECT. It writes no snapshot, no
fact, no job_run, nothing -- if a mismatch is found, this script reports it
and stops there; designing a fix is a different package (P45's own scope
boundary; see prompts/P45-ingest-provenance.md).

Costs real object-store reads: one GetObject per snapshot row, streamed and
hashed in full, not a HeadObject short-circuit -- byte_size and http_status
alone cannot tell you whether the bytes themselves still match, which is
the entire question this script exists to answer. Needs valid
OBJECT_STORE_URL / OBJECT_STORE_ACCESS_KEY / OBJECT_STORE_SECRET_KEY
credentials for whatever bucket the audited database's snapshot rows point
at, and DATABASE_URL for that database. Refuses a non-local DATABASE_URL
via infra.env.get_db()'s own existing LEDGEX_ALLOW_REMOTE_DB guard -- no
second guard is written here.

Every category below is counted by a direct, positive query -- "how many
snapshots have a hash match, a byte_size match, AND a 2xx status" is never
computed by subtracting the bad categories from the total. A snapshot can
be unreadable (object missing / access denied / malformed object_uri) --
that is its own category, disjoint from "hash mismatch," not folded into
it.
"""
import hashlib
import os
import sys
from urllib.parse import urlparse

import boto3
import psycopg2.extras
from botocore.exceptions import ClientError

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from infra.env import env, get_db  # noqa: E402

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB -- streamed, never buffered whole in memory


def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=env("OBJECT_STORE_URL"),
        aws_access_key_id=env("OBJECT_STORE_ACCESS_KEY"),
        aws_secret_access_key=env("OBJECT_STORE_SECRET_KEY"),
    )


def parse_s3_uri(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise RuntimeError(f"not an s3:// URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def fetch_all_snapshots(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, source_id, object_uri, content_hash, media_type,
                   byte_size, http_status, fetched_at
            FROM snapshot
            ORDER BY source_id, fetched_at
            """
        )
        return cur.fetchall()


def verify_one_snapshot(s3, row):
    """Re-read the real bytes at row['object_uri'] and compare against the
    row's own content_hash/byte_size. Returns a dict describing exactly
    what was found -- never raises for an ordinary mismatch or a missing
    object, both of which are findings this audit exists to report, not
    exceptional conditions that abort the run. A genuinely unexpected
    exception (a network failure, a malformed credential) is NOT caught
    here and is allowed to abort the whole run loudly, same as every other
    script in this repo."""
    try:
        bucket, key = parse_s3_uri(row["object_uri"])
    except RuntimeError as e:
        return {"readable": False, "reason": "malformed_object_uri", "detail": str(e)}

    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        return {"readable": False, "reason": f"object_store_error:{code}", "detail": str(e)}

    hasher = hashlib.sha256()
    byte_size = 0
    for chunk in obj["Body"].iter_chunks(chunk_size=CHUNK_SIZE):
        if not chunk:
            continue
        hasher.update(chunk)
        byte_size += len(chunk)
    digest = hasher.hexdigest()

    return {
        "readable": True,
        "hash_match": digest == row["content_hash"],
        "size_match": byte_size == row["byte_size"],
        "observed_hash": digest,
        "observed_size": byte_size,
    }


def facts_citing(conn, snapshot_ids):
    """Direct join, real column names read from the live schema (fact.id,
    fact.parcel_id, fact.field_key, fact.snapshot_id; parcel.id,
    parcel.jurisdiction_id, parcel.apn) -- not transcribed from any prompt.
    Returns {snapshot_id: [{"fact_id", "field_key", "parcel_id",
    "jurisdiction_id", "apn"}, ...]}."""
    if not snapshot_ids:
        return {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT f.snapshot_id, f.id AS fact_id, f.field_key,
                   p.id AS parcel_id, p.jurisdiction_id, p.apn
            FROM fact f
            JOIN parcel p ON p.id = f.parcel_id
            WHERE f.snapshot_id = ANY(%s)
            ORDER BY f.snapshot_id, p.jurisdiction_id, p.apn, f.field_key
            """,
            (list(snapshot_ids),),
        )
        rows = cur.fetchall()
    out = {}
    for row in rows:
        out.setdefault(row["snapshot_id"], []).append(dict(row))
    return out


def count_direct(conn, sql, params=()):
    """A category counted by its OWN positive query, never derived by
    subtracting other categories from a total."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def main():
    conn = get_db()
    s3 = get_s3()

    snapshots = fetch_all_snapshots(conn)
    total = len(snapshots)
    print(f"=== SNAPSHOT PROVENANCE AUDIT ===")
    print(f"snapshot rows found: {total}\n")

    if total == 0:
        print("No snapshot rows in this database. Nothing to audit.")
        conn.rollback()
        conn.close()
        return

    byte_flags = []      # snapshot ids where re-read bytes disagree with the row, or the object was unreadable
    status_flags = []    # snapshot ids whose recorded http_status was not 2xx (or was never recorded)
    clean_count = 0

    print("--- per-snapshot byte verification (re-read object_uri, hash, compare) ---")
    for row in snapshots:
        sid = row["id"]
        result = verify_one_snapshot(s3, row)
        if not result["readable"]:
            print(f"  UNREADABLE  {sid}  reason={result['reason']}")
            byte_flags.append((sid, result))
            continue
        if result["hash_match"] and result["size_match"]:
            clean_count += 1
            continue
        problems = []
        if not result["hash_match"]:
            problems.append(
                f"content_hash mismatch (row={row['content_hash']}, observed={result['observed_hash']})"
            )
        if not result["size_match"]:
            problems.append(
                f"byte_size mismatch (row={row['byte_size']}, observed={result['observed_size']})"
            )
        print(f"  MISMATCH    {sid}  " + "; ".join(problems))
        byte_flags.append((sid, result))

    print(f"\n  {clean_count} of {total} snapshots: bytes at object_uri match content_hash AND byte_size")
    print(f"  {len(byte_flags)} of {total} snapshots: flagged (mismatch or unreadable)")

    print("\n--- per-snapshot http_status ---")
    for row in snapshots:
        status = row["http_status"]
        ok = status is not None and 200 <= status < 300
        if not ok:
            print(f"  NON-2XX     {row['id']}  http_status={status}")
            status_flags.append(row["id"])
    print(f"\n  {len(status_flags)} of {total} snapshots: http_status was not 2xx (NULL counts as not-2xx)")

    # Direct positive queries -- never subtraction. "Good provenance" is its
    # own condition, asked for by name.
    good_status_count = count_direct(
        conn,
        "SELECT count(*) FROM snapshot WHERE http_status IS NOT NULL AND http_status BETWEEN 200 AND 299",
    )
    total_count = count_direct(conn, "SELECT count(*) FROM snapshot")
    print(f"\n  direct query -- snapshots with a recorded 2xx http_status: {good_status_count} of {total_count}")

    flagged_ids = sorted({sid for sid, _ in byte_flags} | set(status_flags))
    print(f"\n--- flagged snapshots (byte mismatch/unreadable UNION non-2xx status): {len(flagged_ids)} ---")
    for sid in flagged_ids:
        print(f"  {sid}")

    print("\n--- facts citing a flagged snapshot ---")
    citing = facts_citing(conn, flagged_ids)
    total_facts_flagged = sum(len(v) for v in citing.values())
    if not citing:
        print("  none -- no fact row cites any flagged snapshot")
    else:
        for sid in flagged_ids:
            facts = citing.get(sid, [])
            if not facts:
                print(f"  {sid}: 0 facts cite this snapshot")
                continue
            print(f"  {sid}: {len(facts)} fact row(s)")
            for f in facts:
                print(
                    f"    fact_id={f['fact_id']}  field_key={f['field_key']}  "
                    f"parcel_id={f['parcel_id']}  jurisdiction_id={f['jurisdiction_id']}  apn={f['apn']}"
                )
    print(f"\n  total fact rows citing a flagged snapshot: {total_facts_flagged}")

    # Direct positive query for the null-snapshot_id population -- reported,
    # not folded into "flagged," because a NULL snapshot_id is not what this
    # audit is measuring (fact.snapshot_id is nullable in the schema; a
    # facts-with-no-snapshot audit is a different question than "did the
    # snapshot this fact DOES cite turn out to match its own bytes").
    facts_no_snapshot = count_direct(conn, "SELECT count(*) FROM fact WHERE snapshot_id IS NULL")

    print("\n=== SUMMARY ===")
    print(f"snapshots audited:                          {total}")
    print(f"snapshots with clean bytes (hash+size match): {clean_count}")
    print(f"snapshots flagged (byte mismatch/unreadable): {len(byte_flags)}")
    print(f"snapshots flagged (non-2xx/missing status):   {len(status_flags)}")
    print(f"snapshots flagged (union of the two above):   {len(flagged_ids)}")
    print(f"fact rows citing a flagged snapshot:          {total_facts_flagged}")
    print(f"distinct parcels among those fact rows:       "
          f"{len({f['parcel_id'] for v in citing.values() for f in v})}")
    print(f"\nfact rows with snapshot_id IS NULL (separate question, not flagged): {facts_no_snapshot}")

    print("\n=== UNCOVERED BY THIS AUDIT ===")
    print("  - Whether the bytes a load actually PARSED at the time matched what is stored now:")
    print("    this audit re-reads object_uri as it exists AT AUDIT TIME. A snapshot's bytes")
    print("    could only diverge from what an earlier load consumed if the object store itself")
    print("    was mutated after that load ran -- this audit has no record of what any load")
    print("    actually read at load time, only what verified_snapshot_file() would compute now.")
    print("  - job_run rows are not examined here at all (status, error, schema_drift, metrics) --")
    print("    this audit is about snapshot bytes and fact provenance, not job execution history.")
    print("  - A snapshot with NO fact citing it is not itself flagged as a problem by this audit --")
    print("    an uncited snapshot is not a provenance defect, it is simply unused.")
    print("  - No remediation is attempted or proposed by this script. See prompts/P45-ingest-provenance.md")
    print("    for whether these findings warrant a follow-up package.")

    conn.rollback()  # no writes were made; explicit no-op to leave nothing pending
    conn.close()


if __name__ == "__main__":
    main()
