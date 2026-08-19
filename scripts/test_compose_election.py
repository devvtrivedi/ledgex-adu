#!/usr/bin/env python3
"""Invariant test for the election parameter (P34, README finding #35).

Proves the three distinct L5 outcomes compose_property_file.py's own
election-aware rule selection can now produce are each reached by their
own distinct cause, not conflated:

  election=None                -> ELECTION_REQUIRED, no `rule` query ever
                                    attempted (nothing to look up).
  election="state" supplied,    -> ELECTION_NOT_SUPPORTED, no `rule` query
  no CONCLUSION_RULE_KEYS entry    ever attempted (this composer has no
                                    rule_key for this pairing at all).
  election="city" supplied,     -> RULE_UNAVAILABLE, a REAL query against
  entry found, but no `rule`       `rule` runs and genuinely finds nothing
  row exists for this test         -- a temporal claim, not a composer-
  jurisdiction                     knowledge gap.

The third case is the one that matters most: it proves election="city"
resolves a real rule_key and reaches core/rules.select_effective_rule()
for real (proven separately, against a synthetic jurisdiction/rule_key,
by tests/core/test_rules.py) rather than silently short-circuiting the
same way the first two do. Uses a synthetic test_* jurisdiction with NO
rule row seeded at all -- this proves the mechanism, not README finding
#35's own one real seeded rule (ca_san_jose, city-only); see
prompts/P34-election-parameter-build.md for that argument and for why a
second, State-standards rule is deliberately not seeded here or anywhere
else in this package.

Runs against a real database -- writes permanent rows (property_file
carries no immutability trigger, but this is still a real write, not a
mock). Fresh, uniquely-suffixed test.* jurisdiction/licence/source/
field/parcel ids per run so repeated runs never collide.
"""
import datetime
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


def _seed(conn, suffix):
    jurisdiction_id = f"test_p34_election_{suffix}"
    licence_id = f"test.p34_election_licence_{suffix}"
    source_id = f"test.p34_election_source_{suffix}"
    field_key = f"test.p34_election_field_{suffix}"
    apn = f"TEST-P34-ELECTION-{suffix}"

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, "
            "supported, geometry_tier_enabled) "
            "VALUES (%s, 'Test', 'city', 'CA', 'v1.0', true, false) ON CONFLICT (id) DO NOTHING",
            (jurisdiction_id,),
        )
        cur.execute(
            "INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution, "
            "attribution_text, observed_at, cleared_by, cleared_at) "
            "VALUES (%s, 'Test', 'open', 'allowed', 'allowed', NULL, now(), NULL, NULL) "
            "ON CONFLICT (id) DO NOTHING",
            (licence_id,),
        )
        cur.execute(
            "INSERT INTO licence_channel (licence_id, channel, allowed, rationale) "
            "VALUES (%s, 'paid_property_file', false, 'test fixture: blocked, matching real state') "
            "ON CONFLICT (licence_id, channel) DO NOTHING",
            (licence_id,),
        )
        cur.execute(
            "INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status, "
            "phase_status_reason, endpoint_url, licence_id, active) "
            "VALUES (%s, %s, 'Test Source', 'Test', 'bulk', 'active', 'test fixture', "
            "'https://example.com', %s, false) ON CONFLICT (id) DO NOTHING",
            (source_id, jurisdiction_id, licence_id),
        )
        digest = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars
        snapshot_id = f"{source_id}:sha256:{digest}"
        cur.execute(
            "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size, "
            "request, http_status, fetched_at, licence_observed_id) "
            "VALUES (%s, %s, 's3://test/fixture', %s, 'application/json', 1, '{}'::jsonb, 200, "
            "now(), %s) ON CONFLICT (id) DO NOTHING",
            (snapshot_id, source_id, digest, licence_id),
        )
        cur.execute(
            "INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description) "
            "VALUES (%s, 'Test', 'public_record', 'string', 'parcel', 'test fixture') "
            "ON CONFLICT (field_key) DO NOTHING",
            (field_key,),
        )
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (jurisdiction_id, apn),
        )
        parcel_id = cur.fetchone()[0]
        now_ts = datetime.datetime.now(datetime.timezone.utc)
        cur.execute(
            "INSERT INTO fact (parcel_id, jurisdiction_id, field_key, value, method, "
            "source_id, snapshot_id, retrieved_at, source_url, licence_id, confidence, "
            "confidence_rule_id, effective_from, pack_version) "
            "VALUES (%s, %s, %s, '\"x\"'::jsonb, 'bulk', %s, %s, %s, 'https://example.com', "
            "%s, 'high', 'test.rule', %s, 'v1.0')",
            (parcel_id, jurisdiction_id, field_key, source_id, snapshot_id, now_ts, licence_id, now_ts),
        )
    conn.commit()
    return jurisdiction_id, parcel_id


def _refusal_codes(conn, property_file_id):
    with conn.cursor() as cur:
        cur.execute("SELECT refusals, election FROM property_file WHERE id = %s", (property_file_id,))
        refusals, election = cur.fetchone()
    return [r["code"] for r in refusals], election


def test_election_none_refuses_election_required_no_rule_query():
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    _jid, parcel_id = _seed(conn, f"{suffix}_none")

    pf_id = cpf.compose(conn, parcel_id, "paid_property_file", election=None)
    codes, election = _refusal_codes(conn, pf_id)

    check("election=None: ELECTION_REQUIRED present", "ELECTION_REQUIRED" in codes, f"got {codes}")
    check("election=None: RULE_UNAVAILABLE absent (no query ever attempted)",
          "RULE_UNAVAILABLE" not in codes, f"got {codes}")
    check("election=None: ELECTION_NOT_SUPPORTED absent", "ELECTION_NOT_SUPPORTED" not in codes, f"got {codes}")
    check("election=None: property_file.election is NULL", election is None, f"got {election!r}")

    conn.close()


def test_election_state_refuses_election_not_supported_no_rule_query():
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    _jid, parcel_id = _seed(conn, f"{suffix}_state")

    pf_id = cpf.compose(conn, parcel_id, "paid_property_file", election="state")
    codes, election = _refusal_codes(conn, pf_id)

    check("election='state': ELECTION_NOT_SUPPORTED present", "ELECTION_NOT_SUPPORTED" in codes, f"got {codes}")
    check("election='state': RULE_UNAVAILABLE absent (no query ever attempted -- no dict entry to look up)",
          "RULE_UNAVAILABLE" not in codes, f"got {codes}")
    check("election='state': ELECTION_REQUIRED absent", "ELECTION_REQUIRED" not in codes, f"got {codes}")
    check("election='state': property_file.election echoes the supplied value",
          election == "state", f"got {election!r}")

    conn.close()


def test_election_city_reaches_a_real_rule_query_and_refuses_rule_unavailable():
    """The one case that must NOT short-circuit: election="city" resolves
    a real rule_key (CONCLUSION_RULE_KEYS has this exact entry) and this
    synthetic test jurisdiction genuinely has no `rule` row at all -- so
    select_effective_rule() runs for real and correctly refuses
    RULE_UNAVAILABLE, not ELECTION_NOT_SUPPORTED. Proves the three codes
    are reached by three different code paths, not one path with three
    labels."""
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    _jid, parcel_id = _seed(conn, f"{suffix}_city")

    pf_id = cpf.compose(conn, parcel_id, "paid_property_file", election="city")
    codes, election = _refusal_codes(conn, pf_id)

    check("election='city', no seeded rule: RULE_UNAVAILABLE present", "RULE_UNAVAILABLE" in codes, f"got {codes}")
    check("election='city': ELECTION_REQUIRED absent", "ELECTION_REQUIRED" not in codes, f"got {codes}")
    check("election='city': ELECTION_NOT_SUPPORTED absent (a rule_key WAS known)",
          "ELECTION_NOT_SUPPORTED" not in codes, f"got {codes}")
    check("election='city': property_file.election echoes the supplied value",
          election == "city", f"got {election!r}")

    conn.close()


def test_invalid_election_value_raises_immediately():
    """KNOWN_ELECTIONS validation (compose_property_file.py) -- a caller/
    programmer error, not a customer-facing refusal; must raise before
    ever reaching the database, not surface as a 500 from the
    property_file_election_known CHECK (0052)."""
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    _jid, parcel_id = _seed(conn, f"{suffix}_invalid")

    raised = False
    try:
        cpf.compose(conn, parcel_id, "paid_property_file", election="county")
    except ValueError as e:
        raised = True
        check("invalid election: ValueError names the bad value", "county" in str(e), str(e))
    check("invalid election ('county'): raises ValueError", raised)

    conn.close()


if __name__ == "__main__":
    test_election_none_refuses_election_required_no_rule_query()
    test_election_state_refuses_election_not_supported_no_rule_query()
    test_election_city_reaches_a_real_rule_query_and_refuses_rule_unavailable()
    test_invalid_election_value_raises_immediately()
    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)
