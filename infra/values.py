"""Value-normalization helpers with no domain content.

Second half of the first extraction slice -- see infra/env.py's module
docstring. decimal_default was `_decimal_default` (leading underscore)
in every source copy; renamed on the move, since a name that signals
"private to this module" stops being honest the moment it's a shared
export. Body is otherwise verbatim.
"""
import decimal


def is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def canonicalize_identifier(raw):
    """Strip surrounding whitespace and a leading apostrophe from a raw
    source identifier string. Returns None unchanged (blank detection is
    is_blank's job, not this function's).

    Both artifacts are real, observed source defects, not invented rules:
    - Leading apostrophe: a spreadsheet-export "force text" marker.
      Measured against the real ca_san_jose.building_permits_active CSV:
      1 of 17,499 rows (ASSESSORS_PARCEL_NUMBER = "'67620002").
    - Surrounding whitespace: measured against the real
      ca_san_jose.parcels GeoJSON: 3 of 225,039 features' raw APN
      property (e.g. "26137026 ", trailing space) -- ingest_parcels.py
      previously stored this verbatim in parcel.apn, which would never
      string-equal a clean permit APN even after the permit side was
      independently .strip()'d.

    Stripped twice (whitespace, then the apostrophe, then whitespace
    again) to handle the two artifacts composing in either order (e.g. a
    stray leading space before an apostrophe) -- not a new rule, just a
    safe sequencing of the two already-observed ones.

    Deliberately narrow: does not touch case, internal characters, or any
    other shape. Two other anomalous APN shapes exist in the real parcels
    data ('?' placeholders, already handled by is_unresolvable_apn's own
    check, and a 5-occurrence 'XX'-prefixed placeholder shape) -- neither
    is a raw/canonical string-representation difference like the two
    above, so neither is normalised here. See ingest_parcels.py's
    is_unresolvable_apn for why 'XX' is a separate, not-yet-addressed
    finding rather than a canonicalisation rule.
    """
    if raw is None:
        return raw
    s = raw.strip()
    if s.startswith("'"):
        s = s[1:]
    return s.strip()


def decimal_default(o):
    # ijson parses GeoJSON coordinate numbers as decimal.Decimal; json.dumps
    # has no default encoding for it. float() loses no precision that
    # matters for a geometry coordinate here (this is not a currency value).
    if isinstance(o, decimal.Decimal):
        return float(o)
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
