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

Same jurisdiction-free shape as core/store.insert_facts, and now (P24)
the same tuple-not-type shape too: insert_exceptions() takes
list[core.model.ParcelException], not positional 7-tuples -- P22
deferred this adoption deliberately (real hazard: detector_key/
detector_version, both `text NOT NULL` with no CHECK in
0010_exceptions.sql, are the same shape of transposition risk
confidence_rule_id/pack_version were for Fact, and corrupting either
would break the exact-version matching close_resolved_exceptions()/
close_exceptions_for_parcels()/relink_reopened_exceptions()/
retire_stranded_exceptions() all rely on) but on blast radius and
severity, not on the hazard being smaller -- 4 call sites across 3
files, against a database row with no whole-row immutability trigger
(unlike fact/0017/0040), so a transposed value here is theoretically
correctable later by a migration UPDATE. P22's own report named this
explicitly, not left unmentioned; P24 is that named later package.

detail's encoding contract settled separately from Fact.value's, not
inherited from it -- see core/model.ParcelException's own docstring,
design decision (d). Unlike Fact.value, detail keeps its native
dict[str, Any] typing (already committed since P21): every real caller's
payload is plain, Decimal-free, geometry-free strings, so nothing forces
the infra/-import question Fact.value's option (a) hit. insert_
exceptions() does the json.dumps() itself now -- one encoding rule, in
one place; callers pass a real dict, never a pre-encoded string.

ParcelException does NOT have nine unwritten fields the way Fact did
(checked, not assumed): of its 15 fields, 7 are written here; of the 8
that are not, 7 are legitimately never caller-set at insert time
(id/detected_at/outcome are DB-defaulted; resolved_at/resolved_by/
resolution_notes/reopened_from_id are lifecycle state this module's own
closure functions below set later, never at detection). Exactly one --
ruleset_version -- is a real choice not yet forced by any caller, and is
refused the same way Fact's nine were: a ParcelException carrying a
value there gets a loud, immediate error naming the field, not a silent
drop.

close_resolved_exceptions() and relink_reopened_exceptions() (P9,
prompts/P9-exception-resolution.md) are the closure half of exception
resolution -- deliberately NOT added to insert_exceptions()'s own shape
or call sites. load_zoning (scripts/ingest_zoning_permits.py) wires in
both, unchanged: it is the one detector that recomputes a full, current
classification every run and can therefore tell "still true" from "no
longer true" by exclusion. phase_e (scripts/ingest_parcels.py, P13) wires
in close_exceptions_for_parcels() -- not close_resolved_exceptions(),
which needs that same full-recompute pass and phase_e's CHANGED branch
does not have one; see that function's own docstring for the full
argument -- and relink_reopened_exceptions() unchanged (general-purpose
by construction, needs no recompute). flag_invalid_geometry.py's two
detectors call insert_exceptions() exactly as before, untouched.

retire_stranded_exceptions() (P16, prompts/P16-*.md, README finding #18)
is a THIRD, separate closure shape -- not a change to either of the two
above, which the P16 report argued and this module keeps exempt. Both
existing closures answer "did the current run positively determine this
condition changed" (condition_cleared, requires either a full recompute
or a caller-known resolved set). retire_stranded_exceptions() answers a
different question that has nothing to do with any run's findings: "does
this row's detector_version still exist as a rule anything evaluates."
Triggered once, by whoever bumps a DETECTOR_VERSION_* constant, not by
any regular ingest run -- no call site wires this in automatically,
deliberately, unlike every function above it in this file.
"""
import json

import psycopg2.extras

from core.model import ParcelException

EXCEPTION_COLUMNS = (
    "parcel_id, jurisdiction_id, type, severity, "
    "detector_key, detector_version, detail"
)
EXCEPTION_TEMPLATE = "(%s, %s, %s, %s, %s, %s, %s::jsonb)"

# The one ParcelException field insert_exceptions() does not write -- see
# this module's own docstring for why it's one, not Fact's nine.
_UNWRITTEN_FIELDS_AND_DEFAULTS = (
    ("ruleset_version", None),
)


def _check_no_unwritten_fields(pe):
    for field_name, default in _UNWRITTEN_FIELDS_AND_DEFAULTS:
        value = getattr(pe, field_name)
        if value != default:
            raise ValueError(
                f"ParcelException.{field_name}={value!r} was set, but "
                f"insert_exceptions() does not write that column (see "
                f"core/exceptions.py's own module docstring) -- it would "
                f"be silently dropped, not persisted."
            )


def insert_exceptions(cur, exceptions, page_size=2000):
    """exceptions: list[core.model.ParcelException]. Builds the same
    7-tuple this table has always taken (EXCEPTION_COLUMNS' order,
    unchanged) from each ParcelException's named fields -- see this
    module's docstring for which field is refused rather than silently
    ignored, and for detail's own encoding contract. page_size default
    (2000) matches two of the four original call sites; the other two
    pass 500 explicitly -- see module docstring.

    Refuses anything that is not actually a ParcelException -- notably a
    bare tuple, the exact shape every call site used to hand-build,
    same reasoning as core/store.insert_facts()."""
    for pe in exceptions:
        if not isinstance(pe, ParcelException):
            raise TypeError(
                f"insert_exceptions() requires core.model.ParcelException "
                f"instances, got {type(pe).__name__!r}."
            )
        _check_no_unwritten_fields(pe)
    exception_rows = [
        (
            str(pe.parcel_id), pe.jurisdiction_id, pe.type, pe.severity,
            pe.detector_key, pe.detector_version, json.dumps(pe.detail),
        )
        for pe in exceptions
    ]
    psycopg2.extras.execute_values(
        cur,
        f"INSERT INTO parcel_exception ({EXCEPTION_COLUMNS}) VALUES %s",
        exception_rows,
        template=EXCEPTION_TEMPLATE,
        page_size=page_size,
    )


def close_resolved_exceptions(cur, detector_key, detector_version, still_true_pairs):
    """P9 (prompts/P9-exception-resolution.md): the closure half of
    exception resolution. still_true_pairs: iterable of (parcel_id, reason)
    the CURRENT run found still true -- the same shape load_zoning's own
    existing_open already computes. Closes every currently-open row for
    this EXACT (detector_key, detector_version) -- not any other version,
    see the migration's own header (0047) for why cross-version closure
    would fabricate a claim the current run never evaluated -- whose
    (parcel_id, detail->>'reason') is NOT in still_true_pairs: outcome =
    'condition_cleared', resolved_at = clock_timestamp(), resolved_by =
    detector_key (0015's biconditional requires resolved_by non-null for
    any non-open outcome; the running detector is the true, correct answer
    to "who resolved this", not a documented convention -- see P9's
    correction (b)). One set-based UPDATE, not a per-row loop. Returns the
    number of rows closed.

    An empty still_true_pairs is not a caller error -- it means the run
    found nothing true at all, and every currently-open row for this
    detector_key/detector_version is correctly closed."""
    pairs = list(still_true_pairs)
    parcel_ids = [p for p, _r in pairs]
    reasons = [r for _p, r in pairs]
    cur.execute(
        """
        UPDATE parcel_exception pe
           SET outcome = 'condition_cleared',
               resolved_at = clock_timestamp(),
               resolved_by = %(detector_key)s
         WHERE pe.detector_key = %(detector_key)s
           AND pe.detector_version = %(detector_version)s
           AND pe.outcome = 'open'
           AND NOT EXISTS (
                 SELECT 1
                   FROM unnest(%(parcel_ids)s::uuid[], %(reasons)s::text[]) AS st(parcel_id, reason)
                  WHERE st.parcel_id = pe.parcel_id
                    AND st.reason = (pe.detail ->> 'reason')
               )
        """,
        {
            "detector_key": detector_key,
            "detector_version": detector_version,
            "parcel_ids": parcel_ids,
            "reasons": reasons,
        },
    )
    return cur.rowcount


def close_exceptions_for_parcels(cur, detector_key, detector_version, parcel_ids):
    """P13 (prompts/P13-apn-resolvability-flip.md): closes every currently
    open (detector_key, detector_version) exception for the given
    parcel_ids, unconditionally -- condition_cleared, resolved_at =
    clock_timestamp(), resolved_by = detector_key.

    Deliberately NOT close_resolved_exceptions() above, despite the
    identical outcome columns: that function needs still_true_pairs, a
    FULL recompute of "every parcel this run found still true for this
    detector," to safely infer what to close by exclusion -- correct for
    load_zoning, which reclassifies every parcel against the spatial join
    every single run. Phase E's CHANGED branch has no equivalent
    full-recompute pass (P9's own scoping note for #17 says so explicitly,
    and that is why this closure was deferred rather than bolted on as-is)
    -- it only ever sees the parcels that changed. Passing an incomplete
    still_true_pairs to close_resolved_exceptions here would close every
    OTHER currently-open parcel_apn_unresolvable exception in the database,
    not just the ones this run resolved.

    This function needs no such inference: the caller already knows, for
    each parcel_id given, that its condition definitely cleared THIS run
    (it just wrote that parcel a new resolvable parcel.apn fact) -- a
    direct, targeted close, not an exclusion over a global "still true"
    set. Returns the number of rows closed."""
    if not parcel_ids:
        return 0
    cur.execute(
        """
        UPDATE parcel_exception
           SET outcome = 'condition_cleared',
               resolved_at = clock_timestamp(),
               resolved_by = %(detector_key)s
         WHERE detector_key = %(detector_key)s
           AND detector_version = %(detector_version)s
           AND outcome = 'open'
           AND parcel_id = ANY(%(parcel_ids)s::uuid[])
        """,
        {
            "detector_key": detector_key,
            "detector_version": detector_version,
            "parcel_ids": list(parcel_ids),
        },
    )
    return cur.rowcount


def relink_reopened_exceptions(cur, detector_key, detector_version):
    """The other half of P9's reopening decision (prompts/P9-exception-
    resolution.md). Call AFTER inserting a fresh batch of open rows for
    this exact (detector_key, detector_version), in the same transaction.
    For every currently-open row at this key with reopened_from_id still
    NULL, points it at the most recently resolved_at prior row sharing its
    exact (parcel_id, detail->>'reason'), if one exists -- a first-ever
    finding, with no prior row at that key, is left NULL, correctly: it is
    not a reopening. One set-based UPDATE, not a per-row loop or a
    per-pair query. Idempotent by construction (reopened_from_id IS NULL
    in the WHERE clause): an already-linked row is never touched again, so
    calling this after every run only ever links that run's own genuinely
    new rows -- it cannot retroactively relabel a row a past run already
    decided was NOT a reopening. Returns the number of rows linked."""
    cur.execute(
        """
        UPDATE parcel_exception new_pe
           SET reopened_from_id = prior.id
          FROM (
                SELECT DISTINCT ON (parcel_id, reason) id, parcel_id, reason, resolved_at
                  FROM (
                        SELECT id, parcel_id, (detail ->> 'reason') AS reason, resolved_at
                          FROM parcel_exception
                         WHERE detector_key = %(detector_key)s
                           AND detector_version = %(detector_version)s
                           AND outcome <> 'open'
                       ) AS closed
                 ORDER BY parcel_id, reason, resolved_at DESC
               ) AS prior
         WHERE new_pe.detector_key = %(detector_key)s
           AND new_pe.detector_version = %(detector_version)s
           AND new_pe.outcome = 'open'
           AND new_pe.reopened_from_id IS NULL
           AND new_pe.parcel_id = prior.parcel_id
           AND (new_pe.detail ->> 'reason') = prior.reason
        """,
        {"detector_key": detector_key, "detector_version": detector_version},
    )
    return cur.rowcount


def retire_stranded_exceptions(cur, detector_key, retired_version):
    """P16 (prompts/P16-*.md, README finding #18): the disposition for an
    open exception whose raising detector_version is no longer evaluated by
    anything -- a detector_version bump (e.g. zoning_spatial_join_
    unresolvable 1.0 -> 2.0) strands every older-version open row, since
    close_resolved_exceptions()/close_exceptions_for_parcels()/
    relink_reopened_exceptions() all match detector_version exactly, on
    purpose (0047's header; widening that match would fabricate a
    condition_cleared claim the current rule never evaluated).

    NOT one of those three functions and NOT wired into any ingest call
    site -- a version bump is a one-time code change, not a regular run's
    output. Call this once, by hand, for (detector_key, retired_version)
    immediately after retiring a DETECTOR_VERSION_* constant in a script.

    Sets outcome='version_retired' (0050), resolved_at=clock_timestamp(),
    resolved_by='system:detector_version_retired' -- the retirement pass
    itself is the actor, not the original detector_key (which never
    re-evaluated these rows) and not a person (I14). resolution_notes
    records which version was retired. detail (the original evidence),
    exception_evidence and reopened_from_id are untouched -- this asserts
    nothing about the condition these rows describe, only that nothing
    will ever re-evaluate them under the retired rule.

    Scoped to outcome='open' rows at the EXACT (detector_key,
    retired_version) given -- every other version, and every already-
    resolved row, is untouched by construction (WHERE clause, not
    filtered in application code). Idempotent: a second call with the same
    arguments matches zero rows (outcome is no longer 'open') and returns
    0. Returns the number of rows retired."""
    cur.execute(
        """
        UPDATE parcel_exception
           SET outcome = 'version_retired',
               resolved_at = clock_timestamp(),
               resolved_by = 'system:detector_version_retired',
               resolution_notes = 'detector_version ' || %(retired_version)s || ' retired'
         WHERE detector_key = %(detector_key)s
           AND detector_version = %(retired_version)s
           AND outcome = 'open'
        """,
        {"detector_key": detector_key, "retired_version": retired_version},
    )
    return cur.rowcount
