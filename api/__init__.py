"""P40: read-only internal viewer over the LedgeX database. One to three
trusted users, internal testing only -- NOT a customer-facing surface.

This is NOT §4's api/ ("FastAPI over core.compose and commerce"). Zero of
§4's 16 specified endpoints are implemented here. This package exists
because there is currently no serving layer of any kind (prompts/
P40-internal-viewer.md §0) and operational state (rights position, ingest
health, exceptions, real facts) is otherwise invisible to anyone but a
person running ad-hoc SQL. See that report for the full argument, including
why a composed/partial view is deliberately not built (none exists), why
the rights gate is not duplicated here (scripts.compose_property_file.
evaluate_rights_gate is imported, not reimplemented), and why this must not
be exposed beyond localhost until entitlement (commerce/) exists.
"""
