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

Requires DATABASE_URL only. Writes a small number of permanent rows under
jurisdiction_id='test_p59_c1' (parcel is not immutable, but this follows
the same "real, permanent, clearly-namespaced, harmless" convention this
suite's siblings already use -- see test_snapshot_race_invariant.py's own
docstring). No licence/source rows touched at all (sidesteps the C15
attribution-contamination hazard entirely -- this invariant needs only
jurisdiction + parcel + parcel_exception, none of which touch licence).

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


def main():
    conn = get_db()
    try:
        parcel_id = _seed(conn)
        test_naive_centroid_fails_and_misclassifies(conn, parcel_id)
        test_populate_interior_centroids_fixes_it(conn, parcel_id)
    finally:
        conn.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
