#!/usr/bin/env python3
"""P42: automates the actual I6 assertion P40/P42's own reports made as a
one-off transcript -- that a rights-blocked fact's value never appears
anywhere in api/'s serialized response body, on the exact parcel
scripts/seed_internal_test_licences.py produces.

Does NOT run the seed itself. The seed is gated by an explicit opt-in and
makes a PERMANENT write (licence/licence_channel rows that can never be
deleted or updated) -- a test script silently triggering that as a side
effect would be exactly the accident the seed's own opt-in gate exists to
prevent. If the expected parcel isn't there, this refuses loudly and names
the exact command to run first, rather than seeding it for you.

Calls api.main.get_parcel_facts directly, as a plain function -- not over
HTTP. Serializes the return value through the SAME Pydantic response_model
(api.main.ParcelFactsResponse) FastAPI itself would use to build the real
wire response, so "the sentinel string does not appear in the serialized
response body" is tested against the actual production serialization path,
not a hand-rolled approximation of it -- without adding a new test-only HTTP
client dependency (fastapi.testclient.TestClient needs httpx, not currently
a dependency of this repo, for exactly this one script) just to reach code
this script can call directly.

Read-only. Writes nothing. Safe to run any number of times, against any
database that already carries the seed's parcel.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
import api.main as viewer  # noqa: E402
import seed_internal_test_licences as seeder  # noqa: E402

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


BLOCKED_SENTINEL = "BLOCKED FIXTURE VALUE - MUST NOT RENDER"


def find_seeded_parcel(conn):
    jurisdiction_id = f"{seeder._NAMESPACE}.viewer_demo"
    apn = f"{seeder._NAMESPACE.upper()}-VIEWER-DEMO-1"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM parcel WHERE jurisdiction_id = %s AND apn = %s ORDER BY id",
            (jurisdiction_id, apn),
        )
        row = cur.fetchone()
    if row is None:
        raise SystemExit(
            f"No seeded parcel found (jurisdiction_id={jurisdiction_id!r}, apn={apn!r}). "
            f"This test reads scripts/seed_internal_test_licences.py's own output -- it "
            f"does not create it. Run it first: "
            f"SEED_INTERNAL_TEST_LICENCES=1 python3 scripts/seed_internal_test_licences.py"
        )
    return str(row[0])


def test_rights_gate_holds_on_the_seeded_parcel():
    conn = get_db()
    parcel_id = find_seeded_parcel(conn)

    # get_parcel_facts is a plain function under FastAPI's decorator (FastAPI
    # does not wrap route functions in a way that hides the original
    # callable) -- call it directly as ordinary Python, exactly like every
    # scripts/test_compose_*.py file already calls compose_property_file's
    # own functions directly rather than through a process boundary.
    result = viewer.get_parcel_facts(parcel_id, as_of=None, conn=conn)
    conn.close()

    check("facts[] is non-empty (the seed's own permitted rows)", len(result["facts"]) > 0,
          f"got {result['facts']}")
    check("omitted_for_rights[] is non-empty (P42's own blocked fixture)",
          len(result["omitted_for_rights"]) > 0,
          "empty -- this is exactly the gap P42 fixed; re-run the seed script")
    check("the blocked entry cites the REAL cc_by_4_0 licence",
          any(o["licence_id"] == "cc_by_4_0" for o in result["omitted_for_rights"]),
          f"got {result['omitted_for_rights']}")
    check("no permitted fact carries the real cc_by_4_0 licence",
          not any(f["licence_id"] == "cc_by_4_0" for f in result["facts"]),
          f"got {result['facts']}")

    # THE actual I6 assertion: serialize through the SAME response_model
    # FastAPI uses to build the real wire response, then search the exact
    # bytes a real client would receive.
    serialized = viewer.ParcelFactsResponse.model_validate(result).model_dump_json()
    check("blocked sentinel value does not appear anywhere in the serialized response",
          BLOCKED_SENTINEL not in serialized,
          f"LEAK: {BLOCKED_SENTINEL!r} found in serialized response body")


if __name__ == "__main__":
    test_rights_gate_holds_on_the_seeded_parcel()
    print(f"\n{len(failures)} failure(s)" if failures else "\nAll assertions passed")
    sys.exit(1 if failures else 0)
