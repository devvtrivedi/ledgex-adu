"""L5: rule selection. First real content -- refuse-only proven first,
same discipline P25's core/calc.py already established for L7.

I1: this module is jurisdiction-free. jurisdiction_id and rule_key are
PARAMETERS, not lookups -- this file contains no jurisdiction id, no
rule content, no hardcoded rule_key, exactly the same shape core/calc.py
already uses for geometry_tier_enabled. The one real hardcoded fact this
package adds (which rule_key a given conclusion needs) is a
jurisdiction-scoped constant and does NOT live here -- it lives in
scripts/compose_property_file.py, the same home ingest_parcels.py/
ingest_zoning_permits.py already use for their own jurisdiction-scoped
SOURCE_ID/JURISDICTION_ID constants. Putting it here would fail
make check-boundary: build/check_jurisdiction_names.py's own BLOCKLIST
includes real jurisdiction ids, scoped to core/**/*.py -- confirmed by reading
that script directly, not assumed. See prompts/P31-l5-refuse-first-one-
real-rule.md section 2 for the full argument.

WHY refuse-only is not "refuse, or select" done halfway: unlike
core/calc.py's own geometry gate (a hardcoded boolean check with no
database read at all), rule selection has always needed a real query --
there is no "harder" version of this function waiting for a later
package. What IS still out of scope: nothing in this codebase yet
declares which rule_key a conclusion depends on beyond the one hardcoded
entry P31 adds in scripts/compose_property_file.py (Shape 1, a
one-jurisdiction, one-conclusion constant, not a general mechanism --
the per-jurisdiction conclusions file sec 7.4 names, remains undesigned).
And no caller anywhere APPLIES a selected rule's own params to compute a
conclusion -- this module only ever SELECTS a rule's identity; I11's own
"application" half stays unexercised until a real rule-consuming
computation exists (the same class of future package core/calc.py's own
docstring already names for its own geometry_tier_enabled=True branch).
"""
from core.model import Refusal, Result, Rule


def select_effective_rule(cur, jurisdiction_id: str, rule_key: str, as_of) -> "Result[Rule]":
    """0009's own effective-window columns, read literally:
    effective_from <= as_of AND (effective_to IS NULL OR effective_to >
    as_of) -- the identical half-open-interval shape parcel_exception/
    fact's own valid-time columns already use elsewhere in this schema,
    not invented here. Highest version wins when more than one row is
    effective (0013's own supersession model: a correction is a NEW
    version plus the old one's effective_to being retired, never an
    UPDATE -- at most one row should ever be effective for a given
    jurisdiction_id/rule_key at a given as_of in a correctly-maintained
    table, but ORDER BY version DESC LIMIT 1 is the honest tie-break
    even if that invariant is ever violated, rather than an arbitrary
    row via a bare fetchone() on an unordered result -- the exact
    "arbitrary pick" shape this codebase has found and fixed twice
    before, in compose_property_file's own identifier-handling and
    reconciliation code paths (README findings #4/#15).

    Returns Result.refuse(Refusal(code="RULE_UNAVAILABLE", stage="L5",
    ...)) when no row is effective -- REFUSAL_CODES member, never before
    raised by any code in this repository (confirmed by grep before this
    package). Returns Result.ok(Rule(...)) on a match, carrying the
    selected row's real identity -- not the row's own params; a caller
    that needs to APPLY the rule's params is a real future need this
    package does not build for."""
    cur.execute(
        """
        SELECT id, jurisdiction_id, rule_key, version, citation, pack_version,
               effective_from, effective_to
        FROM rule
        WHERE jurisdiction_id = %s
          AND rule_key = %s
          AND effective_from <= %s
          AND (effective_to IS NULL OR effective_to > %s)
        ORDER BY version DESC
        LIMIT 1
        """,
        (jurisdiction_id, rule_key, as_of, as_of),
    )
    row = cur.fetchone()
    if row is None:
        return Result.refuse(Refusal(
            code="RULE_UNAVAILABLE",
            stage="L5",
            message=(
                f"No rule effective for jurisdiction_id={jurisdiction_id!r}, "
                f"rule_key={rule_key!r} as of {as_of}."
            ),
            detail={"jurisdiction_id": jurisdiction_id, "rule_key": rule_key, "as_of": str(as_of)},
        ))
    (rid, jid, rkey, version, citation, pack_version, effective_from, effective_to) = row
    return Result.ok(Rule(
        id=rid,
        jurisdiction_id=jid,
        rule_key=rkey,
        version=version,
        citation=citation,
        pack_version=pack_version,
        effective_from=effective_from,
        effective_to=effective_to,
    ))
