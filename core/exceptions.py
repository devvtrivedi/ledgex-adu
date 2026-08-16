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

close_resolved_exceptions() and relink_reopened_exceptions() (P9,
prompts/P9-exception-resolution.md) are the closure half of exception
resolution -- deliberately NOT added to insert_exceptions()'s own shape
or call sites. Only load_zoning (scripts/ingest_zoning_permits.py) wires
them in: it is the one detector that recomputes a full, current
classification every run and can therefore tell "still true" from
"no longer true". phase_e and flag_invalid_geometry.py's two detectors
call insert_exceptions() exactly as before, untouched.
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
