"""L4: fact storage -- the write side of "a source observed this value."

insert_facts() is the one shared shape the copy-list audit found: the
execute_values call at phase_e (scripts/ingest_parcels.py), load_zoning
and load_permits (scripts/ingest_zoning_permits.py) -- confirmed
byte-identical (same SQL text, same template, same page_size=2000)
across all three before this move, diffed pairwise, not assumed.

Widened from 14 to 15 columns (local_verbatim added) for an identifier
canonicalisation fix in a caller: fact.local_verbatim has existed since 0006 ("the
source's own string. NEVER discard.") and no caller wrote it. Once
phase_e started canonicalising parcel.apn (stripping a leading
apostrophe / surrounding whitespace) before it becomes the fact's value,
NOT recording the pre-canonicalisation raw string here would be exactly
the discard that comment forbids. This is a shared primitive, so the
column is positional for every caller, not just the one that needed it --
load_zoning and load_permits pass NULL (no single raw string is
naturally "the" verbatim form for a spatial-join classification or a
computed permits.active flag); phase_e's parcel.apn fact is the one
caller that populates it for real.

Widened again, 15 to 17 (supersedes_fact_id, supersession_reason) for
Phase B reconciliation: any of the three callers can now write a
successor fact retiring a prior one (0025), and the pairing is enforced
by fact_supersession_reason_biconditional -- both NULL or both set, never
one alone. Same shared-primitive reasoning as local_verbatim: every
caller's tuples grow two columns whether or not that particular call site
currently writes any successors.

insert_facts() now takes list[core.model.Fact], not positional 17-tuples
(P22) -- callers no longer hand-order a tuple; this file is the one
place that knows FACT_COLUMNS' order, and every caller names fields via
Fact's own constructor instead. The mapping from a raw source property to
a canonical field_key stays in scripts/*.py, unmoved, jurisdiction-
specific (I1) -- this function still knows nothing about what any field
means for any real place, only which of Fact's fields become which
column.

The hazard this replaces was understated by this file's own prior
version: "a caller that gets the tuple's column order wrong fails at
INSERT time with a type-mismatch error naming a position" is true only
for differently-typed positions. confidence_rule_id and pack_version
(0006: both `text NOT NULL`, no CHECK on either -- verified directly, not
assumed) are same-typed and both freeform, so transposing them inserted
CLEANLY, storing the wrong value in each column permanently -- 0017
(fact_no_delete) means a row like that can never be removed, only
superseded, and only once someone notices it's wrong. Fact's own
model_validators run at construction, before any tuple exists to insert;
see tests/core/test_fact_adoption_hazard.py for the RED-first proof that
this exact transposition is now refused, not merely harder to type by
accident.

Fact models 29 fields -- the full `fact` row, not just the 17 this
function writes. Twelve are absent from FACT_COLUMNS: id and recorded_at
are DB-defaulted (gen_random_uuid(), clock_timestamp()) and
superseded_at is lifecycle state a fact only acquires once superseded,
after insertion -- correctly never written by an INSERT, not an
oversight. The other nine (unit, layer_item_id, source_published_at,
source_cadence_stated, effective_to, conflict, method_version,
ruleset_version, source_asserted_as_of) are a real choice, not yet
forced by any caller: no append site in either ingest script currently
computes a value for any of them. Widening the INSERT to also write all
nine would be new scope -- persisting fields nothing currently populates
-- not this package's fix; reported, not absorbed. Left UNWRITTEN, not
silently dropped: _check_no_unwritten_fields() below refuses any Fact
carrying a non-default value in one of the nine before building any
tuple, so a caller that starts populating one of them gets a loud,
immediate error naming the field -- not a silent no-op where the model
claimed to hold a value insert_facts never persisted, which would be a
worse failure than the transposition this package fixes: a model
actively lying about what it writes.
"""
import psycopg2.extras

from core.model import Fact

FACT_COLUMNS = (
    "parcel_id, jurisdiction_id, field_key, value, method, "
    "source_id, snapshot_id, retrieved_at, source_url, "
    "licence_id, confidence, confidence_rule_id, "
    "effective_from, pack_version, local_verbatim, "
    "supersedes_fact_id, supersession_reason"
)
FACT_TEMPLATE = "(%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"

# The nine Fact fields insert_facts() does not write -- see this module's
# own docstring. id, recorded_at and superseded_at are deliberately NOT
# in this list: they are legitimately never caller-set at insert time
# (DB-defaulted or post-insertion lifecycle state), not "not yet handled".
_UNWRITTEN_FIELDS_AND_DEFAULTS = (
    ("unit", None),
    ("layer_item_id", None),
    ("source_published_at", None),
    ("source_cadence_stated", None),
    ("effective_to", None),
    ("conflict", "agree"),
    ("method_version", None),
    ("ruleset_version", None),
    ("source_asserted_as_of", None),
)


def _check_no_unwritten_fields(fact):
    for field_name, default in _UNWRITTEN_FIELDS_AND_DEFAULTS:
        value = getattr(fact, field_name)
        if value != default:
            raise ValueError(
                f"Fact.{field_name}={value!r} was set, but insert_facts() does "
                f"not write that column (see core/store.py's own module "
                f"docstring for the full list) -- it would be silently "
                f"dropped, not persisted."
            )


def insert_facts(cur, facts):
    """facts: list[core.model.Fact]. Builds the same 17-tuple this table
    has always taken (FACT_COLUMNS' order, unchanged) from each Fact's
    named fields -- see this module's docstring for which fields those
    are and which nine are refused instead of silently ignored.
    page_size=2000 was identical at all three original call sites, so it
    stays fixed here rather than becoming a parameter nothing currently
    needs to vary.

    Refuses anything that is not actually a Fact -- notably a bare
    tuple, the exact shape this function used to accept, and the shape
    this whole package exists to stop callers from hand-building. This
    is the one hazard a type system CAN mechanically enforce here (see
    core/model.py's own docstring, design decision (c), for what it
    cannot: a Fact constructed with two values swapped between two
    same-typed named fields is still a valid Fact)."""
    for f in facts:
        if not isinstance(f, Fact):
            raise TypeError(
                f"insert_facts() requires core.model.Fact instances, got "
                f"{type(f).__name__!r} -- see this function's own "
                f"docstring for why a bare tuple is refused, not accepted "
                f"and hoped to be shaped right."
            )
        _check_no_unwritten_fields(f)
    fact_rows = [
        (
            str(f.parcel_id), f.jurisdiction_id, f.field_key, f.value, f.method,
            f.source_id, f.snapshot_id, f.retrieved_at, f.source_url,
            f.licence_id, f.confidence, f.confidence_rule_id,
            f.effective_from, f.pack_version, f.local_verbatim,
            str(f.supersedes_fact_id) if f.supersedes_fact_id is not None else None,
            f.supersession_reason,
        )
        for f in facts
    ]
    psycopg2.extras.execute_values(
        cur,
        f"INSERT INTO fact ({FACT_COLUMNS}) VALUES %s",
        fact_rows,
        template=FACT_TEMPLATE,
        page_size=2000,
    )
