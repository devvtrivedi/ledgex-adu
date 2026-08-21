#!/usr/bin/env python3
"""P40 internal viewer -- FastAPI app. Read-only, no auth, localhost only.

Run: python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8420
(from the repo root -- REPO_ROOT below assumes that CWD, same as every
scripts/*.py entry point already does).

DO NOT EXPOSE THIS BEYOND LOCALHOST. There is no authentication, no
session, no role system -- commerce/ and entitlement do not exist yet, and
a half-built auth layer would be worse than an honestly absent one
(prompts/P40-internal-viewer.md, boundary 5). Bind to 127.0.0.1 only.

READ-ONLY, STRUCTURALLY. Every route below is a GET. There is no POST, PUT,
PATCH or DELETE anywhere in this module that touches a public table -- the
one write path in this package (scripts/seed_internal_test_licences.py) is
a separate, explicitly-gated CLI script, never reachable through this app.

CONNECTION HANDLING. Each request opens its own connection via
infra.env.get_db() and closes it in a `finally`, after an explicit
rollback -- never pooled, never reused across requests. This is a
deliberate choice, not an oversight: with 1-3 internal users hitting a
handful of read endpoints, a real connection pool is exactly the kind of
"anticipated, not forced by need" complexity requirements.txt's own comment
already argues against for this codebase, and a fresh connection per
request trivially satisfies "every request ends its own transaction"
(Prompt 1's Finding A: a pooled connection holding an unclosed transaction
across requests is what makes that finding real) -- there is no connection
left open for a second request to inherit a mess from. If this viewer ever
needs real concurrency or a persistent pool, that is a future package's
decision to make deliberately, not this one's to back into.

RIGHTS GATE. GET /v1/parcels/{parcel_id}/facts is the one route that puts
fact VALUES on a screen, which makes it an output channel under I6 exactly
like the composer (§1.1). It calls scripts.compose_property_file's own
evaluate_rights_gate() -- the SAME function _compose() calls, imported, not
reimplemented -- so this app cannot drift from the composer's own rights
decisions. See that function's own docstring, and prompts/
P40-internal-viewer.md §0 (D3), for why this is not yet core/rights.py.
"""
import datetime
import os
import re
import sys
import uuid
from typing import Literal

import psycopg2.extensions
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from infra.env import get_db  # noqa: E402
import compose_property_file as cpf  # noqa: E402 -- module under reuse, not reimplemented

# D1 (prompts/P40-internal-viewer.md §0): this viewer reads on the existing
# `api` output_channel enum member, not a new one. Every route below that
# touches facts uses exactly this channel -- never a query parameter a
# caller could widen.
VIEWER_CHANNEL = "api"

# P41 Fix 2: makes evaluate_rights_gate's own docstring true. That docstring
# says "api/ validates the same way against the same constant [KNOWN_CHANNELS]"
# -- it did not, until this line. Module-level, so a typo or a future
# VIEWER_CHANNEL edit fails LOUDLY at import/startup (SystemExit, nothing ever
# serves a request), never silently gates real fact values on a channel that
# does not exist. No live bug today (VIEWER_CHANNEL="api" already IS a real
# member) -- this is a docstring-was-testimony-not-evidence repair, not a bug
# fix, per CONVENTIONS' own line on the subject.
if VIEWER_CHANNEL not in cpf.KNOWN_CHANNELS:
    raise SystemExit(
        f"api/main.py's VIEWER_CHANNEL={VIEWER_CHANNEL!r} is not one of "
        f"compose_property_file.KNOWN_CHANNELS={cpf.KNOWN_CHANNELS!r} -- refusing to "
        f"start. Every route that gates fact values must use a real output_channel "
        f"enum member (D1); serving requests against an invalid channel would make "
        f"every fact silently RIGHTS_BLOCKED for a reason that has nothing to do with "
        f"rights."
    )

# P41 Fix 1: read live from a real database, not transcribed from any prompt
# or migration comment -- `SELECT enum_range(NULL::exception_outcome)` against
# ledgex_p40_gate1 returned exactly these six, in this order. FastAPI's own
# Literal-based Query validation is the boundary check (see get_exceptions'
# own `outcome` parameter below) -- this tuple exists so the accepted values
# and this module's own error text can never disagree with each other, the
# same reason KNOWN_CHANNELS exists in compose_property_file.py.
KNOWN_EXCEPTION_OUTCOMES = (
    "open", "confirmed", "false_positive", "unresolved", "condition_cleared",
    "version_retired",
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = FastAPI(
    title="LedgeX internal viewer (P40)",
    description=(
        "Read-only internal tool. NOT §4's api/ -- zero of the 16 spec-defined "
        "endpoints are implemented here. Internal testing only; do not expose "
        "beyond localhost."
    ),
    version="internal-0.1.0",
)


def _db():
    """One connection per request, closed (with a rollback first) in a
    `finally` -- see this module's own docstring for why this is not a
    pool."""
    conn = get_db()
    try:
        yield conn
    finally:
        # P41 Fix 3(iii): named constant, not the bare 0 literal this used to
        # read -- compose_property_file.py's own P39 fix for the identical
        # check uses psycopg2.extensions.TRANSACTION_STATUS_IDLE. Two
        # spellings of one concept across two files is exactly how a future
        # reader learns the wrong one.
        if conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            conn.rollback()
        conn.close()


def _rows_as_dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


@app.get("/")
def index():
    """Serves the one self-contained HTML viewer. NOT in website/ -- that
    directory is generated from docs/*.md by build/build_website.py and
    qa_check.py's check_website_current fails docs.yml if it drifts; this
    file is unrelated to that pipeline entirely."""
    return FileResponse(os.path.join(STATIC_DIR, "viewer.html"))


# ---------------------------------------------------------------------------
# RIGHTS AND SOURCES
# ---------------------------------------------------------------------------

@app.get("/v1/rights")
def get_rights(conn=Depends(_db)):
    """licence x licence_channel, joined. The rationale is already written
    for humans (§7.3: licences.yaml is the single source of truth for
    channel eligibility) -- surfaced verbatim, never paraphrased, per this
    package's own instruction."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT l.id AS licence_id, l.display_name, l.restriction, "
            "l.commercial_use, l.redistribution, l.cleared_by, l.cleared_at, "
            "lc.channel, lc.allowed, lc.rationale "
            "FROM licence l "
            "JOIN licence_channel lc ON lc.licence_id = l.id "
            "ORDER BY l.id, lc.channel"
        )
        return {"data": _rows_as_dicts(cur)}


@app.get("/v1/sources")
def get_sources(conn=Depends(_db)):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, jurisdiction_id, display_name, steward, method, "
            "phase_status, phase_status_reason, licence_id, endpoint_url, "
            "cadence_stated, url_verified_at, active, earliest_record_date, "
            "expected_fields FROM source ORDER BY jurisdiction_id, id"
        )
        return {"data": _rows_as_dicts(cur)}


# ---------------------------------------------------------------------------
# INGEST HEALTH
# ---------------------------------------------------------------------------

@app.get("/v1/job-runs")
def get_job_runs(
    status: str | None = Query(None, description="filter: running|succeeded|failed|skipped_unchanged"),
    conn=Depends(_db),
):
    with conn.cursor() as cur:
        if status:
            cur.execute(
                "SELECT id, job_key, jurisdiction_id, source_id, status, started_at, "
                "finished_at, snapshot_id, rows_in, rows_out, schema_drift, error, metrics "
                "FROM job_run WHERE status = %s ORDER BY started_at DESC LIMIT 500",
                (status,),
            )
        else:
            cur.execute(
                "SELECT id, job_key, jurisdiction_id, source_id, status, started_at, "
                "finished_at, snapshot_id, rows_in, rows_out, schema_drift, error, metrics "
                "FROM job_run ORDER BY started_at DESC LIMIT 500"
            )
        return {"data": _rows_as_dicts(cur)}


# ---------------------------------------------------------------------------
# EXCEPTIONS (Track A)
# ---------------------------------------------------------------------------

@app.get("/v1/exceptions")
def get_exceptions(
    # P41 Fix 1: outcome is compared directly against parcel_exception.outcome,
    # a real Postgres ENUM column (exception_outcome) -- an unvalidated value
    # reaches that comparison as a bare literal and Postgres itself rejects it
    # (psycopg2.errors.InvalidTextRepresentation, surfacing as an unhandled
    # 500) rather than silently matching nothing. Literal[*KNOWN_EXCEPTION_
    # OUTCOMES] makes FastAPI's own validation machinery reject a non-member
    # before this function body ever runs -- a 422, self-documented in /docs,
    # naming the parameter and every accepted value -- with zero bespoke
    # validation code and zero risk of this description string drifting from
    # the tuple that actually gates it (they are now the same object).
    outcome: Literal[*KNOWN_EXCEPTION_OUTCOMES] = "open",
    detector_key: str | None = None,
    detector_version: str | None = None,
    conn=Depends(_db),
):
    clauses = ["outcome = %s"]
    params = [outcome]
    if detector_key:
        clauses.append("detector_key = %s")
        params.append(detector_key)
    if detector_version:
        clauses.append("detector_version = %s")
        params.append(detector_version)
    where = " AND ".join(clauses)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id, parcel_id, jurisdiction_id, type, severity, detector_key, "
            f"detector_version, ruleset_version, detail, detected_at, outcome, "
            f"resolved_at, resolved_by, resolution_notes, reopened_from_id "
            f"FROM parcel_exception WHERE {where} ORDER BY detected_at DESC LIMIT 500",
            params,
        )
        return {"data": _rows_as_dicts(cur)}


# ---------------------------------------------------------------------------
# COMPOSITIONS
# ---------------------------------------------------------------------------

@app.get("/v1/property-files")
def get_property_files(conn=Depends(_db)):
    """property_file with its refusals array (already jsonb) plus the
    property_file_fact links and their `use` value. No composed/partial
    example is invented -- every row here is exactly what
    compose_property_file.py actually wrote (today, always status='refused'
    -- prompts/P40-internal-viewer.md boundary 4)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, parcel_id, jurisdiction_id, channel, status, composed_at, "
            "as_of, pack_version, ruleset_version, composer_version, "
            "geometry_tier_used, election, refusals, omitted_for_rights, "
            "attribution, unmet_fields, delivered_at, compose_ms "
            "FROM property_file ORDER BY composed_at DESC LIMIT 200"
        )
        files = _rows_as_dicts(cur)
        for f in files:
            cur.execute(
                "SELECT fact_id, use FROM property_file_fact WHERE property_file_id = %s "
                "ORDER BY use, fact_id",
                (f["id"],),
            )
            f["facts"] = _rows_as_dicts(cur)
        return {"data": files}


# ---------------------------------------------------------------------------
# FACTS -- THROUGH THE RIGHTS GATE
# ---------------------------------------------------------------------------

class FactEnvelopeLite(BaseModel):
    fact_id: str
    field_key: str
    value: object
    licence_id: str
    source_id: str | None = None
    snapshot_id: str | None = None
    method: str | None = None
    retrieved_at: datetime.datetime | None = None
    is_derived: bool


class OmittedForRights(BaseModel):
    field_key: str
    licence_id: str
    reason: str


class ParcelFactsResponse(BaseModel):
    """P41 Fix 3(ii): FactEnvelopeLite used to be declared and never
    referenced anywhere -- a model claiming to describe a response shape it
    did not actually gate. Wired in as this route's own response_model
    (not just FactEnvelopeLite alone: the route's real top-level shape is
    this wrapper, two differently-shaped lists, not a bare list of facts) --
    self-documents in /docs, and FastAPI/Pydantic will now silently DROP any
    field this module returns but doesn't declare here, which is exactly why
    `is_derived` (added on FactEnvelopeLite above) had to be added in the
    same edit as this model: without it, wiring response_model in would have
    silently deleted the I9 derived-fact signal from every response, a real
    regression caught by writing this docstring, not by a test."""
    parcel_id: str
    as_of: datetime.datetime
    channel: str
    facts: list[FactEnvelopeLite]
    omitted_for_rights: list[OmittedForRights]


@app.get("/v1/parcels/{parcel_id}/facts", response_model=ParcelFactsResponse)
def get_parcel_facts(
    parcel_id: str,
    as_of: datetime.datetime | None = Query(None, description="RFC 3339 UTC; defaults to now() (§4.1)"),
    conn=Depends(_db),
):
    """current_fact_at(ts) for one parcel, split into permitted vs
    omitted_for_rights by the SAME gate compose() uses -- boundary 3.
    channel is always VIEWER_CHANNEL ('api', D1); not a query parameter --
    widening it per-request would be exactly the "second gate that could
    silently disagree" this package's own D3 argues against.

    P41 Fix 3(i): parcel_id is validated as a real UUID at the boundary
    (400 if not) and checked for existence (404 if well-formed but no such
    parcel) BEFORE current_fact_at() ever runs -- current_fact_at(ts) casts
    its own parcel_id filter to uuid internally, and an unvalidated
    non-uuid string reached that cast as a bare value and surfaced as an
    uncaught psycopg2.errors.InvalidTextRepresentation -> HTTP 500. Chosen
    404 over an empty 200 for "well-formed uuid, no such parcel": this
    codebase already draws exactly this distinction one layer down
    (compose_property_file's own PARCEL_REFERENCE_UNKNOWN vs PARCEL_NO_FACTS
    -- P37, README finding #40) -- a parcel that does not exist is a
    different, more specific condition than a real parcel with zero current
    facts, and collapsing them back into one 200 here would lose a
    distinction the composer itself considers worth keeping."""
    try:
        uuid.UUID(parcel_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"parcel_id={parcel_id!r} is not a valid UUID.",
        )

    ts = as_of or datetime.datetime.now(datetime.timezone.utc)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM parcel WHERE id = %s", (parcel_id,))
        if cur.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail=f"No parcel exists with id={parcel_id!r}.",
            )

        cur.execute(
            "SELECT id, field_key, licence_id, value, source_id, snapshot_id, method, "
            "retrieved_at FROM current_fact_at(%s) WHERE parcel_id = %s "
            "ORDER BY field_key",
            (ts, parcel_id),
        )
        touched_full = cur.fetchall()
        # evaluate_rights_gate's own shape is (fact_id, field_key, licence_id,
        # value) 4-tuples -- current_fact_at returns more columns here (for
        # provenance display), so project down to exactly what the gate
        # expects rather than changing the gate's signature for this caller.
        touched_for_gate = [(r[0], r[1], r[2], r[3]) for r in touched_full]
        allowed_by_licence, blocked_by_licence = cpf.evaluate_rights_gate(
            cur, touched_for_gate, VIEWER_CHANNEL
        )

    permitted = []
    omitted_for_rights = []
    for fact_id, field_key, licence_id, value, source_id, snapshot_id, method, retrieved_at in touched_full:
        row = {
            "fact_id": str(fact_id), "field_key": field_key, "value": value,
            "licence_id": licence_id, "source_id": source_id,
            "snapshot_id": snapshot_id, "method": method, "retrieved_at": retrieved_at,
            # I9: a derived conclusion must never render in the visual/structural
            # treatment reserved for a retrieved fact. No derived fact exists
            # anywhere in this database yet (method='derived' has zero rows,
            # confirmed by this package's own report), so this is untested
            # against real data -- but it costs nothing to build the
            # distinction in now rather than retrofit it at the first one.
            # method IS the right proxy here, not a separate lookup: fact's
            # own fact_provenance_complete CHECK already ties method='derived'
            # to having no source_id/snapshot_id, so it is the same signal
            # field_definition.claim would give, already on this row.
            "is_derived": method == "derived",
        }
        if allowed_by_licence.get(licence_id, False):
            permitted.append(row)
        else:
            omitted_for_rights.append({
                "field_key": field_key, "licence_id": licence_id,
                "reason": f"Licence {licence_id!r} forbids channel {VIEWER_CHANNEL!r} "
                          f"(§7.3, I6) -- default-deny applies whether the licence "
                          f"explicitly denies this channel or simply has no allowed=true "
                          f"row for it.",
            })

    return {
        "parcel_id": parcel_id,
        "as_of": ts,
        "channel": VIEWER_CHANNEL,
        "facts": permitted,
        "omitted_for_rights": omitted_for_rights,
    }


# ---------------------------------------------------------------------------
# SCHEMA STATE
# ---------------------------------------------------------------------------

@app.get("/v1/schema")
def get_schema_state(conn=Depends(_db)):
    migrations_dir = os.path.join(REPO_ROOT, "db", "migrations")
    # P41 Fix 3(iv): the NNNN_snake_case.sql naming convention is enforced by
    # convention, not by anything mechanical -- a non-matching filename used
    # to raise AttributeError on re.match(...).None.group(1). Every current
    # file matches (confirmed: unrecognized_files is empty against the real
    # tree, not merely assumed to be), so this was latent, never live -- but
    # skip-and-report is the honest response to a convention with no
    # enforcement, not a guess that it will always hold.
    on_disk = []
    unrecognized_files = []
    for f in sorted(os.listdir(migrations_dir)):
        if not f.endswith(".sql"):
            continue
        m = re.match(r"^(\d{4})_", f)
        if m:
            on_disk.append(m.group(1))
        else:
            unrecognized_files.append(f)
    on_disk = sorted(on_disk)
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
        has_ledger = cur.fetchone()[0]
        if not has_ledger:
            return {
                "has_ledger": False,
                "on_disk_count": len(on_disk),
                "recorded_count": 0,
                "missing": on_disk,
                "unexpected": [],
                "unrecognized_files": unrecognized_files,
            }
        cur.execute("SELECT version, applied_at, baselined FROM schema_migrations ORDER BY version")
        recorded_rows = _rows_as_dicts(cur)
    recorded = sorted(r["version"] for r in recorded_rows)
    return {
        "has_ledger": True,
        "on_disk_count": len(on_disk),
        "recorded_count": len(recorded),
        "missing": sorted(set(on_disk) - set(recorded)),
        "unexpected": sorted(set(recorded) - set(on_disk)),
        "recorded": recorded_rows,
        "unrecognized_files": unrecognized_files,
    }
