"""L6: parcel exceptions -- the record of what could not be resolved.

insert_exceptions() is the shared shape from the copy-list audit's
parcel_exception execute_values call, found at 4 occurrences: phase_e
(scripts/ingest_parcels.py), load_zoning (scripts/ingest_zoning_permits.py),
and both flag_parcel_geometry/flag_zoning_source_geometry
(scripts/flag_invalid_geometry.py). SQL text and template are
byte-identical across all four, diffed pairwise, not assumed. page_size
was NOT identical: 2000 at the first two, 500 at both
flag_invalid_geometry.py call sites, with no comment at either site
explaining the choice. Preserved as a parameter rather than picked a
winner -- nothing in the record justifies forcing one number on every
caller, and unifying it would be a behavior change dressed as a
refactor.

Same jurisdiction-free/tuple-not-type shape as core/store.insert_facts
-- see that module's docstring for the reasoning, which applies here
unchanged.
"""
import psycopg2.extras

EXCEPTION_COLUMNS = (
    "parcel_id, jurisdiction_id, type, severity, "
    "detector_key, detector_version, detail"
)
EXCEPTION_TEMPLATE = "(%s, %s, %s, %s, %s, %s, %s::jsonb)"


def insert_exceptions(cur, exception_rows, page_size=2000):
    """exception_rows: list of 7-tuples, positional, in EXCEPTION_COLUMNS'
    order. page_size default (2000) matches two of the four original call
    sites; the other two pass 500 explicitly -- see module docstring."""
    psycopg2.extras.execute_values(
        cur,
        f"INSERT INTO parcel_exception ({EXCEPTION_COLUMNS}) VALUES %s",
        exception_rows,
        template=EXCEPTION_TEMPLATE,
        page_size=page_size,
    )
