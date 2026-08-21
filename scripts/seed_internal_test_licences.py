#!/usr/bin/env python3
"""P40 — seed NEW internal-test licence rows so the internal viewer has real,
rights-PERMITTED data to render alongside the real, rights-BLOCKED cc0/
cc_by_4_0 data. Read this whole docstring before running it.

WHY THIS EXISTS. Counsel's per-resource licence confirmation (LD-1) is not
required for internal testing (founder's own ratified scope decision,
prompts/P40-internal-viewer.md §0). But every real licence_channel row is
allowed=false (0030, pending clearance), so a viewer built only against real
data would show nothing but RIGHTS_BLOCKED, on every screen, forever, until
LD-1 clears -- not enough to prove the I6 gate itself is wired correctly.
This script seeds a second, clearly-fake rights position (D2 namespace,
below) that the SAME gate (core.rights.evaluate_rights_gate, moved there
from scripts/compose_property_file.py by P47) permits, so the viewer can be
exercised end to end without touching, or pretending to touch, the real
licences' position.

P42 (README/P40 review): the demo parcel this script creates also carries ONE
fact citing the REAL cc_by_4_0 licence, unchanged and still allowed=false on
every channel (see BLOCKED FIXTURE FACT below) -- so the parcel this script
produces is, BY CONSTRUCTION, the one-parcel/one-channel/both-outcomes proof
P40's own report depends on: a real, cc_by_4_0-blocked fact sitting next to
the permitted internal_test.* facts. Before P42, that proof existed only as a
hand-inserted row on a different real parcel, described in prose but not
reproducible from this script alone (P40 review, finding recorded in
prompts/P40-internal-viewer.md's own Review findings section). Run this
script, then `GET /v1/parcels/<the parcel id this script prints>/facts` on
channel `api`, and the split is right there: N permitted facts under
`facts`, one blocked fact (licence_id `cc_by_4_0`) under `omitted_for_rights`.

BLOCKED FIXTURE FACT -- READ THIS BEFORE ASSUMING "seeds a real licence" MEANS
"touches the real licence." It does not. This script INSERTs exactly one
`fact` row whose `licence_id` column is the literal string `'cc_by_4_0'` --
the real licence's own primary key, referenced the same way any other fact
in this database already does. That is the ONLY thing about this fixture
that is real. Its `source_id`, `snapshot_id` and `field_key` are all fresh
`internal_test.*` rows this script creates and owns, exactly like every other
row below. No row belonging to `cc0`/`cc_by_4_0` themselves -- not `licence`,
not `licence_channel` -- is ever written, updated or read-for-mutation by
this script. Citing a real licence id from a new fact row is the same
operation `db/seeds/day4_sources.sql` performs constantly for its own real
facts; it is not a special case and it does not require, use, or imply any
kind of elevated permission over the licence itself.

PERMANENT WRITES -- READ THIS BEFORE RUNNING, NOT AFTER.
Every licence and licence_channel row this script writes is in the database
FOREVER, the same as cc0 and cc_by_4_0 already are:
  - licence_no_delete / licence_no_update (0027) -- a licence row can never
    be deleted, and never updated, once it exists.
  - licence_channel_no_delete / licence_channel_no_update (0033) -- the
    same, one level down.
  - (licence_id, channel) is licence_channel's own PRIMARY KEY, so there is
    no "corrected" second row to insert later either -- get a rationale
    wrong here and it is wrong forever, not merely inconvenient to fix.
db/tests/teardown.sql deletes from exactly seven tables (exception_evidence,
job_run, parcel, parcel_exception, property_file, property_file_fact,
source_feature_identity) and by design never touches licence, source or
jurisdiction. It will not clean this up, and it is not supposed to.

NOT CLEARANCE. Running this script does not constitute, and must never be
read as implying, counsel's clearance of cc0 or cc_by_4_0. LD-1 stays open.
The real licence rows -- cleared_by NULL, cleared_at NULL -- and all 12 of
their real licence_channel rows -- every one allowed=false -- are completely
untouched by anything below. This script only ever INSERTs new rows under a
new namespace; it has no UPDATE, DELETE or TRUNCATE anywhere in it.

D2 NAMESPACE: every id this script creates -- both licences, the
jurisdiction, the source(s), the field_definition(s) -- carries the
`internal_test.` prefix. Deliberately NOT db/tests/invariants.sql's `test.`
prefix: db/tests/teardown.sql keys its cleanup off `TEST-%`/`test.%`, and
reusing that prefix would imply these rows are disposable fixtures that get
torn down. They are not -- see "PERMANENT WRITES" above -- so they get a
namespace that says "permanent, deliberate" instead of "fixture, disposable".

GATED BY EXPLICIT OPT-IN, modelled directly on scripts/check_golden.py's own
GOLDEN_ALLOW_RULE_SEED (same shape, same refuse-by-default posture, same
"name the target, say why, name the exact variable" message): refuses by
default, names the database it would write to, states the write is
permanent, and says exactly which environment variable to set if this is
genuinely intended.

IDEMPOTENT. Every INSERT below is ON CONFLICT DO NOTHING. Safe to run twice
against the same database -- a second run reports what it skipped, never
pretends to have written a row it didn't.

NOT wired into any make target, CI workflow or test suite. Run once, by
hand, against a database somebody has already decided is fine to carry these
two permanent licence rows forever.
"""
import datetime
import json
import os
import sys
import uuid

import psycopg2

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from infra.env import get_db  # noqa: E402

_ALLOW_VAR = "SEED_INTERNAL_TEST_LICENCES"
_NAMESPACE = "internal_test"

# D1 (prompts/P40-internal-viewer.md §0): the existing `api` channel, not a
# new enum member. See that report for the full argument -- in short, a new
# `internal_ops` channel would be a rights decision on its face and a spec
# bump, not a judgement call inside a tooling package.
VIEWER_CHANNEL = "api"


def _target_database_name(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        return cur.fetchone()[0]


def _require_opt_in(conn):
    if os.environ.get(_ALLOW_VAR) == "1":
        return
    target = _target_database_name(conn)
    raise SystemExit(
        f"refusing to seed internal_test.* licence rows into {target!r}: this INSERTs "
        f"licence and licence_channel rows that CANNOT ever be removed or edited again "
        f"(licence_no_delete/_no_update, 0027; licence_channel_no_delete/_no_update, "
        f"0033) -- a permanent, one-way action, not a routine check. Refusing by default "
        f"so this cannot be run against a database by accident. If this database is one "
        f"you have already decided is fine to carry these two rows forever, re-run with "
        f"{_ALLOW_VAR}=1. This does not touch, and never implies clearance of, the real "
        f"cc0 / cc_by_4_0 licence rows -- LD-1 remains open regardless of this script."
    )


def _insert_reporting(cur, label, sql, params, key_cols):
    """Runs an ON CONFLICT DO NOTHING insert and reports whether it actually
    wrote the row or found it already there -- never claims a write that
    didn't happen. key_cols: the WHERE clause to check post-insert existence,
    as (column_names_tuple, values_tuple)."""
    cur.execute(sql, params)
    wrote = cur.rowcount > 0
    print(f"  {'wrote' if wrote else 'skipped (already exists)':26s} {label}")
    return wrote


def seed(conn):
    with conn.cursor() as cur:
        print(f"jurisdiction, licences, licence_channel rows (namespace: {_NAMESPACE}.*)")

        jurisdiction_id = f"{_NAMESPACE}.viewer_demo"
        _insert_reporting(
            cur, f"jurisdiction {jurisdiction_id!r}",
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, "
            "supported, geometry_tier_enabled) "
            "VALUES (%s, 'Internal Test (P40 viewer)', 'city', 'CA', 'internal_test@0.1.0', "
            "true, false) ON CONFLICT (id) DO NOTHING",
            (jurisdiction_id,), None,
        )

        licences = [
            (
                f"{_NAMESPACE}.cc0",
                "Internal Test -- CC0 analogue (NOT the real cc0, no rights meaning)",
                "open",
            ),
            (
                f"{_NAMESPACE}.cc_by_4_0",
                "Internal Test -- CC BY 4.0 analogue (NOT the real cc_by_4_0, no rights meaning)",
                "attribution",
            ),
        ]
        for licence_id, display_name, restriction in licences:
            attribution_text = "Internal test fixture -- P40 viewer only." if restriction == "attribution" else None
            _insert_reporting(
                cur, f"licence {licence_id!r}",
                "INSERT INTO licence (id, display_name, restriction, commercial_use, "
                "redistribution, attribution_text, observed_at, cleared_by, cleared_at, notes) "
                "VALUES (%s, %s, %s, 'allowed', 'allowed', %s, now(), 'internal_test_seed', now(), "
                "'P40 internal-test namespace -- NOT the real licence, NOT counsel clearance, "
                "asserts nothing about LD-1.') ON CONFLICT (id) DO NOTHING",
                (licence_id, display_name, restriction, attribution_text), None,
            )
            _insert_reporting(
                cur, f"licence_channel ({licence_id!r}, {VIEWER_CHANNEL!r})",
                "INSERT INTO licence_channel (licence_id, channel, allowed, rationale) "
                "VALUES (%s, %s, true, 'P40 internal-test fixture: deliberately allowed so the "
                "viewer has real, rights-permitted data to render. Not a statement about the "
                "real licence this id parallels.') ON CONFLICT (licence_id, channel) DO NOTHING",
                (licence_id, VIEWER_CHANNEL), None,
            )

        print("source, snapshot, field_definition, parcel, fact rows")

        now_ts = datetime.datetime.now(datetime.timezone.utc)
        parcel_apn = f"{_NAMESPACE.upper()}-VIEWER-DEMO-1"
        # 0034 dropped parcel's (jurisdiction_id, apn) uniqueness deliberately
        # (real APN collisions) -- there is no unique constraint here for
        # ON CONFLICT to target, so plain "ON CONFLICT DO NOTHING" never
        # actually conflicts and a second run would insert a second parcel
        # row. WHERE NOT EXISTS is the correct idempotency guard for a table
        # with no unique index to lean on, same shape as the fact insert
        # below (which has the identical problem for the same reason).
        _insert_reporting(
            cur, f"parcel apn={parcel_apn!r}",
            "INSERT INTO parcel (jurisdiction_id, apn) "
            "SELECT %s, %s WHERE NOT EXISTS ("
            "  SELECT 1 FROM parcel WHERE jurisdiction_id = %s AND apn = %s"
            ")",
            (jurisdiction_id, parcel_apn, jurisdiction_id, parcel_apn), None,
        )
        # ORDER BY id, never a bare fetchone() on an unordered result -- the
        # exact "arbitrary pick" shape this repo has already found and fixed
        # twice elsewhere (resolve_parcel_id_by_apn's own precedent). With
        # the WHERE NOT EXISTS guard above this is normally exactly one row;
        # ORDER BY is the honest tie-break if that is ever violated, not a
        # silent guess.
        cur.execute("SELECT id FROM parcel WHERE jurisdiction_id = %s AND apn = %s ORDER BY id",
                    (jurisdiction_id, parcel_apn))
        parcel_id = cur.fetchone()[0]

        for i, (licence_id, _, _) in enumerate(licences):
            suffix = licence_id.split(".", 1)[1]  # cc0 / cc_by_4_0
            source_id = f"{_NAMESPACE}.viewer_source_{suffix}"
            field_key = f"{_NAMESPACE}.viewer_field_{suffix}"

            _insert_reporting(
                cur, f"source {source_id!r}",
                "INSERT INTO source (id, jurisdiction_id, display_name, steward, method, "
                "phase_status, phase_status_reason, endpoint_url, licence_id, active) "
                "VALUES (%s, %s, %s, 'P40 internal test', 'bulk', 'active', "
                "'P40 internal-test fixture -- not a real ingest source', "
                "'https://internal-test.invalid/p40', %s, false) ON CONFLICT (id) DO NOTHING",
                (source_id, jurisdiction_id, f"Internal Test Source ({suffix})", licence_id), None,
            )

            digest = uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}-{i}").hex + uuid.uuid5(uuid.NAMESPACE_DNS, source_id).hex
            digest = digest[:64]
            snapshot_id = f"{source_id}:sha256:{digest}"
            _insert_reporting(
                cur, f"snapshot {snapshot_id!r}",
                "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, "
                "byte_size, request, http_status, fetched_at, licence_observed_id) "
                "VALUES (%s, %s, 's3://internal-test/p40/fixture', %s, 'application/json', 1, "
                "'{}'::jsonb, 200, now(), %s) ON CONFLICT (id) DO NOTHING",
                (snapshot_id, source_id, digest, licence_id), None,
            )

            _insert_reporting(
                cur, f"field_definition {field_key!r}",
                "INSERT INTO field_definition (field_key, display_name, claim, value_type, "
                "category, description) VALUES (%s, %s, 'public_record', 'string', 'parcel', "
                "'P40 internal-test fixture field -- not a real field.') "
                "ON CONFLICT (field_key) DO NOTHING",
                (field_key, f"Internal Test Field ({suffix})"), None,
            )

            _insert_reporting(
                cur, f"fact {field_key!r} on parcel {parcel_id}",
                "INSERT INTO fact (parcel_id, jurisdiction_id, field_key, value, method, "
                "source_id, snapshot_id, retrieved_at, source_url, licence_id, confidence, "
                "confidence_rule_id, effective_from, pack_version) "
                "SELECT %s, %s, %s, %s, 'bulk', %s, %s, %s, 'https://internal-test.invalid/p40', "
                "%s, 'high', 'internal_test.rule', %s, 'internal_test@0.1.0' "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM fact WHERE parcel_id = %s AND field_key = %s AND licence_id = %s"
                ")",
                (
                    parcel_id, jurisdiction_id, field_key, f'"visible via {VIEWER_CHANNEL}"',
                    source_id, snapshot_id, now_ts, licence_id, now_ts,
                    parcel_id, field_key, licence_id,
                ), None,
            )

        # P42: the blocked-fixture fact. Same parcel as every internal_test.*
        # fact above -- the whole point is one row in one table on one
        # screen, not a second parcel. source_id/snapshot_id/field_key are
        # internal_test.* like everything else; licence_id is the real,
        # unchanged 'cc_by_4_0' -- see BLOCKED FIXTURE FACT in this module's
        # own docstring for why that is not the same thing as touching the
        # real licence.
        blocked_source_id = f"{_NAMESPACE}.viewer_source_blocked_fixture"
        blocked_field_key = f"{_NAMESPACE}.viewer_field_blocked_fixture"
        real_licence_id = "cc_by_4_0"

        _insert_reporting(
            cur, f"source {blocked_source_id!r} (cites REAL licence {real_licence_id!r})",
            "INSERT INTO source (id, jurisdiction_id, display_name, steward, method, "
            "phase_status, phase_status_reason, endpoint_url, licence_id, active) "
            "VALUES (%s, %s, 'Internal Test Source (blocked fixture)', 'P40 internal test', "
            "'bulk', 'active', 'P42 fixture -- proves the gate blocks a REAL licence on the "
            "seeded parcel', 'https://internal-test.invalid/p40', %s, false) "
            "ON CONFLICT (id) DO NOTHING",
            (blocked_source_id, jurisdiction_id, real_licence_id), None,
        )

        blocked_digest = (uuid.uuid5(uuid.NAMESPACE_URL, f"{blocked_source_id}-blocked").hex
                           + uuid.uuid5(uuid.NAMESPACE_DNS, blocked_source_id).hex)[:64]
        blocked_snapshot_id = f"{blocked_source_id}:sha256:{blocked_digest}"
        _insert_reporting(
            cur, f"snapshot {blocked_snapshot_id!r} (licence_observed_id={real_licence_id!r})",
            "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, "
            "byte_size, request, http_status, fetched_at, licence_observed_id) "
            "VALUES (%s, %s, 's3://internal-test/p40/blocked-fixture', %s, 'application/json', "
            "1, '{}'::jsonb, 200, now(), %s) ON CONFLICT (id) DO NOTHING",
            (blocked_snapshot_id, blocked_source_id, blocked_digest, real_licence_id), None,
        )

        _insert_reporting(
            cur, f"field_definition {blocked_field_key!r}",
            "INSERT INTO field_definition (field_key, display_name, claim, value_type, "
            "category, description) VALUES (%s, 'Internal Test Field (blocked fixture)', "
            "'public_record', 'string', 'parcel', "
            "'P42 fixture field -- its one fact deliberately cites the real cc_by_4_0 "
            "licence so the gate has something real to refuse on the seeded parcel.') "
            "ON CONFLICT (field_key) DO NOTHING",
            (blocked_field_key,), None,
        )

        # The sentinel value: obviously fake, greppable, and exactly what
        # evidence assertions (this script's own callers, and scripts/
        # test_viewer_rights_gate.py) search for to prove it never appears
        # in any response body.
        blocked_value = "BLOCKED FIXTURE VALUE - MUST NOT RENDER"
        _insert_reporting(
            cur, f"fact {blocked_field_key!r} on parcel {parcel_id} (licence={real_licence_id!r}, BLOCKED)",
            "INSERT INTO fact (parcel_id, jurisdiction_id, field_key, value, method, "
            "source_id, snapshot_id, retrieved_at, source_url, licence_id, confidence, "
            "confidence_rule_id, effective_from, pack_version) "
            "SELECT %s, %s, %s, %s, 'bulk', %s, %s, %s, 'https://internal-test.invalid/p40', "
            "%s, 'high', 'internal_test.rule', %s, 'internal_test@0.1.0' "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM fact WHERE parcel_id = %s AND field_key = %s AND licence_id = %s"
            ")",
            (
                parcel_id, jurisdiction_id, blocked_field_key, json.dumps(blocked_value),
                blocked_source_id, blocked_snapshot_id, now_ts, real_licence_id, now_ts,
                parcel_id, blocked_field_key, real_licence_id,
            ), None,
        )

    conn.commit()
    return jurisdiction_id, parcel_id, len(licences)


def main():
    conn = get_db()
    try:
        _require_opt_in(conn)
        jurisdiction_id, parcel_id, n_permitted = seed(conn)
        print(f"\ndone. jurisdiction={jurisdiction_id!r} parcel_id={parcel_id}")
        # P42: this used to say "every fact seeded above IS allowed" -- no
        # longer true, and saying so was the reproducibility gap the P40
        # review found. One fact is deliberately blocked; say so, plainly,
        # not folded into the "all permitted" line it used to share.
        print(f"channel={VIEWER_CHANNEL!r} -- {n_permitted} fact(s) permitted on {VIEWER_CHANNEL!r} "
              f"(internal_test.* licences); 1 fact BLOCKED on {VIEWER_CHANNEL!r} by the REAL "
              f"cc_by_4_0 licence, deliberately -- that block is the proof the gate works, not "
              f"a bug. Every real cc0/cc_by_4_0 licence row remains unchanged.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
