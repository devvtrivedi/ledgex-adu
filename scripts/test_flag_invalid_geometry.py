#!/usr/bin/env python3
"""Regression fixture for C4 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md):
proves flag_invalid_geometry.flag_parcel_geometry() actually fires on a
self-intersecting polygon, that the new generated `parcel.geom_valid`
column (0057) tracks it automatically, and that the closure path added by
this pass (core.exceptions.close_exceptions_for_parcels, reused, not a
second hand-rolled UPDATE) actually closes the exception once the source
geometry is corrected -- C4's own complaint was that no closure path
existed at all, leaving a source-side fix flagged open forever.

Requires DATABASE_URL only. Writes permanent rows under jurisdiction_id=
'test_p59_c4' (parcel is not immutable; parcel_exception's own outcome can
transition, so this is more reversible than most fixtures in this suite,
but rows are not deleted -- same "real, permanent, namespaced, harmless"
convention as this suite's siblings). No licence/source rows touched.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_flag_invalid_geometry.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import os
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
from flag_invalid_geometry import flag_parcel_geometry, DETECTOR_KEY_PARCEL_GEOM, DETECTOR_VERSION  # noqa: E402

JURISDICTION_ID = "test_p59_c4"

# The same real self-intersecting geometry class the audit's own 28 parcels
# carry -- a bowtie: two triangles sharing only a crossing point.
SELF_INTERSECTING_WKT = "POLYGON((0 0, 10 10, 10 0, 0 10, 0 0))"
VALID_WKT = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _seed_parcel(conn, wkt):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported) "
            "VALUES (%s, 'P59 C4 test fixture', 'city', 'CA', 'v1.0', true) "
            "ON CONFLICT (id) DO NOTHING",
            (JURISDICTION_ID,),
        )
        parcel_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO parcel (id, jurisdiction_id, apn, geom) "
            "VALUES (%s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))",
            (parcel_id, JURISDICTION_ID, f"TEST-C4-{parcel_id[:8]}", wkt),
        )
    conn.commit()
    return parcel_id


def _open_exception(conn, parcel_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT outcome FROM parcel_exception WHERE parcel_id = %s "
            "AND detector_key = %s AND detector_version = %s ORDER BY detected_at DESC LIMIT 1",
            (parcel_id, DETECTOR_KEY_PARCEL_GEOM, DETECTOR_VERSION),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _geom_valid(conn, parcel_id):
    with conn.cursor() as cur:
        cur.execute("SELECT geom_valid FROM parcel WHERE id = %s", (parcel_id,))
        return cur.fetchone()[0]


def main():
    conn = get_db()
    parcel_id = _seed_parcel(conn, SELF_INTERSECTING_WKT)

    check("fixture check: the bowtie geometry is genuinely invalid (ST_IsValid)",
          _geom_valid(conn, parcel_id) is False,
          f"got geom_valid={_geom_valid(conn, parcel_id)!r} -- fixture does not exercise the failure mode")

    flag_parcel_geometry(conn)
    check("C4 FIX: an open parcel_geometry_invalid exception was opened for the invalid parcel",
          _open_exception(conn, parcel_id) == "open",
          f"got outcome={_open_exception(conn, parcel_id)!r}")

    # Simulate a source-side republish with a corrected shape -- the same
    # kind of write ingest_parcels.py's own parcel_geom_cache_updates path
    # already performs for a changed feature, not a repair of the SAME
    # stored geometry (that stays banned at rest -- see this pass's own
    # report). geom_valid recomputes automatically (GENERATED STORED).
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE parcel SET geom = ST_Multi(ST_GeomFromText(%s, 4326)) WHERE id = %s",
            (VALID_WKT, parcel_id),
        )
    conn.commit()

    check("geom_valid (0057, generated column) recomputed to true automatically after the UPDATE",
          _geom_valid(conn, parcel_id) is True,
          f"got geom_valid={_geom_valid(conn, parcel_id)!r}")

    flag_parcel_geometry(conn)
    check("C4 FIX: the exception is CLOSED (condition_cleared) once the geometry is corrected -- "
          "the closure path this pass added, not left open forever",
          _open_exception(conn, parcel_id) == "condition_cleared",
          f"got outcome={_open_exception(conn, parcel_id)!r}")

    conn.close()
    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
