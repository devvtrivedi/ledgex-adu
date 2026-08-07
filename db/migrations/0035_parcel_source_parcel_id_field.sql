-- 0035_parcel_source_parcel_id_field.sql
-- Serves: I2, I7. Parcel identity diagnostic, §6.1 task shape B.
--
-- Captures PARCELID as a fact -- not as a column, not as a uniqueness
-- assertion. The diagnostic found PARCELID unique across all 225,039
-- features (0 missing, 0 duplicates) and, unlike APN, actively curated by
-- the source's own reviewers (one duplicate-APN group's NOTES documents
-- PARCELID being hand-renumbered to resolve a collision). But PARCELID's
-- cross-export stability is exactly as unverified as OBJECTID's: every
-- fetch available -- the original pair and a fresh live pull taken to
-- specifically test this -- came back byte-identical, so there has been
-- no observed change to test PARCELID's persistence against. Recording
-- it now, as a fact with full provenance, is what makes that question
-- answerable LATER: the day the source changes an already-cited
-- PARCELID, fact_no_update (I4) forces a new fact row that supersedes the
-- old one, supersession_reason (0025) records why, and only then does a
-- real prior-value comparison exist. Without this row, there is nothing
-- to compare a future change against -- capturing it is the prerequisite
-- to the stability question, not an answer to it.
--
-- NOT adopted as a matching key. No uniqueness constraint, no FK, no
-- change to parcel.id (already a correct surrogate) or how a fact is
-- linked to a parcel. That decision -- whether PARCELID, or anything
-- else, should ever anchor cross-fetch parcel identity -- waits on an
-- observed source change to PARCELID and is explicitly out of scope
-- here.
--
-- INTID skipped: the diagnostic checked all 225,039 features and found
-- INTID == int(PARCELID) with zero exceptions. It is a redundant
-- integer-typed mirror of PARCELID, not a second observation -- recording
-- it would duplicate a fact for no informational gain.
--
-- OBJECTID skipped: its range (1..423,153 across 225,039 features) is
-- consistent with a persistent internal edit counter rather than a
-- fresh-per-export artifact, which is a point in its favor -- but it is
-- an untested hypothesis, not a finding, for the same reason PARCELID's
-- stability is untested (no observed export-to-export change exists to
-- check either against). Capturing an identifier whose export-order-
-- artifact risk was specifically flagged as a serious error to get wrong,
-- alongside a better-evidenced identifier, adds noise without adding
-- confidence. If OBJECTID ever needs capturing, that is its own
-- migration, made on its own evidence.

INSERT INTO field_definition (
    field_key, display_name, claim, value_type, unit, category,
    stale_after_days, required_for_file, phase1_deferred, deferral_reason,
    description
) VALUES (
    'parcel.source_parcel_id',
    'Source Parcel ID (county GIS internal identifier)',
    'public_record',
    'string',
    NULL,
    'parcel',
    NULL,
    false,
    false,
    NULL,
    'PARCELID as supplied by ca_san_jose.parcels -- the source''s own internal GIS row identifier, distinct from APN. Recorded as an observation with full provenance, not as a matching key: see 0035''s header for why capture now, adoption later. Confirmed unique and fully populated across all 225,039 features in the parcel identity diagnostic (2026-08). INTID is not captured separately: confirmed identical to int(PARCELID) with zero exceptions.'
)
ON CONFLICT (field_key) DO NOTHING;

-- Guarded, matched on the specific old value (0023's pattern): a database
-- seeded from the now-corrected db/seeds/day4_sources.sql already has
-- parcel.source_parcel_id in expected_fields, so this UPDATE matches zero
-- rows there and is a true no-op. A database seeded before this fix (or a
-- migrations-only database with no source row at all, e.g. CI) also
-- matches zero rows -- UPDATE, unlike INSERT, has no foreign-key
-- collision to guard against here (see CLAUDE.md's migration-vs-CI
-- convention): it simply updates nothing when the row doesn't exist yet.
UPDATE source
SET expected_fields = '["parcel.apn","parcel.geometry","parcel.source_parcel_id"]'::jsonb
WHERE id = 'ca_san_jose.parcels'
  AND expected_fields = '["parcel.apn","parcel.geometry"]'::jsonb;
