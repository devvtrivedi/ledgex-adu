#!/usr/bin/env python3
"""Regression fixture for A-N8 (P59C, LEDGEX-P59B-ENGINEERING-REPORT.md
sec 2.3): parcel_centroid_not_interior exceptions were open-forever by
construction -- load_zoning wrote them (via populate_interior_centroids'
own still-bad set) but nothing ever closed one, even though load_zoning
already recomputes that exact still-true set in full on every run (the
same precondition core.exceptions.close_resolved_exceptions already
requires for DETECTOR_KEY_ZONING_UNRESOLVABLE's own closure two blocks
below it in the same file -- reused here, not a second hand-rolled UPDATE).

**Corrected 2026-09-01 (P61Y).** Both arms used to seed the SAME bowtie
(self-intersecting) geometry. Under narrowed D-6.6 (P61G, 2026-08-31),
populate_interior_centroids derives from
`ST_CollectionExtract(ST_MakeValid(geom), 3)`, and that exact bowtie
repairs into two real triangles (verified directly below, the same fact
recorded for the identical shape in test_centroid_interior_invariant.py
and test_zoning_centroid_exclusion.py) -- so run 1 no longer opened an
exception for EITHER arm, the precondition this test's own design
requires never held, and the two arms were not being distinguished at
all. Fixed by starting both arms from a genuinely UNREPAIRABLE geometry
instead (`DEGENERATE_LINE_WKT`, verified directly below to repair to
`POLYGON EMPTY`) -- the file's contract is unchanged, only the starting
fixture is corrected to actually exercise it. This is a re-point, not a
weakened assertion: run 1's own two checks ("exception opens") are
exactly as strict as before, now against a fixture that actually
satisfies their own precondition.

Two parcels, two real load_zoning() runs:
  - REPAIRED: seeded with an UNREPAIRABLE geometry -- opens a
    parcel_centroid_not_interior exception on run 1. Its geometry is
    corrected to a valid polygon between runs (0057's geom_valid tracks it
    automatically -- no exception-table code touches this). Run 2's
    populate_interior_centroids can now derive a real interior centroid
    for it, so it drops out of centroid_still_bad -- the exception must
    close (condition_cleared).
  - STILL-BAD: seeded with the same UNREPAIRABLE geometry, left untouched
    between runs -- stays in centroid_still_bad on both runs (still
    unrepairable, not merely still invalid -- narrowed D-6.6 would
    repair-and-classify a merely-invalid-but-repairable geometry, which
    would silently defeat this arm's own purpose). The exception must
    stay open across both. Proven distinguishable from REPAIRED, not
    merely asserted correct in isolation -- a run where both arms behave
    identically is exactly the failure this fix exists to prevent.

Requires DATABASE_URL only (no day4_sources.sql dependency for the
REPAIRED/STILL-BAD parcels themselves, but load_zoning's own job_run.
snapshot_id FK needs a real ca_san_jose.zoning_districts source row --
same requirement scripts/test_zoning_centroid_exclusion.py already
states; refuses loudly, naming the exact command, if not seeded).

Writes two parcels under jurisdiction_id='ca_san_jose' (load_zoning's own
JURISDICTION_ID is a hardcoded module constant -- same constraint every
other P59 zoning/permits fixture already accepts), APNs prefixed
'TEST-AN8-'. DELETES both parcels and their parcel_exception rows at the
end of every run, pass or fail; leaves the two snapshot rows it creates
permanently (immutable, 0021) -- same accepted convention
test_zoning_centroid_exclusion.py already uses.

NOT safe against a database already carrying real bulk zoning/parcel
data -- load_zoning reclassifies every parcel with a non-null centroid on
every run. Safe against ledgex_test/ledgex_ci and a disposable local
ledgex_schema_check with no real bulk parcels loaded.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_zoning_centroid_exception_closure.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import datetime
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

# P61Y: the former starting fixture for both arms -- ST_IsValid = false,
# but ST_CollectionExtract(ST_MakeValid(this), 3) is two real triangles
# (verified in _seed below), so it repairs under narrowed D-6.6 and no
# longer belongs here. Kept only as a named reference for that fact, not
# used to seed anything in this file anymore.
BOWTIE_INVALID_WKT = "POLYGON((0 0, 10 10, 10 0, 0 10, 0 0))"
# P61Y: the real starting fixture for both arms now -- the same degenerate,
# zero-area, self-doubling-back ring P61G verified
# (test_centroid_interior_invariant.py:146) repairs to POLYGON EMPTY.
# Re-verified directly in _seed below, not trusted from that citation.
DEGENERATE_LINE_WKT = "POLYGON((0 0, 10 0, 5 0, 0 0))"
VALID_SQUARE_WKT = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"
# Far away from both fixture geometries -- an empty zoning-districts
# snapshot is fine (this test is about the centroid detector, not
# classification), but load_zoning needs at least a well-formed
# FeatureCollection to parse.
DISTRICT_WKT = "POLYGON((100 100, 110 100, 110 110, 100 110, 100 100))"

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _insert_snapshot(cur):
    digest = uuid.uuid4().hex + uuid.uuid4().hex
    snapshot_id = f"{SOURCE_ID_ZONING}:sha256:{digest}"
    cur.execute(
        """
        INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type,
                               byte_size, request, http_status, fetched_at, licence_observed_id)
        VALUES (%s, %s, %s, %s, 'application/geo+json', 0, '{}'::jsonb, 200, now(), %s)
        """,
        (snapshot_id, SOURCE_ID_ZONING, f"s3://test-an8/{digest}", digest, LICENCE_ID_ZONING),
    )
    return snapshot_id


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
        repaired_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO parcel (id, jurisdiction_id, apn, geom) "
            "VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))",
            (repaired_id, JURISDICTION_ID, f"TEST-AN8-REPAIRED-{repaired_id[:8]}", DEGENERATE_LINE_WKT),
        )
        still_bad_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO parcel (id, jurisdiction_id, apn, geom) "
            "VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))",
            (still_bad_id, JURISDICTION_ID, f"TEST-AN8-STILLBAD-{still_bad_id[:8]}", DEGENERATE_LINE_WKT),
        )
        # P61Y: verify the starting fixture is genuinely unrepairable for
        # BOTH parcels, not trusted from the module-level comment alone --
        # this is exactly the property the original bowtie silently lost
        # under narrowed D-6.6.
        cur.execute(
            "SELECT id, geom_valid, ST_IsEmpty(ST_CollectionExtract(ST_MakeValid(geom), 3)) "
            "FROM parcel WHERE id = ANY(%s::uuid[])",
            ([repaired_id, still_bad_id],),
        )
        by_id = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    conn.commit()
    for label, pid in (("REPAIRED", repaired_id), ("STILL-BAD", still_bad_id)):
        is_valid, repair_is_empty = by_id[pid]
        check(
            f"fixture check ({label}): starting geometry is genuinely invalid (geom_valid = false)",
            is_valid is False,
            f"got geom_valid={is_valid}",
        )
        check(
            f"fixture check ({label}): starting geometry's repair is genuinely empty "
            f"(so run 1 will actually open an exception for it)",
            repair_is_empty is True,
            f"got repair_is_empty={repair_is_empty}",
        )
    return repaired_id, still_bad_id


def _write_snapshot_geojson():
    fd, path = tempfile.mkstemp(suffix=".geojson", prefix="test_an8_zoning_")
    with os.fdopen(fd, "w") as f:
        json.dump({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"FACILITYID": "TEST-AN8-DISTRICT", "ZONING": "R-1", "ZONINGABBREV": "R1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[100, 100], [110, 100], [110, 110], [100, 110], [100, 100]]],
                },
            }],
        }, f)
    return path


def _run_load_zoning(seed_conn):
    with seed_conn.cursor() as cur:
        snapshot_id = _insert_snapshot(cur)
    seed_conn.commit()
    path = _write_snapshot_geojson()
    try:
        zoning_conn = get_db()  # load_zoning owns and closes its own connection
        load_zoning(zoning_conn, path, snapshot_id, datetime.datetime.now(datetime.timezone.utc))
    finally:
        os.unlink(path)
    return snapshot_id


def _open_exception_ids(cur, parcel_id):
    cur.execute(
        "SELECT id FROM parcel_exception WHERE parcel_id = %s AND detector_key = %s AND outcome = 'open'",
        (parcel_id, DETECTOR_KEY_CENTROID_NOT_INTERIOR),
    )
    return {r[0] for r in cur.fetchall()}


def test_closure_by_exclusion(conn, repaired_id, still_bad_id):
    # Run 1: both parcels are invalid -- both open an exception.
    _run_load_zoning(conn)
    with conn.cursor() as cur:
        repaired_open_1 = _open_exception_ids(cur, repaired_id)
        still_bad_open_1 = _open_exception_ids(cur, still_bad_id)
    check("run 1: REPAIRED parcel's exception opens", len(repaired_open_1) == 1, f"got {repaired_open_1}")
    check("run 1: STILL-BAD parcel's exception opens", len(still_bad_open_1) == 1, f"got {still_bad_open_1}")

    # Between runs: repair ONE parcel's geometry (valid + interior-derivable).
    # 0057's geom_valid tracks this automatically -- no exception-table code
    # touches it here.
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE parcel SET geom = ST_Multi(ST_GeomFromText(%s, 4326)), centroid = NULL WHERE id = %s",
            (VALID_SQUARE_WKT, repaired_id),
        )
    conn.commit()

    # Run 2: REPAIRED is now valid/interior-derivable -> drops out of
    # centroid_still_bad -> its exception must close. STILL-BAD is
    # unchanged -> stays open.
    _run_load_zoning(conn)
    with conn.cursor() as cur:
        repaired_open_2 = _open_exception_ids(cur, repaired_id)
        still_bad_open_2 = _open_exception_ids(cur, still_bad_id)
        cur.execute(
            "SELECT outcome, resolved_by FROM parcel_exception WHERE id = %s",
            (next(iter(repaired_open_1)),),
        )
        repaired_row_outcome, repaired_row_resolved_by = cur.fetchone()

    check(
        "A-N8 FIX: REPAIRED parcel's exception is CLOSED after its geometry was fixed",
        len(repaired_open_2) == 0,
        f"got {repaired_open_2}",
    )
    check(
        "A-N8 FIX: the closed row's own outcome is condition_cleared, resolved_by the detector",
        repaired_row_outcome == "condition_cleared" and repaired_row_resolved_by == DETECTOR_KEY_CENTROID_NOT_INTERIOR,
        f"got outcome={repaired_row_outcome!r} resolved_by={repaired_row_resolved_by!r}",
    )
    check(
        "A-N8: STILL-BAD parcel's exception stays OPEN across both runs",
        still_bad_open_2 == still_bad_open_1,
        f"run1={still_bad_open_1} run2={still_bad_open_2}",
    )

    # P61Y: the two arms must be ACTUALLY distinguishable, not merely each
    # individually correct in isolation -- a run where both arms behave
    # identically (both closed, or both still open) is exactly the failure
    # narrowed D-6.6's repairable bowtie silently produced before this fix,
    # and two individually-"correct" checks can both pass on such a run if
    # read in isolation. State per-arm, per-run, explicitly:
    print(f"  REPAIRED  run1_open={repaired_open_1}  run2_open={repaired_open_2}")
    print(f"  STILL-BAD run1_open={still_bad_open_1}  run2_open={still_bad_open_2}")
    check(
        "P61Y: REPAIRED and STILL-BAD are distinguishable after run 2 "
        "(one closed, one still open -- not both the same)",
        (len(repaired_open_2) == 0) != (len(still_bad_open_2) == 0),
        f"repaired_open_2={repaired_open_2} still_bad_open_2={still_bad_open_2}",
    )
    check(
        "P61Y: both arms actually opened an exception on run 1 (the precondition "
        "this test's own design requires -- silently false before this fix)",
        len(repaired_open_1) == 1 and len(still_bad_open_1) == 1,
        f"repaired_open_1={repaired_open_1} still_bad_open_1={still_bad_open_1}",
    )


def _cleanup(conn, parcel_ids):
    conn.rollback()
    with conn.cursor() as cur:
        for parcel_id in parcel_ids:
            cur.execute("SELECT count(*) FROM fact WHERE parcel_id = %s", (parcel_id,))
            if cur.fetchone()[0]:
                print(f"[cleanup] NOTE -- parcel {parcel_id} has fact row(s); not deleted (I4).")
                continue
            cur.execute("DELETE FROM parcel_exception WHERE parcel_id = %s", (parcel_id,))
            cur.execute("DELETE FROM parcel WHERE id = %s", (parcel_id,))
    conn.commit()
    print(f"[cleanup] removed fixture rows for {len(parcel_ids)} parcel(s)")


def main():
    conn = get_db()
    parcel_ids = []
    try:
        repaired_id, still_bad_id = _seed(conn)
        parcel_ids = [repaired_id, still_bad_id]
        test_closure_by_exclusion(conn, repaired_id, still_bad_id)
    finally:
        if parcel_ids:
            _cleanup(conn, parcel_ids)
        conn.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
