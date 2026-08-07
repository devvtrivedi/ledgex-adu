-- 0034_parcel_apn_not_identity.sql
-- Serves: I2 (a Fact's provenance, not a denormalised column, is the
-- record). Parcel identity diagnostic.
--
-- THE EVIDENCE. A full-file analysis of ca_san_jose.parcels' real
-- ~210MB export (225,039 features; Phase C's own summary: 225,030
-- non-blank APNs, 224,977 distinct, 9 null/blank) found the 53 "duplicate
-- occurrences" are 49 distinct APNs colliding across 102 features (53
-- excess). Of the 58 pairwise geometry relationships across those 49
-- groups: 24 disjoint, 32 touching, 2 with ~zero intersection area
-- (topology fuzz, functionally touching). LOTNUM (the source's own lot
-- number) differs between members in 44 of 49 groups. Of the 5 groups
-- where LOTNUM DOES match -- the closest candidates for "one lot, split
-- geometry" -- each independently shows a near-zero-area sliver
-- counterpart, a resurvey area mismatch, an "APNU_" (APN Update) batch
-- code, or an old-vs-new PARCELID pairing, not a genuine physical split.
-- The source's own working convention for a real multi-part parcel is a
-- native MultiPolygon feature (89 of them exist in the file); checked:
-- zero overlap between those 89 MultiPolygon APNs and the 49
-- duplicate-APN set. 9 of the 49 duplicate APN values are not even real
-- APNs -- they are the literal placeholder string fragment '???' (e.g.
-- '27704???'), used by the source for an unresolved suffix; unrelated
-- lots collide on an identical wildcard, not on a real shared identity.
-- One group's own NOTES field documents the source's reviewers actively
-- renumbering PARCELID to resolve a DIFFERENT duplicate collision
-- ("ID was 1000025370 but this was duplicate 8-9-21") in the same batch
-- that left APN undifferentiated. None of this supports "one legal
-- parcel, incorrectly exported as separate features" (the hypothesis
-- tested first, per instruction) -- it supports APN being stale across
-- replats, subdivisions and renumbering events that the source's own
-- PARCELID/PLANCRT/PLANMOD/NOTES fields track and APN does not. This is
-- B4 (ML review) confirmed, and confirmed as a stronger claim than B4
-- made: not merely fragile over time, but already non-unique within a
-- single point-in-time export.
--
-- Separately: 9 features have a genuinely blank APN. All 9 are
-- PARCELTYPE='Tax', FEATURECLASS='Parcel' (not a distinct ROW/water
-- type by the source's own typing); 6 of 9 carry
-- NOTES='No APN, data reviewer correction.' -- an explicit, human,
-- source-side acknowledgement of the gap, not an ingest miss. All 9
-- carry a valid PARCELID. Areas range from ~5K to ~977K (SHAPE_Area
-- units unconfirmed, per 0026 -- not uniformly slivers).
--
-- THE DECISION (reported before writing, not decided silently): does
-- parcel.apn survive as a column at all? KEPT, demoted from identity to
-- a non-authoritative cache -- not dropped. The alternative (drop the
-- column; APN lives only as a fact) matches this project's general
-- preference for a single source of truth, but there is a closer, more
-- specific precedent already in this schema: source.phase_status/active
-- vs. licence_channel (0002, §7.3). licence_channel is the sole runtime
-- authority there too, yet phase_status was KEPT as a column --
-- "descriptive, not authoritative... records why a source is off so a
-- human can read the ledger" -- guarded only by a same-row CHECK
-- (source_active_matches_phase) that cannot and does not verify
-- phase_status actually agrees with licence_channel, a different table.
-- parcel.apn versus current_fact is the identical shape of problem; this
-- migration applies the identical, already-adopted answer, rather than
-- inventing a second one. Dropping the column instead would also break
-- scripts/ingest_parcels.py's Phase D (three functions reference
-- parcel.apn directly) and remove the only current indexed lookup
-- (parcel_apn_prefix) with no replacement, since core/ and api/ do not
-- exist yet to redesign a lookup path around. situs_address is treated
-- identically for the same reason and needs no DDL change here -- it
-- was already nullable with no uniqueness constraint.
--
-- THE CASE AGAINST THIS DECISION, recorded rather than suppressed:
-- unlike phase_status, there is NO enforcement available here at all --
-- not even source_active_matches_phase's narrow same-row check. If a
-- parcel.apn fact is ever superseded, this column will silently keep
-- showing the old value forever, with nothing in CI able to notice.
-- That is a real, deliberately-accepted liability, not a solved one --
-- COMMENT ON COLUMN below is the only enforcement this migration
-- provides, and it is documentation, not a constraint.
--
-- THE CHANGE. Two identity assertions the evidence disproves:
--   - UNIQUE (jurisdiction_id, apn): 49 real collisions in the current
--     export alone.
--   - apn NOT NULL: 9 features supply no APN at all, acknowledged by the
--     source's own reviewers.
-- Both dropped. Checked before writing, not assumed: confirmed the live
-- constraint name (parcel_jurisdiction_id_apn_key) via
-- SELECT conname FROM pg_constraint WHERE conrelid = 'parcel'::regclass,
-- the same discipline 0015 used rather than guessing Postgres's
-- auto-generated name.
--
-- NOT touched: parcel.id (already a correct surrogate, per instruction),
-- parcel_apn_prefix (the index remains useful for a non-unique,
-- non-authoritative lookup-by-prefix; nothing about it asserted
-- uniqueness), parcel_id_jurisdiction_id_unique (unrelated -- backs the
-- parcel_exception/property_file composite FKs, not apn).

ALTER TABLE parcel
    DROP CONSTRAINT parcel_jurisdiction_id_apn_key;

ALTER TABLE parcel
    ALTER COLUMN apn DROP NOT NULL;

COMMENT ON COLUMN parcel.apn IS
    'Non-authoritative cache of the most recently observed parcel.apn fact -- NOT unique (49 confirmed source collisions), NOT required (9 confirmed source blanks; also NULL for a parcel whose only identifying feature carried an unresolved "???" placeholder, per policy: no fact is written for a non-value, so no cache value exists either). The fact ledger (query current_fact / fact for field_key=''parcel.apn'') is authoritative; this column reflects it only as of the last write and does not update on supersession. See 0034 for the evidence this was demoted on.';

COMMENT ON COLUMN parcel.situs_address IS
    'Non-authoritative cache of the most recently observed parcel.situs_address fact, same status as parcel.apn -- see its comment. Currently always NULL: ca_san_jose.parcels does not supply an address-shaped property (0026), so no fact and no cache value exists yet for any row.';
