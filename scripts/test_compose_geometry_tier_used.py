#!/usr/bin/env python3
"""Invariant test for property_file.geometry_tier_used (P25).

Invariant under test: geometry_tier_used must reflect the composing
jurisdiction's REAL geometry_tier_enabled column, not a hardcoded
literal. The historical bug (compose_property_file.py hardcoded
geometry_tier_used=false unconditionally) was invisible because every
real jurisdiction also defaults geometry_tier_enabled=false -- the
identical "coincidence masks the bug until one side moves" shape README
finding #22 (P11, permits.active vs None) already hit once.

The geometry_tier_enabled=False case alone can never prove this fix: it
is indistinguishable from the old, hardcoded-false bug by observation
alone (both write false). This test also exercises the True case --
which core/calc's own evaluate_geometry_dependent_conclusion()
deliberately raises NotImplementedError for (P25: no real geometry
computation exists yet, see that module's own docstring) -- by stubbing
that one function out for THIS test only. This isolates "does compose()
correctly read and pass through jurisdiction.geometry_tier_enabled" from
"does core/calc correctly handle geometry_tier_enabled=True", which is
its own, separate coverage (tests/core/test_calc.py).

RED proof (this bug being real) is not re-run every time this file runs
-- see prompts/P25-geometry-disabled-base-core.md for the transcript:
pre-fix code, run against a real jurisdiction with geometry_tier_enabled
flipped to true, produced geometry_tier_used=false in the written row.
This file tests only the fixed, current behavior going forward.

Runs against a real database -- writes permanent rows (property_file
carries no immutability trigger, but this is still a real write, not a
mock). Fresh, uniquely-suffixed test.* jurisdiction/licence/source/
field/parcel ids per run so repeated runs never collide.
"""
import datetime
import os
import sys
import uuid
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import compose_property_file as cpf  # noqa: E402 -- module under test
from core.model import Result  # noqa: E402
from infra.env import get_db  # noqa: E402

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def _seed(conn, suffix, geometry_tier_enabled):
    jurisdiction_id = f"test_p25_geom_{suffix}"
    licence_id = f"test.p25_geom_licence_{suffix}"
    source_id = f"test.p25_geom_source_{suffix}"
    field_key = f"test.p25_geom_field_{suffix}"
    apn = f"TEST-P25-GEOM-{suffix}"

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, "
            "supported, geometry_tier_enabled) "
            "VALUES (%s, 'Test', 'city', 'CA', 'v1.0', true, %s) ON CONFLICT (id) DO NOTHING",
            (jurisdiction_id, geometry_tier_enabled),
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
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW current_fact")
    conn.commit()
    return parcel_id


def test_geometry_tier_used_reflects_the_real_column():
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]

    parcel_id_true = _seed(conn, f"{suffix}_true", True)
    parcel_id_false = _seed(conn, f"{suffix}_false", False)

    # Stubbed for this test ONLY -- Result.ok(None) is itself invalid
    # (core/model.Result's own __init__ guard: exactly one of
    # value/refusal, never neither), so a non-None sentinel stands in.
    # Never inspected by compose_property_file.py beyond .is_refused.
    with mock.patch.object(cpf, "evaluate_geometry_dependent_conclusion", return_value=Result.ok("stub")):
        result_true = cpf.compose(conn, parcel_id_true, "paid_property_file")
        result_false = cpf.compose(conn, parcel_id_false, "paid_property_file")

    # P38, README finding #41: compose() returns Result[T] uniformly --
    # unwrapped explicitly (fail LOUDLY on the wrong shape, not with
    # check()'s own soft record-and-continue -- a bad value here must
    # not flow into the SQL query below). Both parcels are real (freshly
    # seeded above) and STANDING-BLOCKER.md's own rights posture
    # guarantees at least one refusal (RIGHTS_BLOCKED), so both calls
    # always write a real row.
    assert result_true.is_ok and result_true.value is not cpf.NOTHING_COMPOSED, \
        f"expected a written row, got {result_true}"
    assert result_false.is_ok and result_false.value is not cpf.NOTHING_COMPOSED, \
        f"expected a written row, got {result_false}"
    pf_id_true = result_true.value
    pf_id_false = result_false.value

    with conn.cursor() as cur:
        cur.execute("SELECT geometry_tier_used FROM property_file WHERE id = %s", (pf_id_true,))
        used_true = cur.fetchone()[0]
        cur.execute("SELECT geometry_tier_used FROM property_file WHERE id = %s", (pf_id_false,))
        used_false = cur.fetchone()[0]

    check("geometry_tier_enabled=True jurisdiction writes property_file.geometry_tier_used=True",
          used_true is True, f"got {used_true}")
    check("geometry_tier_enabled=False jurisdiction writes property_file.geometry_tier_used=False",
          used_false is False, f"got {used_false}")

    conn.close()


if __name__ == "__main__":
    test_geometry_tier_used_reflects_the_real_column()
    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)
