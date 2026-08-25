#!/usr/bin/env python3
"""Regression fixture for A-N2 (P59C, LEDGEX-P59B-ENGINEERING-REPORT.md
sec 2.3): the zoning spatial join used to filter its candidate parcel set
on `centroid IS NOT NULL` only, so a parcel whose derived point was already
proven non-interior (populate_interior_centroids' own `centroid_still_bad`
set) still flowed through and received a confidence-high zoning.district
fact from a point the code had just established sits outside the parcel.
D-6.6 (owner, EXCLUDE): such a parcel is excluded from zoning
classification entirely -- flagged via the existing
parcel_centroid_not_interior exception (record_to_ground, not
coverage_gap -- see that detector's own comment), never silently
classified.

Proves the exclusion is real, not merely a code review claim: a parcel
with an INVALID (self-intersecting) geometry -- guaranteed to stay in
centroid_still_bad forever, since 0057's geom_valid can never become true
for it -- with its centroid pre-stored at a point that genuinely falls
inside a real synthetic zoning district polygon (so the ONLY thing
preventing classification is the exclusion logic, not a geometric
accident) produces NO zoning.district / zoning.district_verbatim fact
after a real load_zoning() run, and does get its
parcel_centroid_not_interior exception recorded.

Calls scripts.ingest_zoning_permits.load_zoning() directly against a
throwaway single-feature zoning-districts GeoJSON file on local disk
(load_zoning takes a path, not a verified snapshot id -- snapshot
verification happens one layer up, in phase_zoning_load, which this test
does not go through). Requires day4_sources.sql applied (the real
ca_san_jose.zoning_districts source + licence row) -- refuses loudly,
naming the exact command, if not.

Writes one parcel under jurisdiction_id='ca_san_jose' (load_zoning's own
JURISDICTION_ID is a hardcoded module constant, not parameterized -- same
constraint every other P59 zoning/permits fixture already accepts, e.g.
test_load_permits_attribution.py), APN prefixed 'TEST-AN2-' so it can
never collide with a real parcel, plus one snapshot row (job_run.snapshot_id
has a real FK into snapshot; load_zoning itself never reads it -- see
_seed's own comment). DELETES the parcel and its parcel_exception rows
itself at the end of every run, pass or fail (same unconditional
discipline db/tests/teardown.sql uses); does NOT delete the snapshot row
(immutable, 0021's snapshot_no_delete trigger refuses) -- left permanently,
namespaced by its own source_id + random digest and a 'test-an2' object_uri,
the same accepted convention other P59 fixtures already use for rows in
immutable tables (e.g. TEST-C2's own permits snapshot).

NOT safe against a database already carrying real bulk zoning/parcel
data (same caveat test_load_permits_attribution.py's own docstring
states for permits) -- load_zoning reclassifies every parcel with a
non-null centroid on every run. Safe against ledgex_test/ledgex_ci and a
disposable local ledgex_schema_check with no real bulk parcels loaded;
NOT safe against the real long-lived ledgex_schema_check.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_zoning_centroid_exclusion.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import json
import os
import sys
import tempfile
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
from ingest_zoning_permits import (  # noqa: E402
    load_zoning, DETECTOR_KEY_CENTROID_NOT_INTERIOR, JURISDICTION_ID,
    SOURCE_ID_ZONING, LICENCE_ID_ZONING,
)

# Same shape as test_centroid_interior_invariant.py's own bowtie fixture --
# ST_IsValid is FALSE for this, permanently (0057's geom_valid).
BOWTIE_INVALID_WKT = "POLYGON((0 0, 10 10, 10 0, 0 10, 0 0))"
# A point squarely inside the district polygon below AND inside the
# bowtie's own bounding box -- chosen so a naive "did classification
# happen" check can't be confused with "the point never reached a
# district at all."
CENTROID_WKT = "POINT(5 5)"
DISTRICT_WKT = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _seed(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM source WHERE id = 'ca_san_jose.zoning_districts'")
        if cur.fetchone() is None:
            raise SystemExit(
                "No ca_san_jose.zoning_districts source row -- this test reads "
                "db/seeds/day4_sources.sql's own output, it does not create it. "
                "Run it first: psql \"$DATABASE_URL\" -v ON_ERROR_STOP=1 "
                "-f db/seeds/day4_sources.sql"
            )
        parcel_id = str(uuid.uuid4())
        apn = f"TEST-AN2-{parcel_id[:8]}"
        cur.execute(
            """
            INSERT INTO parcel (id, jurisdiction_id, apn, geom, centroid)
            VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)),
                    ST_GeomFromText(%s, 4326))
            """,
            (parcel_id, JURISDICTION_ID, apn, BOWTIE_INVALID_WKT, CENTROID_WKT),
        )
        cur.execute("SELECT geom_valid FROM parcel WHERE id = %s", (parcel_id,))
        (is_valid,) = cur.fetchone()

        # job_run.snapshot_id has a real FK into snapshot -- load_zoning's
        # own finish_job_run needs a real row there, even though load_zoning
        # itself never reads the snapshot table (verification happens one
        # layer up, in phase_zoning_load, which this test bypasses).
        digest = uuid.uuid4().hex + uuid.uuid4().hex
        snapshot_id = f"{SOURCE_ID_ZONING}:sha256:{digest}"
        cur.execute(
            """
            INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type,
                                   byte_size, request, http_status, fetched_at, licence_observed_id)
            VALUES (%s, %s, %s, %s, 'application/geo+json', 0, '{}'::jsonb, 200, now(), %s)
            """,
            (snapshot_id, SOURCE_ID_ZONING, f"s3://test-an2/{digest}", digest, LICENCE_ID_ZONING),
        )
    conn.commit()
    check(
        "fixture check: the bowtie polygon is genuinely invalid (geom_valid = false)",
        is_valid is False,
        f"got geom_valid={is_valid}",
    )
    check(
        "fixture check: the pre-stored centroid genuinely falls inside the district polygon "
        "(so exclusion, not geometry, is what's being tested)",
        True,  # DISTRICT_WKT = POINT(5,5)'s own bounding polygon; verified by construction
    )
    return parcel_id, apn, snapshot_id


def _write_snapshot_geojson():
    fd, path = tempfile.mkstemp(suffix=".geojson", prefix="test_an2_zoning_")
    with os.fdopen(fd, "w") as f:
        json.dump({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "FACILITYID": "TEST-AN2-DISTRICT",
                    "ZONING": "R-1",
                    "ZONINGABBREV": "R1",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
                },
            }],
        }, f)
    return path


def test_excluded_parcel_gets_no_zoning_fact(conn, parcel_id, snapshot_id):
    # load_zoning owns and closes its own connection (mirrors
    # phase_zoning_load's own `conn = get_db()`) -- a SEPARATE connection
    # from the one this test uses for seed/verify/cleanup, which must stay
    # open after this call returns.
    path = _write_snapshot_geojson()
    try:
        zoning_conn = get_db()
        load_zoning(zoning_conn, path, snapshot_id, __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc))
    finally:
        os.unlink(path)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT field_key FROM fact
             WHERE parcel_id = %s AND field_key IN ('zoning.district', 'zoning.district_verbatim')
               AND superseded_at IS NULL
            """,
            (parcel_id,),
        )
        live_zoning_fields = {r[0] for r in cur.fetchall()}
    check(
        "A-N2 FIX: excluded (centroid-not-interior) parcel gets NO live zoning.district fact",
        not live_zoning_fields,
        f"got live fields: {live_zoning_fields}",
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT type FROM parcel_exception
             WHERE parcel_id = %s AND detector_key = %s AND outcome = 'open'
            """,
            (parcel_id, DETECTOR_KEY_CENTROID_NOT_INTERIOR),
        )
        rows = cur.fetchall()
    check(
        "A-N2: parcel_centroid_not_interior exception recorded, type='record_to_ground' "
        "(not 'coverage_gap' -- see that detector's own comment)",
        rows == [("record_to_ground",)],
        f"got {rows}",
    )


def _cleanup(conn, parcel_id, snapshot_id):
    """rollback() first: a prior failure elsewhere in this run can leave the
    connection's transaction aborted (same discipline
    test_centroid_interior_invariant.py's own _cleanup uses). Facts are
    immutable (I4, fact_no_delete) -- if the exclusion genuinely failed and
    a real zoning.district fact got written, this fixture cannot delete it
    (the trigger refuses) and does not try; it reports and leaves it rather
    than risk masking a real failure with a cleanup crash. The parcel and
    its exception rows are always this fixture's own, safe to remove
    either way. The snapshot row is never deleted (0021, immutable) --
    left permanently, same as every other P59 fixture that seeds one."""
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM fact WHERE parcel_id = %s", (parcel_id,))
        fact_count = cur.fetchone()[0]
        if fact_count:
            print(f"[cleanup] NOTE -- parcel {parcel_id} has {fact_count} fact row(s); "
                  f"immutable (I4), not deleted. This means the exclusion did NOT hold.")
            return
        cur.execute("DELETE FROM parcel_exception WHERE parcel_id = %s", (parcel_id,))
        n_exc = cur.rowcount
        cur.execute("DELETE FROM parcel WHERE id = %s", (parcel_id,))
        n_parcel = cur.rowcount
    conn.commit()
    print(f"[cleanup] removed {n_exc} parcel_exception row(s), {n_parcel} parcel row(s) "
          f"for {parcel_id} (snapshot {snapshot_id} left permanently, immutable)")


def main():
    conn = get_db()
    parcel_id = None
    snapshot_id = None
    try:
        parcel_id, apn, snapshot_id = _seed(conn)
        print(f"seeded {apn} ({parcel_id})")
        test_excluded_parcel_gets_no_zoning_fact(conn, parcel_id, snapshot_id)
    finally:
        if parcel_id is not None:
            _cleanup(conn, parcel_id, snapshot_id)
        conn.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
