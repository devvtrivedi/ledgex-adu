"""P31: core/rules.select_effective_rule() -- L5, refuse-first.

Requires a real, schema-migrated DATABASE_URL -- same reason every other
real-database test in tests/core/ does (no pytest-postgresql). Uses its
own synthetic test_* jurisdiction/rule_key, never ca_san_jose or any real
rule content -- this file proves the SELECTION mechanism, not this
package's own one real seeded rule (see prompts/P31-l5-refuse-first-one-
real-rule.md section 3 for that proof, against the real row, on a real
database, not here).
"""
import datetime
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.rules import select_effective_rule  # noqa: E402
from infra.env import get_db  # noqa: E402

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="requires a real, schema-migrated DATABASE_URL -- see this file's own module docstring",
)

JURISDICTION_ID = "test_jurisdiction_p31_l5"


def _seed_jurisdiction(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES (%s, 'P31 L5 test fixture', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """,
            (JURISDICTION_ID,),
        )
    conn.commit()


def test_effective_rule_found_unpacks_every_column_correctly():
    """B8 (P59C): the success path (a real match, Result.ok(Rule(...)))
    was tested by nothing -- a transposition between two adjacent
    same-typed columns in the SELECT/unpack (citation and pack_version,
    both free strings) would ship green. Every field distinguishable
    (citation and pack_version deliberately different literal strings, not
    both 'v1.0'-shaped) so a swap is caught, not accidentally masked by
    two fields sharing a value."""
    conn = get_db()
    _seed_jurisdiction(conn)
    rule_key = "test.p31.b8_transposition_check"
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rule (
                    id, jurisdiction_id, rule_key, version, effective_from, effective_to,
                    citation, source_text_uri, params, pack_version,
                    authored_by, reviewed_by, review_mode, reviewed_at, attestation_uri
                ) VALUES (
                    'test.p31.b8_rule_v1', %s, %s, 1, '2020-01-01', NULL,
                    'Municipal Code 20.80.175 (B8 citation, NOT a pack version)',
                    'https://example.com/b8-source', '{}'::jsonb, 'b8-pack-version-v9.9',
                    'p59c-test', 'p59c-test', 'solo_founder_attestation', now(),
                    'https://example.com/b8-attestation'
                )
                ON CONFLICT (id) DO NOTHING
                """,
                (JURISDICTION_ID, rule_key),
            )
        conn.commit()

        with conn.cursor() as cur:
            result = select_effective_rule(cur, JURISDICTION_ID, rule_key, datetime.date(2026, 1, 1))

        assert result.is_ok, f"expected a match, got a refusal: {result.refusal if not result.is_ok else None}"
        rule = result.value
        assert rule.id == "test.p31.b8_rule_v1"
        assert rule.jurisdiction_id == JURISDICTION_ID
        assert rule.rule_key == rule_key
        assert rule.version == 1
        assert rule.citation == "Municipal Code 20.80.175 (B8 citation, NOT a pack version)"
        assert rule.pack_version == "b8-pack-version-v9.9"
        assert rule.effective_from == datetime.date(2020, 1, 1)
        assert rule.effective_to is None
    finally:
        conn.close()


def test_no_rule_effective_refuses_by_name():
    """The whole point of building this refuse-first: a jurisdiction_id/
    rule_key with zero matching rows anywhere in the table must refuse
    RULE_UNAVAILABLE by name, not raise, not silently return None, not
    fetchone() an arbitrary unrelated row."""
    conn = get_db()
    _seed_jurisdiction(conn)
    try:
        with conn.cursor() as cur:
            result = select_effective_rule(
                cur, JURISDICTION_ID, "test.p31.no_such_rule_key", datetime.date(2026, 1, 1)
            )
        assert result.is_refused, "expected a refusal, got a value"
        assert result.refusal.code == "RULE_UNAVAILABLE"
        assert result.refusal.stage == "L5"
        assert JURISDICTION_ID in result.refusal.message
        assert "test.p31.no_such_rule_key" in result.refusal.message
    finally:
        conn.close()
