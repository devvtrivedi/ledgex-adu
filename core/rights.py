"""Layer X: the I6 rights gate. §2's own diagram names this slot
("core/rights/ X") since before any code existed under core/ at all.

P47 (README finding #45): moved here from scripts/compose_property_file.py,
where evaluate_rights_gate() and KNOWN_CHANNELS lived since P39/P40 --
staying there was a deliberate, reported deferral (P40 §0 D3): the
import-linter contract that was supposed to gate a new core/ submodule
correctly could not, at the time, actually do so (finding #45's own stale
blacklist), so extracting into core/ then would have added a fourth thing
that contract silently didn't cover, compounding the problem rather than
fixing it. P47 fixes that contract first (.importlinter,
i15-commerce-core-allowlist) and only then makes this move -- the
precondition D3 named for revisiting the decision is now satisfied.

EXACTLY ONE FUNCTION, EXACTLY TWO CALL SITES, unchanged by this move:
scripts/compose_property_file.py's _compose() and api/main.py's
get_parcel_facts(), one call each -- the entire reason finding #45 was safe
to defer across four packages is that a single shared implementation cannot
drift between the two places that put fact values on a screen. This module
adds no wrapper, no second variant, no convenience overload -- both callers
import this exact function and call it exactly as before; only the import
path changed (api/main.py no longer imports scripts/compose_property_file.py
at all -- that was the whole api/ -> scripts/ edge finding #45's A2 existed
to remove).

§2: "core/* may import core/model, infra/, and stdlib/third-party only."
This module imports none of those -- KNOWN_CHANNELS is a plain tuple and
evaluate_rights_gate takes a psycopg2 cursor as a plain argument, never
importing psycopg2 or anything else itself. Trivially compliant, not
coincidentally: a rights-evaluation function has no reason to know how its
cursor was constructed.
"""

# P39, moved here P47. The `output_channel` enum's six members, read from
# db/schema.sql's own CREATE TYPE public.output_channel (0001, widened by
# 0031 with analytics and model_training) and re-confirmed against a live
# database's pg_enum before being written here -- not transcribed from §4 or
# §7.3 prose, neither of which enumerates all six in one place.
#
# WHY THIS EXISTS. `election` has been validated at this boundary since P34
# and `parcel_id` became a typed refusal in P37. `channel` was the one
# remaining caller-supplied value with no boundary check at all -- it
# reached the licence_channel query below as a bare literal and failed
# there as psycopg2.errors.InvalidTextRepresentation, naming the enum but
# not the parameter, AFTER the composition had already opened a transaction
# and read the parcel. Confirmed directly against a real database, not
# inferred (P39's own RED transcript).
#
# NOT A REFUSAL CODE. §9's refusal table has no member for "the channel you
# named does not exist," and §9's own closing line puts this class in the
# ERROR taxonomy, verbatim: "Errors (application/problem+json): schema-drift
# (502), source-timeout (504), invalid-request (400), not-found (404),
# conflict (409), internal (500)." A refusal is a valid business answer
# about a real channel (RIGHTS_BLOCKED is one); an unknown channel is a
# malformed request, which is a 400, not a 200 with status:"refused".
# Inventing a refusal code for it would need a spec bump and a §12 row
# (I17), which CONVENTIONS says to stop and report rather than absorb --
# so ValueError here (compose_property_file.py's own compose() raises it),
# matching `election` exactly, and api/ maps a bad channel the same way
# `status`/`outcome` are mapped: FastAPI's own boundary validation, never a
# manual check reaching this far in.
#
# FOURTH COPY OF A DATABASE VOCABULARY, DELIBERATELY LEFT UNDIFFED. Refusal
# codes have three copies and build/qa_check.py's check_refusal_codes_match_spec()
# diffs them, because all three are hand-maintained prose/Python lists that
# can silently disagree with each other. This is not that shape:
# output_channel is a Postgres ENUM, so the database rejects an unknown
# value on contact -- the failure a diff would prevent (a stale Python list
# quietly admitting a value the database does not have) is impossible here,
# and the opposite drift (the enum gains a member this tuple lacks) surfaces
# as a loud ValueError naming the channel, never as silent wrong behavior.
# Recorded as a decision, not an omission: if a future channel is added and
# this tuple is forgotten, the symptom is a refused call with an accurate
# message, not a wrong answer.
KNOWN_CHANNELS = (
    "free_snapshot",
    "paid_property_file",
    "api",
    "bulk_export",
    "analytics",
    "model_training",
)


def evaluate_rights_gate(cur, touched, channel):
    """I6 (§1.1, §7.3): every touched fact must have an explicit
    allowed=true licence_channel row for this channel. Absence is
    default-deny, the same as an explicit false -- both block. Gates every
    TOUCHED fact, not only every rendered one (§1.1: "a fact used to
    resolve jurisdiction participates in composition even if it is not
    rendered").

    P40 (README finding #45's own D3 fallout): first extracted out of
    _compose() unchanged (same query, same two-pass shape), so a second
    reader (api/'s viewer, which also puts fact values on a screen and is
    therefore also an output channel under I6) could call this ONE
    implementation instead of growing a silently-divergent copy -- at the
    time, kept in scripts/ rather than moved to this module because the
    import-linter contract meant to gate a new core/ submodule correctly
    could not yet do so.

    P47 (README finding #45, closed): moved into core/rights.py itself,
    §2's own layer X slot, now that .importlinter's commerce/core contract
    has been repaired first. Same function, same two call sites
    (scripts/compose_property_file.py's _compose(), api/main.py's
    get_parcel_facts()), only the import path changed.

    touched: iterable of (fact_id, field_key, licence_id, value) rows,
    exactly current_fact_at's own shape (and _compose's own `touched`
    local). channel: an output_channel enum member -- caller's
    responsibility to validate (compose() does this via KNOWN_CHANNELS
    before touching a query; api/ validates the same way against the same
    constant, both imported from this module).

    Returns (allowed_by_licence, blocked_by_licence):
      allowed_by_licence  -- {licence_id: bool}, exactly the licence_channel
                              rows found for this channel among the touched
                              facts' licence ids. A licence_id with no row
                              here is default-deny, not KeyError -- callers
                              read it with .get(licence_id, False), never []
                              or direct indexing.
      blocked_by_licence  -- {licence_id: [field_key, ...]}, every touched
                              field whose licence does NOT carry an
                              allowed=true row for this channel.
    """
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

    return allowed_by_licence, blocked_by_licence
