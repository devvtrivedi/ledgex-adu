#!/usr/bin/env python3
"""Invariant test for compose_property_file's APN collision handling
(Fix 3).

Invariant under test: composing by a colliding APN must never silently
pick one of the candidate parcels. 0034 dropped parcel's (jurisdiction_id,
apn) uniqueness -- 44 real collisions exist in the live parcels snapshot
-- so a plain `WHERE apn = %s` + fetchone() is a real, reachable bug, not
a theoretical one: it resolves an ambiguous input to an arbitrary parcel
with no error, no log, nothing telling the caller a choice was made at
all.

Runs the REAL scripts/compose_property_file.py resolve_parcel_id_by_apn()
against a real database with two real, freshly-seeded parcels sharing one
apn -- not a mock, the actual resolution path --parcel-apn drives.

Requires DATABASE_URL for a scratch database (this test commits real
parcel/fact-adjacent rows).

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/test_compose_collision_invariant.py

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import os
import sys
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import compose_property_file as cpf  # noqa: E402 -- module under test, imported, not reimplemented
from infra.env import get_db  # noqa: E402


def seed_colliding_parcels(conn, apn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES ('ca_san_jose', 'City of San Jose', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """
        )
        ids = []
        for _ in range(2):
            cur.execute(
                "INSERT INTO parcel (jurisdiction_id, apn) VALUES ('ca_san_jose', %s) RETURNING id",
                (apn,),
            )
            ids.append(str(cur.fetchone()[0]))
    conn.commit()
    return ids


def run():
    apn = f"COLLIDE-{uuid.uuid4().hex[:8]}"
    conn = get_db()
    candidate_ids = seed_colliding_parcels(conn, apn)
    print(f"[test] apn={apn!r} seeded on 2 real colliding parcels: {candidate_ids}")

    resolve = getattr(cpf, "resolve_parcel_id_by_apn", None)
    if resolve is None:
        print("[test] FAIL: resolve_parcel_id_by_apn does not exist. The old compose(conn, apn, "
              "channel) resolves an ambiguous apn via a plain 'WHERE apn = %s' + fetchone(), "
              "silently picking one of the colliding parcels with no error, no log, nothing -- "
              "a real, reachable data-integrity bug (0034 dropped APN uniqueness; 44 real "
              "collisions exist in the live snapshot).")
        conn.close()
        return 1

    try:
        picked = resolve(conn, apn)
    except SystemExit as e:
        msg = str(e)
        missing = [cid for cid in candidate_ids if cid not in msg]
        if missing:
            print(f"[test] FAIL: raised on the collision (good), but the message doesn't name "
                  f"every candidate id -- missing {missing}. Message: {msg}")
            conn.close()
            return 1
        print(f"[test] PASS: collision on apn={apn!r} raised, naming every candidate id: {msg}")
        conn.close()
        return 0
    else:
        print(f"[test] FAIL: resolve_parcel_id_by_apn did NOT raise on a real collision -- "
              f"silently returned parcel_id={picked!r}, one of {candidate_ids} picked arbitrarily "
              f"with no error.")
        conn.close()
        return 1


if __name__ == "__main__":
    sys.exit(run())
