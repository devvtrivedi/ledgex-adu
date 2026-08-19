#!/usr/bin/env python3
"""make golden -- two of SPEC.md sec 1.2's four fixture classes (P20:
refused; P25: geometry-disabled), plus one additional fixture beyond
that taxonomy (P34: election_required, README finding #35 -- see this
module's own P34 note further down and SPEC.md sec 6.6's own P34
implementation note for why it is additional, not a fifth taxonomy
member).

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

Decided: exit code tracks ONLY whether the real, built checks are all
correct (0 = refused AND geometry-disabled AND election_required all
passed; 1 = any failed OR broke). The two absent taxonomy classes are
named explicitly, unconditionally, on EVERY run, pass or fail -- never
folded into a bare "PASSED" that could be misread as full coverage.
Same shape as db/tests/invariants.sql's known_gaps/test_skipped
sections (P9/P14): real coverage counted honestly, absence stated
loudly, neither silently inflated nor silently hidden.

P34 (README finding #35): a third fixture, election_required, checks
scripts/compose_property_file.py's new election parameter -- passing
election=None (the one case every pre-P34 caller of compose() already
exercises, since the parameter is new and optional) reaches L5's
ELECTION_REQUIRED refusal before any `rule` query is attempted, adding
a THIRD co-occurring refusal (alongside GEOMETRY_TIER_DISABLED and
RIGHTS_BLOCKED, same accumulation reasoning P25 already established
above) to this fixture specifically. The other two fixtures
(refused, geometry-disabled) now pass election="city" explicitly --
the one real, seeded rule -- so their own shape and refusal count are
UNCHANGED by this package; only election_required is new. This is
deliberately not counted as a fifth/replacement member of sec 1.2's
own four-class taxonomy (MISSING_CLASSES, below, is unchanged) -- it
is a real, additional check the taxonomy predates. election's own
ELECTION_NOT_SUPPORTED branch (election supplied, no CONCLUSION_RULE_KEYS
entry) is deliberately NOT given a fourth fixture here: mechanically
identical to this one (skip the `rule` query, append a refusal) with
only the code string differing -- proven instead at the pytest/script
level, scripts/test_compose_election.py, which is the check that
actually adds coverage a fourth near-byte-identical fixture would not.

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

  --bless overwrites ALL THREE tests/golden/ca_san_jose/{refused,
  geometry_disabled,election_required}.json with this run's own
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
# P34, README finding #35: a THIRD fixture, election_required -- see this
# module's own docstring update and SPEC.md sec 6.6's P34 implementation
# note for why this is deliberately NOT a fifth/replacement member of the
# original composed/partial/refused/geometry-disabled taxonomy MISSING_CLASSES
# tracks below (unchanged by this addition), but a real, additional check
# beyond it.
ELECTION_REQUIRED_FIXTURE_PATH = os.path.join(
    REPO_ROOT, "tests", "golden", "ca_san_jose", "election_required.json"
)
GOLDEN_CHANNEL = "paid_property_file"
GOLDEN_AS_OF = datetime.datetime(2099, 1, 1, tzinfo=datetime.timezone.utc)
GOLDEN_DIGEST = hashlib.sha256(b"golden-refused-fixture-v1").hexdigest()
GEOMETRY_DISABLED_GOLDEN_DIGEST = hashlib.sha256(b"golden-geometry-disabled-fixture-v1").hexdigest()
ELECTION_REQUIRED_GOLDEN_DIGEST = hashlib.sha256(b"golden-election-required-fixture-v1").hexdigest()

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
        #
        # P32, finding #36: ON CONFLICT (id) DO UPDATE, not DO NOTHING --
        # this is finding #32's exact shape (two independent seeders,
        # same PK, DO NOTHING), reintroduced one package after #32 was
        # fixed elsewhere. DO NOTHING would let this copy silently drift
        # from day4_sources.sql's own row with nothing to catch it --
        # ruleset_version is only rule_key@version, so a citation/
        # pack_version edit to one seeder alone would pass make golden
        # while the two rows quietly disagreed. DO UPDATE is verified
        # safe against 0013's rule_no_destructive_update() before relying
        # on it, not assumed: run directly against a real row, identical
        # values succeed with no exception (both of the trigger's own
        # guards short-circuit on IS NOT DISTINCT FROM); a deliberately
        # drifted column raises the exact "I18 violated" text. This is
        # strictly stronger than #32's own remedy could get for `source`
        # (no immutability trigger exists there) -- here, silent drift
        # becomes a loud, correctly-named exception naming exactly which
        # row disagrees, not merely prevented.
        # P33, finding #37: rule_no_delete (0013) makes this INSERT an
        # IRREVERSIBLE write -- once it lands, no principal can ever
        # remove this row from this database again. Gated, not routine:
        # only the row's genuine first-ever appearance in THIS database
        # needs confirmation (a second or third call within the same run
        # -- P34 added a third fixture class, so seed_reference_rows()
        # now runs three times per `make golden`, not two -- or a later
        # run against a database that already has it, is just
        # re-confirming/refreshing an irreversible action that already
        # happened -- victimless, same as any other idempotent seed
        # row here). Checked by existence, not by call count, so this
        # gate is correct regardless of which of the per-run calls
        # reaches it first. GOLDEN_ALLOW_RULE_SEED=1 is the explicit
        # confirmation -- set unconditionally in db.yml (CI's own
        # databases are disposable, torn down with the runner regardless
        # of what 0013 blocks) and left UNSET by default locally, so a
        # bare `make golden` against Makefile's own DATABASE_URL default
        # (ledgex_schema_check, the real shared dev database) fails
        # loud, before writing anything, instead of silently planting a
        # permanent row -- the exact risk finding #37 named.
        cur.execute("SELECT 1 FROM rule WHERE id = %s", ("ca_san_jose.adu_detached_max_height_city_standards.v1",))
        rule_row_exists = cur.fetchone() is not None
        if not rule_row_exists and os.environ.get("GOLDEN_ALLOW_RULE_SEED") != "1":
            raise SystemExit(
                "make golden is about to INSERT a rule row "
                "('ca_san_jose.adu_detached_max_height_city_standards.v1') that CANNOT ever "
                "be removed from this database again (0013's rule_no_delete raises "
                "unconditionally) -- this is a permanent, one-way action, not a routine "
                "check. Refusing by default so a bare `make golden` cannot silently plant "
                "this into a real, shared database (Makefile's own DATABASE_URL default is "
                "ledgex_schema_check). If this database is genuinely disposable and you "
                "intend this, re-run with GOLDEN_ALLOW_RULE_SEED=1. If it is not disposable, "
                "run `db/seeds/day4_sources.sql` against it deliberately instead, as its own "
                "considered action, not as a side effect of a check."
            )
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
            ON CONFLICT (id) DO UPDATE SET
                jurisdiction_id = EXCLUDED.jurisdiction_id,
                rule_key = EXCLUDED.rule_key,
                version = EXCLUDED.version,
                effective_from = EXCLUDED.effective_from,
                effective_to = EXCLUDED.effective_to,
                citation = EXCLUDED.citation,
                source_text_uri = EXCLUDED.source_text_uri,
                params = EXCLUDED.params,
                pack_version = EXCLUDED.pack_version,
                authored_by = EXCLUDED.authored_by,
                reviewed_by = EXCLUDED.reviewed_by,
                review_mode = EXCLUDED.review_mode,
                reviewed_at = EXCLUDED.reviewed_at,
                attestation_uri = EXCLUDED.attestation_uri
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
        for digest in (GOLDEN_DIGEST, GEOMETRY_DISABLED_GOLDEN_DIGEST, ELECTION_REQUIRED_GOLDEN_DIGEST):
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


def run_composition(apn, digest, election):
    conn = get_db()
    seed_reference_rows(conn)
    parcel_id = make_fixture_parcel_and_fact(conn, apn, ip.snapshot_id_for(digest))

    property_file_id = cpf.compose(conn, parcel_id, GOLDEN_CHANNEL, election=election, as_of=GOLDEN_AS_OF)
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


def _election_required_refusal(refusals):
    return next((r for r in refusals if r.get("code") == "ELECTION_REQUIRED"), None)


def check_fixture(name, fixture_path, apn, digest, election, expect_election_required, bless, failures):
    """One fixture class's full check: run the real composition, assert
    every expected refusal POSITIVELY (sec 6.6: "a golden file that lost a
    refusal is a regression" -- no code's presence is left to the
    full-object compare alone, a bug there should never be able to hide
    a missing refusal), then the full normalized compare. Appends to the
    shared `failures` list rather than returning its own -- all three
    fixture classes' checks contribute to ONE overall exit code, same as
    before P25 widened this from one fixture to two and P34 widened it
    again to three.

    expect_election_required (P34): RIGHTS_BLOCKED and GEOMETRY_TIER_DISABLED
    are asserted unconditionally, every fixture, every run -- unchanged
    since P25 (every real composition today hits both). ELECTION_REQUIRED
    is asserted only for the one fixture that supplies election=None; the
    other two now pass election="city" explicitly and must NOT carry it,
    so the expected total refusal count differs (3 vs 2) rather than being
    hardcoded to one number for every class."""
    print(f"\n--- {name} ---")
    normalized, facts_normalized, composer_version_shape_ok = run_composition(apn, digest, election)
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
    expected_count = 3 if expect_election_required else 2
    check(f"exactly {expected_count} refusal(s) present", len(actual_refusals) == expected_count,
          f"got {len(actual_refusals)}")

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

    election_required = _election_required_refusal(actual_refusals)
    if expect_election_required:
        check("ELECTION_REQUIRED refusal present", election_required is not None,
              f"codes present: {[r.get('code') for r in actual_refusals]}")
        if election_required:
            check("ELECTION_REQUIRED stage is L5", election_required.get("stage") == "L5",
                  f"got {election_required.get('stage')!r}")
            check("ELECTION_REQUIRED names the refused conclusion (placement)",
                  election_required.get("detail", {}).get("conclusion") == "placement",
                  f"got {election_required.get('detail', {}).get('conclusion')!r}")
    else:
        check("ELECTION_REQUIRED refusal absent (election='city' was supplied)",
              election_required is None, f"codes present: {[r.get('code') for r in actual_refusals]}")

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

    print("GOLDEN: checking 2 of 4 sec 1.2 fixture classes this run -- refused, geometry-disabled -- "
          "plus one additional fixture beyond that taxonomy (election_required, P34, README finding #35).")
    print(f"GOLDEN: NOT covered within sec 1.2's taxonomy (see scripts/check_golden.py's own module "
          f"docstring and STANDING-BLOCKER.md for why): {', '.join(MISSING_CLASSES)}.")

    failures = []
    # P34: refused/geometry-disabled now pass election="city" explicitly --
    # the one real, seeded rule -- so their own shape and refusal count are
    # unchanged by this package. election_required passes election=None,
    # the one case every pre-P34 caller already exercised (the parameter is
    # new and optional), and expects a third, additional refusal.
    check_fixture("refused", FIXTURE_PATH, "GOLDEN-REFUSED-FIXTURE", GOLDEN_DIGEST,
                  "city", False, args.bless, failures)
    check_fixture("geometry-disabled", GEOMETRY_DISABLED_FIXTURE_PATH, "GOLDEN-GEOMETRY-DISABLED-FIXTURE",
                  GEOMETRY_DISABLED_GOLDEN_DIGEST, "city", False, args.bless, failures)
    check_fixture("election-required", ELECTION_REQUIRED_FIXTURE_PATH, "GOLDEN-ELECTION-REQUIRED-FIXTURE",
                  ELECTION_REQUIRED_GOLDEN_DIGEST, None, True, args.bless, failures)

    if args.bless:
        return 0

    print(f"\nGOLDEN SUMMARY: {'PASSED' if not failures else 'FAILED'} "
          f"({len(failures)} failure(s)). Coverage this run: 2/4 sec 1.2 fixture classes "
          f"(refused, geometry-disabled) plus 1 additional fixture beyond that taxonomy "
          f"(election_required). NOT covered within sec 1.2's taxonomy: {', '.join(MISSING_CLASSES)}.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
