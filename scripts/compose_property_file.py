#!/usr/bin/env python3
"""Minimal composer: prove the refusal path, before any success path exists.

A FOURTH script, still not core/ -- module boundaries come after a
non-ingest consumer exists to compare against the three ingests, and
this is that consumer, not the trigger to extract one yet.

env/get_db were previously copied from ingest_parcels.py's pattern;
imported from infra/ now instead, the first extraction slice out of
all four scripts -- see infra/__init__.py for why that's not core/.

Scope, deliberately small, per instruction:
  - read one parcel's current facts via current_fact_at(now()) (C5, 0036)
  - L7 (P25): evaluate the "placement" geometry-dependent conclusion
    against this jurisdiction's geometry_tier_enabled -- core/calc,
    refuse-only, never computes or persists a derived fact
  - apply the I6 rights gate (L8) to every TOUCHED fact, not just
    rendered ones -- runs regardless of L7's own outcome, see P25's own
    report for why (refusals accumulate across stages, they do not
    short-circuit the pipeline)
  - on any refusal from either stage: write property_file(status='refused',
    refusals populated -- L7's and L8's together, delivered_at NULL) and
    link every touched fact via property_file_fact
  - on zero refusals from either stage: report that both gates passed
    and STOP -- no rendering, no payload assembly, no success/partial
    path. That is real, unbuilt scope, not a case this script fakes an
    answer for.

WHY refusal first, and why every run today refuses. 0030 set every
licence_channel row (cc0, cc_by_4_0, all six channels each) to
allowed=false pending counsel clearance. Every fact this project has
ingested carries one of those two licences. So the I6 gate blocks
every touched fact, on every channel, for every parcel, right now --
not because this composer is broken, but because the rights position
IS "nothing is cleared yet." Proving that is the actual milestone:
a well-formed refused property_file, for the right reason, is a
positive result here, not a placeholder for a success path that
doesn't exist yet. geometry_tier_enabled defaults false for every
jurisdiction too (0002_registries.sql), so a real composition today
always carries at least a GEOMETRY_TIER_DISABLED refusal alongside
RIGHTS_BLOCKED -- two independent, honestly-arrived-at reasons the same
file refuses, not one masking the other.

use='input' for every property_file_fact row this script writes, not
'gate' or 'rendered': 'gate' (per 0012's own comment) names facts that
resolve JURISDICTION and never appear in a payload (e.g. a
city_limits-shaped fact) -- nothing ingested so far plays that role.
'rendered' would claim these facts appear in a delivered payload, which
is false for a refused file (I6: nothing renders). 'input' is what is
actually true: every touched fact was read as an input to the (aborted)
composition attempt.

Refusal codes this script can emit, all already named in §9's refusal
code table, none invented for this script: RIGHTS_BLOCKED (L8),
GEOMETRY_TIER_DISABLED (L7, P25), RULE_UNAVAILABLE (L5, P31),
ELECTION_REQUIRED and ELECTION_NOT_SUPPORTED (both L5, P34, README
finding #35 -- see 0053's own migration header for why these are two
codes, not one, and not folded into RULE_UNAVAILABLE), PARCEL_REFERENCE_
UNKNOWN (L0) and PARCEL_NO_FACTS (L8, both P37, README finding #40 --
see 0055's own migration header for why neither reuses PARCEL_NOT_FOUND
or COVERAGE_GAP/INSUFFICIENT_COVERAGE despite the adjacent names), and
LICENCE_UNKNOWN (L0, P53, prompts/P53-l0-gate.md -- the jurisdiction
gate; D14, P59: this list previously omitted it, though it is the one
refusal code every current real composition against a real database
emits, since no jurisdiction.incorporated fact is ever seeded for a real
parcel yet).
PARCEL_REFERENCE_UNKNOWN is the one code this script returns as a typed
Result directly, never as a property_file row -- see compose()'s own
docstring.
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
import psycopg2.extensions
import psycopg2.extras

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from infra.env import env, get_db  # noqa: E402
from core.calc import evaluate_geometry_dependent_conclusion  # noqa: E402
from core.model import Refusal, Result  # noqa: E402
from core.rules import select_effective_rule  # noqa: E402
from core.rights import KNOWN_CHANNELS, evaluate_rights_gate  # noqa: E402

# P31: Shape 1 -- a hardcoded, narrowly-scoped constant naming which
# rule_key each conclusion this composer knows about depends on, for
# ONE jurisdiction only. NOT a general mechanism: a second jurisdiction's
# own rule for "placement" forces this exact dict to be rewritten (at
# minimum keyed on jurisdiction_id too) -- accepted knowingly, per the
# founder's own ratified decision (prompts/P31-l5-refuse-first-one-real-
# rule.md section 2). jurisdictions/ca_san_jose/conclusions.yaml (sec
# 7.4) remains undesigned and is not what this constant is.
#
# Lives here, not in core/rules.py: this is a jurisdiction-scoped fact,
# and core/ must contain no jurisdiction name (I1) -- confirmed via
# make check-boundary, not assumed. This is the same home
# ingest_parcels.py/ingest_zoning_permits.py already use for their own
# jurisdiction-scoped SOURCE_ID/JURISDICTION_ID constants.
#
# P34, README finding #35: generalized from {conclusion: rule_key} to
# {(conclusion, election): rule_key} -- Bulletin #210 page 3's own words,
# "the standards cannot be mixed," mean "placement" has no single
# rule_key at all; it has one PER regime the applicant elects. Still
# Shape 1 (hardcoded, one jurisdiction, now also one election-vocabulary
# -- not a general mechanism): only the ("placement", "city") entry
# exists. A caller supplying election="state" finds no entry, on
# purpose -- this composer has not been taught a State-standards
# rule_key yet (README finding #35's own bulletin footer names the real
# next source, HCD's ADU Handbook, not fetched or read here; seeding it
# is its own later package, same pacing P31 used for the first rule).
# ("placement", "state") is deliberately absent, not stubbed to None or
# any other placeholder -- .get()'s own None return on a missing key is
# what ELECTION_NOT_SUPPORTED (0053, this package) refuses on.
CONCLUSION_RULE_KEYS = {
    ("placement", "city"): "adu.detached.max_height.city_standards",
}

# The only two literal values Bulletin #210 names (§9.1's own "City
# Standards" / "State Standards" vocabulary) -- validated at the Python
# boundary, not left to fail against property_file_election_known's DB
# CHECK (0052). compose() is called directly today (scripts/CLI,
# scripts/check_golden.py), never from an untrusted HTTP body -- a value
# outside this set is a caller/programmer error, not a customer input
# this function must refuse gracefully, so it raises immediately rather
# than manufacturing a third refusal code for "not even a real election."
KNOWN_ELECTIONS = ("city", "state")

class _NothingComposed:
    """P38, README finding #41. compose() returns Result[T] uniformly --
    see compose()'s own docstring for the full argument (I8's guarded
    Result.value/.refusal accessors make a caller's forgotten type check
    raise loudly and automatically, rather than requiring every call site
    to remember its own isinstance assertion, the discipline gap that
    produced finding #41 in the first place). Result.ok(None) is itself
    invalid (core.model.Result's own __init__ guard: exactly one of
    value/refusal, never neither) -- NOTHING_COMPOSED is the sentinel
    that stands in for "the rights gate passed, nothing was refused,
    nothing was written" without smuggling a real None through a
    wrapper that structurally forbids it. A class, not a bare object(),
    so its repr is self-describing in a traceback or a stray print,
    rather than "<object object at 0x...>"."""
    def __repr__(self):
        return "NOTHING_COMPOSED"


NOTHING_COMPOSED = _NothingComposed()


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


def resolve_parcel_id_by_apn(conn, apn):
    """Resolve apn to exactly one parcel id -- the --parcel-apn convenience
    path. 0034 dropped parcel's (jurisdiction_id, apn) uniqueness (49
    collisions measured at the time; 44 in the current live snapshot,
    dataset drift since -- see Fix 3's report) specifically because APN is
    not a reliable identity. A plain WHERE apn = %s / fetchone() silently
    picks whichever row Postgres happens to return first for a colliding
    apn -- an arbitrary, unstable choice with no error, no log, nothing
    telling the caller a choice was even made. Never do that: on a
    collision, name every candidate id and stop. --parcel-id exists
    precisely so a caller who already knows which parcel they mean never
    has to go through this resolution at all."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM parcel WHERE apn = %s ORDER BY id", (apn,))
        rows = cur.fetchall()
    if not rows:
        raise SystemExit(f"no parcel with apn={apn!r}")
    if len(rows) > 1:
        ids = [str(r[0]) for r in rows]
        raise SystemExit(
            f"apn={apn!r} matches {len(ids)} parcels -- ambiguous (0034 dropped APN "
            f"uniqueness). Candidates: {ids}. Pass one of these to --parcel-id instead "
            f"of --parcel-apn; this script will never guess which one you meant."
        )
    return rows[0][0]


def compose(conn, parcel_id, channel, election=None, as_of=None):
    """P39, corrected by P46 (README finding #48 -- the original review graded
    this a Medium defect; re-reading it against the real two exit paths below
    found the claim narrower than reported, not wrong in the same way). compose()
    OWNS THE TRANSACTION BOUNDARY; _compose() below does the work. Every argument
    for the return contract, the three states and the refusal accumulation lives
    on _compose's own docstring.

    THIS WRAPPER HAS TWO EXITS WITH DIFFERENT TRANSACTION GUARANTEES, not one
    uniform guarantee -- read both before assuming either applies to the other:

      - VALID channel (in KNOWN_CHANNELS): control reaches the try/finally below.
        _compose() runs -- and whether it returns the written-row state (already
        conn.commit()'d, by _compose itself), one of the two non-writing states,
        or raises, this wrapper's own `finally` ends whatever transaction is left
        open on `conn` before compose() returns to its caller. The connection is
        always IDLE by the time this exit is observed.
      - INVALID channel (not in KNOWN_CHANNELS): raises ValueError BEFORE the
        try/finally begins -- before this function has issued one statement on
        `conn`. compose() does not open, commit or roll back anything on this
        path: whatever transaction `conn` was already in (open or idle) when
        compose() was called is exactly what the caller has when the ValueError
        propagates. This is NOT the first exit's guarantee restated -- compose()
        never touches a transaction here, it does not "leave one open" in the
        sense of having opened one and failed to close it. A caller with its own
        uncommitted work in progress before calling compose() with a bad channel
        keeps that work exactly as open as it left it.

    WHY THE SECOND EXIT WAS LEFT AS-IS RATHER THAN MADE TO MATCH THE FIRST
    (considered, not silently decided): making the invalid-channel path also
    roll back `conn` would mean compose() reaching into and discarding a
    caller's own pre-existing, uncommitted transaction as a side effect of an
    input-validation error detected before compose() has done any work at all
    -- a STRONGER, more surprising claim on the caller's connection than the
    current code makes, not a weaker one. None of the real call sites
    listed below need it: an invalid channel reaching compose() is a
    programming error on the caller's side (a hardcoded literal, not
    user input at this layer), caught in development, not a runtime condition
    a caller's transaction discipline should have to defend against.

    THE GAP THIS CLOSES (README finding #42). _compose() opens a cursor and
    issues SELECTs immediately, which starts a transaction (infra.env.get_db
    sets autocommit = False). Only ONE of its three exits ended that
    transaction -- the written-row path, via its own conn.commit(). Measured
    directly against a real database, not inferred:

        PARCEL_REFERENCE_UNKNOWN return -> get_transaction_status() == 2 INTRANS
        NOTHING_COMPOSED return        -> get_transaction_status() == 2 INTRANS
        unknown-channel raise          -> get_transaction_status() == 3 INERROR

    and, because nothing rolled back that INERROR, the very next compose() call
    on the same connection died with `InFailedSqlTransaction: current
    transaction is aborted` -- a valid request failing for a reason that names
    nothing about the bad request that actually caused it. Invisible under the
    CLI (one process, one composition, conn.close() in a finally) and invisible
    under every current test suite (each builds its own connection). Live the
    moment api/ reuses a connection across requests, which is the whole reason
    this fix lands before api/ rather than with it.

    WHY try/finally, NOT `with conn:`. psycopg2's connection context manager is
    a TRANSACTION manager: it COMMITS on clean exit. That is wrong on both
    non-writing paths -- neither wrote anything, and committing a read-only
    transaction to end it would also silently commit whatever a future edit
    added before those returns. It would also sit awkwardly around _compose's
    own explicit conn.commit(), leaving two things that both believe they own
    the commit. try/finally keeps the existing commit exactly where it is and
    adds only the missing half.

    WHY THE STATUS CHECK rather than an unconditional rollback: after a
    successful commit the connection is already IDLE, and issuing ROLLBACK
    there makes Postgres emit `WARNING: there is no transaction in progress` on
    every single successful composition. Checking first keeps a clean run
    silent.

    PRECONDITION ON THE CALLER, stated because this wrapper cannot enforce it,
    and scoped to the VALID-channel exit above -- the invalid-channel exit
    touches no transaction at all, so it carries no such precondition:
    a caller must COMMIT its own fixture/setup writes BEFORE calling compose()
    with a channel that will pass the KNOWN_CHANNELS check, because the
    rollback in `finally` ends whatever transaction is open on `conn`,
    including work the caller started. D14 (P59): re-verified fresh against
    the current tree, by reading each call site rather than reusing an old
    count -- NINE real call sites today, not five (five was the original
    P41 count; P53's own test_compose_l0_gate.py added three more test
    functions calling compose(), and this pass's own C3 fix added a
    fourth, test_explicit_false_value_still_refuses -- five + one more from
    l0_gate's own four = nine): check_golden.run_composition
    (seed_reference_rows and make_fixture_parcel_and_fact both commit),
    test_compose_election._seed, test_compose_parcel_refusals (both call
    sites), test_compose_geometry_tier_used._seed, and
    test_compose_l0_gate.py's four test functions
    (test_negative_control_jurisdiction_unresolvable_still_refuses,
    test_positive_companion_jurisdiction_resolvable_does_not_refuse,
    test_explicit_false_value_still_refuses,
    test_untouched_jurisdiction_never_gates -- each commits its own
    `_seed_l0_gate_fixture`/`_seed_fact` calls before its own compose()).
    """
    if channel not in KNOWN_CHANNELS:
        raise ValueError(
            f"channel={channel!r} is not one of {KNOWN_CHANNELS!r} -- an "
            f"invalid-request (400) in §9's own error taxonomy, not a refusal: "
            f"§9's refusal table has no code for a channel that does not exist, "
            f"and inventing one would need a spec bump and a §12 row (I17). "
            f"Raised HERE, at the boundary, so it never reaches the "
            f"licence_channel query as a bare enum literal -- which is where it "
            f"used to fail, as psycopg2 InvalidTextRepresentation naming the "
            f"enum but not this parameter, after a transaction was already open."
        )

    try:
        return _compose(conn, parcel_id, channel, election=election, as_of=as_of)
    finally:
        if conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            conn.rollback()


def _compose(conn, parcel_id, channel, election=None, as_of=None):
    """as_of: normally None -- the real CLI path below always composes
    against the live clock (SELECT clock_timestamp()), unchanged. An
    explicit value is a testability seam for scripts/check_golden.py
    only (P20): SPEC.md §6.6 says a golden fixture's as_of is "pinned by
    the fixture, not by now()" -- distinct from composed_at/delivered_at/
    retrieved_at/fetched_at, which are merely normalised to <TS> after
    the fact. Pinning it for real (passing a fixed value in) rather than
    normalising it away is the more faithful reading: it makes
    current_fact_at's point-in-time read itself deterministic, not just
    the comparison after the read already happened.

    election (P34, README finding #35): which of Bulletin #210's two ADU
    development-standards regimes ("city" or "state") this request
    elects, when the conclusions this composer evaluates need one.
    Request-scoped, exactly like as_of/channel -- read once, here, never
    persisted to the fact ledger (I13: an applicant's own design choice
    about their project, not a claim about the world; see
    prompts/P33-correct-36-close-37-design-35.md section 3's verbatim §7
    precedent argument). Defaults to None, and None is a real, named
    case, not a silent resolution to "city" -- a conclusion that needs an
    election with none supplied refuses ELECTION_REQUIRED (0053) rather
    than guessing. Synchronous only (I14): this function never persists
    a partial/pending request and waits for election to arrive later --
    it is read from this exact call, once, or the composition refuses in
    this same call and returns. A follow-up is always a brand-new
    request, never a resumed one.

    Return value -- Result[T], UNIFORMLY (P38, README finding #41; P37
    made this heterogeneous -- Result.refuse(...)/str/None -- and that
    was itself the bug: check_golden.py's own run_composition() bound
    the return to property_file_id and checked only `is None`, so a
    Result arrived truthy and flowed on as a uuid, failing downstream
    with a misleading `can't adapt type 'Result'` -- confirmed directly
    against a real database, not inferred. Reachable the moment ANY
    caller's parcel_id can be wrong, not merely today's fixture-scoped
    callers). Every caller now gets exactly one contract: call
    .is_refused / .is_ok before touching .value -- Result's own guarded
    accessors (core/model.py) raise RuntimeError immediately, by name,
    if that check is skipped, rather than requiring every call site to
    remember its own isinstance assertion (the discipline gap finding
    #41 itself is an instance of). Three states, ALL wrapped, not three
    shapes:
      Result.refuse(Refusal(code="PARCEL_REFERENCE_UNKNOWN", ...))
        -- parcel_id does not resolve. No property_file row is written --
           cannot be: parcel_id is NOT NULL REFERENCES parcel(id), and
           there is no parcel to attach one to. This is the one case a
           typed in-memory return value, not a database row, is the only
           honest artifact this function can produce.
      Result.ok(property_file_id)  (a real str)
        -- a row was written, refused or not; covers every other refusal
           this function accumulates (GEOMETRY_TIER_DISABLED, L5's three
           outcomes, RIGHTS_BLOCKED, PARCEL_NO_FACTS) the same way it
           always has.
      Result.ok(NOTHING_COMPOSED)
        -- the rights gate passed and no geometry/L5/parcel-coverage
           refusal fired either; nothing composed, nothing written (see
           this function's own print statement for why that is not
           itself evidence of readiness). Result.ok(None) is itself
           invalid (core.model.Result's own __init__ guard: exactly one
           of value/refusal, never neither) -- NOTHING_COMPOSED (this
           module's own sentinel, above) is what stands in for that
           state instead of smuggling a real None past a wrapper that
           structurally forbids it. It was never a refusal to begin
           with, so Result.ok(...), not Result.refuse(...), is correct
           here -- callers distinguish it from a written row with
           `result.value is NOTHING_COMPOSED`, not by its own type.
    """
    if election is not None and election not in KNOWN_ELECTIONS:
        raise ValueError(
            f"election={election!r} is not one of {KNOWN_ELECTIONS!r} -- a caller/"
            f"programmer error (compose() is called directly today, never from an "
            f"untrusted request body), not a customer input this function refuses "
            f"gracefully. Pass None, 'city' or 'state'."
        )

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
        if as_of is None:
            cur.execute("SELECT clock_timestamp()")
            as_of = cur.fetchone()[0]

        # By id, never by apn: 0034 dropped (jurisdiction_id, apn)
        # uniqueness (Fix 3) -- a WHERE apn = %s / fetchone() here would
        # silently pick an arbitrary one of up to several parcels sharing
        # a colliding apn. parcel_id is the only identifier this function
        # trusts; --parcel-apn (see resolve_parcel_id_by_apn / __main__)
        # resolves to one BEFORE calling in, erroring loudly if it can't.
        #
        # P37, README finding #40: a caller-supplied parcel_id that does
        # not resolve is a deterministic runtime condition (I8), not a
        # programmer error -- re-graded from the SystemExit this used to
        # raise, live today for any caller, not merely once api/ exists.
        # No property_file row is possible here (parcel_id is NOT NULL
        # REFERENCES parcel(id), and there is no parcel to attach one to)
        # -- Result.refuse() is the only honest artifact, returned
        # directly, not written. Distinct from PARCEL_NOT_FOUND (§9,
        # stage L0, "APN not present in any parcel layer") -- that is an
        # ADDRESS/APN resolution failure; this is a by-id lookup of an
        # already-internal identifier, a different condition a customer
        # acts on differently (see 0055's own header for the full
        # argument).
        cur.execute("SELECT id, jurisdiction_id, apn FROM parcel WHERE id = %s", (parcel_id,))
        row = cur.fetchone()
        if row is None:
            return Result.refuse(Refusal(
                code="PARCEL_REFERENCE_UNKNOWN",
                stage="L0",
                message=(
                    f"No parcel exists with id={parcel_id!r}. This is a direct-by-id "
                    f"lookup, not an APN resolution -- distinct from PARCEL_NOT_FOUND "
                    f"(§9: 'APN not present in any parcel layer')."
                ),
                detail={"parcel_id": str(parcel_id)},
            ))
        parcel_id, jurisdiction_id, apn = row

        # P53: also select boundary_source_id -- the L0/LD-1 gate's own
        # activation switch (prompts/P53-l0-gate.md, design D-C). NULL for
        # every jurisdiction except ca_san_jose (0056 sets it there only) --
        # every test.*/internal_test.* fixture jurisdiction elsewhere in this
        # database is unaffected by the check built from it, below.
        cur.execute(
            "SELECT pack_version, geometry_tier_enabled, boundary_source_id "
            "FROM jurisdiction WHERE id = %s",
            (jurisdiction_id,),
        )
        pack_version, geometry_tier_enabled, boundary_source_id = cur.fetchone()

        # L5 (P34, generalizing P31): rule selection, refuse-first
        # (core/rules.py). Runs unconditionally, same shape as L7's
        # geometry gate below -- accumulated into the same refusals list,
        # not a short-circuit. "placement" is the only conclusion this
        # minimal composer knows about today (P25); CONCLUSION_RULE_KEYS
        # is now keyed on (conclusion, election) (README finding #35), so
        # resolving a rule_key needs an election first. Three distinct,
        # honestly-separate outcomes here, not one code standing in for
        # all three (0053's own header has the full argument):
        #   election is None              -> ELECTION_REQUIRED. No DB
        #                                     lookup attempted -- there is
        #                                     nothing to look up yet.
        #   election given, no dict entry -> ELECTION_NOT_SUPPORTED. No DB
        #                                     lookup attempted -- this
        #                                     composer has no rule_key for
        #                                     this (conclusion, election)
        #                                     pairing at all, independent
        #                                     of any as-of date.
        #   election given, entry found   -> select_effective_rule() runs
        #                                     for real and may itself
        #                                     refuse RULE_UNAVAILABLE -- a
        #                                     different, temporal claim.
        # selected_rule/rule_result stay None when this stage refuses
        # before ever reaching a query -- ruleset_version below reflects
        # exactly which of the three happened, honestly, never a
        # hardcoded placeholder in any case.
        selected_rule = None
        required_rule_key = None
        rule_result = None
        election_refusal = None
        if election is None:
            election_refusal = {
                "code": "ELECTION_REQUIRED",
                "stage": "L5",
                "message": (
                    "placement depends on which ADU development-standards regime "
                    "this request elects (Bulletin #210: City, Municipal Code "
                    "20.80.175, or State, 20.80.176), and none was supplied."
                ),
                "detail": {"conclusion": "placement"},
            }
        else:
            required_rule_key = CONCLUSION_RULE_KEYS.get(("placement", election))
            if required_rule_key is None:
                election_refusal = {
                    "code": "ELECTION_NOT_SUPPORTED",
                    "stage": "L5",
                    "message": (
                        f"placement has no known rule_key for election={election!r} in "
                        f"this composer yet (README finding #35) -- distinct from no "
                        f"rule currently being effective."
                    ),
                    "detail": {"conclusion": "placement", "election": election},
                }
            else:
                rule_result = select_effective_rule(cur, jurisdiction_id, required_rule_key, as_of)

        # C5 (0036): the point-in-time read path, not the cached matview --
        # this is a live composition, not a report against a stale refresh.
        # Same as_of captured above, not a second now().
        cur.execute(
            "SELECT id, field_key, licence_id, value FROM current_fact_at(%s) WHERE parcel_id = %s",
            (as_of, parcel_id),
        )
        touched = cur.fetchall()
        # P37, README finding #40: a resolved parcel with zero current
        # facts is also a deterministic runtime condition, not a
        # programmer error -- re-graded from the SystemExit this used to
        # raise. UNLIKE the parcel-not-found case above, a property_file
        # row CAN be written here (parcel_id/jurisdiction_id are both
        # real, satisfying every FK) and IS -- accumulated into `refusals`
        # below the same way GEOMETRY_TIER_DISABLED/L5's outcomes already
        # are (P25: refusals accumulate, never short-circuit). Not
        # COVERAGE_GAP/INSUFFICIENT_COVERAGE -- both presuppose a
        # "required fields" mechanism this composer has never built (see
        # 0055's own header); zero facts is a distinct, prior condition,
        # its own code, not either of those by default.
        no_facts_refusal = None
        if not touched:
            no_facts_refusal = {
                "code": "PARCEL_NO_FACTS",
                "stage": "L8",
                "message": (
                    f"parcel {parcel_id} (apn={apn!r}) has no current facts as of "
                    f"{as_of} -- nothing for this composer to gate or deliver."
                ),
                "detail": {"parcel_id": str(parcel_id), "apn": apn},
            }

        print(f"parcel {parcel_id} (apn={apn!r}): {len(touched)} touched facts")
        for fact_id, field_key, licence_id, value in touched:
            print(f"  {field_key:28s} licence={licence_id:12s} value={json.dumps(value)}")

        # I6 rights gate. P40: extracted to evaluate_rights_gate() so api/'s
        # viewer can call the ONE gate implementation instead of growing a
        # second copy that could silently disagree with this one. P47:
        # evaluate_rights_gate itself now lives in core/rights.py (finding
        # #45, closed) -- imported above, same function, same call here.
        allowed_by_licence, blocked_by_licence = evaluate_rights_gate(cur, touched, channel)

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    # L7 (P25): geometry-dependent conclusion gate, runs regardless of L8's
    # own outcome below -- see this package's own report for the full
    # argument, in short: §5's compose loop is an unconditional
    # straight-line sequence (L0 -> ... -> L7 -> L6 -> L8 -> decide), and
    # §6.6 ("a golden file that lost a refusal is a regression")
    # presupposes multiple co-occurring refusals are the normal shape, not
    # the exception. Refuse-only: core/calc never computes or persists a
    # derived fact here (see its own module docstring for why).
    refusals = []

    # L0 (P53, prompts/P53-l0-gate.md, design D-C): the L0/LD-1 jurisdiction
    # gate, given a real runtime representation for the first time. Refuses
    # LICENCE_UNKNOWN -- an existing, correct sec 9 code ("Default deny.
    # Applies at L0 when a gate source is unconfirmed", sec 1.1) that no
    # code path has ever emitted before this -- when a jurisdiction has
    # DECLARED which source resolves its boundary (boundary_source_id IS NOT
    # NULL) but no current jurisdiction.incorporated fact exists for this
    # parcel to satisfy it. Only ca_san_jose declares one today (0056);
    # every other jurisdiction's boundary_source_id stays NULL, so this
    # check never fires for them -- D-C's own scoping argument, enforced
    # here rather than merely stated. No new query: `touched` is exactly the
    # same current_fact_at() result the I6 gate above already consumed.
    # This never calls evaluate_rights_gate and never reads licence_channel
    # -- it is a presence/absence check, wholly independent of any licence's
    # own clearance state, which is the entire point (the gate must hold
    # even if cc0/cc_by_4_0 were fully cleared).
    # C3 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): the original check below
    # was presence-only -- `any(field_key == ... for _, field_key, _, _ in
    # touched)` destructured the VALUE away and never read it, so an
    # explicit jurisdiction.incorporated=false fact (0056's own designed
    # meaning: "NOT in this jurisdiction") suppressed the refusal exactly
    # like true does. Fixed to require the value itself be True, not merely
    # present -- absence (no such fact at all) and an explicit False both
    # now refuse, only True satisfies. Source-scoping (requiring the fact
    # come specifically from boundary_source_id) is NOT implemented here --
    # see this pass's own report for why: pairing it with the only route
    # that would make it coherent (flipping ca_san_jose.city_limits off
    # method='manual') is blocked today by source_endpoint_required's own
    # CHECK (method='manual' OR endpoint_url IS NOT NULL) without a real,
    # verified endpoint, which P53-l0-gate.md's own Obstacle 2 already ruled
    # out fabricating. Recorded as a known, coupled gap, not silently
    # dropped.
    # A-N11 (P59C): incorporated_value/_present are read separately from
    # _satisfied so the refusal message below can tell "no fact at all"
    # apart from "an explicit False fact" -- the single shared message
    # used to say "no current jurisdiction.incorporated fact exists" in
    # BOTH cases, which is factually wrong for the explicit-False case (a
    # sourced fact exists and says the parcel is NOT in the jurisdiction).
    incorporated_present = False
    incorporated_value = None
    for _, field_key, _, value in touched:
        if field_key == "jurisdiction.incorporated":
            incorporated_present = True
            incorporated_value = value
            break
    incorporated_satisfied = incorporated_value is True
    if boundary_source_id is not None and not incorporated_satisfied:
        if incorporated_present:
            # Explicit False: honest about what's actually there. Not the
            # absent-case message below -- keeping that one byte-identical
            # is what avoids reblessing any golden fixture (A-N11).
            fact_clause = (
                "a current jurisdiction.incorporated fact exists and is False "
                "(this parcel is asserted NOT to be in the jurisdiction)"
            )
        else:
            fact_clause = "no current jurisdiction.incorporated fact exists for this parcel"
        refusals.append({
            "code": "LICENCE_UNKNOWN",
            "stage": "L0",
            "message": (
                f"Jurisdiction {jurisdiction_id!r} declares boundary_source_id="
                f"{boundary_source_id!r} as the source that resolves its boundary, but "
                f"{fact_clause} -- "
                f"default deny (§1.1, §9)."
            ),
            "detail": {
                "jurisdiction_id": jurisdiction_id,
                "boundary_source_id": boundary_source_id,
                "field_key": "jurisdiction.incorporated",
            },
        })

    # L7 (P25): geometry-dependent conclusion gate, runs regardless of L8's
    # own outcome below -- see this package's own report for the full
    # argument, in short: §5's compose loop is an unconditional
    # straight-line sequence (L0 -> ... -> L7 -> L6 -> L8 -> decide), and
    # §6.6 ("a golden file that lost a refusal is a regression")
    # presupposes multiple co-occurring refusals are the normal shape, not
    # the exception. Refuse-only: core/calc never computes or persists a
    # derived fact here (see its own module docstring for why).
    geometry_result = evaluate_geometry_dependent_conclusion("placement", geometry_tier_enabled)
    if geometry_result.is_refused:
        refusals.append(geometry_result.refusal.model_dump())

    # PARCEL_NO_FACTS (P37, README finding #40): folded in here, same
    # accumulation reasoning as L7/L5/L8 -- never a short-circuit.
    if no_facts_refusal is not None:
        refusals.append(no_facts_refusal)

    # L5 (P34, generalizing P31): fold this stage's own refusal into the
    # same accumulated list -- same reasoning as L7 above, a straight-line
    # sequence, never a short-circuit. election_refusal takes precedence
    # (it means rule_result never ran); otherwise rule_result's own
    # refusal, if any. selected_rule stays None whenever L5 refuses, by
    # any of the three routes.
    if election_refusal is not None:
        refusals.append(election_refusal)
    elif rule_result.is_refused:
        refusals.append(rule_result.refusal.model_dump())
    else:
        selected_rule = rule_result.value

    # ruleset_version (I11): the real selected rule's own identity when
    # L5 found one, an honest negative fact for whichever of the three L5
    # outcomes happened when it didn't -- never the old hardcoded
    # "unevaluated -- L5 Rules not yet built" lie in any case. rule_key@
    # version, not the row's own opaque id: directly traceable back to
    # CONCLUSION_RULE_KEYS above without a second lookup.
    if selected_rule is not None:
        ruleset_version = f"{selected_rule.rule_key}@{selected_rule.version}"
    elif election_refusal is not None:
        ruleset_version = f"no rule selected: {election_refusal['code']}"
    else:
        ruleset_version = (
            f"no rule effective: jurisdiction={jurisdiction_id}, "
            f"rule_key={required_rule_key}, as_of={as_of}"
        )

    # L8 rights gate (unchanged logic, now accumulated with L7 above
    # rather than being the only possible source of a refusal).
    for licence_id in sorted(blocked_by_licence):
        field_keys = sorted(blocked_by_licence[licence_id])
        refusals.append({
            "code": "RIGHTS_BLOCKED",
            "stage": "L8",
            "message": f"Licence {licence_id} forbids channel {channel} for touched field(s): {', '.join(field_keys)}.",
            "detail": {"licence_id": licence_id, "channel": channel, "field_keys": field_keys},
        })

    if not refusals:
        print(f"\nRIGHTS GATE PASSED for channel={channel!r}: every touched fact's licence "
              f"permits this channel, and no geometry-dependent conclusion was refused. "
              f"No property_file written -- composing a real file (rendering, payload "
              f"assembly, a success/partial path) is out of scope for this minimal "
              f"composer. This is the expected outcome only when a licence_channel row "
              f"has been deliberately flipped for verification; do not treat it as "
              f"evidence anything is ready to ship.")
        return Result.ok(NOTHING_COMPOSED)

    payload = {"status": "refused", "refusals": refusals, "attribution": [], "omitted_for_rights": []}
    payload_json = json.dumps(payload, sort_keys=True)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    property_file_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO property_file (
                id, parcel_id, jurisdiction_id, channel, status, as_of,
                pack_version, ruleset_version, composer_version, election,
                geometry_tier_used, refusals, omitted_for_rights, attribution,
                payload, payload_hash, delivered_at, compose_ms
            ) VALUES (
                %s, %s, %s, %s, 'refused', %s,
                %s, %s, %s, %s,
                %s, %s::jsonb, '[]'::jsonb, '{}',
                %s::jsonb, %s, NULL, %s
            )
            """,
            (
                property_file_id, parcel_id, jurisdiction_id, channel, as_of,
                pack_version, ruleset_version, composer_version, election,
                geometry_tier_enabled, json.dumps(refusals), payload_json, payload_hash, elapsed_ms,
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
    return Result.ok(property_file_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--parcel-id", help="parcel.id (uuid) -- unambiguous, the primary way to select a parcel")
    group.add_argument("--parcel-apn", help="convenience lookup by apn -- ERRORS naming every candidate "
                                             "id if apn matches more than one parcel (0034 dropped APN "
                                             "uniqueness); never picks one")
    parser.add_argument("--channel", default="paid_property_file")
    parser.add_argument("--election", choices=KNOWN_ELECTIONS, default=None,
                         help="Which ADU development-standards regime this request elects "
                              "(README finding #35) -- omit to see the real ELECTION_REQUIRED "
                              "refusal path, same as every composition before this flag existed.")
    args = parser.parse_args()

    conn = get_db()
    try:
        parcel_id = args.parcel_id or resolve_parcel_id_by_apn(conn, args.parcel_apn)
        result = compose(conn, parcel_id, args.channel, election=args.election)
        # P38, README finding #41: compose() now returns Result[T]
        # uniformly -- is_refused/is_ok checked explicitly before .value
        # is ever touched, the one contract every caller shares.
        if result.is_refused:
            refusal = result.refusal
            print(f"\nREFUSED before any property_file could be written: "
                  f"{refusal.code}: {refusal.message}")
            sys.exit(1)
        elif result.value is NOTHING_COMPOSED:
            pass  # compose()'s own RIGHTS GATE PASSED print already said everything
        # else: result.value is the written property_file_id; compose()
        # itself already printed the full summary.
    finally:
        conn.close()
