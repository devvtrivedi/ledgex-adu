#!/usr/bin/env python3
"""make golden -- two of SPEC.md sec 1.2's four fixture classes (P20:
refused; P25: geometry-disabled).

SPEC.md sec 1.2's golden row names four fixture classes: composed, partial,
refused, and geometry-disabled Base Core. This checks two -- refused and
geometry-disabled -- because those are the only two reachable today.
STANDING-BLOCKER.md: every licence_channel row is allowed=false,
cleared_by/cleared_at/evidence_uri all NULL, pending counsel/owner
clearance that has not happened. compose_property_file.py's I6 rights gate
therefore blocks every touched fact, on every channel, for every parcel --
correctly, because that is genuinely the rights state today, not a code
gap. Building a composed/partial fixture would mean fabricating a licence
clearance that does not exist -- exactly the "do not invent values to fill
a silence" rule this project is organised around.

P25: BOTH fixtures now carry TWO refusals, not one -- a real, load-bearing
consequence of settling how refusals compose across stages (see this
package's own report). SPEC.md sec 5's compose loop is an unconditional
straight-line sequence (L0 -> ... -> L7 -> L6 -> L8 -> decide -> persist,
no conditional/branching language anywhere), and sec 6.6 ("a golden file
that lost a refusal is a regression") presupposes multiple co-occurring
refusals are the normal shape -- refusals ACCUMULATE across stages, they
do not short-circuit the pipeline. jurisdiction.geometry_tier_enabled
defaults false for every jurisdiction (0002_registries.sql), so L7's
geometry gate now refuses (GEOMETRY_TIER_DISABLED) on every single
composition attempt today, alongside whatever L8's rights gate already
refused -- there is no way to touch a real fact today without ALSO hitting
the universal rights block, so a "geometry-disabled-only" fixture with a
single refusal is not constructible without fabricating rights clearance,
the same prohibition that keeps composed/partial unbuilt. The two fixture
files are kept separate anyway, matching sec 1.2's own four-class
taxonomy: their content is close today, by coincidence of the current
real state, but the moment rights ever clear, "refused" and
"geometry-disabled" stop being the same shape at all (composed/partial
with a per-conclusion refusal is not a refused file) -- separating them
now avoids a bigger fixture-file split later.

THE COVERAGE TRAP, decided, not defaulted (P20; still true at 2/4, P25).
Exiting 0 unconditionally once ANY fixture class passes would be
indistinguishable from a target that checked all four -- the exact
silently-passing-gate shape this repo already fixed in qa_check,
conformance, test and db-test. But exiting 1 unconditionally
(conformance/test's own current stance) is also wrong here, for a
different reason: those two targets exit 1 because they check NOTHING --
any other exit code would be false. This target checks something REAL,
now two somethings. Exiting 1 regardless of whether those real checks
pass would make golden's own exit code carry zero information (broken
checks and correctly-passing ones would look identical), which would
make P20's own break-then-revert proof meaningless -- there would be no
way to observe "red" as distinct from "genuinely covers less than four
classes."

Decided: exit code tracks ONLY whether the two real, built checks are
both correct (0 = refused AND geometry-disabled both passed; 1 = either
failed OR broke). The two absent classes are named explicitly,
unconditionally, on EVERY run, pass or fail -- never folded into a bare
"PASSED" that could be misread as full coverage. Same shape as
db/tests/invariants.sql's known_gaps/test_skipped sections (P9/P14):
real coverage counted honestly, absence stated loudly, neither silently
inflated nor silently hidden.

COMPOSER_VERSION -- a real, reported deviation from SPEC.md sec 6.6's
literal text, not a silent one. sec 6.6 says composer_version is
"Retained -- a version bump should fail the test and force a
re-blessing." compose_property_file.py's own get_composer_version()
derives it from `git rev-parse HEAD` -- "compose@<sha>" or
"compose@<sha>-dirty" -- which changes on EVERY commit to this repo,
including ones that never touch the composer at all (this package's own
remaining commits, for instance). Literal exact-match retention would
make golden red on the very next unrelated commit, permanently, which is
not what sec 6.6 means by "a version bump" (a deliberate, meaningful
change to composition logic) -- git-SHA granularity is finer than
semantic-version granularity, and retaining it literally would be
actively harmful to golden's purpose here even though get_composer_version()'s
own docstring gives a genuinely good reason for that granularity at the
property_file ROW level (real provenance, not signal-free). Resolved
pragmatically, not silently: composer_version is retained in the sense
that it is present and its SHAPE is asserted (a well-formed
"compose@<40-hex-sha>[-dirty]" or "compose@no-git:..." string) rather
than compared byte-for-byte against one frozen golden SHA. This still
catches a genuinely broken get_composer_version() (empty string,
malformed output) -- a narrower guarantee than sec 6.6's literal text,
reported here rather than picked silently. The real fix -- whether
composer_version needs a separate, coarser "composition logic version"
distinct from its own git-SHA provenance value, or whether golden
fixtures should simply be re-blessed as a matter of routine on every
commit -- is a genuine open question, not decided by this package.

AS_OF -- pinned for real, not merely normalised away. sec 6.6 lists
composed_at/delivered_at/retrieved_at/fetched_at as "Replaced with <TS>"
but as_of separately as "Pinned by the fixture, not by now()" -- distinct
wording, read here as a distinct mechanism: compose_property_file.py's
compose() gained an optional as_of= parameter (P20) so this script can
pass a fixed, far-future timestamp (GOLDEN_AS_OF below) instead of
compose()'s own default `SELECT clock_timestamp()`. Far-future, not an
arbitrary past date: current_fact_at(ts) requires
f.recorded_at <= ts AND f.effective_from <= ts, and this script's own
fixture fact is inserted with the real, live now() as its recorded_at/
effective_from -- a fixed year-2099 as_of is guaranteed to be at or after
that for the foreseeable life of this repo, without needing to also
override the fact insert's own timestamps.

Usage:
  DATABASE_URL=... .venv-ingest/bin/python3 scripts/check_golden.py [--bless]

  --bless overwrites BOTH tests/golden/ca_san_jose/refused.json and
  tests/golden/ca_san_jose/geometry_disabled.json with this run's own
  normalised output, instead of comparing against them -- the "reviewed
  fixture update" sec 1.2's own pass condition names. Never run --bless as
  part of `make golden` itself; it is a human, deliberate action.

Exit code 0 = both checks passed. Exit code 1 = either failed.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import ingest_parcels as ip  # noqa: E402 -- reused for its honest reference-row shape
import compose_property_file as cpf  # noqa: E402 -- module under test, imported, not reimplemented
from infra.env import get_db  # noqa: E402

FIXTURE_PATH = os.path.join(REPO_ROOT, "tests", "golden", "ca_san_jose", "refused.json")
GEOMETRY_DISABLED_FIXTURE_PATH = os.path.join(
    REPO_ROOT, "tests", "golden", "ca_san_jose", "geometry_disabled.json"
)
GOLDEN_CHANNEL = "paid_property_file"
GOLDEN_AS_OF = datetime.datetime(2099, 1, 1, tzinfo=datetime.timezone.utc)
GOLDEN_DIGEST = hashlib.sha256(b"golden-refused-fixture-v1").hexdigest()
GEOMETRY_DISABLED_GOLDEN_DIGEST = hashlib.sha256(b"golden-geometry-disabled-fixture-v1").hexdigest()

MISSING_CLASSES = ["composed", "partial"]

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
COMPOSER_VERSION_RE = re.compile(r"^compose@([0-9a-f]{40}(-dirty)?|no-git:.+)$")
TS_FIELDS = {"composed_at", "delivered_at", "retrieved_at", "fetched_at"}
STRIPPED_FIELDS = {"compose_ms", "source_calls", "compute_cost_micros", "storage_cost_micros"}
SORTED_LIST_FIELDS = {"unmet_fields", "refusals", "attribution", "omitted_for_rights"}


def seed_reference_rows(conn):
    """Honest, non-fabricated values -- same pattern
    scripts/test_refresh_failure_invariant.py's seed_reference_rows()
    already established post-P11 (see that function's own comment): reuses
    ingest_parcels.py's REAL LICENCE_ID/JURISDICTION_ID/SOURCE_ID, with
    observed_at/cleared_by/cleared_at matching db/seeds/day4_sources.sql
    exactly, never a fabricated clearance."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, observed_at, cleared_by, cleared_at)
            VALUES (%s, 'CC BY 4.0', 'attribution', 'allowed', 'allowed', 'City of San Jose',
                    '2026-07-31'::timestamptz, NULL, NULL)
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.LICENCE_ID,),
        )
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES (%s, 'City of San Jose', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.JURISDICTION_ID,),
        )
        cur.execute(
            """
            INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status,
                                 phase_status_reason, endpoint_url, licence_id, active)
            VALUES (%s, %s, 'Parcels', 'City of San Jose', 'bulk', 'active', 'golden fixture',
                    'https://example.com/parcels', %s, false)
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.SOURCE_ID, ip.JURISDICTION_ID, ip.LICENCE_ID),
        )
        cur.execute(
            """
            INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description)
            VALUES ('parcel.apn', 'APN', 'public_record', 'string', 'parcel', 'Assessor parcel number')
            ON CONFLICT (field_key) DO NOTHING
            """
        )
        # P31: same real rule db/seeds/day4_sources.sql seeds for a real
        # local/production database -- CI's schema job never runs
        # db/seeds/ (CLAUDE.md's own documented rule), so make golden's
        # own composition (now calling L5 for real, replacing the old
        # ruleset_version placeholder) needs this row seeded here too, or
        # every golden composition would refuse RULE_UNAVAILABLE instead
        # of finding the real rule GOLDEN_AS_OF (2099-01-01) is well
        # within. Identical values to day4_sources.sql's own row, not an
        # independently invented copy -- see that file and
        # prompts/P31-l5-refuse-first-one-real-rule.md section 3 for the
        # full citation/attestation argument.
        cur.execute(
            """
            INSERT INTO rule (
                id, jurisdiction_id, rule_key, version, effective_from, effective_to,
                citation, source_text_uri, params, pack_version,
                authored_by, reviewed_by, review_mode, reviewed_at, attestation_uri
            ) VALUES (
                'ca_san_jose.adu_detached_max_height_city_standards.v1', %s,
                'adu.detached.max_height.city_standards', 1, '2026-03-05'::date, NULL,
                'City of San José Bulletin #210, "ADU Universal Checklist," updated 03/05/2026, '
                    'Part 3 (Single-Family Properties, City Development Standards, Detached ADU) -- '
                    'summarizing San José Municipal Code Section 20.80.175, not its verbatim text.',
                'https://github.com/devvtrivedi/ledgex-adu/blob/6dca93c330e80cb91571bc24955e71eb6fb95954/jurisdictions/ca_san_jose/evidence/bulletin-210-adu-universal-checklist-2026-03-05.pdf',
                '{"first_story_max_ft": 18, "second_story_max_ft": 25, "max_stories": 2}'::jsonb,
                'ca_san_jose_rules@0.1.0',
                'devtrivedi06@gmail.com', 'devtrivedi06@gmail.com', 'solo_founder_attestation',
                '2026-08-18'::timestamptz,
                'https://github.com/devvtrivedi/ledgex-adu/blob/6dca93c330e80cb91571bc24955e71eb6fb95954/jurisdictions/ca_san_jose/evidence/attestation-adu-detached-max-height-city-standards.md'
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.JURISDICTION_ID,),
        )
        # Fixed, reused snapshots -- ON CONFLICT DO NOTHING, permanent by
        # design (0021), same as the idempotent reference rows above.
        # snapshot_id must be STABLE run to run for sec 6.6's "Retained --
        # a changed snapshot should fail the test" to mean anything. Two
        # distinct digests (P25) -- one per fixture class, so the refused
        # and geometry-disabled property_files link to their own,
        # separately-identifiable snapshot, not a shared one.
        for digest in (GOLDEN_DIGEST, GEOMETRY_DISABLED_GOLDEN_DIGEST):
            uri = ip.object_uri("golden-fixture-bucket", digest)
            cur.execute(
                """
                INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size,
                                       request, http_status, fetched_at, licence_observed_id)
                VALUES (%s, %s, %s, %s, 'application/json', 1, '{}'::jsonb, 200, now(), %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (ip.snapshot_id_for(digest), ip.SOURCE_ID, uri, digest, ip.LICENCE_ID),
            )
    conn.commit()


def make_fixture_parcel_and_fact(conn, apn, snapshot_id):
    """A fresh parcel every run (0034 dropped apn uniqueness -- a constant,
    grep-able apn across runs is fine, safe, never ambiguous, since this
    script always looks the id up by RETURNING, never by apn). One fact,
    fixed field_key/value/licence_id every run -- what actually drives
    payload_hash's stability, not the parcel/fact ids themselves (those
    are uuids, normalised away below). apn/snapshot_id parameterized
    (P25) so the refused and geometry-disabled fixtures use their own
    distinct, non-colliding parcels against the same jurisdiction."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (ip.JURISDICTION_ID, apn),
        )
        parcel_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO fact (
                parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
                retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
                effective_from, pack_version
            ) VALUES (
                %s, %s, 'parcel.apn', %s::jsonb, 'bulk', %s, %s,
                now(), 'https://example.com/parcels', %s, 'high', 'rule_1', now(), 'v1.0'
            )
            """,
            (parcel_id, ip.JURISDICTION_ID, json.dumps(apn), ip.SOURCE_ID, snapshot_id, ip.LICENCE_ID),
        )
    conn.commit()
    return parcel_id


def _replace_uuids(obj, token_map):
    if isinstance(obj, str):
        if UUID_RE.match(obj):
            if obj not in token_map:
                token_map[obj] = f"<UUID:{len(token_map) + 1}>"
            return token_map[obj]
        return obj
    if isinstance(obj, list):
        return [_replace_uuids(v, token_map) for v in obj]
    if isinstance(obj, dict):
        return {k: _replace_uuids(v, token_map) for k, v in obj.items()}
    return obj


def _sort_lists(obj):
    if isinstance(obj, dict):
        return {k: _sort_lists(v) for k, v in obj.items()}
    if isinstance(obj, list):
        items = [_sort_lists(v) for v in obj]
        try:
            return sorted(items, key=lambda x: json.dumps(x, sort_keys=True))
        except TypeError:
            return items
    return obj


def normalize(pf_row, pf_facts):
    """SPEC.md sec 6.6, applied field by field -- see this module's own
    docstring for the two deviations (composer_version, as_of) and why."""
    token_map = {}

    row = dict(pf_row)
    composer_version_raw = row.pop("composer_version")
    composer_version_shape_ok = bool(COMPOSER_VERSION_RE.match(composer_version_raw or ""))

    normalized = {}
    for key, value in row.items():
        if key in STRIPPED_FIELDS:
            continue
        if key in TS_FIELDS:
            normalized[key] = "<TS>" if value is not None else None
            continue
        if key == "as_of":
            # Pinned by the fixture (GOLDEN_AS_OF), not normalised away --
            # retained as its own literal, stable value.
            normalized[key] = value.isoformat() if hasattr(value, "isoformat") else value
            continue
        normalized[key] = value

    normalized = _replace_uuids(normalized, token_map)
    for field in SORTED_LIST_FIELDS:
        if field in normalized and normalized[field] is not None:
            normalized[field] = _sort_lists(normalized[field])
    if isinstance(normalized.get("payload"), dict):
        for field in ("refusals", "attribution", "omitted_for_rights"):
            if field in normalized["payload"]:
                normalized["payload"][field] = _sort_lists(normalized["payload"][field])

    normalized["composer_version"] = "<COMPOSER_VERSION:shape-checked-only>"

    facts_normalized = _sort_lists(_replace_uuids(
        [{"fact_id": f["fact_id"], "use": f["use"], "snapshot_id": f["snapshot_id"]} for f in pf_facts],
        token_map,
    ))

    return normalized, facts_normalized, composer_version_shape_ok


def run_composition(apn, digest):
    conn = get_db()
    seed_reference_rows(conn)
    parcel_id = make_fixture_parcel_and_fact(conn, apn, ip.snapshot_id_for(digest))

    property_file_id = cpf.compose(conn, parcel_id, GOLDEN_CHANNEL, as_of=GOLDEN_AS_OF)
    if property_file_id is None:
        raise SystemExit(
            "compose() returned None (rights gate PASSED) -- this means "
            "licence_channel has been flipped to allowed=true since STANDING-BLOCKER.md "
            "was last true. That is real news, not a fixture bug -- see this "
            "script's own module docstring."
        )

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM property_file WHERE id = %s", (property_file_id,))
        col_names = [d.name for d in cur.description]
        pf_row = dict(zip(col_names, cur.fetchone()))
        # property_file itself has no snapshot_id column -- sec 6.6's
        # "snapshot_id ... Retained -- a changed snapshot should fail the
        # test" is about the linked fact's OWN snapshot_id, joined here so
        # a changed snapshot for the touched fact actually shows up in the
        # comparison.
        cur.execute(
            """
            SELECT pff.fact_id, pff.use, f.snapshot_id
              FROM property_file_fact pff JOIN fact f ON f.id = pff.fact_id
             WHERE pff.property_file_id = %s
             ORDER BY pff.fact_id
            """,
            (property_file_id,),
        )
        pf_facts = [{"fact_id": str(r[0]), "use": r[1], "snapshot_id": r[2]} for r in cur.fetchall()]
    conn.close()

    # jsonb columns already decoded by psycopg2; uuid columns come back as
    # uuid.UUID objects, not str -- normalize() expects str for its own
    # UUID_RE match, and json.dump needs plain str/dict/list anyway.
    for k, v in list(pf_row.items()):
        if hasattr(v, "hex") and not isinstance(v, (bytes, bytearray)):
            pf_row[k] = str(v)

    return normalize(pf_row, pf_facts)


def _rights_blocked_refusal(refusals):
    return next((r for r in refusals if r.get("code") == "RIGHTS_BLOCKED"), None)


def _geometry_tier_disabled_refusal(refusals):
    return next((r for r in refusals if r.get("code") == "GEOMETRY_TIER_DISABLED"), None)


def check_fixture(name, fixture_path, apn, digest, bless, failures):
    """One fixture class's full check: run the real composition, assert
    both refusals POSITIVELY (sec 6.6: "a golden file that lost a
    refusal is a regression" -- neither code's presence is left to the
    full-object compare alone, a bug there should never be able to hide
    a missing refusal), then the full normalized compare. Appends to the
    shared `failures` list rather than returning its own -- both fixture
    classes' checks contribute to ONE overall exit code, same as before
    P25 widened this from one fixture to two."""
    print(f"\n--- {name} ---")
    normalized, facts_normalized, composer_version_shape_ok = run_composition(apn, digest)
    output = {"property_file": normalized, "property_file_fact": facts_normalized}

    if bless:
        os.makedirs(os.path.dirname(fixture_path), exist_ok=True)
        with open(fixture_path, "w") as f:
            json.dump(output, f, indent=2, sort_keys=True)
            f.write("\n")
        print(f"GOLDEN: blessed {fixture_path}")
        return

    def check(label, condition, detail=""):
        status = "PASS" if condition else "FAIL"
        print(f"[{status}] {name}: {label}" + (f" -- {detail}" if detail and not condition else ""))
        if not condition:
            failures.append(f"{name}: {label}")

    check("composer_version is well-formed (compose@<sha>[-dirty] or compose@no-git:...)",
          composer_version_shape_ok)

    if not os.path.exists(fixture_path):
        check("golden fixture file exists", False, f"missing: {fixture_path} (run --bless once to create it)")
        return

    with open(fixture_path) as f:
        expected = json.load(f)

    actual_refusals = normalized.get("refusals") or []
    # P25: BOTH refusals asserted positively, every fixture, every run --
    # see this module's own docstring for why neither fixture can show
    # only one of the two today.
    check("exactly two refusals present", len(actual_refusals) == 2, f"got {len(actual_refusals)}")

    rights = _rights_blocked_refusal(actual_refusals)
    check("RIGHTS_BLOCKED refusal present", rights is not None, f"codes present: {[r.get('code') for r in actual_refusals]}")
    if rights:
        check("RIGHTS_BLOCKED stage is L8", rights.get("stage") == "L8", f"got {rights.get('stage')!r}")
        check("RIGHTS_BLOCKED cites the fixture's own licence_id",
              rights.get("detail", {}).get("licence_id") == ip.LICENCE_ID,
              f"got {rights.get('detail', {}).get('licence_id')!r}")
        check("RIGHTS_BLOCKED cites parcel.apn among its blocked field_keys",
              "parcel.apn" in rights.get("detail", {}).get("field_keys", []),
              f"got {rights.get('detail', {}).get('field_keys')!r}")

    geometry = _geometry_tier_disabled_refusal(actual_refusals)
    check("GEOMETRY_TIER_DISABLED refusal present", geometry is not None,
          f"codes present: {[r.get('code') for r in actual_refusals]}")
    if geometry:
        check("GEOMETRY_TIER_DISABLED stage is L7", geometry.get("stage") == "L7", f"got {geometry.get('stage')!r}")
        # I10: "refuse BY NAME" -- the refusal must identify WHICH
        # conclusion, not merely that something was refused.
        check("GEOMETRY_TIER_DISABLED names the refused conclusion (placement)",
              geometry.get("detail", {}).get("conclusion") == "placement",
              f"got {geometry.get('detail', {}).get('conclusion')!r}")

    check("normalized property_file matches the committed golden fixture",
          output == expected,
          f"\n  expected: {json.dumps(expected, indent=2, sort_keys=True)}"
          f"\n  actual:   {json.dumps(output, indent=2, sort_keys=True)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bless", action="store_true",
                         help="overwrite the committed fixtures with this run's output, "
                              "instead of comparing against them")
    args = parser.parse_args()

    print("GOLDEN: checking 2 of 4 fixture classes this run -- refused, geometry-disabled.")
    print(f"GOLDEN: NOT covered (see scripts/check_golden.py's own module docstring "
          f"and STANDING-BLOCKER.md for why): {', '.join(MISSING_CLASSES)}.")

    failures = []
    check_fixture("refused", FIXTURE_PATH, "GOLDEN-REFUSED-FIXTURE", GOLDEN_DIGEST, args.bless, failures)
    check_fixture("geometry-disabled", GEOMETRY_DISABLED_FIXTURE_PATH, "GOLDEN-GEOMETRY-DISABLED-FIXTURE",
                  GEOMETRY_DISABLED_GOLDEN_DIGEST, args.bless, failures)

    if args.bless:
        return 0

    print(f"\nGOLDEN SUMMARY: {'PASSED' if not failures else 'FAILED'} "
          f"({len(failures)} failure(s)). Coverage this run: 2/4 fixture classes "
          f"(refused, geometry-disabled). NOT covered: {', '.join(MISSING_CLASSES)}.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
