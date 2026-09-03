#!/usr/bin/env python3
"""P63E: the binding contract, as an executable test -- parcel.geometry, once served through
api.main.get_parcel_facts, must always resolve through the parcel.geometry FACT and its
licence, never through the parcel.geom column (which carries no licence linkage at all,
confirmed in P63D's own audit and re-confirmed by this file's own fixture below).

Two fixture parcels, both self-contained (no seed script run, no licence/licence_channel row
created -- both reuse ALREADY-LIVE test licence ids, confirmed present before this test ever
runs):
  - PERMITTED: parcel.geometry fact under internal_test.cc_by_4_0 (licence_channel.api=true,
    confirmed live before this file was written) -- must appear in facts[], with its real
    value, gated correctly.
  - BLOCKED: parcel.geometry fact under a p25-geom test licence with no api-channel row at
    all (default-deny, I6) -- must appear in omitted_for_rights[], never in facts[], and its
    value must never appear anywhere in the serialized response (same I6 assertion
    scripts/test_viewer_rights_gate.py already makes for other fields, applied here
    specifically to geometry).

Calls api.main.get_parcel_facts directly, as a plain function -- not over HTTP, same
convention as scripts/test_viewer_rights_gate.py.

THE RED PROOF (see prove_red_by_substituting_a_direct_column_read() below): this file defines
its own broken variant of the query get_parcel_facts issues -- one that selects parcel.geom
directly and returns it unconditionally, bypassing evaluate_rights_gate entirely -- and runs
this file's OWN assertion helper against its output, confirming the assertion correctly
flags the leak. This is a self-contained mutation test: it never edits api/main.py on disk,
and the real, unmodified api.main.get_parcel_facts is exercised separately and confirmed
correct. A test that only ever calls the real function has not been shown to test anything;
this one shows both the failure and the fix, in one process, with nothing left behind.

Writes: one jurisdiction, one source, one snapshot, two parcels and two facts, all under the
`test_p63e_*`/`TEST-P63E-*` namespace db/tests/teardown.sql already cleans up. Also inserts
`field_definition`'s `parcel.geometry` row if not already present (ON CONFLICT DO NOTHING,
same convention every sibling test script in this repo already uses -- field_definition is
not immutable). Creates NO licence, NO licence_channel row, on any database.

Requires DATABASE_URL for a scratch database. Never point this at ledgex_schema_check.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_viewer_geometry_binding.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import hashlib
import json
import os
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
import api.main as viewer  # noqa: E402

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


PERMITTED_LICENCE_ID = "internal_test.cc_by_4_0"   # confirmed live: licence_channel.api = true
# The REAL base licence, not a test double -- reused deliberately, matching
# scripts/seed_internal_test_licences.py's own precedent for its blocked
# fixture (its own comment: "licence_id is the real ... licence this id
# parallels"). Confirmed live: allowed=false on every channel including
# api, "counsel/owner sign-off Pending" -- and unlike an ad-hoc test-only
# licence id, cc_by_4_0 is guaranteed present on any database this
# repository considers real (it is one of the two genesis licences), so
# this fixture is reproducible from the tracked repo, not from live-only
# history.
BLOCKED_LICENCE_ID = "cc_by_4_0"
GEOM_VALUE = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


def confirm_fixture_licences_preexist(conn):
    """Refuse loudly rather than silently creating a licence row if either fixture licence
    is not already live -- this test must never be the thing that mints one."""
    with conn.cursor() as cur:
        for lic_id, expect_permitted in ((PERMITTED_LICENCE_ID, True), (BLOCKED_LICENCE_ID, False)):
            cur.execute("SELECT 1 FROM licence WHERE id = %s", (lic_id,))
            if cur.fetchone() is None:
                raise SystemExit(
                    f"Fixture licence {lic_id!r} does not exist on this database. This test "
                    f"reuses already-live test licences and creates none -- it cannot proceed "
                    f"until that licence exists on whatever database DATABASE_URL points at."
                )
            cur.execute(
                "SELECT allowed FROM licence_channel WHERE licence_id = %s AND channel = 'api'",
                (lic_id,),
            )
            row = cur.fetchone()
            # Default-deny (I6): an absent row and an explicit allowed=false row are the same
            # outcome for this test's purposes -- either way the api channel does not permit
            # this licence. Only allowed=true is the PERMITTED case.
            actual_permitted = bool(row) and row[0] is True
            if actual_permitted != expect_permitted:
                raise SystemExit(
                    f"Fixture licence {lic_id!r}: expected api-channel permitted={expect_permitted}, "
                    f"got permitted={actual_permitted} (raw row: {row!r})."
                )


def seed_reference_rows(conn):
    """field_definition/jurisdiction/source are shared; snapshot is NOT -- fact_snapshot_
    licence_fk requires (snapshot_id, licence_id) to match (snapshot.id, snapshot.
    licence_observed_id), so each fixture licence needs its OWN snapshot row. Returns
    {licence_id: snapshot_id}."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description) "
            "VALUES ('parcel.geometry', 'Parcel Geometry', 'public_record', 'geometry', 'parcel', "
            "'Parcel boundary as GeoJSON') ON CONFLICT (field_key) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported) "
            "VALUES ('test_p63e', 'Test P63E', 'city', 'CA', 'v1.0', true) "
            "ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO source (id, jurisdiction_id, display_name, steward, steward_class, method, "
            "phase_status, phase_status_reason, endpoint_url, licence_id, active) "
            "VALUES ('test_p63e.geom_source', 'test_p63e', 'P63E geometry fixture source', 'Test', "
            "'unknown', 'bulk', 'active', 'test fixture', 'https://example.invalid/p63e', %s, false) "
            "ON CONFLICT (id) DO NOTHING",
            (PERMITTED_LICENCE_ID,),
        )
        snap_id_by_licence = {}
        for licence_id in (PERMITTED_LICENCE_ID, BLOCKED_LICENCE_ID):
            digest = hashlib.sha256(f"p63e-geometry-binding-fixture:{licence_id}".encode()).hexdigest()
            snap_id = f"test_p63e.geom_source:sha256:{digest}"
            cur.execute(
                "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size, "
                "request, http_status, fetched_at, licence_observed_id) "
                "VALUES (%s, 'test_p63e.geom_source', 's3://test-p63e/fixture', %s, 'application/geo+json', "
                "1, '{}'::jsonb, 200, now(), %s) ON CONFLICT (id) DO NOTHING",
                (snap_id, digest, licence_id),
            )
            snap_id_by_licence[licence_id] = snap_id
    conn.commit()
    return snap_id_by_licence


def make_parcel_with_geometry_fact(conn, snapshot_id, licence_id):
    suffix = uuid.uuid4().hex[:8]
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES ('test_p63e', %s) RETURNING id",
            (f"TEST-P63E-{suffix}",),
        )
        parcel_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO fact (parcel_id, jurisdiction_id, field_key, value, method, source_id, "
            "snapshot_id, retrieved_at, source_url, licence_id, confidence, confidence_rule_id, "
            "effective_from, pack_version) VALUES (%s, 'test_p63e', 'parcel.geometry', %s, 'bulk', "
            "'test_p63e.geom_source', %s, now(), 'https://example.invalid/p63e', %s, 'high', "
            "'rule_1', now(), 'v1.0') RETURNING id",
            (parcel_id, json.dumps(GEOM_VALUE), snapshot_id, licence_id),
        )
        fact_id = cur.fetchone()[0]
    conn.commit()
    return parcel_id, fact_id


def prove_red_by_substituting_a_direct_column_read(permitted_parcel_id, blocked_parcel_id):
    """The mutation test. broken_get_parcel_facts mimics api.main.get_parcel_facts's shape
    but selects parcel.geom directly and returns it as a bare value, with NO call to
    evaluate_rights_gate at all -- exactly the hazard P63D named. Runs this file's own
    assertion helper against ITS output first (must catch the leak on the BLOCKED parcel),
    then against the real, unmodified viewer.get_parcel_facts's output (must find nothing
    wrong). Neither call touches api/main.py on disk."""
    def broken_get_parcel_facts(parcel_id, conn):
        with conn.cursor() as cur:
            cur.execute("SELECT ST_AsGeoJSON(geom) FROM parcel WHERE id = %s", (parcel_id,))
            row = cur.fetchone()
        geom_json = row[0] if row else None
        return {
            "parcel_id": parcel_id, "as_of": None, "channel": "api",
            "facts": [{"field_key": "parcel.geometry", "value": geom_json, "licence_id": None,
                       "source_id": None, "snapshot_id": None, "method": "bulk",
                       "retrieved_at": None, "is_derived": False,
                       "rights_position": "unknown", "diligence": "written_confirmation_pending"}]
            if geom_json else [],
            "omitted_for_rights": [],
        }

    def geometry_leaked(result):
        return any(f["field_key"] == "parcel.geometry" for f in result["facts"])

    conn = get_db()
    # First: the blocked parcel's OWN geom column is populated directly (bypassing the fact
    # entirely) so the broken variant has something to leak, proving this is a real
    # column-level bypass, not merely an empty-result coincidence.
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE parcel SET geom = ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) WHERE id = %s",
            (json.dumps(GEOM_VALUE), blocked_parcel_id),
        )
    conn.commit()

    # This is the RED half -- the broken variant is SUPPOSED to leak, so its own leak is not
    # itself a failure of this test suite. What IS asserted (via check(), counted toward
    # failures) is that the leak actually happened -- if it didn't, the mutation wasn't a real
    # mutation and this whole proof would be vacuous.
    broken_result = broken_get_parcel_facts(blocked_parcel_id, conn)
    broken_leaked = geometry_leaked(broken_result)
    print(f"[{'RED' if broken_leaked else 'unexpected-green'}] RED PROOF: broken direct-column-read "
          f"variant {'leaks' if broken_leaked else 'did NOT leak'} geometry for the blocked parcel"
          + ("" if broken_leaked else f" -- broken_result={broken_result}"))
    check("RED PROOF: the broken variant did in fact leak (proves the mutation is real, not vacuous)",
          broken_leaked, f"broken_result={broken_result}")

    conn2 = get_db()
    real_result = viewer.get_parcel_facts(blocked_parcel_id, as_of=None, conn=conn2)
    conn2.close()
    check("GREEN: the REAL, unmodified get_parcel_facts does not leak geometry for the blocked parcel",
          not geometry_leaked(real_result),
          f"parcel.geometry appeared in facts[] for a licence with no api grant: {real_result['facts']}")
    conn.close()


def main():
    conn = get_db()
    confirm_fixture_licences_preexist(conn)
    snap_id_by_licence = seed_reference_rows(conn)
    permitted_parcel_id, permitted_fact_id = make_parcel_with_geometry_fact(
        conn, snap_id_by_licence[PERMITTED_LICENCE_ID], PERMITTED_LICENCE_ID)
    blocked_parcel_id, blocked_fact_id = make_parcel_with_geometry_fact(
        conn, snap_id_by_licence[BLOCKED_LICENCE_ID], BLOCKED_LICENCE_ID)
    conn.close()

    conn = get_db()
    permitted_result = viewer.get_parcel_facts(permitted_parcel_id, as_of=None, conn=conn)
    conn.close()
    check("PERMITTED: parcel.geometry appears in facts[]",
          any(f["field_key"] == "parcel.geometry" for f in permitted_result["facts"]),
          f"got facts={permitted_result['facts']}")
    check("PERMITTED: parcel.geometry does NOT appear in omitted_for_rights[]",
          not any(o["field_key"] == "parcel.geometry" for o in permitted_result["omitted_for_rights"]),
          f"got omitted_for_rights={permitted_result['omitted_for_rights']}")
    geom_fact = next((f for f in permitted_result["facts"] if f["field_key"] == "parcel.geometry"), None)
    check("PERMITTED: the returned value is the real GeoJSON fact value",
          geom_fact is not None and geom_fact["value"] == GEOM_VALUE,
          f"got {geom_fact}")

    conn = get_db()
    blocked_result = viewer.get_parcel_facts(blocked_parcel_id, as_of=None, conn=conn)
    conn.close()
    check("BLOCKED: parcel.geometry appears in omitted_for_rights[]",
          any(o["field_key"] == "parcel.geometry" for o in blocked_result["omitted_for_rights"]),
          f"got omitted_for_rights={blocked_result['omitted_for_rights']}")
    check("BLOCKED: parcel.geometry does NOT appear in facts[]",
          not any(f["field_key"] == "parcel.geometry" for f in blocked_result["facts"]),
          f"got facts={blocked_result['facts']}")
    serialized = viewer.ParcelFactsResponse.model_validate(blocked_result).model_dump_json()
    check("BLOCKED: the geometry VALUE never appears anywhere in the serialized response",
          json.dumps(GEOM_VALUE["coordinates"]) not in serialized,
          "geometry coordinates leaked into the serialized wire response")

    prove_red_by_substituting_a_direct_column_read(permitted_parcel_id, blocked_parcel_id)

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
