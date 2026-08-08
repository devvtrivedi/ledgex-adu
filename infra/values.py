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


def decimal_default(o):
    # ijson parses GeoJSON coordinate numbers as decimal.Decimal; json.dumps
    # has no default encoding for it. float() loses no precision that
    # matters for a geometry coordinate here (this is not a currency value).
    if isinstance(o, decimal.Decimal):
        return float(o)
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
