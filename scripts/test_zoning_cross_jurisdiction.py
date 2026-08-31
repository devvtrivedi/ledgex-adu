#!/usr/bin/env python3
"""Regression fixture for P61A: scripts/ingest_zoning_permits.py had no
jurisdiction filter on any of its four `FROM parcel` reads
(populate_interior_centroids' UPDATE and residual SELECT, load_zoning's
spatial-join candidate set and its all_parcel_ids classification set),
while every downstream write hardcodes jurisdiction_id=JURISDICTION_ID
("ca_san_jose", this module's own module-level constant). A parcel
belonging to any OTHER jurisdiction that reached a write path violated one
of two composite foreign keys (fact_parcel_jurisdiction_fk,
parcel_exception_parcel_jurisdiction_fk -- both correctly checking
(parcel_id, jurisdiction_id) against the real parcel row) and aborted the
whole load_zoning transaction.

First observed by P61's rehearsal via a test_p59_c4 fixture parcel whose
centroid this module's own C1 fix (populate_interior_centroids) populated
for the very first time -- fixtures never go through Phase D, so a
never-populated centroid had always kept such parcels out of the
classification loop before C1 stopped skipping NULL-centroid rows
unconditionally. See P61-REHEARSAL-REPORT.md sec5 and P61A-LEDGER.md.

Two independent scenarios, because the two foreign keys fire at different
points in load_zoning's own write order (supersede -> insert_facts ->
close -> insert_exceptions -- see load_zoning's own body) and a foreign
parcel that MATCHES a district masks a foreign parcel that ZERO-MATCHES,
by aborting the transaction first:

  1. A foreign-jurisdiction parcel whose (pre-set, not derived) centroid
     falls INSIDE the one throwaway district polygon below -- classified
     "matched", reaches insert_facts BEFORE any exception code runs. This
     is fact_parcel_jurisdiction_fk, and P61 never saw it (its own fixture
     parcel zero-matched).
  2. A foreign-jurisdiction parcel whose centroid falls OUTSIDE every real
     district polygon -- classified "zero_match", reaches insert_exceptions
     with a coverage_gap ParcelException. This is
     parcel_exception_parcel_jurisdiction_fk, the one P61 actually hit.

The fix (P61A-1) scopes all four `FROM parcel` reads to
jurisdiction_id=JURISDICTION_ID, so neither foreign parcel ever enters
`all_parcel_ids` at all -- no fact, no exception, no FK violation, for
either.

Calls scripts.ingest_zoning_permits.load_zoning() directly against a
throwaway single-feature zoning-districts GeoJSON file on local disk, same
shape scripts/test_zoning_centroid_exclusion.py already uses. Requires
day4_sources.sql applied (the real ca_san_jose.zoning_districts source +
licence row) -- refuses loudly, naming the exact command, if not.

Creates one throwaway jurisdiction row ('test_p61a_foreign', ON CONFLICT
DO NOTHING, never deleted -- same permanent-fixture-infrastructure
convention scripts/test_flag_invalid_geometry.py's own 'test_p59_c4' row
already uses) plus two parcels under it, APN-prefixed 'TEST-P61A-' so they
can never collide with a real parcel. DELETES both parcels itself at the
end of every run, pass or fail (same unconditional discipline
db/tests/teardown.sql uses) -- safe to delete unconditionally because on
GREEN neither parcel ever gets a fact or exception row, and on RED
load_zoning's own except block rolls back its transaction before this
script's cleanup ever runs, so nothing downstream of the parcel exists to
delete either way. Does NOT delete the jurisdiction row or either snapshot
row (immutable infrastructure, same convention as every other P59 zoning
fixture).

NOT safe against a database already carrying real bulk zoning/parcel data
-- load_zoning reclassifies every parcel with a non-null centroid under
JURISDICTION_ID on every run. Safe against ledgex_test/ledgex_ci and a
disposable local ledgex_schema_check with no real bulk parcels loaded;
NOT safe against the real long-lived ledgex_schema_check.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_zoning_cross_jurisdiction.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import json
import os
import sys
import tempfile
import uuid
import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
from ingest_zoning_permits import (  # noqa: E402
    load_zoning, JURISDICTION_ID, SOURCE_ID_ZONING, LICENCE_ID_ZONING,
)

FOREIGN_JURISDICTION_ID = "test_p61a_foreign"

# A small valid square, unrelated to the district polygon below -- only
# `centroid` (pre-set directly, not derived) drives the join; geom just
# needs to be a real, valid polygon so nothing downstream chokes on NULL.
# Deliberately NOT (0,0)-(10,10): that exact square is already in permanent
# use by the real database's own test_p59_c4 fixture parcels (verified --
# `SELECT ST_AsText(geom) FROM parcel WHERE jurisdiction_id='test_p59_c4'`
# returns MULTIPOLYGON(((0 0,10 0,10 10,0 10,0 0))) for all four of them).
# Reusing it here would let load_zoning's centroid-population UPDATE (on
# unscoped/pre-fix code) drag those OTHER foreign fixtures into this
# script's own snapshot's candidate set too, contaminating scenario
# isolation -- found for real, not by inspection: the first RED run of
# this test (on the pre-fix tree) showed 4 "matched" parcels, not the 1
# this script seeded, because test_p59_c4's own fixtures matched the same
# polygon this test used to use.
PARCEL_GEOM_WKT = "POLYGON((600 600, 600 601, 601 601, 601 600, 600 600))"

# The one throwaway zoning district in the snapshot both scenarios share.
DISTRICT_WKT = "POLYGON((500 500, 510 500, 510 510, 500 510, 500 500))"
MATCHED_CENTROID_WKT = "POINT(505 505)"       # inside DISTRICT_WKT -> "matched"
ZERO_MATCH_CENTROID_WKT = "POINT(-500 -500)"  # nowhere near it -> "zero_match"

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _seed_jurisdiction(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM source WHERE id = 'ca_san_jose.zoning_districts'")
        if cur.fetchone() is None:
            raise SystemExit(
                "No ca_san_jose.zoning_districts source row -- this test reads "
                "db/seeds/day4_sources.sql's own output, it does not create it. "
                "Run it first: psql \"$DATABASE_URL\" -v ON_ERROR_STOP=1 "
                "-f db/seeds/day4_sources.sql"
            )
        cur.execute(
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported) "
            "VALUES (%s, 'P61A cross-jurisdiction test fixture', 'city', 'CA', 'v1.0', true) "
            "ON CONFLICT (id) DO NOTHING",
            (FOREIGN_JURISDICTION_ID,),
        )
    conn.commit()


def _seed_foreign_parcel(conn, centroid_wkt, apn_suffix):
    with conn.cursor() as cur:
        parcel_id = str(uuid.uuid4())
        apn = f"TEST-P61A-{apn_suffix}-{parcel_id[:8]}"
        cur.execute(
            """
            INSERT INTO parcel (id, jurisdiction_id, apn, geom, centroid)
            VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)),
                    ST_GeomFromText(%s, 4326))
            """,
            (parcel_id, FOREIGN_JURISDICTION_ID, apn, PARCEL_GEOM_WKT, centroid_wkt),
        )
        cur.execute("SELECT jurisdiction_id FROM parcel WHERE id = %s", (parcel_id,))
        (seeded_jurisdiction,) = cur.fetchone()
    conn.commit()
    check(
        f"fixture check ({apn_suffix}): parcel seeded under a NON-ca_san_jose jurisdiction",
        seeded_jurisdiction == FOREIGN_JURISDICTION_ID and seeded_jurisdiction != JURISDICTION_ID,
        f"got jurisdiction_id={seeded_jurisdiction!r}",
    )
    return parcel_id, apn


def _seed_snapshot(conn):
    # job_run.snapshot_id has a real FK into snapshot -- load_zoning's own
    # finish_job_run/fail_job_run need a real row here, even though
    # load_zoning itself never reads the snapshot table (verification
    # happens one layer up, in phase_zoning_load, which this test bypasses).
    digest = uuid.uuid4().hex + uuid.uuid4().hex
    snapshot_id = f"{SOURCE_ID_ZONING}:sha256:{digest}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type,
                                   byte_size, request, http_status, fetched_at, licence_observed_id)
            VALUES (%s, %s, %s, %s, 'application/geo+json', 0, '{}'::jsonb, 200, now(), %s)
            """,
            (snapshot_id, SOURCE_ID_ZONING, f"s3://test-p61a/{digest}", digest, LICENCE_ID_ZONING),
        )
    conn.commit()
    return snapshot_id


def _write_snapshot_geojson():
    fd, path = tempfile.mkstemp(suffix=".geojson", prefix="test_p61a_zoning_")
    with os.fdopen(fd, "w") as f:
        json.dump({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "FACILITYID": "TEST-P61A-DISTRICT",
                    "ZONING": "R-1",
                    "ZONINGABBREV": "R1",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[500, 500], [510, 500], [510, 510], [500, 510], [500, 500]]],
                },
            }],
        }, f)
    return path


def _run_load_zoning(snapshot_id):
    # load_zoning owns and closes its own connection (mirrors
    # phase_zoning_load's own `conn = get_db()`) -- a SEPARATE connection
    # from the one this script's seed/verify/cleanup uses, which must stay
    # open across both scenarios.
    path = _write_snapshot_geojson()
    try:
        zoning_conn = get_db()
        load_zoning(zoning_conn, path, snapshot_id,
                     datetime.datetime.now(datetime.timezone.utc))
    finally:
        os.unlink(path)


def _assert_no_live_rows(conn, parcel_id, label):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT field_key FROM fact
             WHERE parcel_id = %s AND field_key IN ('zoning.district', 'zoning.district_verbatim')
               AND superseded_at IS NULL
            """,
            (parcel_id,),
        )
        live_fields = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT type FROM parcel_exception WHERE parcel_id = %s", (parcel_id,))
        exception_rows = cur.fetchall()
    check(
        f"{label}: foreign parcel gets NO live zoning fact",
        not live_fields,
        f"got live fields: {live_fields}",
    )
    check(
        f"{label}: foreign parcel gets NO parcel_exception row",
        not exception_rows,
        f"got: {exception_rows}",
    )


def scenario_matched(conn):
    """Foreign parcel whose centroid falls inside a real district ->
    "matched" -> reaches insert_facts. Pre-fix: fact_parcel_jurisdiction_fk."""
    parcel_id, apn = _seed_foreign_parcel(conn, MATCHED_CENTROID_WKT, "MATCHED")
    snapshot_id = _seed_snapshot(conn)
    print(f"[scenario 1: matched] seeded {apn} ({parcel_id})")
    try:
        _run_load_zoning(snapshot_id)
    except Exception as e:
        check("scenario 1 (matched foreign parcel): load_zoning does NOT raise", False,
              f"{type(e).__name__}: {e}")
        check(
            "scenario 1: the error, if any, is the expected fact_parcel_jurisdiction_fk "
            "(proves this is the real defect, not an unrelated crash)",
            "fact_parcel_jurisdiction_fk" in str(e),
            f"got: {type(e).__name__}: {e}",
        )
        conn.rollback()
        return parcel_id
    _assert_no_live_rows(conn, parcel_id, "scenario 1 (matched)")
    return parcel_id


def scenario_zero_match(conn):
    """Foreign parcel whose centroid falls outside every real district ->
    "zero_match" -> reaches insert_exceptions. Pre-fix:
    parcel_exception_parcel_jurisdiction_fk -- the one P61 actually hit."""
    parcel_id, apn = _seed_foreign_parcel(conn, ZERO_MATCH_CENTROID_WKT, "ZEROMATCH")
    snapshot_id = _seed_snapshot(conn)
    print(f"[scenario 2: zero-match] seeded {apn} ({parcel_id})")
    try:
        _run_load_zoning(snapshot_id)
    except Exception as e:
        check("scenario 2 (zero-match foreign parcel): load_zoning does NOT raise", False,
              f"{type(e).__name__}: {e}")
        check(
            "scenario 2: the error, if any, is the expected "
            "parcel_exception_parcel_jurisdiction_fk (P61's own failure)",
            "parcel_exception_parcel_jurisdiction_fk" in str(e),
            f"got: {type(e).__name__}: {e}",
        )
        conn.rollback()
        return parcel_id
    _assert_no_live_rows(conn, parcel_id, "scenario 2 (zero-match)")
    return parcel_id


def _cleanup(conn, parcel_ids):
    conn.rollback()
    with conn.cursor() as cur:
        for parcel_id in parcel_ids:
            cur.execute("SELECT count(*) FROM fact WHERE parcel_id = %s", (parcel_id,))
            (fact_count,) = cur.fetchone()
            if fact_count:
                print(f"[cleanup] NOTE -- parcel {parcel_id} has {fact_count} fact row(s); "
                      f"immutable (I4), not deleted. The fix did NOT hold for this parcel.")
                continue
            cur.execute("DELETE FROM parcel_exception WHERE parcel_id = %s", (parcel_id,))
            cur.execute("DELETE FROM parcel WHERE id = %s", (parcel_id,))
    conn.commit()
    print(f"[cleanup] removed parcel/parcel_exception rows for {len(parcel_ids)} fixture parcel(s) "
          f"(jurisdiction '{FOREIGN_JURISDICTION_ID}' and both snapshot rows left permanently)")


def main():
    conn = get_db()
    _seed_jurisdiction(conn)
    parcel_ids = []
    try:
        parcel_ids.append(scenario_matched(conn))
        parcel_ids.append(scenario_zero_match(conn))
    finally:
        _cleanup(conn, [p for p in parcel_ids if p is not None])
        conn.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
