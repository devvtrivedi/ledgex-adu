#!/usr/bin/env python3
"""Invariant test for C1 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): the
zoning join's point must be guaranteed INTERIOR to its own parcel.
ST_Centroid alone is not -- for a concave, L-shaped, "C"-shaped or
multi-part parcel it can fall outside the polygon, into a neighboring
district's polygon, with no anomaly recorded (a single containing polygon
with one distinct zoning value is indistinguishable from a clean match).

Fixture: a genuine "C"-bracket parcel (single ring, non-convex) --

    (0,0) -> (10,0) -> (10,4) -> (4,4) -> (4,6) -> (10,6) -> (10,10) -> (0,10) -> (0,0)

a 10x10 square with a notch cut from the right side spanning x in [4,10],
y in [4,6]. The area-weighted centroid of this exact shape works out to
approximately (4.73, 5.0) -- INSIDE the notch, i.e. OUTSIDE the polygon.
Two synthetic "district" polygons: OWN_DISTRICT (x in [0,4], full height --
contains the parcel's solid left column, and the ST_PointOnSurface fallback
lands at (2,5), squarely inside it -- confirmed directly, not assumed) and
NEIGHBOR_DISTRICT (x in [4,10], full height -- contains the naive centroid
at (4.73,5), which sits inside the notch's own empty space).

Proves both directions, not just the fix in isolation:
  1. The naive ST_Centroid(geom) is NOT interior to the parcel (confirms
     this fixture actually exercises the failure mode, not a shape that
     happens to work anyway) AND falls inside NEIGHBOR_DISTRICT --
     reproducing C1's exact misclassification.
  2. scripts.ingest_zoning_permits.populate_interior_centroids() produces a
     point that IS interior to the parcel, and that point falls inside
     OWN_DISTRICT, not NEIGHBOR_DISTRICT -- the parcel classifies to its
     own district under the fix.

A-N3 (P59C): the original fixture above seeds `centroid` as NULL, so it
only exercises the `centroid IS NULL` disjunct of populate_interior_
centroids' own re-derive predicate -- reverting just the
`OR NOT ST_Contains(geom, centroid)` disjunct (the half that un-wedges an
already-stored wrong point) left this suite green. A second fixture, the
same C-shape but with the naive (non-interior) centroid PRE-STORED at
insert time, closes that gap.

A-N4 (P59C): a third fixture, a self-intersecting ("bowtie") polygon --
ST_IsValid = false, 0057's geom_valid -- proves populate_interior_
centroids does not raise a GEOS error and abort its caller's transaction
when invalid geometry is present, and that the row is routed to the
still_not_interior exception path rather than silently skipped.

Requires DATABASE_URL only. Writes three parcel rows under jurisdiction_id=
'test_p59_c1', then DELETES them itself at the end of every run, pass or
fail (same unconditional discipline db/tests/teardown.sql uses, and the
same zero-fact-only safety check: this fixture never writes a fact,
verified directly before deleting, not assumed). No licence/source rows
touched at all (sidesteps the C15 attribution-contamination hazard
entirely -- this invariant needs only jurisdiction + parcel, neither of
which touch licence).

Corrected (P59->P60, follow-up finding): this docstring previously
claimed permanence was a deliberate, "harmless" convention -- the same
claim test_flag_invalid_geometry.py's docstring made, which turned out to
be false there (a real accumulating orphan, caught via a false positive
in a live ST_IsValid sweep). Checked here on the strength of that same
finding, not assumed clean by association: this script has the identical
shape (standalone `make` target, never through `make db-test`, writes a
permanently fact-less parcel) and is fixed the same way.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_centroid_interior_invariant.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import os
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
from ingest_zoning_permits import populate_interior_centroids  # noqa: E402

JURISDICTION_ID = "test_p59_c1"

C_SHAPE_WKT = (
    "POLYGON((0 0, 10 0, 10 4, 4 4, 4 6, 10 6, 10 10, 0 10, 0 0))"
)
OWN_DISTRICT_WKT = "POLYGON((0 0, 4 0, 4 10, 0 10, 0 0))"
NEIGHBOR_DISTRICT_WKT = "POLYGON((4 0, 10 0, 10 10, 4 10, 4 0))"

# A-N4: self-intersecting "bowtie" -- ST_IsValid(this) is FALSE (0057's
# geom_valid generated column computes it), so ST_Centroid/ST_PointOnSurface/
# ST_Contains are all liable to raise a GEOS error on it (A-N4's concern).
BOWTIE_INVALID_WKT = "POLYGON((0 0, 10 10, 10 0, 0 10, 0 0))"

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _seed(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES (%s, 'P59 C1 test fixture', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """,
            (JURISDICTION_ID,),
        )
        parcel_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO parcel (id, jurisdiction_id, apn, geom)
            VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))
            """,
            (parcel_id, JURISDICTION_ID, f"TEST-C1-{parcel_id[:8]}", C_SHAPE_WKT),
        )
    conn.commit()
    return parcel_id


def _seed_pre_stored_bad_centroid(conn):
    """A-N3: the SAME C-shaped parcel, but with the naive (non-interior)
    ST_Centroid pre-stored as `centroid` at insert time -- reproducing an
    already-stored-wrong point from before this fix existed, or from a
    later geometry update that lands centroid outside geom again. Only the
    `OR NOT ST_Contains(geom, centroid)` disjunct in
    populate_interior_centroids' own UPDATE re-derives THIS row; the
    `centroid IS NULL` disjunct alone never touches it, since centroid is
    NOT NULL here by construction."""
    with conn.cursor() as cur:
        parcel_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO parcel (id, jurisdiction_id, apn, geom, centroid)
            VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)),
                    ST_Centroid(ST_GeomFromText(%s, 4326)))
            """,
            (parcel_id, JURISDICTION_ID, f"TEST-C1-STOREDBAD-{parcel_id[:8]}",
             C_SHAPE_WKT, C_SHAPE_WKT),
        )
    conn.commit()
    return parcel_id


def _seed_invalid_geometry(conn):
    """A-N4: a self-intersecting polygon (ST_IsValid = false, 0057's
    geom_valid). Proves populate_interior_centroids does not raise a GEOS
    error and abort the caller's transaction when an invalid geometry is
    present, and that the row is routed into still_not_interior instead of
    silently skipped or silently classified against an unverifiable point."""
    with conn.cursor() as cur:
        parcel_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO parcel (id, jurisdiction_id, apn, geom)
            VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))
            """,
            (parcel_id, JURISDICTION_ID, f"TEST-C1-INVALID-{parcel_id[:8]}",
             BOWTIE_INVALID_WKT),
        )
        cur.execute("SELECT geom_valid FROM parcel WHERE id = %s", (parcel_id,))
        (is_valid,) = cur.fetchone()
    conn.commit()
    check(
        "fixture check: the bowtie polygon is genuinely invalid (geom_valid = false)",
        is_valid is False,
        f"got geom_valid={is_valid} -- fixture does not exercise A-N4's failure mode",
    )
    return parcel_id


def test_naive_centroid_fails_and_misclassifies(conn, parcel_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ST_Contains(geom, ST_Centroid(geom)) AS naive_is_interior,
                ST_Contains(ST_GeomFromText(%s, 4326), ST_Centroid(geom)) AS naive_in_neighbor
            FROM parcel WHERE id = %s
            """,
            (NEIGHBOR_DISTRICT_WKT, parcel_id),
        )
        naive_is_interior, naive_in_neighbor = cur.fetchone()

    check(
        "fixture check: naive ST_Centroid is NOT interior to the C-shaped parcel",
        naive_is_interior is False,
        f"got naive_is_interior={naive_is_interior} -- fixture does not exercise the failure mode",
    )
    check(
        "fixture check: naive ST_Centroid lands inside the WRONG (neighbor) district",
        naive_in_neighbor is True,
        f"got naive_in_neighbor={naive_in_neighbor}",
    )


def test_populate_interior_centroids_fixes_it(conn, parcel_id):
    with conn.cursor() as cur:
        recomputed, still_bad = populate_interior_centroids(cur)
    conn.commit()

    check(
        "populate_interior_centroids recomputed at least our fixture parcel",
        recomputed >= 1,
        f"rowcount={recomputed}",
    )
    check(
        "populate_interior_centroids left no residual non-interior points for our fixture",
        parcel_id not in still_bad,
        f"still_bad={still_bad}",
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ST_Contains(geom, centroid) AS is_interior,
                ST_Contains(ST_GeomFromText(%s, 4326), centroid) AS in_own_district,
                ST_Contains(ST_GeomFromText(%s, 4326), centroid) AS in_neighbor_district
            FROM parcel WHERE id = %s
            """,
            (OWN_DISTRICT_WKT, NEIGHBOR_DISTRICT_WKT, parcel_id),
        )
        is_interior, in_own, in_neighbor = cur.fetchone()

    check(
        "C1 FIX: corrected centroid is interior to the parcel",
        is_interior is True,
        f"got is_interior={is_interior}",
    )
    check(
        "C1 FIX: parcel classifies to its OWN district",
        in_own is True,
        f"got in_own_district={in_own}",
    )
    check(
        "C1 FIX: parcel does NOT classify to the neighbor's district",
        in_neighbor is False,
        f"got in_neighbor_district={in_neighbor}",
    )


def test_pre_stored_bad_centroid_is_rederived(conn, parcel_id):
    """A-N3: proves the `OR NOT ST_Contains(geom, centroid)` disjunct
    specifically -- not just the `centroid IS NULL` arm -- by seeding a
    centroid that is already wrong (not NULL) and confirming
    populate_interior_centroids re-derives it to an interior point."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ST_Contains(geom, centroid) FROM parcel WHERE id = %s",
            (parcel_id,),
        )
        (pre_fix_is_interior,) = cur.fetchone()
    check(
        "fixture check: the pre-stored centroid is NOT interior before the fix runs",
        pre_fix_is_interior is False,
        f"got {pre_fix_is_interior} -- fixture does not exercise the stored-bad-point case",
    )

    with conn.cursor() as cur:
        recomputed, still_bad = populate_interior_centroids(cur)
    conn.commit()

    check(
        "A-N3 FIX: pre-stored bad centroid is re-derived (not left stale)",
        parcel_id not in still_bad,
        f"still_bad={still_bad}",
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ST_Contains(geom, centroid) FROM parcel WHERE id = %s",
            (parcel_id,),
        )
        (post_fix_is_interior,) = cur.fetchone()
    check(
        "A-N3 FIX: re-derived centroid is now interior to the parcel",
        post_fix_is_interior is True,
        f"got {post_fix_is_interior}",
    )


def test_invalid_geometry_does_not_abort(conn, parcel_id):
    """A-N4: proves an invalid (self-intersecting) geometry present in the
    same UPDATE/SELECT pass does not raise a GEOS error (which would abort
    the whole caller's transaction -- load_zoning's, in production), and
    that the invalid-geometry parcel is routed into still_not_interior
    rather than silently classified or silently dropped."""
    with conn.cursor() as cur:
        recomputed, still_bad = populate_interior_centroids(cur)
    conn.commit()

    check(
        "A-N4 FIX: populate_interior_centroids did not raise on invalid geometry "
        "(reached this line at all)",
        True,
    )
    check(
        "A-N4 FIX: invalid-geometry parcel is routed to still_not_interior",
        parcel_id in still_bad,
        f"still_bad={still_bad}",
    )


def _cleanup(conn, parcel_ids):
    """Delete this run's own fixture parcels. Run unconditionally (pass or
    fail), same discipline as db/tests/teardown.sql. Safety check mirrors
    I4/0017 directly rather than assuming: this fixture never writes a
    fact (see module docstring), but refuses to delete if one somehow
    exists, rather than risk it. rollback() first: a prior failure
    elsewhere in this same run can leave the connection's transaction
    aborted, and Postgres refuses every further statement -- including
    this cleanup's own SELECT -- until it is rolled back (found live
    while proving test_flag_invalid_geometry.py's identical fix)."""
    conn.rollback()
    with conn.cursor() as cur:
        for parcel_id in parcel_ids:
            cur.execute("SELECT count(*) FROM fact WHERE parcel_id = %s", (parcel_id,))
            fact_count = cur.fetchone()[0]
            if fact_count:
                print(f"[cleanup] SKIPPED -- parcel {parcel_id} has {fact_count} fact row(s), "
                      f"not deleting (I4). This should never happen for this fixture; investigate.")
                continue
            cur.execute("DELETE FROM parcel WHERE id = %s", (parcel_id,))
            print(f"[cleanup] removed {cur.rowcount} parcel row(s) for {parcel_id}")
    conn.commit()


def main():
    conn = get_db()
    parcel_ids = []
    try:
        parcel_id = _seed(conn)
        parcel_ids.append(parcel_id)
        test_naive_centroid_fails_and_misclassifies(conn, parcel_id)
        test_populate_interior_centroids_fixes_it(conn, parcel_id)

        stored_bad_id = _seed_pre_stored_bad_centroid(conn)
        parcel_ids.append(stored_bad_id)
        test_pre_stored_bad_centroid_is_rederived(conn, stored_bad_id)

        invalid_id = _seed_invalid_geometry(conn)
        parcel_ids.append(invalid_id)
        test_invalid_geometry_does_not_abort(conn, invalid_id)
    finally:
        # Unconditional, pass or fail -- same discipline as
        # db/tests/teardown.sql, run here because nothing else ever will
        # (this script is wired standalone, never through make db-test).
        if parcel_ids:
            _cleanup(conn, parcel_ids)
        conn.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
