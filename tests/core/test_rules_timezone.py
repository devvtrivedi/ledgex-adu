"""C7 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): core.rules.select_effective_rule
compares a `date` column (rule.effective_from/effective_to) against a
`timestamptz` as_of -- Postgres promotes the date at SESSION-LOCAL
midnight, so the comparison's answer depends on the connecting session's
timezone unless something pins it. infra.env.get_db() now pins every
connection to UTC via the startup `options` parameter (not a `SET TIME
ZONE` statement, which a later rollback would silently undo).

What this proves, precisely: (1) get_db()'s own connection is ALWAYS
session timezone UTC, regardless of what an unpinned connection's session
default happens to be -- the actual real-world attack surface is
different developer machines / CI runners with different Postgres client
or server default TimeZone configuration (PGTZ, postgresql.conf, locale),
not application code calling SET TIME ZONE mid-transaction. (2) the SAME
rule row and the SAME as_of instant, compared through get_db()'s pinned
connection, gives the SAME (UTC-canonical) answer every time -- proven by
contrasting it against a deliberately-unpinned connection whose session
default is forced to America/Los_Angeles immediately after connecting
(simulating what an unpinned connection on a Pacific-configured
environment would naturally see as ITS OWN session default, the real
vulnerability class), which gives the OPPOSITE, wrong answer at this
exact boundary -- confirming the fixture genuinely exercises the
timezone-sensitive date-promotion mechanism, not a fixture that would
pass regardless.

Requires a real, schema-migrated DATABASE_URL, same as
tests/core/test_rules.py.
"""
import datetime
import os
import sys
from pathlib import Path

import psycopg2
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.rules import select_effective_rule  # noqa: E402
from infra.env import env, get_db  # noqa: E402

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="requires a real, schema-migrated DATABASE_URL -- see this file's own module docstring",
)

JURISDICTION_ID = "test_jurisdiction_p59_c7"
RULE_KEY = "test.p59.c7.timezone_boundary"

# A rule effective for exactly one day: 2026-06-15. BOUNDARY_AS_OF
# (2026-06-16 03:00 UTC) is 2026-06-15 20:00 in America/Los_Angeles (UTC-7
# in June, DST) -- so whether this row is "effective" at that instant
# depends entirely on which calendar day the comparing session's own
# timezone thinks it currently is when the `date` column is promoted.
BOUNDARY_AS_OF = datetime.datetime(2026, 6, 16, 3, 0, 0, tzinfo=datetime.timezone.utc)


def _seed(conn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported) "
            "VALUES (%s, 'P59 C7 test fixture', 'city', 'CA', 'v1.0', true) "
            "ON CONFLICT (id) DO NOTHING",
            (JURISDICTION_ID,),
        )
        cur.execute(
            "INSERT INTO rule (id, jurisdiction_id, rule_key, version, effective_from, effective_to, "
            "citation, source_text_uri, params, pack_version, authored_by, reviewed_by, "
            "review_mode, reviewed_at, attestation_uri) "
            "VALUES (%s, %s, %s, 1, '2026-06-15', '2026-06-16', "
            "'test fixture citation', 'https://example.invalid/p59-c7', '{}'::jsonb, 'v1.0', "
            "'test_p59_c7', 'test_p59_c7', 'solo_founder_attestation', now(), "
            "'https://example.invalid/p59-c7') "
            "ON CONFLICT (jurisdiction_id, rule_key, version) DO NOTHING",
            (f"{JURISDICTION_ID}.{RULE_KEY}.v1", JURISDICTION_ID, RULE_KEY),
        )
    conn.commit()


def test_get_db_connection_is_always_utc():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW timezone")
            tz = cur.fetchone()[0]
    finally:
        conn.close()
    assert tz == "UTC", f"get_db()'s own connection is not pinned to UTC -- got {tz!r}"


def test_rule_effectivity_stable_via_get_db_but_sensitive_via_unpinned_connection():
    seed_conn = get_db()
    _seed(seed_conn)
    seed_conn.close()

    # Pinned (the fix): get_db()'s own connection, unconditionally UTC.
    pinned_conn = get_db()
    try:
        with pinned_conn.cursor() as cur:
            pinned_result = select_effective_rule(cur, JURISDICTION_ID, RULE_KEY, BOUNDARY_AS_OF)
    finally:
        pinned_conn.close()

    # Unpinned: a bare psycopg2.connect() (bypassing get_db() entirely,
    # the same shape check_golden.py/smoke_real.py/migrate.py already use
    # for their own separate reasons), with its session default forced to
    # America/Los_Angeles immediately after connecting -- representing
    # what an unpinned connection's OWN session default would be on a
    # Pacific-configured environment, not a mid-transaction override.
    unpinned_conn = psycopg2.connect(env("DATABASE_URL"))
    try:
        with unpinned_conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'America/Los_Angeles'")
            unpinned_result = select_effective_rule(cur, JURISDICTION_ID, RULE_KEY, BOUNDARY_AS_OF)
    finally:
        unpinned_conn.close()

    assert pinned_result.is_ok is False, (
        f"fixture check: expected the UTC-pinned answer to be 'not effective' at this "
        f"boundary -- got {pinned_result}"
    )
    assert unpinned_result.is_ok is True, (
        f"fixture check: expected the Pacific-timezone answer to DISAGREE (be "
        f"'effective') at this exact boundary -- got {unpinned_result}. If this is not "
        f"True, the fixture does not exercise the timezone-sensitive mechanism at all."
    )
    assert pinned_result.is_ok != unpinned_result.is_ok, (
        "C7 regression: get_db()'s pinned connection and an unpinned connection's own "
        "session default now agree -- either the boundary fixture stopped exercising "
        "the mechanism, or get_db()'s pin silently stopped mattering."
    )
