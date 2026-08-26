#!/usr/bin/env python3
"""P53 -- proof that the L0/LD-1 jurisdiction gate (prompts/P53-l0-gate.md,
design D-C) is real, not merely notional, and that it holds independently of
cc0/cc_by_4_0's own clearance posture.

THE NEGATIVE CONTROL (P52 sec 5 item 5's own requirement, restated by P53 sec
7): a fixture whose ONE touched fact cites a FULLY-CLEARED test licence
(licence_channel.allowed=true -- the cc0/cc_by_4_0-equivalent of "already
cleared") but whose jurisdiction has no jurisdiction.incorporated fact.
Composition must STILL refuse, via LICENCE_UNKNOWN, with RIGHTS_BLOCKED
absent -- proving the refusal's cause is jurisdiction resolution, not rights
clearance. Without this test, a change that adds rows but never actually
wires _compose() to check them would look done while changing nothing --
exactly the failure shape P52 sec 5 named.

THE POSITIVE COMPANION: same fixture, but the parcel ALSO carries a
jurisdiction.incorporated fact. LICENCE_UNKNOWN must be ABSENT. Without this
test, a hardcoded "always refuse for this jurisdiction" would pass the
negative control while not being a real, two-sided gate at all -- P53's own
prompt calls this out by name and requires it not be dropped.

THE UNTOUCHED-JURISDICTION CONTROL: same fixture, but jurisdiction.
boundary_source_id is left NULL (the default every OTHER test jurisdiction
in this suite already uses, and the default every jurisdiction in this
database had before this pass). LICENCE_UNKNOWN must be ABSENT -- proving
the gate only activates for a jurisdiction that has actually declared it
needs one (D-C's whole scoping argument, made concrete rather than asserted).

THE ACTIVATION-SWITCH CHECK: separately, queries the REAL ca_san_jose
jurisdiction row and fails loudly if boundary_source_id is not exactly
'ca_san_jose.city_limits' -- a gate whose own activation switch is silently
unset must not be able to look healthy. Requires db/seeds/day4_sources.sql
to have been applied; refuses loudly, naming the exact command, if not --
same shape scripts/test_viewer_rights_gate.py's own find_seeded_parcel()
already uses.

Runs against a real database -- writes permanent rows for every property_file
this composes (property_file itself carries no immutability trigger, same as
scripts/test_compose_parcel_refusals.py already notes), fresh uniquely-suffixed
test.*/test_p53_l0_* ids per run so repeated runs never collide. Never touches
cc0, cc_by_4_0, or any real licence_channel row.
"""
import os
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import compose_property_file as cpf  # noqa: E402 -- module under test
from infra.env import get_db  # noqa: E402

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _seed_l0_gate_fixture(conn, suffix, set_boundary_source_id):
    """One fresh test jurisdiction, one FULLY-CLEARED test licence (allowed=
    true on paid_property_file -- the cc0/cc_by_4_0-equivalent of "already
    cleared", isolating the L0 dimension exactly the way db/tests/
    invariants.sql's own 0029 fixtures isolate one rights dimension at a
    time), one boundary-source stub (method='manual' -- matches the
    production design in prompts/P53-l0-gate.md sec 3/4: it can never
    produce a fact, I13, so it is never mistaken for a real ingest path),
    and one real data source for the parcel's own ordinary fact.

    Creation order matters and mirrors the production seed's own resolution
    of the FK-ordering problem (prompts/P53-l0-gate.md sec 2): jurisdiction
    first (boundary_source_id NULL), then the source rows (which need the
    jurisdiction to already exist), THEN the boundary_source_id UPDATE
    (which needs the source row to already exist). Never inserted with
    boundary_source_id set directly in the same statement as the
    jurisdiction row -- the production code cannot do that either, and this
    fixture is deliberately not an easier case than production.
    """
    jurisdiction_id = f"test_p53_l0_{suffix}"
    licence_id = f"test.p53_l0_{suffix}"
    boundary_source_id = f"{jurisdiction_id}.city_limits_stub"
    parcel_source_id = f"{jurisdiction_id}.parcels_stub"

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, "
            "supported, geometry_tier_enabled) "
            "VALUES (%s, 'Test P53 L0 gate', 'city', 'CA', 'v1.0', true, false) "
            "ON CONFLICT (id) DO NOTHING",
            (jurisdiction_id,),
        )
        cur.execute(
            "INSERT INTO licence (id, display_name, restriction, commercial_use, "
            "redistribution, observed_at, cleared_by, cleared_at) "
            "VALUES (%s, 'Test P53 fully-cleared licence', 'open', 'allowed', 'allowed', "
            "now(), 'test_p53_seed', now()) ON CONFLICT (id) DO NOTHING",
            (licence_id,),
        )
        cur.execute(
            "INSERT INTO licence_channel (licence_id, channel, allowed, rationale) "
            "VALUES (%s, 'paid_property_file', true, "
            "'test fixture: fully cleared, isolates the L0 gate dimension under test') "
            "ON CONFLICT (licence_id, channel) DO NOTHING",
            (licence_id,),
        )
        cur.execute(
            "INSERT INTO source (id, jurisdiction_id, display_name, steward, method, "
            "phase_status, phase_status_reason, licence_id, active) "
            "VALUES (%s, %s, 'Test P53 boundary source stub', 'Test', 'manual', "
            "'blocked_rights', 'test fixture -- never produces a fact, I13', %s, false) "
            "ON CONFLICT (id) DO NOTHING",
            (boundary_source_id, jurisdiction_id, licence_id),
        )
        cur.execute(
            "INSERT INTO source (id, jurisdiction_id, display_name, steward, method, "
            "phase_status, phase_status_reason, endpoint_url, licence_id, active) "
            "VALUES (%s, %s, 'Test P53 parcel source', 'Test', 'bulk', 'active', "
            "'test fixture', 'https://example.invalid/p53', %s, false) "
            "ON CONFLICT (id) DO NOTHING",
            (parcel_source_id, jurisdiction_id, licence_id),
        )
        cur.execute(
            "INSERT INTO field_definition (field_key, display_name, claim, value_type, "
            "category, description) VALUES ('parcel.apn', 'APN', 'public_record', "
            "'string', 'parcel', 'Assessor parcel number') ON CONFLICT (field_key) DO NOTHING"
        )
        # Self-contained regardless of whether the real migration has run --
        # this test must work in both the RED (pre-implementation) and GREEN
        # (post-implementation) state, so it never depends on
        # jurisdiction.incorporated already being a real field_definition row.
        cur.execute(
            "INSERT INTO field_definition (field_key, display_name, claim, value_type, "
            "category, description) VALUES ('jurisdiction.incorporated', "
            "'Jurisdiction incorporated', 'public_record', 'boolean', 'jurisdiction', "
            "'Whether this parcel resolves within the jurisdiction''s incorporated "
            "boundary.') ON CONFLICT (field_key) DO NOTHING"
        )
        if set_boundary_source_id:
            cur.execute(
                "UPDATE jurisdiction SET boundary_source_id = %s "
                "WHERE id = %s AND boundary_source_id IS NULL",
                (boundary_source_id, jurisdiction_id),
            )
    conn.commit()
    return jurisdiction_id, licence_id, parcel_source_id


def _seed_fact(conn, jurisdiction_id, source_id, licence_id, suffix, field_key, value_json, parcel_id=None):
    with conn.cursor() as cur:
        if parcel_id is None:
            cur.execute(
                "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
                (jurisdiction_id, f"TEST-P53-L0-{suffix}"),
            )
            parcel_id = cur.fetchone()[0]
        digest = (uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}-{field_key}-{suffix}").hex
                  + uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_id}-{field_key}-{suffix}").hex)[:64]
        snapshot_id = f"{source_id}:sha256:{digest}"
        cur.execute(
            "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, "
            "byte_size, request, http_status, fetched_at, licence_observed_id) "
            "VALUES (%s, %s, 's3://test-p53/fixture', %s, 'application/json', 1, "
            "'{}'::jsonb, 200, now(), %s) ON CONFLICT (id) DO NOTHING",
            (snapshot_id, source_id, digest, licence_id),
        )
        cur.execute(
            "INSERT INTO fact (parcel_id, jurisdiction_id, field_key, value, method, "
            "source_id, snapshot_id, retrieved_at, source_url, licence_id, confidence, "
            "confidence_rule_id, effective_from, pack_version) "
            "VALUES (%s, %s, %s, %s::jsonb, 'bulk', %s, %s, now(), "
            "'https://example.invalid/p53', %s, 'high', 'test_p53_rule', now(), 'v1.0')",
            (parcel_id, jurisdiction_id, field_key, value_json, source_id, snapshot_id, licence_id),
        )
    conn.commit()
    return parcel_id


def _refusal_codes(conn, pf_id):
    with conn.cursor() as cur:
        cur.execute("SELECT refusals FROM property_file WHERE id = %s", (pf_id,))
        refusals = cur.fetchone()[0]
    return refusals, [r.get("code") for r in refusals]


def test_negative_control_jurisdiction_unresolvable_still_refuses():
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    jurisdiction_id, licence_id, source_id = _seed_l0_gate_fixture(conn, suffix, set_boundary_source_id=True)
    parcel_id = _seed_fact(conn, jurisdiction_id, source_id, licence_id, suffix,
                            "parcel.apn", f'"TEST-P53-NEG-{suffix}"')

    result = cpf.compose(conn, parcel_id, "paid_property_file", election="city")

    check("negative control: Result.is_ok (a row is written, not refused before one could be)",
          result.is_ok, f"got {result}")
    if result.is_ok:
        refusals, codes = _refusal_codes(conn, result.value)
        check("negative control: LICENCE_UNKNOWN present despite a fully-cleared licence",
              "LICENCE_UNKNOWN" in codes, f"got {codes}")
        lic_unknown = next((r for r in refusals if r.get("code") == "LICENCE_UNKNOWN"), None)
        if lic_unknown:
            check("negative control: LICENCE_UNKNOWN stage is L0",
                  lic_unknown.get("stage") == "L0", f"got {lic_unknown.get('stage')!r}")
            check("negative control: LICENCE_UNKNOWN names this jurisdiction",
                  lic_unknown.get("detail", {}).get("jurisdiction_id") == jurisdiction_id,
                  f"got {lic_unknown.get('detail')}")
        check("negative control: RIGHTS_BLOCKED ABSENT (the touched fact's own licence "
              "IS fully cleared -- proves independence from licence_channel state)",
              "RIGHTS_BLOCKED" not in codes, f"got {codes}")

    conn.close()


def test_positive_companion_jurisdiction_resolvable_does_not_refuse():
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    jurisdiction_id, licence_id, source_id = _seed_l0_gate_fixture(conn, suffix, set_boundary_source_id=True)
    parcel_id = _seed_fact(conn, jurisdiction_id, source_id, licence_id, suffix,
                            "parcel.apn", f'"TEST-P53-POS-{suffix}"')
    # The gate-satisfying fact -- same parcel, same fully-cleared licence.
    _seed_fact(conn, jurisdiction_id, source_id, licence_id, suffix,
               "jurisdiction.incorporated", "true", parcel_id=parcel_id)

    result = cpf.compose(conn, parcel_id, "paid_property_file", election="city")

    check("positive companion: Result.is_ok", result.is_ok, f"got {result}")
    if result.is_ok:
        _, codes = _refusal_codes(conn, result.value)
        check("positive companion: LICENCE_UNKNOWN ABSENT once a jurisdiction.incorporated "
              "fact exists -- proves this is a real, two-sided gate, not a hardcoded refusal",
              "LICENCE_UNKNOWN" not in codes, f"got {codes}")

    conn.close()


def test_explicit_false_value_still_refuses():
    """C3 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md; A-N11, P59C: corrected
    from a C1 mislabel). The pre-fix gate
    destructured the VALUE away and checked presence only, so an explicit
    jurisdiction.incorporated=false fact -- 0056's own designed meaning,
    "NOT in this jurisdiction" -- suppressed the refusal exactly like true
    does. Same fixture as the positive companion above, but the gate-fact's
    value is false, not true. LICENCE_UNKNOWN must be PRESENT -- this is the
    exact regression case: it would incorrectly be ABSENT if the value
    predicate (`value is True`) were reverted back to a presence-only check."""
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    jurisdiction_id, licence_id, source_id = _seed_l0_gate_fixture(conn, suffix, set_boundary_source_id=True)
    parcel_id = _seed_fact(conn, jurisdiction_id, source_id, licence_id, suffix,
                            "parcel.apn", f'"TEST-P53-FALSEVAL-{suffix}"')
    # The gate fact IS present, but its value is false -- a sourced
    # statement that this parcel is NOT in the jurisdiction.
    _seed_fact(conn, jurisdiction_id, source_id, licence_id, suffix,
               "jurisdiction.incorporated", "false", parcel_id=parcel_id)

    result = cpf.compose(conn, parcel_id, "paid_property_file", election="city")

    check("explicit false: Result.is_ok (a row is written, not refused before one could be)",
          result.is_ok, f"got {result}")
    if result.is_ok:
        _, codes = _refusal_codes(conn, result.value)
        check("explicit false: LICENCE_UNKNOWN PRESENT -- an explicit false must refuse "
              "exactly like absence does, not be treated as satisfying the gate",
              "LICENCE_UNKNOWN" in codes, f"got {codes}")

    conn.close()


def test_untouched_jurisdiction_never_gates():
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    jurisdiction_id, licence_id, source_id = _seed_l0_gate_fixture(conn, suffix, set_boundary_source_id=False)
    parcel_id = _seed_fact(conn, jurisdiction_id, source_id, licence_id, suffix,
                            "parcel.apn", f'"TEST-P53-UNTOUCHED-{suffix}"')

    result = cpf.compose(conn, parcel_id, "paid_property_file", election="city")

    check("untouched jurisdiction: Result.is_ok", result.is_ok, f"got {result}")
    if result.is_ok:
        _, codes = _refusal_codes(conn, result.value)
        check("untouched jurisdiction: LICENCE_UNKNOWN ABSENT (boundary_source_id NULL, "
              "the default every other test jurisdiction in this suite already uses) -- "
              "proves the gate only activates where it was deliberately declared",
              "LICENCE_UNKNOWN" not in codes, f"got {codes}")

    conn.close()


def test_real_ca_san_jose_boundary_source_id_is_set():
    """The activation-switch check the P53 prompt itself requires: a gate
    whose own switch is silently unset must not be able to look healthy."""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT boundary_source_id FROM jurisdiction WHERE id = 'ca_san_jose'")
        row = cur.fetchone()
    conn.close()
    if row is None:
        raise SystemExit(
            "No jurisdiction row for 'ca_san_jose' -- this test reads db/seeds/"
            "day4_sources.sql's own output, it does not create it. Run it first: "
            "psql \"$DATABASE_URL\" -v ON_ERROR_STOP=1 -f db/seeds/day4_sources.sql"
        )
    check("real ca_san_jose: boundary_source_id is set to 'ca_san_jose.city_limits' "
          "(the L0 gate's own activation switch)",
          row[0] == "ca_san_jose.city_limits", f"got {row[0]!r}")


if __name__ == "__main__":
    test_negative_control_jurisdiction_unresolvable_still_refuses()
    test_positive_companion_jurisdiction_resolvable_does_not_refuse()
    test_explicit_false_value_still_refuses()
    test_untouched_jurisdiction_never_gates()
    test_real_ca_san_jose_boundary_source_id_is_set()
    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)
