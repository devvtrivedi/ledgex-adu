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
