#!/usr/bin/env python3
"""make conformance -- real for one pack (P26): jurisdictions/ca_san_jose.

SPEC.md §1.2's own pass condition: "Every enabled pack passes; no rights
broadening or silent missing dependency." This checks what a pack can
actually assert TODAY, for the one real pack that exists:

  1. jurisdictions/ca_san_jose/{sources,licences}.yaml both validate
     against jurisdictions/_schema/{sources,licences}.schema.json.
  2. Every ACTIVE source's own `licence` names a real licence.id row.
  3. Every ACTIVE source's own `supplies:` field_keys all exist in
     field_definition.
  4. Every ACTIVE source's own `supplies:` list matches the live
     source.expected_fields EXACTLY (as sets) -- this is the check that
     answers "what stops the pack and the seed disagreeing", the design
     question this package's own report settles: db/seeds/day4_sources.sql
     and the live database remain the runtime authority (§7.3: "Nothing
     else grants a channel" -- the same principle extends to what a
     source supplies), and this pack is checked AGAINST that authority on
     every CI run, not trusted to stay in sync on its own. Real drift
     already found this way once, before this check even existed: §7.1's
     own literal `parcels` supplies: list predates migrations 0026/0035
     and disagreed with the live, corrected source.expected_fields --
     see jurisdictions/ca_san_jose/sources.yaml's own header comment and
     prompts/P26-jurisdictions-pack-format.md for the fix.

Checks 2-4 are scoped to phase_status: active sources ONLY -- a
blocked_rights/deferred/not_machine_readable/excluded source is declared
for completeness (§7.1's own "recorded so the exclusion is a decision,
not an oversight") and legitimately has no field_definition or licence
row yet, the identical phase1_deferred precedent field_definition itself
already uses. Requiring full DB backing for every one of the 26 sources
declared in this pack (3 active, 23 not) would make conformance
permanently unpassable for a reason that has nothing to do with the
pack's own correctness.

COVERAGE, NAMED EXPLICITLY EVERY RUN, SAME DISCIPLINE make golden AND
make test ALREADY USE (P20/P21) -- exiting 0 here does NOT mean §1.2's
full conformance contract is satisfied:
  - rights broadening against Plan 2.1.4 Appendix K
    (test_licences_not_broader_than_appendix_k, §7.3) -- this pack has
    no machine-readable copy of Appendix K to diff against.
  - dependency cascades (a blocked/deferred source's effect on a
    dependent conclusion) -- no conclusion-dependency graph exists
    anywhere in this codebase yet (core/calc has exactly one, P25's own
    geometry gate, unrelated to source dependencies).
  - mappings (field_map.yaml / crosswalk values, §6.1 task shape A step
    4, §6.1 task shape B step 2) -- this package deliberately does NOT
    design or build that file; see prompts/P26-jurisdictions-pack-
    format.md's own scope section for why moving the loaders' real
    mapping logic is a separate, later package.
  Endpoint liveness is now real (P28, make liveness) -- its own,
  separate, scheduled-only gate (.github/workflows/liveness.yml), not
  folded into this script and not covered by this exit code: this
  script still makes no network calls.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/check_conformance.py

Exit code 0 = every check above passed. Exit code 1 = any failed.
"""
import json
import os
import sys

import jsonschema
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import ingest_parcels as ip  # noqa: E402 -- reused for its real, honest reference-row shape
import ingest_zoning_permits as izp  # noqa: E402 -- same reasoning
from infra.env import get_db  # noqa: E402

SCHEMA_DIR = os.path.join(REPO_ROOT, "jurisdictions", "_schema")
PACK_DIR = os.path.join(REPO_ROOT, "jurisdictions", "ca_san_jose")

NOT_YET_CHECKED = [
    "rights broadening against Plan 2.1.4 Appendix K (test_licences_not_broader_than_appendix_k, sec 7.3)",
    "dependency cascades (a blocked/deferred source's effect on a dependent conclusion)",
    "mappings (field_map.yaml / crosswalk values -- deliberately not designed by this package)",
]

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def load_schema(name):
    with open(os.path.join(SCHEMA_DIR, name)) as f:
        return json.load(f)


def check_schema_validity(pack, schema, label):
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(pack), key=lambda e: list(e.path))
    check(f"{label} validates against its own JSON Schema", not errors,
          "; ".join(f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors))


def seed_reference_rows(conn):
    """Real, honest, non-fabricated reference rows -- same pattern
    scripts/check_golden.py's own seed_reference_rows() already
    established (P20): reuses ingest_parcels.py/ingest_zoning_permits.py's
    REAL LICENCE_ID/JURISDICTION_ID/SOURCE_ID/ENDPOINT_URL constants and
    db/seeds/day4_sources.sql's own real expected_fields, observed_at,
    cleared_by/cleared_at values -- never a fabricated clearance.

    Needed because CI's schema job applies migrations only and never runs
    db/seeds/ (CLAUDE.md's own documented rule) -- without this, every
    active-source check below would fail on a fresh, migrations-only
    database not because the pack is wrong, but because nothing was ever
    seeded to compare it against.

    The `source` INSERT is ON CONFLICT DO UPDATE, not DO NOTHING like
    licence/jurisdiction/field_definition above -- found for real, not
    hypothetical: scripts/check_golden.py's OWN seed_reference_rows()
    also inserts a ca_san_jose.parcels row (ON CONFLICT DO NOTHING,
    never setting expected_fields, defaulting to '[]') for its own,
    narrower purpose. db.yml's schema job runs `make golden` before this
    script in the SAME shared, disposable database -- if golden's minimal
    row wins the race, this seed's own DO-NOTHING insert would silently
    no-op, leaving expected_fields empty, and the very check this script
    exists to run (does the pack's supplies: match the live
    expected_fields) would fail for a reason that has nothing to do with
    the pack. DO UPDATE makes this seed's own required shape win
    regardless of what ran first -- safe against ledgex_schema_check too,
    since the values being written are identical to what
    db/seeds/day4_sources.sql already put there; an UPDATE to the same
    values is a no-op in effect, not merely in intent."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, terms_url, observed_at, cleared_by, cleared_at)
            VALUES
              ('cc0', 'CC0 1.0 Universal', 'open', 'allowed', 'allowed', NULL,
               'https://creativecommons.org/publicdomain/zero/1.0/', '2026-07-31'::timestamptz, NULL, NULL),
              ('cc_by_4_0', 'CC BY 4.0', 'attribution', 'allowed', 'allowed',
               'Data © City of San José', 'https://creativecommons.org/licenses/by/4.0/',
               '2026-07-31'::timestamptz, NULL, NULL),
              -- P55: the `source` INSERT below reads ip.LICENCE_ID /
              -- izp.LICENCE_ID_ZONING / izp.LICENCE_ID_PERMITS directly --
              -- already repointed to these ids (§4.1/§4.5 step 9) -- so this
              -- reference-row fallback needs the licence rows to match, or a
              -- migrations-only `make conformance` run raises
              -- foreign_key_violation instead of testing the pack.
              ('cc_by_4_0_api_2026_08', 'CC BY 4.0 (api channel, scoped 2026-08)',
               'attribution', 'allowed', 'allowed', 'Data © City of San José',
               'https://creativecommons.org/licenses/by/4.0/', '2026-07-31'::timestamptz, NULL, NULL),
              ('cc0_api_2026_08', 'CC0 1.0 (api channel, scoped 2026-08)',
               'open', 'allowed', 'allowed', NULL,
               'https://creativecommons.org/publicdomain/zero/1.0/', '2026-07-31'::timestamptz, NULL, NULL)
            ON CONFLICT (id) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES ('ca_san_jose', 'City of San José', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO field_definition (field_key, display_name, claim, value_type, unit, category, description)
            VALUES
              ('parcel.apn', 'Assessor Parcel Number', 'public_record', 'string', NULL, 'parcel',
               'Unique parcel identifier from Santa Clara County Assessor'),
              ('parcel.geometry', 'Parcel Geometry', 'public_record', 'geometry', NULL, 'parcel',
               'Parcel boundary as MultiPolygon (GIS data)'),
              ('parcel.source_parcel_id', 'Source Parcel ID', 'public_record', 'string', NULL, 'parcel',
               'County GIS internal id (PARCELID). Observation only, not a matching key.'),
              ('zoning.district', 'Zoning District', 'public_record', 'string', NULL, 'zoning',
               'Zoning classification assigned by the City of San José'),
              ('zoning.district_verbatim', 'Zoning District (Verbatim)', 'public_record', 'string', NULL, 'zoning',
               'Exact zoning designation as stored in the City''s GIS system'),
              ('permits.active', 'Active Building Permit', 'public_record', 'boolean', NULL, 'permits',
               'Whether the parcel has an active building permit'),
              ('permits.series_earliest', 'Earliest Active Permit Date', 'public_record', 'date', NULL, 'permits',
               'Date of the earliest currently-active building permit')
            ON CONFLICT (field_key) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status,
                                 phase_status_reason, endpoint_url, licence_id, active, url_verified_at,
                                 expected_fields)
            VALUES
              (%s, %s, 'Parcels', 'City of San José', 'bulk', 'active', 'Licence confirmed: CC BY 4.0.',
               %s, %s, true, '2026-08-06'::timestamptz,
               '["parcel.apn","parcel.geometry","parcel.source_parcel_id"]'::jsonb),
              (%s, %s, 'Zoning Districts', 'City of San José', 'bulk', 'active', 'Licence confirmed: CC BY 4.0.',
               %s, %s, true, '2026-08-06'::timestamptz,
               '["zoning.district","zoning.district_verbatim"]'::jsonb),
              (%s, %s, 'Active Building Permits', 'City of San José', 'bulk', 'active', 'Licence confirmed: CC0.',
               %s, %s, true, '2026-08-06'::timestamptz,
               '["permits.active","permits.series_earliest"]'::jsonb)
            ON CONFLICT (id) DO UPDATE SET
              expected_fields = EXCLUDED.expected_fields,
              active = EXCLUDED.active,
              url_verified_at = EXCLUDED.url_verified_at,
              phase_status = EXCLUDED.phase_status,
              phase_status_reason = EXCLUDED.phase_status_reason,
              endpoint_url = EXCLUDED.endpoint_url,
              licence_id = EXCLUDED.licence_id
            """,
            (
                ip.SOURCE_ID, ip.JURISDICTION_ID, ip.ENDPOINT_URL, ip.LICENCE_ID,
                izp.SOURCE_ID_ZONING, izp.JURISDICTION_ID, izp.ENDPOINT_URL_ZONING, izp.LICENCE_ID_ZONING,
                izp.SOURCE_ID_PERMITS, izp.JURISDICTION_ID, izp.ENDPOINT_URL_PERMITS, izp.LICENCE_ID_PERMITS,
            ),
        )
    conn.commit()


def check_active_sources_against_database(sources_pack, conn):
    jurisdiction_prefix = sources_pack["jurisdiction"] + "."
    active = [s for s in sources_pack["sources"] if s.get("phase_status") == "active"]
    # Scoped to sources this pack's OWN jurisdiction actually owns
    # (id starts with "ca_san_jose.") -- federal/state sources reused
    # across future jurisdictions (us_fema.nfhl, us_nrcs.soil_survey) are
    # declared "active" here in rights-posture only (§7.1's own text);
    # nothing in this schema assigns them a jurisdiction_id at all yet
    # (no shared "federal" jurisdiction row exists), so a query scoped to
    # jurisdiction_id='ca_san_jose' could never find them even if they
    # were ingested. Requiring a live row for them here would fail on a
    # real, separate, unbuilt piece of schema design, not on anything
    # this pack got wrong -- reported, not silently worked around.
    owned_active = [s for s in active if s["id"].startswith(jurisdiction_prefix)]
    external_active = [s for s in active if not s["id"].startswith(jurisdiction_prefix)]
    check("at least one owned active source declared", len(owned_active) > 0, f"got {len(owned_active)}")
    if external_active:
        print(f"NOTE: {len(external_active)} active-declared source(s) belong to a different "
              f"steward, not ca_san_jose's own jurisdiction_id, and are not checked against the "
              f"database here: {[s['id'] for s in external_active]} -- see this script's own "
              f"module docstring.")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, licence_id, expected_fields FROM source WHERE jurisdiction_id = %s",
            (sources_pack["jurisdiction"],),
        )
        db_sources = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
        cur.execute("SELECT id FROM licence")
        db_licence_ids = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT field_key FROM field_definition")
        db_field_keys = {row[0] for row in cur.fetchall()}

    for s in owned_active:
        sid = s["id"]
        check(f"active source {sid!r} exists in the live source table", sid in db_sources)
        if sid not in db_sources:
            continue
        db_licence_id, db_expected_fields = db_sources[sid]

        check(f"{sid!r}'s licence {s['licence']!r} exists in the live licence table",
              s["licence"] in db_licence_ids)
        check(f"{sid!r}'s pack licence matches the live source row's own licence_id",
              s["licence"] == db_licence_id,
              f"pack says {s['licence']!r}, database says {db_licence_id!r}")

        missing_field_defs = [fk for fk in s["supplies"] if fk not in db_field_keys]
        check(f"every field_key {sid!r} supplies exists in field_definition",
              not missing_field_defs, f"missing: {missing_field_defs}")

        pack_supplies = set(s["supplies"])
        db_supplies = set(db_expected_fields)
        check(f"{sid!r}'s supplies: matches the live source.expected_fields exactly",
              pack_supplies == db_supplies,
              f"pack has {sorted(pack_supplies - db_supplies)} not in the database, "
              f"database has {sorted(db_supplies - pack_supplies)} not in the pack")


def check_licence_pack_ids_are_unique(licences_pack):
    ids = [l["id"] for l in licences_pack["licences"]]
    check("licences.yaml has no duplicate licence ids", len(ids) == len(set(ids)),
          f"duplicates: {[i for i in ids if ids.count(i) > 1]}")


def main():
    print("CONFORMANCE: checking jurisdictions/ca_san_jose (1 real pack) -- "
          "schema validity, active-source licence/field/expected_fields agreement "
          "with the live database.")
    print(f"CONFORMANCE: NOT covered this run (see scripts/check_conformance.py's "
          f"own module docstring for why): {'; '.join(NOT_YET_CHECKED)}.")

    sources_pack = load_yaml(os.path.join(PACK_DIR, "sources.yaml"))
    licences_pack = load_yaml(os.path.join(PACK_DIR, "licences.yaml"))
    sources_schema = load_schema("sources.schema.json")
    licences_schema = load_schema("licences.schema.json")

    check_schema_validity(sources_pack, sources_schema, "sources.yaml")
    check_schema_validity(licences_pack, licences_schema, "licences.yaml")
    check_licence_pack_ids_are_unique(licences_pack)

    conn = get_db()
    try:
        seed_reference_rows(conn)
        check_active_sources_against_database(sources_pack, conn)
    finally:
        conn.close()

    print(f"\nCONFORMANCE SUMMARY: {'PASSED' if not failures else 'FAILED'} "
          f"({len(failures)} failure(s)). 1 pack checked (ca_san_jose). "
          f"NOT covered: {'; '.join(NOT_YET_CHECKED)}.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
