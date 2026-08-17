#!/usr/bin/env python3
"""Invariant test for the zoning ambiguity miscount (Fix 2).

Invariant under test: a parcel intersecting more than one zoning polygon
is ambiguous only if those polygons disagree on ZONING. Multiple polygon
rows that all agree (or where the extra row carries no classification at
all) must resolve to a normal fact, not a coverage_gap exception with no
fact -- the old code counted candidate ROWS (count(*) OVER ()), which
misclassified exactly this shape as ambiguous.

Runs the REAL scripts/ingest_zoning_permits.py load_zoning() end to end
against a real database -- real spatial join, real ST_Contains, real
fact/parcel_exception inserts. The zoning "source" is a tiny, synthetic,
two-polygon GeoJSON file reproducing the exact real-world shape found in
ca_san_jose.zoning_districts (FACILITYID 30392: one polygon with
ZONING/ZONINGABBREV both null, overlapping a real classified polygon) --
not a mock of load_zoning's logic, a real input file it parses itself.

Requires DATABASE_URL for a scratch database (this test commits real fact
rows; 0017 forbids deleting them, so use a disposable database, never a
shared one).

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_zoning_ambiguity_invariant.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import datetime
import json
import os
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import ingest_zoning_permits as izp  # noqa: E402 -- module under test, imported, not reimplemented
from infra.env import get_db  # noqa: E402


def seed_reference_rows(conn):
    with conn.cursor() as cur:
        cur.execute(
            # observed_at/cleared_by/cleared_at match db/seeds/day4_sources.sql's own
            # values exactly (not now()/'test'/now()) -- see _p5_setup.py's identical
            # comment: counsel/owner sign-off is genuinely still Pending, and this
            # insert must not fabricate it on whatever database it first reaches.
            """
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, observed_at, cleared_by, cleared_at)
            VALUES (%s, 'CC BY 4.0', 'attribution', 'allowed', 'allowed', 'City of San Jose',
                    '2026-07-31'::timestamptz, NULL, NULL)
            ON CONFLICT (id) DO NOTHING
            """,
            (izp.LICENCE_ID_ZONING,),
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
        cur.execute(
            """
            INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description)
            VALUES
              ('zoning.district', 'Zoning district', 'public_record', 'string', 'zoning', 'Zoning classification'),
              ('zoning.district_verbatim', 'Zoning district (verbatim)', 'public_record', 'string', 'zoning', 'Raw source abbreviation')
            ON CONFLICT (field_key) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size,
                                   request, http_status, fetched_at, licence_observed_id)
            VALUES (%s, %s, 's3://test/fixture', %s, 'application/geo+json', 1,
                    '{}'::jsonb, 200, now(), %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (izp.snapshot_id_for(izp.SOURCE_ID_ZONING, "0" * 64), izp.SOURCE_ID_ZONING, "0" * 64, izp.LICENCE_ID_ZONING),
        )
    conn.commit()


def make_fixture_geojson_path(scratchpad):
    """Two overlapping squares, both containing (0, 0): a real classified
    polygon (FACILITYID 'real', ZONING='A(PD)') and a null-classification
    polygon (FACILITYID 'null-shape', ZONING/ZONINGABBREV both None) --
    the exact real-world shape (FACILITYID=30392) that broke row counting.
    """
    body = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"FACILITYID": "real", "ZONING": "A(PD)", "ZONINGABBREV": "A(PD)"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]
                ]]},
            },
            {
                "type": "Feature",
                "properties": {"FACILITYID": "null-shape", "ZONING": None, "ZONINGABBREV": None},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5], [-0.5, -0.5]
                ]]},
            },
        ],
    }
    path = os.path.join(scratchpad, f"zoning_ambiguity_fixture_{uuid.uuid4().hex}.geojson")
    with open(path, "w") as f:
        json.dump(body, f)
    return path


def make_test_parcel(conn):
    """A parcel whose geom's centroid is (0, 0) -- inside both fixture
    polygons above. A tiny square centered at the origin."""
    token = uuid.uuid4().hex
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO parcel (jurisdiction_id, apn, geom)
            VALUES (%s, %s, ST_Multi(ST_SetSRID(ST_GeomFromText(
                'POLYGON((-0.01 -0.01, 0.01 -0.01, 0.01 0.01, -0.01 0.01, -0.01 -0.01))'
            ), 4326)))
            RETURNING id
            """,
            (izp.JURISDICTION_ID, f"TEST-{token}"),
        )
        parcel_id = cur.fetchone()[0]
    conn.commit()
    return parcel_id


def run():
    scratchpad = "/private/tmp/claude-501/-Users-dev-Desktop-ledgex-adu/59865388-e258-4aba-b756-014d02490b5a/scratchpad"
    os.makedirs(scratchpad, exist_ok=True)

    conn = get_db()
    seed_reference_rows(conn)
    parcel_id = make_test_parcel(conn)
    path = make_fixture_geojson_path(scratchpad)
    print(f"[test] parcel {parcel_id}, fixture {path}")

    retrieved_at = datetime.datetime.now(datetime.timezone.utc)
    izp.load_zoning(conn, path, izp.snapshot_id_for(izp.SOURCE_ID_ZONING, "0" * 64), retrieved_at)

    check_conn = get_db()
    with check_conn.cursor() as cur:
        cur.execute(
            "SELECT field_key, value FROM fact WHERE parcel_id = %s AND field_key LIKE 'zoning.%%' AND superseded_at IS NULL",
            (parcel_id,),
        )
        facts = dict(cur.fetchall())
        cur.execute(
            "SELECT detail->>'reason' FROM parcel_exception WHERE parcel_id = %s AND detector_key = %s",
            (parcel_id, izp.DETECTOR_KEY_ZONING_UNRESOLVABLE),
        )
        exception_reasons = [r[0] for r in cur.fetchall()]
    check_conn.close()
    conn.close()

    print(f"[test] facts for parcel: {facts}")
    print(f"[test] exception reasons for parcel: {exception_reasons}")

    failures = []
    if facts.get("zoning.district") != "A(PD)":
        failures.append(f"expected fact zoning.district='A(PD)', got {facts.get('zoning.district')!r} "
                         f"(a parcel intersecting one real polygon plus one null-classification polygon "
                         f"must resolve to a fact -- there is exactly one real answer)")
    if "multiple_containing_districts" in exception_reasons:
        failures.append(f"got a 'multiple_containing_districts' exception -- this parcel is NOT ambiguous, "
                         f"it has exactly one real classification (the second candidate has no classification "
                         f"at all)")

    if failures:
        print("[test] FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("[test] PASS: parcel with one real + one null-classification containing polygon "
          "resolves to a fact, not a false 'ambiguous' exception.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
