#!/usr/bin/env python3
"""Minimal composer: prove the refusal path, before any success path exists.

A FOURTH script, still not core/ -- module boundaries come after a
non-ingest consumer exists to compare against the three ingests, and
this is that consumer, not the trigger to extract one yet. Copies
(adds to the running list) env/get_db from ingest_parcels.py's pattern.

Scope, deliberately small, per instruction:
  - read one parcel's current facts via current_fact_at(now()) (C5, 0036)
  - apply the I6 rights gate to every TOUCHED fact, not just rendered ones
  - on any blocked fact: write property_file(status='refused',
    refusals populated, delivered_at NULL) and link every touched fact
    via property_file_fact
  - on zero blocked facts: report that the gate passed and STOP -- no
    rendering, no payload assembly, no success/partial path. That is
    real, unbuilt scope, not a case this script fakes an answer for.

WHY refusal first, and why every run today refuses. 0030 set every
licence_channel row (cc0, cc_by_4_0, all six channels each) to
allowed=false pending counsel clearance. Every fact this project has
ingested carries one of those two licences. So the I6 gate blocks
every touched fact, on every channel, for every parcel, right now --
not because this composer is broken, but because the rights position
IS "nothing is cleared yet." Proving that is the actual milestone:
a well-formed refused property_file, for the right reason, is a
positive result here, not a placeholder for a success path that
doesn't exist yet.

use='input' for every property_file_fact row this script writes, not
'gate' or 'rendered': 'gate' (per 0012's own comment) names facts that
resolve JURISDICTION and never appear in a payload (e.g. a
city_limits-shaped fact) -- nothing ingested so far plays that role.
'rendered' would claim these facts appear in a delivered payload, which
is false for a refused file (I6: nothing renders). 'input' is what is
actually true: every touched fact was read as an input to the (aborted)
composition attempt.

Refusal code: RIGHTS_BLOCKED, stage L8 -- both already named in §9's
refusal code table ("Licence forbids this field in this channel"), not
invented for this script.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_composer_version():
    """Derive composer_version from git, not a hand-typed literal --
    the same defect class as url_verified_at = now(): a column whose
    purpose is to record an identity, filled with something that
    doesn't actually track it. A hand-set string like the
    "compose@0.1.0-minimal" this replaces survives a real code change
    with zero signal that anything changed underneath it.

    "compose@<sha>": the exact commit this file's tree matches.
    "compose@<sha>-dirty": HEAD is <sha>, but the working tree has
    uncommitted changes -- recording the SHA alone here would claim a
    clean, reviewable commit produced this row when it didn't; the
    marker says so instead of staying silent about it.

    git unavailable (binary missing, not a git repo, no HEAD yet):
    recorded as "compose@no-git:<reason>" -- deliberately not a
    40-hex-char string, so it can never be mistaken for a real SHA by
    anything that later reads this column, and deliberately not a
    fabricated placeholder SHA either. Composition still proceeds: the
    gap this closes is "can I trust the SHA," not "can this row exist
    at all," and refusing to compose over a missing git binary would
    make the identity problem worse, not better, for the one thing
    that would actually need the record (a refusal, unaffected by
    whether the git binary happens to be installed on this host).
    """
    def run(args):
        try:
            result = subprocess.run(
                args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return None, str(e)
        if result.returncode != 0:
            return None, result.stderr.strip() or f"exit {result.returncode}"
        return result.stdout.strip(), None

    sha, err = run(["git", "rev-parse", "HEAD"])
    if sha is None:
        return f"compose@no-git:{err}"

    status, err = run(["git", "status", "--porcelain"])
    if status is None:
        # Got a SHA but couldn't determine dirty state -- do not claim
        # clean when that claim wasn't actually checked.
        return f"compose@{sha}-dirty-unknown:{err}"

    return f"compose@{sha}-dirty" if status else f"compose@{sha}"


def env(name):
    load_dotenv(override=False)
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"missing required environment variable: {name}")
    return val


def get_db():
    conn = psycopg2.connect(env("DATABASE_URL"))
    conn.autocommit = False
    return conn


def compose(conn, apn, channel):
    t0 = time.monotonic()
    composer_version = get_composer_version()

    with conn.cursor() as cur:
        # Captured ONCE, explicitly, and reused for both the read below and
        # as_of on the INSERT -- not two separate now() calls relying on
        # Postgres freezing now() for the life of one transaction. That
        # freezing is real (confirmed while investigating the first
        # replay: composed_at and as_of came out identical because both
        # were now() inside one uncommitted transaction) but it is a
        # property of THIS transaction's shape, not of this function's
        # design -- a future version that commits between the read and
        # the write would silently break it with no error. Explicit
        # capture makes as_of correct by construction instead of by
        # transaction scoping.
        cur.execute("SELECT clock_timestamp()")
        as_of = cur.fetchone()[0]

        cur.execute("SELECT id, jurisdiction_id FROM parcel WHERE apn = %s", (apn,))
        row = cur.fetchone()
        if row is None:
            raise SystemExit(f"no parcel with apn={apn!r}")
        parcel_id, jurisdiction_id = row

        cur.execute("SELECT pack_version FROM jurisdiction WHERE id = %s", (jurisdiction_id,))
        pack_version = cur.fetchone()[0]

        # C5 (0036): the point-in-time read path, not the cached matview --
        # this is a live composition, not a report against a stale refresh.
        # Same as_of captured above, not a second now().
        cur.execute(
            "SELECT id, field_key, licence_id, value FROM current_fact_at(%s) WHERE parcel_id = %s",
            (as_of, parcel_id),
        )
        touched = cur.fetchall()
        if not touched:
            raise SystemExit(f"parcel {apn} has no current facts -- nothing to compose or gate")

        print(f"parcel {apn} ({parcel_id}): {len(touched)} touched facts")
        for fact_id, field_key, licence_id, value in touched:
            print(f"  {field_key:28s} licence={licence_id:12s} value={json.dumps(value)}")

        # I6 rights gate: every touched fact must have an explicit
        # allowed=true licence_channel row for this channel. Absence is
        # default-deny (§7.3), the same as an explicit false -- both block.
        licence_ids = sorted({row[2] for row in touched})
        cur.execute(
            "SELECT licence_id, allowed FROM licence_channel WHERE licence_id = ANY(%s) AND channel = %s",
            (licence_ids, channel),
        )
        allowed_by_licence = {lic: allowed for lic, allowed in cur.fetchall()}

        blocked_by_licence = {}
        for fact_id, field_key, licence_id, value in touched:
            if not allowed_by_licence.get(licence_id, False):
                blocked_by_licence.setdefault(licence_id, []).append(field_key)

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if not blocked_by_licence:
        print(f"\nRIGHTS GATE PASSED for channel={channel!r}: every touched fact's licence "
              f"permits this channel. No property_file written -- composing a real file "
              f"(rendering, payload assembly, a success/partial path) is out of scope for "
              f"this minimal composer. This is the expected outcome only when a "
              f"licence_channel row has been deliberately flipped for verification; do not "
              f"treat it as evidence anything is ready to ship.")
        return None

    refusals = []
    for licence_id in sorted(blocked_by_licence):
        field_keys = sorted(blocked_by_licence[licence_id])
        refusals.append({
            "code": "RIGHTS_BLOCKED",
            "stage": "L8",
            "message": f"Licence {licence_id} forbids channel {channel} for touched field(s): {', '.join(field_keys)}.",
            "detail": {"licence_id": licence_id, "channel": channel, "field_keys": field_keys},
        })

    payload = {"status": "refused", "refusals": refusals, "attribution": [], "omitted_for_rights": []}
    payload_json = json.dumps(payload, sort_keys=True)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    property_file_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO property_file (
                id, parcel_id, jurisdiction_id, channel, status, as_of,
                pack_version, ruleset_version, composer_version,
                geometry_tier_used, refusals, omitted_for_rights, attribution,
                payload, payload_hash, delivered_at, compose_ms
            ) VALUES (
                %s, %s, %s, %s, 'refused', %s,
                %s, %s, %s,
                false, %s::jsonb, '[]'::jsonb, '{}',
                %s::jsonb, %s, NULL, %s
            )
            """,
            (
                property_file_id, parcel_id, jurisdiction_id, channel, as_of,
                pack_version, "unevaluated -- refused before L5 Rules", composer_version,
                json.dumps(refusals), payload_json, payload_hash, elapsed_ms,
            ),
        )

        pf_fact_rows = [(property_file_id, fact_id, parcel_id, "input") for fact_id, _, _, _ in touched]
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO property_file_fact (property_file_id, fact_id, parcel_id, use) VALUES %s",
            pf_fact_rows,
        )

    conn.commit()
    print(f"\nproperty_file {property_file_id} -> refused ({len(refusals)} refusal(s), "
          f"{len(touched)} touched facts linked, compose_ms={elapsed_ms})")
    for r in refusals:
        print(f"  {r['code']}: {r['message']}")
    return property_file_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--parcel-apn", required=True)
    parser.add_argument("--channel", default="paid_property_file")
    args = parser.parse_args()

    conn = get_db()
    try:
        compose(conn, args.parcel_apn, args.channel)
    finally:
        conn.close()
