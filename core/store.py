"""L4: fact storage -- the write side of "a source observed this value."

insert_facts() is the one shared shape the copy-list audit found: the
14-column execute_values call at phase_e (scripts/ingest_parcels.py),
load_zoning and load_permits (scripts/ingest_zoning_permits.py) --
confirmed byte-identical (same SQL text, same template, same
page_size=2000) across all three before this move, diffed pairwise, not
assumed.

Callers still build the 14-tuple list themselves, according to their
own source-specific mapping from a raw source property to a canonical
field_key. That mapping is jurisdiction-specific and deliberately
does not move here (I1) -- this function knows the tuple's shape and
nothing about what any position means for any real place. The seam
between this file and scripts/*.py's mapping code is the actual boundary
I1 draws; splitting it here is the point of this slice, not a detail of
it.

Positional 14-tuples, not a Fact type: core/model doesn't exist, and
this function is exactly the kind of code that wants one -- a caller
that gets the tuple's column order wrong fails at INSERT time with a
type-mismatch error naming a position, not a field name, and nothing
here stops two callers from building that tuple in different orders by
accident. Not built anyway: forced by need, not anticipated, same as
every other decision in this extraction. See docs/LEDGEX_SPEC.md's
change record for this slice.
"""
import psycopg2.extras

FACT_COLUMNS = (
    "parcel_id, jurisdiction_id, field_key, value, method, "
    "source_id, snapshot_id, retrieved_at, source_url, "
    "licence_id, confidence, confidence_rule_id, "
    "effective_from, pack_version"
)
FACT_TEMPLATE = "(%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"


def insert_facts(cur, fact_rows):
    """fact_rows: list of 14-tuples, positional, in FACT_COLUMNS' order.
    page_size=2000 was identical at all three original call sites, so it
    stays fixed here rather than becoming a parameter nothing currently
    needs to vary."""
    psycopg2.extras.execute_values(
        cur,
        f"INSERT INTO fact ({FACT_COLUMNS}) VALUES %s",
        fact_rows,
        template=FACT_TEMPLATE,
        page_size=2000,
    )
