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
when invalid geometry is present.

P61G (D-6.6, narrowed, 2026-08-31): that same bowtie fixture is now the
REPAIRABLE-invalid arm, not the "stays excluded forever" arm its own name
used to promise -- checked directly, not assumed, before repurposing it:
`ST_CollectionExtract(ST_MakeValid(bowtie), 3)` returns
`MULTIPOLYGON(((0 0,0 10,5 5,0 0)),((10 0,5 5,10 10,10 0)))`, two real
triangles, not empty. Under the narrowed rule this parcel now gets a
centroid (interior to the REPAIRED geometry) and is excluded from
`still_not_interior`. The test below asserts exactly that -- and asserts
`parcel.geom` itself is byte-unchanged and `geom_valid` still reads false,
since the repair is derivation-time-only, never persisted (R5). A fourth
fixture, a genuinely unrepairable degenerate "polygon" (a ring that
doubles back on itself with zero enclosed area -- confirmed directly:
`ST_CollectionExtract(ST_MakeValid(...), 3)` on it returns `POLYGON
EMPTY`), proves the opposite: no centroid, routed to still_not_interior,
unchanged from A-N4's original behavior for the case repair cannot help.

**Corrected 2026-08-31 (P61G) -- a real, pre-existing regression, found
while extending this file, not by inspection.** This fixture used to seed
its four parcels under a private `jurisdiction_id='test_p59_c1'`, isolated
from any real jurisdiction. P61A (commit b7aa8dc) scoped
`populate_interior_centroids`'s own UPDATE and residual SELECT to
`jurisdiction_id = JURISDICTION_ID` (the ingest module's own hardcoded
`'ca_san_jose'` constant) -- correctly, for its own stated reason -- but
that silently made this entire suite inert: `test_p59_c1` is not
`ca_san_jose`, so none of this file's fixtures were ever touched by the
function under test again. Confirmed directly, not inferred: running the
UNMODIFIED pre-P61G version of this file against the current (P61A-fixed)
tree fails 6 of its original assertions, every one with the same
symptom -- `rowcount=0`, `still_bad=[]`, a value that should have been
derived reading back NULL -- because the fixture parcels were invisible
to the scoped function the whole time. Landed in P61A, never caught
because P61A's own verification ran ITS OWN new test
(test_zoning_cross_jurisdiction.py), not this pre-existing one; see
P61G-LEDGER.md for the full account.

Fixed the same way test_zoning_centroid_exclusion.py already handles this
exact constraint: fixtures now seed under `jurisdiction_id=JURISDICTION_ID`
(imported from `ingest_zoning_permits`, i.e. `'ca_san_jose'`), APN-prefixed
`TEST-C1-*` so they can never collide with a real parcel. Needs
`day4_sources.sql` applied first (the real `ca_san_jose` jurisdiction row
comes from there, not from any migration -- confirmed: `grep ca_san_jose
db/migrations/*.sql` finds no INSERT, `db/seeds/day4_sources.sql:268`
does) -- refuses loudly, naming the exact command, if not. NOT safe
against a database already carrying real bulk zoning/parcel data:
`populate_interior_centroids` is now, correctly, a jurisdiction-wide bulk
operation, so calling it recomputes every `ca_san_jose` parcel's centroid,
not just this file's own four -- same caveat
test_zoning_centroid_exclusion.py's own docstring already carries. Safe
against `ledgex_test`/`ledgex_ci` and a disposable local
`ledgex_schema_check` with no real bulk parcels loaded; NOT safe against
the real long-lived `ledgex_schema_check`.

Writes four parcel rows under `jurisdiction_id='ca_san_jose'`, then
DELETES them itself at the end of every run, pass or fail (same
unconditional discipline db/tests/teardown.sql uses, and the same
zero-fact-only safety check: this fixture never writes a fact, verified
directly before deleting, not assumed). No licence rows touched.

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
from ingest_zoning_permits import populate_interior_centroids, JURISDICTION_ID  # noqa: E402

C_SHAPE_WKT = (
    "POLYGON((0 0, 10 0, 10 4, 4 4, 4 6, 10 6, 10 10, 0 10, 0 0))"
)
OWN_DISTRICT_WKT = "POLYGON((0 0, 4 0, 4 10, 0 10, 0 0))"
NEIGHBOR_DISTRICT_WKT = "POLYGON((4 0, 10 0, 10 10, 4 10, 4 0))"

# A-N4: self-intersecting "bowtie" -- ST_IsValid(this) is FALSE (0057's
# geom_valid generated column computes it), so ST_Centroid/ST_PointOnSurface/
# ST_Contains are all liable to raise a GEOS error on it (A-N4's concern).
# P61G: repairs into two real triangles -- verified directly, see module
# docstring -- so this is now the REPAIRABLE-invalid arm.
BOWTIE_INVALID_WKT = "POLYGON((0 0, 10 10, 10 0, 0 10, 0 0))"

# P61G: a degenerate ring that doubles back along itself with zero
# enclosed area -- invalid (ST_IsValid = false), and its repair does NOT
# recover a usable polygon: ST_CollectionExtract(ST_MakeValid(this), 3) is
# verified directly (module docstring) to be POLYGON EMPTY. The
# unrepairable arm.
DEGENERATE_LINE_WKT = "POLYGON((0 0, 10 0, 5 0, 0 0))"

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
                "No ca_san_jose.zoning_districts source row -- this test needs "
                "the real ca_san_jose jurisdiction row from db/seeds/day4_sources.sql, "
                "which populate_interior_centroids is now scoped to (P61A). Run it "
                "first: psql \"$DATABASE_URL\" -v ON_ERROR_STOP=1 "
                "-f db/seeds/day4_sources.sql"
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


def _seed_repairable_invalid_geometry(conn):
    """P61G: the bowtie polygon -- ST_IsValid = false, but its repair
    (ST_CollectionExtract(ST_MakeValid(geom), 3)) yields two real,
    non-empty triangles. Proves both A-N4's original guarantee (no GEOS
    error/abort on invalid input) and the narrowed D-6.6 rule (a repairable
    parcel gets a centroid interior to the REPAIRED geometry and is no
    longer routed to still_not_interior)."""
    with conn.cursor() as cur:
        parcel_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO parcel (id, jurisdiction_id, apn, geom)
            VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))
            """,
            (parcel_id, JURISDICTION_ID, f"TEST-C1-REPAIRABLE-{parcel_id[:8]}",
             BOWTIE_INVALID_WKT),
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
    conn.commit()
    check(
        "fixture check: the bowtie polygon is genuinely invalid (geom_valid = false)",
        is_valid is False,
        f"got geom_valid={is_valid} -- fixture does not exercise A-N4's failure mode",
    )
    check(
        "fixture check: the bowtie's repair is NOT empty (this is the repairable arm)",
        repair_is_empty is False,
        f"got repair_is_empty={repair_is_empty} -- fixture does not exercise the repairable case",
    )
    return parcel_id


def _seed_unrepairable_geometry(conn):
    """P61G: a degenerate zero-area "polygon" (a ring that doubles back
    along itself) -- ST_IsValid = false, AND its repair is genuinely
    unusable (ST_CollectionExtract(ST_MakeValid(geom), 3) is empty).
    Proves the narrowed D-6.6 rule's other half: a parcel whose geometry
    does not repair into a usable polygon is unchanged from A-N4's
    original behavior -- no centroid, routed to still_not_interior."""
    with conn.cursor() as cur:
        parcel_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO parcel (id, jurisdiction_id, apn, geom)
            VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))
            """,
            (parcel_id, JURISDICTION_ID, f"TEST-C1-UNREPAIRABLE-{parcel_id[:8]}",
             DEGENERATE_LINE_WKT),
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
    conn.commit()
    check(
        "fixture check: the degenerate-line polygon is genuinely invalid (geom_valid = false)",
        is_valid is False,
        f"got geom_valid={is_valid} -- fixture does not exercise the invalid-geometry case",
    )
    check(
        "fixture check: the degenerate line's repair IS empty (this is the unrepairable arm)",
        repair_is_empty is True,
        f"got repair_is_empty={repair_is_empty} -- fixture does not exercise the unrepairable case",
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


def test_repairable_invalid_geometry_gets_interior_centroid(conn, parcel_id):
    """A-N4 (unchanged guarantee) + P61G (narrowed D-6.6): the bowtie's
    repair does not raise a GEOS error, AND -- the new part -- the parcel
    now receives a centroid provably interior to the REPAIRED geometry,
    is excluded from still_not_interior, and both parcel.geom and
    geom_valid are left exactly as they were (the repair never persists)."""
    with conn.cursor() as cur:
        cur.execute("SELECT ST_AsText(geom), geom_valid FROM parcel WHERE id = %s", (parcel_id,))
        geom_before, geom_valid_before = cur.fetchone()

    with conn.cursor() as cur:
        recomputed, still_bad = populate_interior_centroids(cur)
    conn.commit()

    check(
        "P61G FIX: populate_interior_centroids did not raise on repairable invalid geometry "
        "(reached this line at all)",
        True,
    )
    check(
        "P61G FIX: repairable-invalid parcel is recomputed (not skipped)",
        recomputed >= 1,
        f"rowcount={recomputed}",
    )
    check(
        "P61G FIX: repairable-invalid parcel is EXCLUDED from still_not_interior "
        "(the narrowed part -- A-N4 alone would have kept it in still_bad forever)",
        parcel_id not in still_bad,
        f"still_bad={still_bad}",
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT centroid IS NOT NULL,
                   ST_Contains(ST_CollectionExtract(ST_MakeValid(geom), 3), centroid),
                   ST_AsText(geom), geom_valid
              FROM parcel WHERE id = %s
            """,
            (parcel_id,),
        )
        has_centroid, interior_to_repaired, geom_after, geom_valid_after = cur.fetchone()

    check(
        "P61G FIX: repairable-invalid parcel received a centroid",
        has_centroid is True,
        f"got has_centroid={has_centroid}",
    )
    check(
        "P61G FIX: the derived centroid is provably interior to the REPAIRED geometry",
        interior_to_repaired is True,
        f"got interior_to_repaired={interior_to_repaired}",
    )
    check(
        "P61G R5: parcel.geom is byte-unchanged (the repair is derivation-time-only)",
        geom_after == geom_before,
        f"before={geom_before!r} after={geom_after!r}",
    )
    check(
        "P61G R5: geom_valid still reads false (stored geometry is still invalid, correctly)",
        geom_valid_after is False and geom_valid_before is False,
        f"before={geom_valid_before} after={geom_valid_after}",
    )


def test_unrepairable_geometry_stays_excluded(conn, parcel_id):
    """P61G: the mirror image of the repairable case above. A parcel whose
    repair does not yield a usable polygon must be unchanged from A-N4's
    original behavior in every particular: no centroid, routed to
    still_not_interior, and does not raise."""
    with conn.cursor() as cur:
        cur.execute("SELECT centroid IS NULL FROM parcel WHERE id = %s", (parcel_id,))
        (centroid_was_null,) = cur.fetchone()
    check(
        "fixture check: unrepairable parcel starts with no centroid",
        centroid_was_null is True,
        f"got centroid_was_null={centroid_was_null}",
    )

    with conn.cursor() as cur:
        recomputed, still_bad = populate_interior_centroids(cur)
    conn.commit()

    check(
        "P61G: populate_interior_centroids did not raise on unrepairable invalid geometry "
        "(reached this line at all)",
        True,
    )
    check(
        "P61G: unrepairable-invalid parcel is routed to still_not_interior, unchanged from A-N4",
        parcel_id in still_bad,
        f"still_bad={still_bad}",
    )

    with conn.cursor() as cur:
        cur.execute("SELECT centroid IS NULL FROM parcel WHERE id = %s", (parcel_id,))
        (centroid_still_null,) = cur.fetchone()
    check(
        "P61G: unrepairable-invalid parcel received NO centroid",
        centroid_still_null is True,
        f"got centroid_still_null={centroid_still_null}",
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

        repairable_id = _seed_repairable_invalid_geometry(conn)
        parcel_ids.append(repairable_id)
        test_repairable_invalid_geometry_gets_interior_centroid(conn, repairable_id)

        unrepairable_id = _seed_unrepairable_geometry(conn)
        parcel_ids.append(unrepairable_id)
        test_unrepairable_geometry_stays_excluded(conn, unrepairable_id)
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
