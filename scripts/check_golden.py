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
D15 (P59): STANDING-BLOCKER.md's original "every licence_channel row is
allowed=false" is no longer true without qualification -- P55's scoped
unblock flipped the api channel to allowed=true for the two *_api_2026_08
licences specifically (cleared_by/cleared_at/evidence_uri remain NULL;
this is a scoped, diligence-incomplete decision, not full clearance --
see this file's own seed_reference_rows() below, and
prompts/P55-scoped-unblock.md). Every OTHER channel, and every other
licence, remains allowed=false pending counsel/owner clearance that has
not happened. compose_property_file.py's I6 rights gate still blocks
every touched fact on THESE fixtures' own channel (paid_property_file, not
api) for every parcel -- correctly, because that is genuinely the rights
state for that channel today, not a code gap. Building a composed/partial
fixture on paid_property_file would still mean fabricating a licence
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

P53: LICENCE_UNKNOWN (the L0/LD-1 jurisdiction gate, prompts/P53-l0-gate.md,
design D-C) joins RIGHTS_BLOCKED and GEOMETRY_TIER_DISABLED on every single
composition today, for the identical reason those two already do: no
jurisdiction.incorporated fact is ever seeded for these fixtures' parcels,
and ca_san_jose now declares jurisdiction.boundary_source_id (0056). This
pass clears nothing -- the fixtures were always morally entitled to this
refusal; it simply had no runtime representation to trigger it before now.
D6 (P59): the refused and geometry-disabled fixtures carry THREE refusals
each after this (RIGHTS_BLOCKED, GEOMETRY_TIER_DISABLED, LICENCE_UNKNOWN)
-- election_required carries FOUR (those three plus its own
ELECTION_REQUIRED, see the P34 note below), not three; this docstring
previously claimed "all three real fixtures now carry THREE refusals,"
which the code itself has never asserted for election_required.

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

Exit code 0 = all three checks (refused, geometry-disabled,
election_required) passed. Exit code 1 = any failed.
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
import psycopg2  # noqa: E402
from infra.env import _is_local, resolved_host  # noqa: E402

# P56 containment (prompts/P56-fixture-contamination-boundary.md close-out).
# This file's own seed_reference_rows()/make_fixture_parcel_and_fact() write
# real snapshot/parcel/fact rows under the REAL ca_san_jose.parcels source id
# and the REAL current licence id, request='{}', bypassing job_run entirely --
# the identical shape README finding #53 names, just a fourth independent
# writer of it (P56 Phase 1 design doc §2.4). infra.env.get_db() reads plain
# DATABASE_URL, which this file used to call directly -- exactly how this
# repo's own freshly-rebuilt ledgex_schema_check was contaminated hours after
# being certified clean, 2026-08-23. GOLDEN_DATABASE_URL is a dedicated
# variable, modelled on scripts/smoke_real.py's own SMOKE_DATABASE_URL
# (step_env(), P50): never falls back to DATABASE_URL under any name, refuses
# a non-local host outright with NO override flag (D3: this family refuses,
# it does not warn-and-continue -- a recorded anomaly nobody reads, per #53,
# is not a boundary), and refuses loudly if the target isn't there or isn't
# migrated+seeded, naming the exact commands that fix it rather than creating
# anything itself.
DEFAULT_GOLDEN_DB = "postgresql://localhost/ledgex_golden"


def golden_get_db():
    golden_url = os.environ.get("GOLDEN_DATABASE_URL") or DEFAULT_GOLDEN_DB

    host = resolved_host(golden_url)
    if not _is_local(golden_url):
        raise SystemExit(
            "refusing to run make golden: GOLDEN_DATABASE_URL resolves to host "
            f"{host!r}, which is not local. This target makes PERMANENT writes "
            "(fact_no_delete/fact_no_update -- 0017, 0007/0040; snapshot_no_update/"
            "_no_delete -- 0021) under the REAL ca_san_jose.parcels source id and "
            "the REAL current licence id, every run. There is no override flag for "
            "this refusal, on the same reasoning scripts/smoke_real.py's own "
            "step_env() already applies to SMOKE_DATABASE_URL: there is no "
            "legitimate reason to point this target at a non-local database.\n"
            f"Set GOLDEN_DATABASE_URL to a local database, e.g. {DEFAULT_GOLDEN_DB}"
        )

    setup_commands = (
        f"    createdb ledgex_golden\n"
        f"    make schema DATABASE_URL={DEFAULT_GOLDEN_DB}\n"
        f"    psql {DEFAULT_GOLDEN_DB} -v ON_ERROR_STOP=1 -f db/seeds/day4_sources.sql"
    )
    try:
        conn = psycopg2.connect(golden_url)
    except Exception as e:
        raise SystemExit(
            f"cannot connect to the golden database ({type(e).__name__}: {str(e).strip()}).\n"
            f"One-time setup, from the repo root:\n{setup_commands}"
        )
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT count(*) FROM schema_migrations")
                n_ledger = cur.fetchone()[0]
            except Exception:
                conn.rollback()
                raise SystemExit(
                    "schema_migrations does not exist -- ledgex_golden has never been "
                    f"migrated. One-time setup:\n{setup_commands}"
                )
            mig_dir = os.path.join(REPO_ROOT, "db", "migrations")
            n_files = len([f for f in os.listdir(mig_dir) if f.endswith(".sql")])
            if n_ledger < n_files:
                conn.rollback()
                raise SystemExit(
                    f"schema_migrations has {n_ledger} row(s) but db/migrations/ has "
                    f"{n_files} .sql file(s) -- ledgex_golden is behind. Run:\n"
                    f"    make migrate DATABASE_URL={golden_url}"
                )
            cur.execute("SELECT 1 FROM source WHERE id = 'ca_san_jose.parcels'")
            if cur.fetchone() is None:
                conn.rollback()
                raise SystemExit(
                    "db/seeds/day4_sources.sql has not been applied to ledgex_golden "
                    f"(no ca_san_jose.parcels source row). Run:\n"
                    f"    psql {golden_url} -v ON_ERROR_STOP=1 -f db/seeds/day4_sources.sql"
                )
    except SystemExit:
        conn.close()
        raise
    conn.rollback()
    return conn


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
        # P55: ip.LICENCE_ID is now 'cc_by_4_0_api_2026_08', not the original
        # 'cc_by_4_0' this INSERT's literal VALUES were written for -- kept
        # byte-identical to db/seeds/day4_sources.sql's own row for this id
        # (the same "every seeder of it must agree exactly" discipline the
        # 'unknown' licence below already follows), not the old text, so a
        # `make golden` run against a truly schema-only database (before
        # day4_sources.sql ever reaches it) cannot permanently (licence is
        # immutable, 0027) plant a mismatched row under this id.
        cur.execute(
            """
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, terms_url, observed_at, cleared_by, cleared_at,
                                  notes)
            VALUES (%s, 'CC BY 4.0 (api channel, scoped 2026-08)', 'attribution', 'allowed',
                    'allowed', 'Data © City of San José',
                    'https://creativecommons.org/licenses/by/4.0/', '2026-07-31'::timestamptz,
                    NULL, NULL,
                    'Owner decision 2026-08-22: licence terms (CC BY 4.0) are identified and '
                    'permit this use (commercial use and redistribution both allowed per the '
                    'licence text itself). Opened for the api channel only -- viewer-only '
                    'display of already-ingested facts. Written confirmation, evidence and '
                    'counsel review remain outstanding (cleared_by/cleared_at/evidence_uri '
                    'NULL, deliberately) -- this row does NOT assert diligence is complete. '
                    'See prompts/P55-scoped-unblock.md and licence_channel.rationale (per '
                    'channel) for the authoritative per-channel decision text. '
                    'SUCCESSION (P55 §12.6): this id did not exist before 2026-08-22 -- it '
                    'was minted then, as a scoping decision (which channel may use already-'
                    'identified terms), under CC BY 4.0 terms whose TEXT was observed '
                    '2026-07-31 (hence observed_at above carries that earlier date, not '
                    'today -- the terms predate this id; this id records a decision about '
                    'them, not a fresh reading of them). Any snapshot row citing this '
                    'licence_id under an EARLIER fetched_at records "these bytes were '
                    'fetched under the terms this id represents," never "this id existed at '
                    'the time of that fetch" -- read literally as the latter it would be '
                    'anachronistic, and must not be read that way.')
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.LICENCE_ID,),
        )
        # licence_channel rows, byte-identical to day4_sources.sql's own six
        # rows for this id -- without these, a make-golden-first database
        # would leave 'api' default-deny (absent row) forever on this
        # immutable id, silently diverging from day4_sources.sql's own
        # allowed=true, functionally, not just cosmetically (unlike the
        # licence row's own display_name/notes text, nothing here is merely
        # descriptive -- I6 reads this table directly).
        cur.execute(
            """
            INSERT INTO licence_channel (licence_id, channel, allowed, rationale) VALUES
              (%s, 'api', true,
               'Owner decision 2026-08-22: licence terms are identified and permit this use. '
               'Opened for viewer-only display (api channel) of already-ingested facts. '
               'Written confirmation / evidence / counsel review remain outstanding -- this '
               'is NOT a diligence-complete signal. See prompts/P55-scoped-unblock.md.'),
              (%s, 'free_snapshot', false,
               'Licence identification confirmed; counsel/owner sign-off Pending. No channel '
               'is cleared for output beyond the api-channel decision recorded above until '
               'sign-off completes.'),
              (%s, 'paid_property_file', false,
               'Licence identification confirmed; counsel/owner sign-off Pending. No channel '
               'is cleared for output beyond the api-channel decision recorded above until '
               'sign-off completes. paid_property_file additionally depends on the L0 gate '
               '(P53, still closed -- no verified ca_san_jose.city_limits ingest exists) and '
               'the boundary cross-check + counsel review named as its own precondition in '
               'P52 §10 / P53 §11, unaffected by this pass either way.'),
              (%s, 'bulk_export', false,
               'Licence identification confirmed; counsel/owner sign-off Pending. No channel '
               'is cleared for output beyond the api-channel decision recorded above until '
               'sign-off completes.'),
              (%s, 'analytics', false,
               'Licence identification confirmed; counsel/owner sign-off Pending. No channel '
               'is cleared for output beyond the api-channel decision recorded above until '
               'sign-off completes.'),
              (%s, 'model_training', false,
               'Denied pending review: no one has yet read cc_by_4_0''s terms as applied '
               'specifically to model-training use, separately from the api-channel decision '
               'above. Requires its own rationale before this can flip.')
            ON CONFLICT (licence_id, channel) DO NOTHING
            """,
            (ip.LICENCE_ID,) * 6,
        )
        cur.execute(
            """
            INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, supported)
            VALUES (%s, 'City of San Jose', 'city', 'CA', 'v1.0', true)
            ON CONFLICT (id) DO NOTHING
            """,
            (ip.JURISDICTION_ID,),
        )

        # P53 (prompts/P53-l0-gate.md): the L0/LD-1 gate's own reference
        # data, seeded here TOO, independently of db/seeds/day4_sources.sql
        # -- this is finding #32/#36's exact shape (two independent
        # seeders, same rows) if only one of them sets it. make golden must
        # exercise the real gate whether or not day4_sources.sql happened
        # to run first (it does, in CI, since P36 -- but a bare local
        # `make golden` against a fresh, schema-only database must not
        # silently skip the gate just because this function's own seed ran
        # alone). Byte-identical values to day4_sources.sql's own 'unknown'
        # licence row and this migration's own (0056) -- licence is
        # immutable (0027) with no IS-NOT-DISTINCT-FROM carve-out, so this
        # can never be DO UPDATE; every seeder of it must agree exactly,
        # the same discipline this function already follows for cc_by_4_0
        # just above.
        cur.execute(
            """
            INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution,
                                  attribution_text, terms_url, evidence_uri, observed_at,
                                  cleared_by, cleared_at, notes)
            VALUES ('unknown', 'Licence not yet observed', 'unknown', 'unknown', 'unknown',
                    NULL, NULL, NULL, '2026-08-22'::timestamptz, NULL, NULL,
                    'LD-1 gate source (jurisdictions/ca_san_jose/sources.yaml: '
                    'ca_san_jose.city_limits). Licence text never observed -- id, '
                    'display_name and every restriction/commercial_use/redistribution '
                    'value match jurisdictions/ca_san_jose/licences.yaml (docs/'
                    'LEDGEX_SPEC.md sec 7.2, id=unknown) verbatim, not independently '
                    'invented. observed_at records the date this row was created (the '
                    'date its UNKNOWN-NESS was recorded), never a date on which the '
                    'licence''s actual terms were read -- no such reading has ever '
                    'happened. See prompts/P53-l0-gate.md.')
            ON CONFLICT (id) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO licence_channel (licence_id, channel, allowed, rationale)
            SELECT 'unknown', c, false,
                   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). '
                   'No channel is ever cleared for an unidentified licence -- identifying '
                   'it requires a new licence row (0027), never an UPDATE to this one.'
              FROM unnest(enum_range(NULL::output_channel)) AS c
            ON CONFLICT (licence_id, channel) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description)
            VALUES ('jurisdiction.incorporated', 'Jurisdiction incorporated', 'public_record',
                    'boolean', 'jurisdiction',
                    'Whether this parcel resolves within the jurisdiction''s incorporated '
                    'boundary, per jurisdictions/ca_san_jose/sources.yaml''s own '
                    'ca_san_jose.city_limits declaration (the L0 gate, sec 1.1). No source '
                    'currently supplies this field as a fact -- see prompts/P53-l0-gate.md; '
                    'the field is declared so the composer''s absence-check has a real '
                    'field_key to require, not so a value exists yet.')
            ON CONFLICT (field_key) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status,
                                 phase_status_reason, endpoint_url, licence_id, active)
            VALUES ('ca_san_jose.city_limits', %s, 'City limits / jurisdiction boundary',
                    'City of San Jose', 'manual', 'blocked_rights',
                    'Licence not observed. Supplies the L0 gate, so under I6 this blocks ALL '
                    'channels including free_snapshot. Launch dependency LD-1. method=''manual'' '
                    'here, not sources.yaml''s own declared method: direct -- no real, verified '
                    'endpoint exists yet (P53-l0-gate.md Obstacle 2); this row exists as '
                    'jurisdiction.boundary_source_id''s FK target, never as an ingest path.',
                    NULL, 'unknown', false)
            ON CONFLICT (id) DO UPDATE SET
                jurisdiction_id = EXCLUDED.jurisdiction_id,
                display_name = EXCLUDED.display_name,
                steward = EXCLUDED.steward,
                method = EXCLUDED.method,
                phase_status = EXCLUDED.phase_status,
                phase_status_reason = EXCLUDED.phase_status_reason,
                endpoint_url = EXCLUDED.endpoint_url,
                licence_id = EXCLUDED.licence_id,
                active = EXCLUDED.active
            """,
            (ip.JURISDICTION_ID,),
        )
        cur.execute(
            """
            UPDATE jurisdiction SET boundary_source_id = 'ca_san_jose.city_limits'
             WHERE id = %s AND boundary_source_id IS NULL
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
    # B2 (P59C): UUID_RE.match (not .search) is a WHOLE-STRING match --
    # a UUID embedded WITHIN a larger string (e.g. a refusal message like
    # "No parcel exists with id=<uuid>...", the shape a PARCEL_NO_FACTS/
    # PARCEL_REFERENCE_UNKNOWN-class fixture's own message text could
    # carry) is NOT tokenized here. CONFIRMED-NOT-AN-ISSUE, not fixed: no
    # such fixture exists today (check_golden.py's three fixture classes
    # -- refused, geometry-disabled, election_required -- carry their
    # UUIDs only as their OWN dedicated whole-string fields, e.g.
    # property_file.id, never embedded in prose), and if one ever did,
    # this fails LOUD, not silent -- the untokenized UUID is fresh every
    # run (uuid4()), so the blessed fixture's frozen copy would mismatch
    # the live run's own value on every subsequent comparison, forever,
    # not pass incorrectly once. If a future fixture DOES embed a UUID in
    # message/prose text, tokenize that string with UUID_RE.sub(...)
    # (a substring replace) before blessing it, or the fixture can never
    # be blessed stably.
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
    conn = golden_get_db()
    seed_reference_rows(conn)
    parcel_id = make_fixture_parcel_and_fact(conn, apn, ip.snapshot_id_for(digest))

    # P38, README finding #41: compose() returns Result[T] uniformly now
    # -- .is_refused checked before .value is ever touched. The old
    # `if property_file_id is None:` here bound the raw return and never
    # saw a Result at all; fed one (PARCEL_REFERENCE_UNKNOWN), it flowed
    # on as truthy and failed downstream with a misleading `can't adapt
    # type 'Result'` -- confirmed directly against a real database before
    # this fix, not inferred. Genuinely unreachable through this
    # function's own fixture parcel (created moments above), same as
    # before -- but no longer silently wrong if that ever changes.
    result = cpf.compose(conn, parcel_id, GOLDEN_CHANNEL, election=election, as_of=GOLDEN_AS_OF)
    if result.is_refused:
        raise SystemExit(
            f"compose() refused before writing a property_file row: "
            f"{result.refusal.code}: {result.refusal.message} -- this fixture's own parcel "
            f"was just created above, so this should be unreachable; see this script's own "
            f"module docstring."
        )
    if result.value is cpf.NOTHING_COMPOSED:
        raise SystemExit(
            "compose() returned NOTHING_COMPOSED (rights gate PASSED) -- this means "
            "licence_channel has been flipped to allowed=true since STANDING-BLOCKER.md "
            "was last true. That is real news, not a fixture bug -- see this "
            "script's own module docstring."
        )
    property_file_id = result.value

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


def _licence_unknown_refusal(refusals):
    return next((r for r in refusals if r.get("code") == "LICENCE_UNKNOWN"), None)


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

    expect_election_required (P34): RIGHTS_BLOCKED, GEOMETRY_TIER_DISABLED
    and LICENCE_UNKNOWN (P53: the L0/LD-1 gate) are asserted unconditionally,
    every fixture, every run -- every real composition today hits all three.
    ELECTION_REQUIRED is asserted only for the one fixture that supplies
    election=None; the other two now pass election="city" explicitly and
    must NOT carry it, so the expected total refusal count differs (4 vs 3)
    rather than being hardcoded to one number for every class."""
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
    # P53: +1 across every fixture -- ca_san_jose now declares
    # boundary_source_id (0056 / db/seeds/day4_sources.sql), and no
    # jurisdiction.incorporated fact is ever seeded for this fixture's
    # parcel, so the L0 gate refuses LICENCE_UNKNOWN on every composition,
    # same as the other two/three refusals every real composition has
    # always carried. See prompts/P53-l0-gate.md sec 6 for the before/after.
    expected_count = 4 if expect_election_required else 3
    check(f"exactly {expected_count} refusal(s) present", len(actual_refusals) == expected_count,
          f"got {len(actual_refusals)}")

    licence_unknown = _licence_unknown_refusal(actual_refusals)
    check("LICENCE_UNKNOWN refusal present (P53: the L0/LD-1 gate)", licence_unknown is not None,
          f"codes present: {[r.get('code') for r in actual_refusals]}")
    if licence_unknown:
        check("LICENCE_UNKNOWN stage is L0", licence_unknown.get("stage") == "L0",
              f"got {licence_unknown.get('stage')!r}")
        check("LICENCE_UNKNOWN cites ca_san_jose's own boundary_source_id",
              licence_unknown.get("detail", {}).get("boundary_source_id") == "ca_san_jose.city_limits",
              f"got {licence_unknown.get('detail', {})}")
        check("LICENCE_UNKNOWN cites jurisdiction.incorporated as the missing field",
              licence_unknown.get("detail", {}).get("field_key") == "jurisdiction.incorporated",
              f"got {licence_unknown.get('detail', {})}")

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

    print(f"GOLDEN: writing to {os.environ.get('GOLDEN_DATABASE_URL') or DEFAULT_GOLDEN_DB} "
          "(GOLDEN_DATABASE_URL, never DATABASE_URL -- P56 containment).")
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
