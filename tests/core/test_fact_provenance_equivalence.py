"""P21, design decision (b): core/model.py's own docstring explains why
Fact's provenance validator and fact_provenance_complete (0006, I2)
cannot be one shared Python object -- SQL cannot import Python. This is
the test that keeps them from drifting apart silently anyway: every
(method, source_id-present, snapshot_id-present, retrieved_at-present,
source_url-present, method_version-present) combination is run through
BOTH core/model.py's Fact validator AND a real INSERT against the real,
currently-migrated fact table, and the two are asserted to agree on
every single one.

Requires a real, schema-migrated DATABASE_URL (the real fact table, real
FKs) -- pytest-postgresql's own bare-provisioned instance cannot run
this: it uses the local system Postgres binary, which does not have
PostGIS installed (confirmed directly, not assumed, during this same
package's own work -- an earlier session in this same environment hit
"extension postgis is not available" against that exact binary), and
the real fact table's own migration chain depends on PostGIS being
present from parcel.geom onward. Same DATABASE_URL-based real-schema
pattern every other test in this repository already uses (scripts/
test_*_invariant.py) -- not a new convention.

Every field NOT under test (parcel_id, jurisdiction_id, field_key,
value, licence_id, confidence, confidence_rule_id, pack_version,
effective_from) is held to a single, always-valid value across every
combination, so any INSERT rejection is attributable ONLY to
fact_provenance_complete, never an incidental FK/NOT NULL mismatch on an
unrelated column.
"""
import datetime
import itertools
import os
import sys
from pathlib import Path

import psycopg2
import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.model import Fact  # noqa: E402
from infra.env import get_db  # noqa: E402

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="requires a real, schema-migrated DATABASE_URL -- see this file's own module docstring",
)

JURISDICTION_ID = "test_jurisdiction_p21"
LICENCE_ID = "test.p21_licence"
PARCEL_APN = "TEST-P21-PROVENANCE"

# One source+snapshot pair PER METHOD, so fact_source_method_fk /
# fact_snapshot_source_fk are always satisfiable whenever a combination
# under test wants source_id/snapshot_id present, for whichever method
# that combination is testing.
SOURCES = {
    "direct": "test.p21_source_direct",
    "bulk": "test.p21_source_bulk",
    "derived": "test.p21_source_derived",
}


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
        for method, source_id in SOURCES.items():
            cur.execute(
                """
                INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status,
                                     phase_status_reason, endpoint_url, licence_id, active)
                VALUES (%s, %s, 'Test Source', 'Test', %s, 'active', 'test fixture',
                        'https://example.com', %s, false)
                ON CONFLICT (id) DO NOTHING
                """,
                (source_id, JURISDICTION_ID, method, LICENCE_ID),
            )
            digest = ("0" if method == "direct" else "1" if method == "bulk" else "2") * 64
            snapshot_id = f"{source_id}:sha256:{digest}"
            cur.execute(
                """
                INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size,
                                       request, http_status, fetched_at, licence_observed_id)
                VALUES (%s, %s, 's3://test/fixture', %s, 'application/json', 1,
                        '{}'::jsonb, 200, now(), %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (snapshot_id, source_id, digest, LICENCE_ID),
            )
        cur.execute(
            """
            INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description)
            VALUES ('test.p21_field', 'Test', 'public_record', 'string', 'parcel', 'test fixture')
            ON CONFLICT (field_key) DO NOTHING
            """
        )
    conn.commit()


def _fresh_parcel(conn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (JURISDICTION_ID, PARCEL_APN),
        )
        parcel_id = cur.fetchone()[0]
    conn.commit()
    return parcel_id


def _snapshot_id_for(method):
    source_id = SOURCES[method]
    digest = ("0" if method == "direct" else "1" if method == "bulk" else "2") * 64
    return f"{source_id}:sha256:{digest}"


NOW = datetime.datetime.now(datetime.timezone.utc)


def _combination_kwargs(method, has_source_id, has_snapshot_id, has_retrieved_at, has_source_url, has_method_version, parcel_id):
    kwargs = dict(
        parcel_id=parcel_id,
        jurisdiction_id=JURISDICTION_ID,
        field_key="test.p21_field",
        value="v",
        method=method,
        licence_id=LICENCE_ID,
        confidence="high",
        confidence_rule_id="rule_1",
        pack_version="v1.0",
        effective_from=NOW,
    )
    kwargs["source_id"] = SOURCES[method] if has_source_id else None
    kwargs["snapshot_id"] = _snapshot_id_for(method) if has_snapshot_id else None
    kwargs["retrieved_at"] = NOW if has_retrieved_at else None
    kwargs["source_url"] = "https://example.com" if has_source_url else None
    kwargs["method_version"] = "v1" if has_method_version else None
    return kwargs


def _pydantic_accepts(kwargs):
    try:
        Fact(**kwargs)
        return True
    except ValidationError:
        return False


def _db_accepts(conn, parcel_id, kwargs):
    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO fact (
                    parcel_id, jurisdiction_id, field_key, value, method,
                    source_id, snapshot_id, retrieved_at, source_url,
                    licence_id, confidence, confidence_rule_id, effective_from, pack_version,
                    method_version
                ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    parcel_id, JURISDICTION_ID, "test.p21_field", '"v"', kwargs["method"],
                    kwargs["source_id"], kwargs["snapshot_id"], kwargs["retrieved_at"], kwargs["source_url"],
                    LICENCE_ID, "high", "rule_1", NOW, "v1.0", kwargs["method_version"],
                ),
            )
        except psycopg2.errors.CheckViolation as e:
            conn.rollback()
            if e.diag.constraint_name != "fact_provenance_complete":
                raise AssertionError(
                    f"rejected by an unexpected constraint {e.diag.constraint_name!r}, "
                    f"not fact_provenance_complete -- test fixture is not isolating the "
                    f"right constraint"
                ) from e
            return False
        else:
            conn.commit()
            return True


COMBINATIONS = list(itertools.product(
    ("direct", "bulk", "derived"),  # method
    (True, False),  # has_source_id
    (True, False),  # has_snapshot_id
    (True, False),  # has_retrieved_at
    (True, False),  # has_source_url
    (True, False),  # has_method_version
))


@pytest.fixture(scope="module")
def db_conn():
    conn = get_db()
    _seed(conn)
    yield conn
    conn.close()


@pytest.mark.parametrize(
    "method,has_source_id,has_snapshot_id,has_retrieved_at,has_source_url,has_method_version",
    COMBINATIONS,
    ids=[
        f"{m}-sid={a}-snap={b}-ret={c}-url={d}-mv={e}"
        for m, a, b, c, d, e in COMBINATIONS
    ],
)
def test_pydantic_and_db_agree(
    db_conn, method, has_source_id, has_snapshot_id, has_retrieved_at, has_source_url, has_method_version
):
    parcel_id = _fresh_parcel(db_conn)
    kwargs = _combination_kwargs(
        method, has_source_id, has_snapshot_id, has_retrieved_at, has_source_url, has_method_version, parcel_id
    )
    pydantic_result = _pydantic_accepts(kwargs)
    db_result = _db_accepts(db_conn, parcel_id, kwargs)
    assert pydantic_result == db_result, (
        f"DISAGREEMENT for method={method} source_id={has_source_id} "
        f"snapshot_id={has_snapshot_id} retrieved_at={has_retrieved_at} "
        f"source_url={has_source_url} method_version={has_method_version}: "
        f"Pydantic {'accepted' if pydantic_result else 'rejected'}, "
        f"database {'accepted' if db_result else 'rejected'}"
    )
