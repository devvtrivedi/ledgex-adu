"""P24: the transposition hazard core/model.ParcelException's adoption
exists to close, and a precise accounting of what "wrong order is now
unrepresentable" does and does not mean -- same shape and same claim as
tests/core/test_fact_adoption_hazard.py (P22), proven independently
here, not assumed to transfer.

Requires a real, schema-migrated DATABASE_URL -- same reason every other
tests/core/ database test does (PostGIS, no pytest-postgresql). NEVER
run this against ledgex_schema_check or any database whose rows matter:
the first test below writes a permanent, deliberately-wrong
parcel_exception row on purpose. Unlike fact, parcel_exception carries
no whole-row immutability trigger (core/exceptions.py's own module
docstring) -- the row is not literally undeletable -- but this test
still treats it as a real database write, never against shared state.
make test's own TEST_DATABASE_URL default (ledgex_test) is disposable by
design (P18/P21), same as every other test in this directory.
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

from core.model import ParcelException  # noqa: E402
from core.exceptions import EXCEPTION_COLUMNS, EXCEPTION_TEMPLATE, insert_exceptions  # noqa: E402
from infra.env import get_db  # noqa: E402

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="requires a real, schema-migrated DATABASE_URL -- see this file's own module docstring",
)

JURISDICTION_ID = "test_jurisdiction_p24_hazard"
FIELD_KEY = "test.p24_hazard_field"


def _seed(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES (%s, 'Test Jurisdiction', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """,
            (JURISDICTION_ID,),
        )
    conn.commit()


def _fresh_parcel(conn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (JURISDICTION_ID, f"TEST-P24-HAZARD-{uuid.uuid4().hex[:8]}"),
        )
        parcel_id = cur.fetchone()[0]
    conn.commit()
    return parcel_id


def _exception_kwargs(parcel_id, detector_key, detector_version):
    return dict(
        parcel_id=parcel_id,
        jurisdiction_id=JURISDICTION_ID,
        type="coverage_gap",
        severity="info",
        detector_key=detector_key,
        detector_version=detector_version,
        detail={"reason": "test"},
    )


@pytest.fixture(scope="module")
def db_conn():
    conn = get_db()
    _seed(conn)
    yield conn
    conn.close()


def test_historical_hazard_reproduced_on_a_bare_tuple(db_conn):
    """RED, reproduced fresh here, not cited from memory: a hand-built
    positional 7-tuple with detector_key (EXCEPTION_COLUMNS position 5)
    and detector_version (position 6) swapped inserts CLEANLY --
    0010_exceptions.sql: both `text NOT NULL` with no CHECK on either.
    Built with the raw SQL insert_exceptions() used to accept directly
    (execute_values + EXCEPTION_TEMPLATE), because insert_exceptions()
    itself now refuses a bare tuple outright (see the next test)."""
    conn = db_conn
    parcel_id = _fresh_parcel(conn)
    real_key = "test.p24_the_real_detector_key"
    real_version = "3.1.4-real"
    bad_row = (
        str(parcel_id), JURISDICTION_ID, "coverage_gap", "info",
        real_version, real_key,  # SWAPPED: position 5 (detector_key) <- WRONG, position 6 (detector_version) <- WRONG
        '{"reason": "test"}',
    )
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur, f"INSERT INTO parcel_exception ({EXCEPTION_COLUMNS}) VALUES %s", [bad_row],
            template=EXCEPTION_TEMPLATE, page_size=1,
        )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT detector_key, detector_version FROM parcel_exception "
            "WHERE parcel_id = %s",
            (parcel_id,),
        )
        stored_key, stored_version = cur.fetchone()

    assert stored_key == real_version, "the swap did not reproduce as predicted"
    assert stored_version == real_key, "the swap did not reproduce as predicted"


def test_insert_exceptions_refuses_a_bare_tuple(db_conn):
    """The mechanical half of what adoption actually prevents: the
    exact tuple shape the test above used -- and every real call site
    used to hand-build -- can no longer reach the database via
    insert_exceptions() at all. A clear TypeError, not a silent
    duck-typed pass-through."""
    conn = db_conn
    parcel_id = _fresh_parcel(conn)
    bad_row = (
        str(parcel_id), JURISDICTION_ID, "coverage_gap", "info",
        "whatever", "whatever", '{"reason": "test"}',
    )
    with pytest.raises(TypeError, match="requires core.model.ParcelException instances"):
        with conn.cursor() as cur:
            insert_exceptions(cur, [bad_row])
    conn.rollback()


def test_insert_exceptions_accepts_a_correctly_named_exception(db_conn):
    """The ordinary, correct case works end to end through the adopted
    insert_exceptions()."""
    conn = db_conn
    parcel_id = _fresh_parcel(conn)
    real_key = "test.p24_correct_detector_key"
    real_version = "1.0.0-correct"
    pe = ParcelException(**_exception_kwargs(parcel_id, real_key, real_version))
    with conn.cursor() as cur:
        insert_exceptions(cur, [pe])
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT detector_key, detector_version FROM parcel_exception WHERE parcel_id = %s",
            (parcel_id,),
        )
        row = cur.fetchone()
    assert row == (real_key, real_version)


def test_a_swapped_value_between_two_named_fields_is_not_caught(db_conn):
    """States plainly what adoption does NOT prevent -- proven, not
    just written in a docstring. Same claim as P22's identical test for
    Fact: ParcelException(detector_key=<detector_version's real value>,
    detector_version=<detector_key's real value>) is exactly as valid
    to Pydantic as the correct call, since both are ordinary non-empty
    strings and nothing in either field's type distinguishes what the
    string MEANS."""
    conn = db_conn
    parcel_id = _fresh_parcel(conn)
    real_key = "test.p24_swap_detector_key"
    real_version = "2.0.0-swap"
    # Deliberately swapped VALUES, correctly NAMED kwargs -- the whole point.
    pe = ParcelException(**_exception_kwargs(parcel_id, real_version, real_key))
    with conn.cursor() as cur:
        insert_exceptions(cur, [pe])  # does NOT raise -- that is the point being proven
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT detector_key, detector_version FROM parcel_exception WHERE parcel_id = %s",
            (parcel_id,),
        )
        stored_key, stored_version = cur.fetchone()
    assert stored_key == real_version, "expected the swap to land exactly as given"
    assert stored_version == real_key, "expected the swap to land exactly as given"


def test_insert_exceptions_refuses_an_exception_with_an_unwritten_field_set(db_conn):
    """core/exceptions.py's own docstring: ParcelException models 15
    fields, insert_exceptions() writes 7. A ParcelException carrying a
    value in ruleset_version -- the one field this function does not
    write -- must be refused, not silently dropped."""
    conn = db_conn
    parcel_id = _fresh_parcel(conn)
    pe = ParcelException(**_exception_kwargs(parcel_id, "test.p24_unwritten", "1.0"))
    # C24.3 (P59, annex): same deliberate use as
    # test_fact_adoption_hazard.py's identical pattern -- ParcelException
    # is frozen, model_copy is the only way to produce a modified copy,
    # and it does not rerun model_validators. Proves insert_exceptions()'s
    # own _check_no_unwritten_fields is real defense-in-depth, not
    # redundant with ParcelException's own validation.
    pe = pe.model_copy(update={"ruleset_version": "v2"})
    with pytest.raises(ValueError, match="ruleset_version.*does not write that column"):
        with conn.cursor() as cur:
            insert_exceptions(cur, [pe])
    conn.rollback()
