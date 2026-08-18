"""P22: the transposition hazard core/model.Fact's adoption exists to
close, and a precise accounting of what "wrong order is now
unrepresentable" does and does not mean. See core/model.py's own module
docstring, design decision (c)'s closing section, for the full argument
this file proves rather than asserts.

Requires a real, schema-migrated DATABASE_URL -- same reason
test_fact_provenance_equivalence.py does (PostGIS, no pytest-postgresql).
NEVER run this against ledgex_schema_check or any database whose rows
matter: the first two tests below write permanent, deliberately-wrong
fact rows on purpose (0017, fact_no_delete) to prove a real hazard, not
a hypothetical one. make test's own TEST_DATABASE_URL default
(ledgex_test) is disposable by design (P18/P21) -- this file relies on
that convention, same as every other test in tests/core/, not on a
second guard of its own.
"""
import datetime
import os
import sys
import uuid
from pathlib import Path

import psycopg2.extras
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.model import Fact  # noqa: E402
from core.store import FACT_COLUMNS, FACT_TEMPLATE, insert_facts  # noqa: E402
from infra.env import get_db  # noqa: E402

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="requires a real, schema-migrated DATABASE_URL -- see this file's own module docstring",
)

JURISDICTION_ID = "test_jurisdiction_p22_hazard"
LICENCE_ID = "test.p22_hazard_licence"
SOURCE_ID = "test.p22_hazard_source"
FIELD_KEY = "test.p22_hazard_field"


def _seed(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, observed_at, cleared_by, cleared_at)
            VALUES (%s, 'Test', 'open', 'allowed', 'allowed', NULL, now(), 'test', now())
            ON CONFLICT (id) DO NOTHING
            """,
            (LICENCE_ID,),
        )
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES (%s, 'Test Jurisdiction', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """,
            (JURISDICTION_ID,),
        )
        cur.execute(
            """
            INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status,
                                 phase_status_reason, endpoint_url, licence_id, active)
            VALUES (%s, %s, 'Test Source', 'Test', 'bulk', 'active', 'test fixture',
                    'https://example.com', %s, false)
            ON CONFLICT (id) DO NOTHING
            """,
            (SOURCE_ID, JURISDICTION_ID, LICENCE_ID),
        )
        digest = "4" * 64
        snapshot_id = f"{SOURCE_ID}:sha256:{digest}"
        cur.execute(
            """
            INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size,
                                   request, http_status, fetched_at, licence_observed_id)
            VALUES (%s, %s, 's3://test/fixture', %s, 'application/json', 1,
                    '{}'::jsonb, 200, now(), %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (snapshot_id, SOURCE_ID, digest, LICENCE_ID),
        )
        cur.execute(
            """
            INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description)
            VALUES (%s, 'Test', 'public_record', 'string', 'parcel', 'test fixture')
            ON CONFLICT (field_key) DO NOTHING
            """,
            (FIELD_KEY,),
        )
    conn.commit()
    return snapshot_id


def _fresh_parcel(conn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (JURISDICTION_ID, f"TEST-P22-HAZARD-{uuid.uuid4().hex[:8]}"),
        )
        parcel_id = cur.fetchone()[0]
    conn.commit()
    return parcel_id


def _fact_kwargs(parcel_id, snapshot_id, confidence_rule_id, pack_version):
    now = datetime.datetime.now(datetime.timezone.utc)
    return dict(
        parcel_id=parcel_id,
        jurisdiction_id=JURISDICTION_ID,
        field_key=FIELD_KEY,
        value='"x"',
        method="bulk",
        source_id=SOURCE_ID,
        snapshot_id=snapshot_id,
        retrieved_at=now,
        source_url="https://example.com",
        licence_id=LICENCE_ID,
        confidence="high",
        confidence_rule_id=confidence_rule_id,
        effective_from=now,
        pack_version=pack_version,
    )


@pytest.fixture(scope="module")
def db_conn():
    conn = get_db()
    snapshot_id = _seed(conn)
    yield conn, snapshot_id
    conn.close()


def test_historical_hazard_reproduced_on_a_bare_tuple(db_conn):
    """RED, reproduced fresh here, not cited from memory: a hand-built
    positional 17-tuple with confidence_rule_id (FACT_COLUMNS position
    12) and pack_version (position 14) swapped inserts CLEANLY --
    0006_fact.sql: both are `text NOT NULL` with no CHECK on either.
    This is the pre-adoption hazard, proven real by reproducing it, not
    the post-adoption behavior -- built with the raw SQL insert_facts()
    used to accept directly (execute_values + FACT_TEMPLATE), because
    insert_facts() itself now refuses a bare tuple outright (see the
    next test) and can no longer be used to reproduce this."""
    conn, snapshot_id = db_conn
    parcel_id = _fresh_parcel(conn)
    now = datetime.datetime.now(datetime.timezone.utc)
    real_rule_id = "test.p22_the_real_rule"
    real_pack_version = "v1.2.3-real"
    bad_row = (
        str(parcel_id), JURISDICTION_ID, FIELD_KEY, '"x"', "bulk",
        SOURCE_ID, snapshot_id, now, "https://example.com",
        LICENCE_ID, "high", real_pack_version,  # position 12 (confidence_rule_id) <- WRONG
        now, real_rule_id, None, None, None,    # position 14 (pack_version) <- WRONG
    )
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur, f"INSERT INTO fact ({FACT_COLUMNS}) VALUES %s", [bad_row],
            template=FACT_TEMPLATE, page_size=1,
        )
    conn.commit()  # PERMANENT by design -- 0017 forbids deleting this row; that IS the hazard.

    with conn.cursor() as cur:
        cur.execute(
            "SELECT confidence_rule_id, pack_version FROM fact "
            "WHERE parcel_id = %s AND field_key = %s",
            (parcel_id, FIELD_KEY),
        )
        stored_rule_id, stored_pack_version = cur.fetchone()

    assert stored_rule_id == real_pack_version, "the swap did not reproduce as predicted"
    assert stored_pack_version == real_rule_id, "the swap did not reproduce as predicted"


def test_insert_facts_refuses_a_bare_tuple(db_conn):
    """The mechanical half of what adoption actually prevents: the
    exact tuple shape the test above used -- and every append site used
    to hand-build -- can no longer reach the database via insert_facts()
    at all. A clear TypeError naming the function and the wrong type,
    not a silent duck-typed pass-through, and not an INSERT-time
    Postgres error naming a position."""
    conn, snapshot_id = db_conn
    parcel_id = _fresh_parcel(conn)
    now = datetime.datetime.now(datetime.timezone.utc)
    bad_row = (
        str(parcel_id), JURISDICTION_ID, FIELD_KEY, '"x"', "bulk",
        SOURCE_ID, snapshot_id, now, "https://example.com",
        LICENCE_ID, "high", "whatever", now, "whatever", None, None, None,
    )
    with conn.cursor() as cur:
        with pytest.raises(TypeError, match="requires core.model.Fact instances"):
            insert_facts(cur, [bad_row])
    conn.rollback()


def test_insert_facts_accepts_a_correctly_named_fact(db_conn):
    """The ordinary, correct case still works end to end through the
    adopted insert_facts()."""
    conn, snapshot_id = db_conn
    parcel_id = _fresh_parcel(conn)
    real_rule_id = "test.p22_correct_rule"
    real_pack_version = "v2.0.0-correct"
    f = Fact(**_fact_kwargs(parcel_id, snapshot_id, real_rule_id, real_pack_version))
    with conn.cursor() as cur:
        insert_facts(cur, [f])
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT confidence_rule_id, pack_version FROM fact "
            "WHERE parcel_id = %s AND field_key = %s",
            (parcel_id, FIELD_KEY),
        )
        row = cur.fetchone()
    assert row == (real_rule_id, real_pack_version)


def test_a_swapped_value_between_two_named_fields_is_not_caught(db_conn):
    """States plainly what adoption does NOT prevent, per this
    package's own instruction -- proven, not just written in a
    docstring. Fact(confidence_rule_id=<pack_version's real value>,
    pack_version=<confidence_rule_id's real value>) is exactly as valid
    to Pydantic as the correct call: both are ordinary non-empty
    strings, and nothing in either field's type distinguishes what the
    string MEANS. This is not a residual gap in this package's fix --
    no type system without semantic tagging can catch it, and this test
    exists so no future reader mistakes "wrong order is now
    unrepresentable" for "wrong values are now impossible" (see
    core/model.py's own docstring, design decision (c), closing
    section, for the argument this test is the proof of)."""
    conn, snapshot_id = db_conn
    parcel_id = _fresh_parcel(conn)
    real_rule_id = "test.p22_swap_rule"
    real_pack_version = "v3.0.0-swap"
    # Deliberately swapped VALUES, correctly NAMED kwargs -- the whole point.
    f = Fact(**_fact_kwargs(parcel_id, snapshot_id, real_pack_version, real_rule_id))
    with conn.cursor() as cur:
        insert_facts(cur, [f])  # does NOT raise -- that is the point being proven
    conn.commit()  # PERMANENT by the same 0017 mechanism as the first test.

    with conn.cursor() as cur:
        cur.execute(
            "SELECT confidence_rule_id, pack_version FROM fact "
            "WHERE parcel_id = %s AND field_key = %s",
            (parcel_id, FIELD_KEY),
        )
        stored_rule_id, stored_pack_version = cur.fetchone()
    assert stored_rule_id == real_pack_version, "expected the swap to land exactly as given"
    assert stored_pack_version == real_rule_id, "expected the swap to land exactly as given"


def test_insert_facts_refuses_a_fact_with_an_unwritten_field_set(db_conn):
    """core/store.py's own docstring: Fact models 29 fields, insert_facts()
    writes 17. A Fact carrying a value in one of the other nine must be
    refused, not silently dropped -- a model claiming to hold a value
    insert_facts() never persists would be a worse failure than the
    transposition this package fixes. No new tuple/INSERT reaches the
    database at all in this case."""
    conn, snapshot_id = db_conn
    parcel_id = _fresh_parcel(conn)
    f = Fact(**_fact_kwargs(parcel_id, snapshot_id, "test.p22_unwritten_rule", "v4.0.0-unwritten"))
    f = f.model_copy(update={"method_version": "v2"})
    with conn.cursor() as cur:
        with pytest.raises(ValueError, match="method_version.*does not write that column"):
            insert_facts(cur, [f])
    conn.rollback()
