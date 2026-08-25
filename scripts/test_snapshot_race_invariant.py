#!/usr/bin/env python3
"""Invariant test for the snapshot-dedup race (README finding #10).

Invariant under test: two concurrent fetches of identical NEW content
(same digest, so the same deterministic snapshot.id) must never crash the
loser. insert_snapshot()'s INSERT is ON CONFLICT (id) DO NOTHING, and the
loser's job_run status must be decided from insert_snapshot()'s own INSERT
rowcount ("inserted"), not from the earlier snapshot_exists() SELECT --
see both functions' own docstrings in ingest_parcels.py/
ingest_zoning_permits.py for the full argument.

Does not need real thread concurrency to prove this: Postgres's own
read-committed semantics make two SEQUENCED connections deterministic --
conn_a's INSERT commits, THEN conn_b's INSERT runs and sees the row
conn_a just committed. That is exactly the losing side of the race
(both connections' own prior snapshot_exists() SELECT already ran and
saw nothing, before either INSERT). Two real, separate psycopg2
connections against a real database, not a mock.

RED proof (this invariant existing at all) is NOT re-run every time this
file runs -- it was a one-time demonstration, using the pre-fix bare
INSERT SQL directly (no ON CONFLICT), shown to raise
psycopg2.errors.UniqueViolation deterministically on the second
connection. See prompts/P19-snapshot-dedup-race.md for that transcript.
This file tests only the fixed, current behavior -- a real regression
guard needs to assert what SHOULD happen going forward, not re-break
itself on every run.

Tests BOTH scripts' insert_snapshot() -- near-duplicate functions with
different signatures, fixed separately, not unified (see
prompts/P19-snapshot-dedup-race.md for why extracting a shared primitive
here would be scope creep).

Runs against a real database (this test commits real, permanent snapshot
rows -- 0021 makes snapshot undeletable, same as fact/rule/licence/
licence_channel -- every run uses a fresh, uniquely-content-hashed digest
so repeated runs never collide with a prior run's rows). Reference rows
(licence/jurisdiction/source/field_definition) seeded with the REAL ids
ingest_parcels.py/ingest_zoning_permits.py hardcode, using the SAME
honest, non-fabricated observed_at/cleared_by/cleared_at values
db/seeds/day4_sources.sql itself uses -- NOT the licence-contamination
shape P11 step 4 fixed in scripts/_p5_setup.py, scripts/_phaseb_setup.py
and this file's three siblings (test_refresh_failure_invariant.py,
test_apn_canonicalization_invariant.py, test_zoning_ambiguity_invariant.py):
counsel/owner sign-off is genuinely still Pending, and no insert in this
repo may claim otherwise.

Requires DATABASE_URL only -- insert_snapshot()/snapshot_exists() are
pure database functions, no object-store interaction (that is
upload_and_verify(), a separate function this test does not call).

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_snapshot_race_invariant.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import datetime
import hashlib
import os
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import ingest_parcels as ip  # noqa: E402 -- module under test, imported, not reimplemented
import ingest_zoning_permits as izp  # noqa: E402 -- module under test, imported, not reimplemented
from infra.env import get_db  # noqa: E402

# C15 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): the ONE source of truth
# for the cc_by_4_0_api_2026_08 licence's display_name/attribution_text,
# byte-identical to db/seeds/day4_sources.sql's own values (confirmed by
# reading that file directly before writing these constants, not
# transcribed from memory). licence is immutable (0027) and every seeder
# here is ON CONFLICT DO NOTHING, so first-writer-wins, permanently -- a
# seeder using anything other than these exact strings corrupts the
# licence's attribution obligation on whatever database it reaches first,
# forever (fixable only by rebuild). This module runs in CI BEFORE
# db/seeds/day4_sources.sql (see this file's own docstring), so it cannot
# simply stop seeding and depend on the real seed -- it must seed the
# canonical values itself. scripts/test_zoning_ambiguity_invariant.py
# imports these same two constants rather than carrying its own copy, so
# the two can no longer independently drift from each other OR from
# day4_sources.sql the way they did before this fix (verified live via S3,
# this pass's own database check: one long-lived database,
# ledgex_smoke_pre_p55_20260822, already carries the wrong, pre-fix
# attribution permanently -- flagged, not repairable, see the P59
# deliverable's S3 row).
CC_BY_4_0_API_2026_08_DISPLAY_NAME = "CC BY 4.0 (api channel, scoped 2026-08)"
CC_BY_4_0_API_2026_08_ATTRIBUTION_TEXT = "Data © City of San José"

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def seed_reference_rows_parcels(conn):
    """Same honest, non-fabricated pattern as test_refresh_failure_invariant.py's
    seed_reference_rows() -- see its own comment for why observed_at/
    cleared_by/cleared_at match db/seeds/day4_sources.sql exactly."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, observed_at, cleared_by, cleared_at)
            VALUES (%s, %s, 'attribution', 'allowed', 'allowed', %s,
                    '2026-07-31'::timestamptz, NULL, NULL)
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.LICENCE_ID, CC_BY_4_0_API_2026_08_DISPLAY_NAME, CC_BY_4_0_API_2026_08_ATTRIBUTION_TEXT),
        )
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES (%s, 'City of San Jose', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.JURISDICTION_ID,),
        )
        cur.execute(
            """
            INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status,
                                 phase_status_reason, endpoint_url, licence_id, active)
            VALUES (%s, %s, 'Parcels', 'City of San Jose', 'bulk', 'active', 'test fixture',
                    'https://example.com/parcels', %s, false)
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.SOURCE_ID, ip.JURISDICTION_ID, ip.LICENCE_ID),
        )
    conn.commit()


def seed_reference_rows_zoning(conn):
    """Same pattern, izp's zoning source/licence -- test_zoning_ambiguity_
    invariant.py's own seed_reference_rows() is the precedent."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, observed_at, cleared_by, cleared_at)
            VALUES (%s, %s, 'attribution', 'allowed', 'allowed', %s,
                    '2026-07-31'::timestamptz, NULL, NULL)
            ON CONFLICT (id) DO NOTHING
            """,
            (izp.LICENCE_ID_ZONING, CC_BY_4_0_API_2026_08_DISPLAY_NAME, CC_BY_4_0_API_2026_08_ATTRIBUTION_TEXT),
        )
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES (%s, 'City of San Jose', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """,
            (izp.JURISDICTION_ID,),
        )
        cur.execute(
            """
            INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status,
                                 phase_status_reason, endpoint_url, licence_id, active)
            VALUES (%s, %s, 'Zoning districts', 'City of San Jose', 'bulk', 'active', 'test fixture',
                    %s, %s, false)
            ON CONFLICT (id) DO NOTHING
            """,
            (izp.SOURCE_ID_ZONING, izp.JURISDICTION_ID, izp.ENDPOINT_URL_ZONING, izp.LICENCE_ID_ZONING),
        )
    conn.commit()


def race_ingest_parcels():
    """Two connections, sequenced (not threaded -- see module docstring),
    both call snapshot_exists() before either has inserted, then both
    call the REAL insert_snapshot(). Winner must report inserted=True;
    loser must report inserted=False with NO exception; exactly one row
    must exist afterward."""
    conn_seed = get_db()
    seed_reference_rows_parcels(conn_seed)
    conn_seed.close()

    digest = hashlib.sha256(uuid.uuid4().bytes).hexdigest()  # snapshot_content_hash_format (0021): must be 64 lowercase hex chars
    sid = ip.snapshot_id_for(digest)

    conn_a = get_db()
    conn_b = get_db()

    exists_a = ip.snapshot_exists(conn_a, sid)
    exists_b = ip.snapshot_exists(conn_b, sid)
    check("ingest_parcels: conn_a sees not-exists before either insert", exists_a is False, f"got {exists_a}")
    check("ingest_parcels: conn_b sees not-exists before either insert", exists_b is False, f"got {exists_b}")

    fetched_at = datetime.datetime.now(datetime.timezone.utc)
    args = (digest, 123, "application/json", 200, fetched_at, "test-bucket")
    sid_a, inserted_a = ip.insert_snapshot(conn_a, *args)
    sid_b, inserted_b = ip.insert_snapshot(conn_b, *args)

    check("ingest_parcels: winner (conn_a) reports inserted=True", inserted_a is True, f"got {inserted_a}")
    check("ingest_parcels: loser (conn_b) reports inserted=False, no exception raised",
          inserted_b is False, f"got {inserted_b}")
    check("ingest_parcels: both return the same sid", sid_a == sid_b == sid,
          f"sid_a={sid_a!r} sid_b={sid_b!r} sid={sid!r}")

    conn_a.close()
    conn_b.close()

    check_conn = get_db()
    with check_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM snapshot WHERE id = %s", (sid,))
        row_count = cur.fetchone()[0]
    check_conn.close()
    check("ingest_parcels: exactly one snapshot row exists after both connections ran",
          row_count == 1, f"got {row_count}")


def race_ingest_zoning_permits():
    """Same shape as race_ingest_parcels(), against izp's own insert_snapshot()
    -- deliberately not sharing code with the above; the two production
    functions are near-duplicates fixed separately, not unified (P19), and
    this test mirrors that rather than hiding it behind a shared helper."""
    conn_seed = get_db()
    seed_reference_rows_zoning(conn_seed)
    conn_seed.close()

    digest = hashlib.sha256(uuid.uuid4().bytes).hexdigest()  # snapshot_content_hash_format (0021): must be 64 lowercase hex chars
    sid = izp.snapshot_id_for(izp.SOURCE_ID_ZONING, digest)

    conn_a = get_db()
    conn_b = get_db()

    exists_a = izp.snapshot_exists(conn_a, sid)
    exists_b = izp.snapshot_exists(conn_b, sid)
    check("ingest_zoning_permits: conn_a sees not-exists before either insert", exists_a is False, f"got {exists_a}")
    check("ingest_zoning_permits: conn_b sees not-exists before either insert", exists_b is False, f"got {exists_b}")

    fetched_at = datetime.datetime.now(datetime.timezone.utc)
    args = (izp.SOURCE_ID_ZONING, digest, 123, "application/json", 200, fetched_at,
            "test-bucket", izp.ENDPOINT_URL_ZONING, izp.LICENCE_ID_ZONING)
    sid_a, inserted_a = izp.insert_snapshot(conn_a, *args)
    sid_b, inserted_b = izp.insert_snapshot(conn_b, *args)

    check("ingest_zoning_permits: winner (conn_a) reports inserted=True", inserted_a is True, f"got {inserted_a}")
    check("ingest_zoning_permits: loser (conn_b) reports inserted=False, no exception raised",
          inserted_b is False, f"got {inserted_b}")
    check("ingest_zoning_permits: both return the same sid", sid_a == sid_b == sid,
          f"sid_a={sid_a!r} sid_b={sid_b!r} sid={sid!r}")

    conn_a.close()
    conn_b.close()

    check_conn = get_db()
    with check_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM snapshot WHERE id = %s", (sid,))
        row_count = cur.fetchone()[0]
    check_conn.close()
    check("ingest_zoning_permits: exactly one snapshot row exists after both connections ran",
          row_count == 1, f"got {row_count}")


if __name__ == "__main__":
    race_ingest_parcels()
    race_ingest_zoning_permits()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)
