#!/usr/bin/env python3
"""Invariant test for PARCEL_REFERENCE_UNKNOWN and PARCEL_NO_FACTS (P37,
README finding #40).

Re-grades two of finding #40's four members from "latent, pending api/" to
"live today": a caller-supplied parcel_id that does not resolve, and a
resolved parcel with zero current facts, are both deterministic runtime
conditions (I8) reachable by ANY caller of compose() today -- not merely a
future api/ -- and both used to crash the process with SystemExit instead
of returning a typed refusal.

RED proof (this bug being real) is not re-run every time this file runs --
see prompts/P37-parcel-refusal-codes.md section 2 for the transcript: the
pre-P37 compose(), run against a real database with a nonexistent
parcel_id and separately against a real parcel with zero facts, raised
SystemExit both times, confirmed directly, not assumed. This file tests
only the fixed, current behavior going forward.

Proves the two new codes are NOT the same fix reused: PARCEL_REFERENCE_
UNKNOWN returns a typed Result directly, with NO property_file row written
(parcel_id has no row to satisfy its own NOT NULL FK against) -- structurally
different from every other refusal this composer produces. PARCEL_NO_FACTS
writes a normal refused property_file row, accumulated with whatever else
this composer's other stages also refuse (P25), with zero property_file_fact
link rows (honestly: nothing was touched).

Runs against a real database -- writes permanent rows for the PARCEL_NO_FACTS
case (property_file carries no immutability trigger, but this is still a
real write, not a mock); writes nothing for the PARCEL_REFERENCE_UNKNOWN
case, which is exactly what it proves. Fresh, uniquely-suffixed test.*
jurisdiction/parcel ids per run so repeated runs never collide.
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


def _seed_jurisdiction(conn, suffix):
    jurisdiction_id = f"test_p37_parcel_{suffix}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, "
            "supported, geometry_tier_enabled) "
            "VALUES (%s, 'Test', 'city', 'CA', 'v1.0', true, false) ON CONFLICT (id) DO NOTHING",
            (jurisdiction_id,),
        )
    conn.commit()
    return jurisdiction_id


def test_nonexistent_parcel_id_refuses_parcel_reference_unknown_no_row():
    conn = get_db()
    fake_parcel_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM property_file")
        before = cur.fetchone()[0]

    # P38, README finding #41: compose() returns Result[T] uniformly now
    # -- isinstance(result, Result) is always true, so that check itself
    # is no longer the interesting assertion; is_refused is.
    result = cpf.compose(conn, fake_parcel_id, "paid_property_file", election="city")

    check("nonexistent parcel_id: Result.is_refused", result.is_refused, f"got {result}")
    if result.is_refused:
        check("nonexistent parcel_id: code is PARCEL_REFERENCE_UNKNOWN",
              result.refusal.code == "PARCEL_REFERENCE_UNKNOWN", f"got {result.refusal.code!r}")
        check("nonexistent parcel_id: stage is L0", result.refusal.stage == "L0",
              f"got {result.refusal.stage!r}")
        check("nonexistent parcel_id: message names the fabricated id",
              fake_parcel_id in result.refusal.message, result.refusal.message)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM property_file")
        after = cur.fetchone()[0]
    check("nonexistent parcel_id: no property_file row written", after == before,
          f"before={before} after={after}")

    conn.close()


def test_zero_facts_refuses_parcel_no_facts_real_row_zero_links():
    conn = get_db()
    suffix = uuid.uuid4().hex[:8]
    jurisdiction_id = _seed_jurisdiction(conn, suffix)

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (jurisdiction_id, f"TEST-P37-NOFACTS-{suffix}"),
        )
        parcel_id = cur.fetchone()[0]
    conn.commit()

    result = cpf.compose(conn, parcel_id, "paid_property_file", election="city")

    check("zero facts: Result.is_ok (a row was written, not refused before one could be)",
          result.is_ok, f"got {result}")
    if result.is_ok:
        check("zero facts: value is a written property_file_id, not NOTHING_COMPOSED",
              result.value is not cpf.NOTHING_COMPOSED, f"got {result.value}")
        pf_id = result.value
        with conn.cursor() as cur:
            cur.execute("SELECT refusals FROM property_file WHERE id = %s", (pf_id,))
            refusals = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM property_file_fact WHERE property_file_id = %s", (pf_id,))
            link_count = cur.fetchone()[0]
        codes = [r.get("code") for r in refusals]
        check("zero facts: PARCEL_NO_FACTS present", "PARCEL_NO_FACTS" in codes, f"got {codes}")
        parcel_no_facts = next((r for r in refusals if r.get("code") == "PARCEL_NO_FACTS"), None)
        if parcel_no_facts:
            check("zero facts: stage is L8", parcel_no_facts.get("stage") == "L8",
                  f"got {parcel_no_facts.get('stage')!r}")
        check("zero facts: zero property_file_fact link rows", link_count == 0, f"got {link_count}")

    conn.close()


if __name__ == "__main__":
    test_nonexistent_parcel_id_refuses_parcel_reference_unknown_no_row()
    test_zero_facts_refuses_parcel_no_facts_real_row_zero_links()
    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)
