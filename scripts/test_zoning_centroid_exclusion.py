#!/usr/bin/env python3
"""Regression fixture for A-N2 (P59C, LEDGEX-P59B-ENGINEERING-REPORT.md
sec 2.3) and its narrowing under D-6.6 (P61G, 2026-08-31): the zoning
spatial join used to filter its candidate parcel set on `centroid IS NOT
NULL` only, so a parcel whose derived point was already proven
non-interior (populate_interior_centroids' own `centroid_still_bad` set)
still flowed through and received a confidence-high zoning.district fact
from a point the code had just established sits outside the parcel. D-6.6
(owner, EXCLUDE) says such a parcel is excluded from zoning classification
entirely -- flagged via the existing parcel_centroid_not_interior
exception (record_to_ground, not coverage_gap -- see that detector's own
comment), never silently classified.

**Corrected 2026-09-01 (P61Y).** This file's original premise was that ANY
invalid (self-intersecting) geometry is "guaranteed to stay in
centroid_still_bad forever, since 0057's geom_valid can never become
true" -- true before P61G, false after. Under narrowed D-6.6,
populate_interior_centroids derives from
`ST_CollectionExtract(ST_MakeValid(geom), 3)`: a parcel whose invalid
geometry repairs into a genuinely usable polygon is no longer
"known-non-interior" and IS classified, using a centroid interior to the
repaired geometry. What decides exclusion now is not `geom_valid` by
itself, but whether the repair succeeds. This file's own former fixture
(the bowtie below, `BOWTIE_INVALID_WKT`) repairs into two real triangles
-- verified directly here, the same fact P61G's own ledger already
recorded for the identical shape in test_centroid_interior_invariant.py
-- so it no longer belongs in a "stays excluded forever" arm; it is now
the "repairs and gets classified" arm below, and the "stays excluded" arm
uses a genuinely unrepairable geometry instead (`DEGENERATE_LINE_WKT`,
also verified directly here to repair to `POLYGON EMPTY`). The file's own
contract is unchanged -- a parcel whose point cannot be proven interior
gets no classification -- only which parcels that describes has narrowed.

Proves both directions of the narrowed boundary in ONE real `load_zoning()`
run against ONE shared district, so the repairable arm's own successful
classification is the positive control for the unrepairable arm's
exclusion claim: same placement, same one-feature district, different
geometry validity/repairability. A fixture that sat outside every
district would pass trivially and prove a zero-match, not an exclusion --
CONVENTIONS.md's "test that encodes the bug" shape, green and worthless.
Confirmed directly below, not assumed: `DISTRICT_WKT` genuinely contains
both the unrepairable arm's pre-stored centroid and the repairable arm's
own freshly-derived one.

  - UNREPAIRABLE: a degenerate, zero-area "polygon" (a ring that doubles
    back on itself) -- ST_IsValid = false, and its repair is genuinely
    unusable (verified below: `ST_CollectionExtract(ST_MakeValid(...), 3)`
    is `POLYGON EMPTY`). Its centroid is PRE-STORED inside the district
    polygon, so the only thing preventing classification is the exclusion
    logic, not a geometric accident -- the positive control (the
    repairable arm, same placement) shows this location classifies for a
    repairable geometry. Must receive NO zoning.district /
    zoning.district_verbatim fact, and must get a
    parcel_centroid_not_interior exception (record_to_ground).

  - REPAIRABLE: the bowtie -- ST_IsValid = false, but its repair (verified
    below) is two real triangles, non-empty. Must receive a live
    zoning.district fact, get NO parcel_centroid_not_interior exception,
    keep geom_valid = false (the stored geometry is still invalid; the
    repair is derivation-time-only, never persisted -- P61G's own R5), and
    keep open a parcel_geometry_invalid exception -- the SEPARATE
    detector flag_invalid_geometry.py raises for any parcel with invalid
    geometry (its own type/severity/detail shape, `DETECTOR_KEY_PARCEL_GEOM`
    = "parcel_geometry_invalid", confirmed against
    scripts/flag_invalid_geometry.py:165-167,252-255, not re-derived from
    memory), tested by test_flag_invalid_geometry.py, not re-tested here.
    This file seeds one directly, mirroring that script's own insert
    shape, purely to prove load_zoning's narrowed derivation does not
    touch a different detector's exception -- it does not invoke
    flag_invalid_geometry.py itself, which is out of this file's scope.

Calls scripts.ingest_zoning_permits.load_zoning() directly against a
throwaway single-feature zoning-districts GeoJSON file on local disk
(load_zoning takes a path, not a verified snapshot id -- snapshot
verification happens one layer up, in phase_zoning_load, which this test
does not go through). Requires day4_sources.sql applied (the real
ca_san_jose.zoning_districts source + licence row) -- refuses loudly,
naming the exact command, if not.

Writes two parcels under jurisdiction_id='ca_san_jose' (load_zoning's own
JURISDICTION_ID is a hardcoded module constant, not parameterized -- same
constraint every other P59 zoning/permits fixture already accepts, e.g.
test_load_permits_attribution.py), APN prefixed 'TEST-AN2-' so they can
never collide with a real parcel, plus one snapshot row (job_run.snapshot_id
has a real FK into snapshot; load_zoning itself never reads it -- see
_seed's own comment). DELETES each parcel and its parcel_exception rows
itself at the end of every run, pass or fail (same unconditional
discipline db/tests/teardown.sql uses); the REPAIRABLE parcel will have
live facts by design (that is the assertion), so I4 correctly leaves its
row (and the parcel_geometry_invalid exception this file seeded for it)
untouched -- same as every other fixture in this repo that seeds a
parcel expected to classify. Does NOT delete the snapshot row (immutable,
0021's snapshot_no_delete trigger refuses) -- left permanently, namespaced
by its own source_id + random digest and a 'test-an2' object_uri, the
same accepted convention other P59 fixtures already use for rows in
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
from core.model import ParcelException  # noqa: E402
from core.exceptions import insert_exceptions  # noqa: E402
from ingest_zoning_permits import (  # noqa: E402
    load_zoning, DETECTOR_KEY_CENTROID_NOT_INTERIOR, JURISDICTION_ID,
    SOURCE_ID_ZONING, LICENCE_ID_ZONING,
)

# Mirrors scripts/flag_invalid_geometry.py:165-167's own constants exactly
# (verified there, not re-derived) -- this file seeds a parcel_geometry_
# invalid exception directly, it does not import or run that script.
DETECTOR_KEY_PARCEL_GEOM = "parcel_geometry_invalid"
DETECTOR_VERSION_PARCEL_GEOM = "1.0"

# UNREPAIRABLE arm: same degenerate, zero-area, self-doubling-back ring
# P61G already found and verified (test_centroid_interior_invariant.py:146)
# repairs to POLYGON EMPTY. Re-verified directly in _seed_unrepairable
# below, not trusted from that citation alone.
DEGENERATE_LINE_WKT = "POLYGON((0 0, 10 0, 5 0, 0 0))"

# REPAIRABLE arm: the same bowtie this file used to (wrongly) treat as
# permanently excluded. ST_IsValid(this) is FALSE, but
# ST_CollectionExtract(ST_MakeValid(this), 3) is two real triangles --
# re-verified directly in _seed_repairable below.
BOWTIE_INVALID_WKT = "POLYGON((0 0, 10 10, 10 0, 0 10, 0 0))"

# Shared district, sized to the bowtie's own bounding box so both arms'
# points -- the unrepairable arm's pre-stored one and the repairable arm's
# freshly-derived one -- land inside it.
DISTRICT_WKT = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"
# The unrepairable arm's pre-stored centroid: the bowtie's own former
# self-intersection point, deliberately inside DISTRICT_WKT.
UNREPAIRABLE_CENTROID_WKT = "POINT(5 5)"

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _seed_unrepairable(conn):
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
        apn = f"TEST-AN2-UNREPAIRABLE-{parcel_id[:8]}"
        cur.execute(
            """
            INSERT INTO parcel (id, jurisdiction_id, apn, geom, centroid)
            VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)),
                    ST_GeomFromText(%s, 4326))
            """,
            (parcel_id, JURISDICTION_ID, apn, BOWTIE_INVALID_WKT, UNREPAIRABLE_CENTROID_WKT),
        )
        cur.execute(
            """
            SELECT geom_valid,
                   ST_IsEmpty(ST_CollectionExtract(ST_MakeValid(geom), 3)),
                   ST_Contains(ST_GeomFromText(%s, 4326), centroid)
              FROM parcel WHERE id = %s
            """,
            (DISTRICT_WKT, parcel_id),
        )
        is_valid, repair_is_empty, centroid_in_district = cur.fetchone()
    conn.commit()
    check(
        "fixture check (UNREPAIRABLE): geometry is genuinely invalid (geom_valid = false)",
        is_valid is False,
        f"got geom_valid={is_valid}",
    )
    check(
        "fixture check (UNREPAIRABLE): its repair is genuinely empty (this is the unrepairable arm)",
        repair_is_empty is True,
        f"got repair_is_empty={repair_is_empty}",
    )
    check(
        "fixture check (UNREPAIRABLE): pre-stored centroid genuinely falls inside the district "
        "(so exclusion, not geography, is what's being tested)",
        centroid_in_district is True,
        f"got centroid_in_district={centroid_in_district}",
    )
    return parcel_id, apn


def _seed_repairable(conn):
    with conn.cursor() as cur:
        parcel_id = str(uuid.uuid4())
        apn = f"TEST-AN2-REPAIRABLE-{parcel_id[:8]}"
        cur.execute(
            """
            INSERT INTO parcel (id, jurisdiction_id, apn, geom)
            VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))
            """,
            (parcel_id, JURISDICTION_ID, apn, DEGENERATE_LINE_WKT),
        )
        cur.execute(
            """
            SELECT geom_valid,
                   ST_IsEmpty(ST_CollectionExtract(ST_MakeValid(geom), 3))
              FROM parcel WHERE id = %s
            """,
            (parcel_id,),
        )
        is_valid, repair_is_empty = cur.fetchone()
        # Seed the SEPARATE parcel_geometry_invalid exception directly
        # (mirrors flag_invalid_geometry.py's own insert -- this file does
        # not invoke that script). Proves load_zoning's own narrowed
        # derivation does not touch a different detector's row.
        insert_exceptions(cur, [
            ParcelException(
                parcel_id=parcel_id, jurisdiction_id=JURISDICTION_ID,
                type="record_to_ground", severity="warning",
                detector_key=DETECTOR_KEY_PARCEL_GEOM, detector_version=DETECTOR_VERSION_PARCEL_GEOM,
                detail={"reason": "test fixture: self-intersecting bowtie, seeded directly"},
            )
        ])
    conn.commit()
    check(
        "fixture check (REPAIRABLE): geometry is genuinely invalid (geom_valid = false)",
        is_valid is False,
        f"got geom_valid={is_valid}",
    )
    check(
        "fixture check (REPAIRABLE): its repair is NOT empty (this is the repairable arm)",
        repair_is_empty is False,
        f"got repair_is_empty={repair_is_empty}",
    )
    return parcel_id, apn


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


def _run_load_zoning(conn, snapshot_id):
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


def test_narrowed_boundary(conn, unrepairable_id, repairable_id, snapshot_id):
    """One real load_zoning() run, both arms present, so the repairable
    arm's own success is the positive control for the unrepairable arm's
    exclusion -- both are tested against the SAME district, at the SAME
    placement."""
    _run_load_zoning(conn, snapshot_id)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT field_key FROM fact
             WHERE parcel_id = %s AND field_key IN ('zoning.district', 'zoning.district_verbatim')
               AND superseded_at IS NULL
            """,
            (unrepairable_id,),
        )
        unrepairable_live_fields = {r[0] for r in cur.fetchall()}
        cur.execute(
            """
            SELECT type FROM parcel_exception
             WHERE parcel_id = %s AND detector_key = %s AND outcome = 'open'
            """,
            (unrepairable_id, DETECTOR_KEY_CENTROID_NOT_INTERIOR),
        )
        unrepairable_centroid_exc = cur.fetchall()

        cur.execute(
            """
            SELECT field_key FROM fact
             WHERE parcel_id = %s AND field_key IN ('zoning.district', 'zoning.district_verbatim')
               AND superseded_at IS NULL
            """,
            (repairable_id,),
        )
        repairable_live_fields = {r[0] for r in cur.fetchall()}
        cur.execute(
            """
            SELECT type FROM parcel_exception
             WHERE parcel_id = %s AND detector_key = %s AND outcome = 'open'
            """,
            (repairable_id, DETECTOR_KEY_CENTROID_NOT_INTERIOR),
        )
        repairable_centroid_exc = cur.fetchall()
        cur.execute("SELECT geom_valid FROM parcel WHERE id = %s", (repairable_id,))
        (repairable_geom_valid,) = cur.fetchone()
        cur.execute(
            """
            SELECT outcome FROM parcel_exception
             WHERE parcel_id = %s AND detector_key = %s
            """,
            (repairable_id, DETECTOR_KEY_PARCEL_GEOM),
        )
        repairable_geom_invalid_exc = cur.fetchall()

    # --- POSITIVE CONTROL, shown not asserted: the repairable arm actually
    # classifies at this placement, in this district, in this same run. ---
    check(
        "POSITIVE CONTROL: REPAIRABLE parcel (same district, same placement) "
        "DOES receive a live zoning.district fact -- proves the unrepairable "
        "arm's absence of a fact is exclusion, not a zero-match accident",
        repairable_live_fields == {"zoning.district", "zoning.district_verbatim"},
        f"got live fields: {repairable_live_fields}",
    )

    # --- UNREPAIRABLE arm: must be excluded, not classified. ---
    check(
        "A-N2/D-6.6 (narrowed): UNREPAIRABLE parcel gets NO live zoning.district fact",
        not unrepairable_live_fields,
        f"got live fields: {unrepairable_live_fields}",
    )
    check(
        "A-N2/D-6.6 (narrowed): UNREPAIRABLE parcel gets a parcel_centroid_not_interior "
        "exception, type='record_to_ground' (not 'coverage_gap')",
        unrepairable_centroid_exc == [("record_to_ground",)],
        f"got {unrepairable_centroid_exc}",
    )

    # --- REPAIRABLE arm: must classify, and must not disturb the OTHER
    # detector's exception. ---
    check(
        "D-6.6 (narrowed) FIX: REPAIRABLE parcel gets NO parcel_centroid_not_interior exception",
        repairable_centroid_exc == [],
        f"got {repairable_centroid_exc}",
    )
    check(
        "P61G R5: REPAIRABLE parcel's geom_valid still reads false "
        "(stored geometry is still invalid; the repair never persists)",
        repairable_geom_valid is False,
        f"got geom_valid={repairable_geom_valid}",
    )
    check(
        "REPAIRABLE parcel's OWN parcel_geometry_invalid exception (a different "
        "detector) is untouched -- still open, not closed by load_zoning's own run",
        repairable_geom_invalid_exc == [("open",)],
        f"got {repairable_geom_invalid_exc}",
    )


def _cleanup(conn, fixtures):
    """rollback() first: a prior failure elsewhere in this run can leave the
    connection's transaction aborted (same discipline
    test_centroid_interior_invariant.py's own _cleanup uses). Facts are
    immutable (I4, fact_no_delete) -- the REPAIRABLE parcel is EXPECTED to
    have live facts (that is the assertion), so its row (and its
    parcel_geometry_invalid exception) is correctly left in place, not an
    error condition. The UNREPAIRABLE parcel is expected to have none and
    is deleted normally. The snapshot row is never deleted (0021,
    immutable) -- left permanently, same as every other P59 fixture that
    seeds one."""
    conn.rollback()
    with conn.cursor() as cur:
        for parcel_id, apn in fixtures:
            cur.execute("SELECT count(*) FROM fact WHERE parcel_id = %s", (parcel_id,))
            fact_count = cur.fetchone()[0]
            if fact_count:
                print(f"[cleanup] {apn}: has {fact_count} fact row(s); immutable (I4), "
                      f"not deleted -- expected for the REPAIRABLE arm.")
                continue
            cur.execute("DELETE FROM parcel_exception WHERE parcel_id = %s", (parcel_id,))
            n_exc = cur.rowcount
            cur.execute("DELETE FROM parcel WHERE id = %s", (parcel_id,))
            n_parcel = cur.rowcount
            conn.commit()
            print(f"[cleanup] {apn}: removed {n_exc} parcel_exception row(s), "
                  f"{n_parcel} parcel row(s)")


def main():
    conn = get_db()
    fixtures = []
    snapshot_id = None
    try:
        unrepairable_id, unrepairable_apn = _seed_unrepairable(conn)
        fixtures.append((unrepairable_id, unrepairable_apn))
        repairable_id, repairable_apn = _seed_repairable(conn)
        fixtures.append((repairable_id, repairable_apn))
        print(f"seeded {unrepairable_apn} ({unrepairable_id}), {repairable_apn} ({repairable_id})")

        digest = uuid.uuid4().hex + uuid.uuid4().hex
        snapshot_id = f"{SOURCE_ID_ZONING}:sha256:{digest}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type,
                                       byte_size, request, http_status, fetched_at, licence_observed_id)
                VALUES (%s, %s, %s, %s, 'application/geo+json', 0, '{}'::jsonb, 200, now(), %s)
                """,
                (snapshot_id, SOURCE_ID_ZONING, f"s3://test-an2/{digest}", digest, LICENCE_ID_ZONING),
            )
        conn.commit()

        test_narrowed_boundary(conn, unrepairable_id, repairable_id, snapshot_id)
    finally:
        if fixtures:
            _cleanup(conn, fixtures)
        conn.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
