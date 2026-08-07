-- 0026_correct_parcels_expected_fields.sql
-- Serves: I9/§7.4 (declared coverage gaps, never silent omissions).
--
-- db/seeds/day4_sources.sql registers ca_san_jose.parcels' expected_fields
-- as ["parcel.apn","parcel.geometry","parcel.lot_area_gis","parcel.situs_address"].
-- scripts/ingest_parcels.py's Phase C inspection (real ~210MB GeoJSON,
-- 225,039 features, every property key enumerated) found the source
-- supplies neither parcel.lot_area_gis nor parcel.situs_address: no
-- address-shaped property exists anywhere in the feature set, and while a
-- SHAPE_Area property is present, it is not treated as parcel.lot_area_gis
-- -- field_definition declares that field's unit as square_feet, and
-- SHAPE_Area's actual unit and computation basis are unconfirmed against
-- this export's EPSG:4326 (geographic, degrees) coordinates. The seed was
-- asserting a coverage it does not have.
--
-- Unlike 0023 (which only needed to patch already-seeded databases,
-- because the endpoint_url it corrected had already been fixed at the
-- seed source in an earlier commit, f8291b7), expected_fields has never
-- been corrected in db/seeds/day4_sources.sql itself before this. A
-- migration alone, guarded or not, cannot fix that: this project's
-- standard flow applies migrations BEFORE any seed runs, so a guarded
-- UPDATE here matches zero rows on a fresh database (source has no rows
-- yet) and then the still-unedited seed file would insert the wrong
-- expected_fields immediately afterward, forever, on every future fresh
-- install -- confirmed directly, not assumed: ran exactly that sequence
-- (26 migrations, then day4_sources.sql) against a scratch database
-- before writing this comment, and expected_fields came out wrong.
--
-- So this is 0016's pattern, not 0023's: db/seeds/day4_sources.sql is
-- ALSO corrected in this same commit (expected_fields narrowed to the two
-- fields actually supplied; phase1_deferred/deferral_reason added to the
-- field_definition INSERT for parcel.lot_area_gis and parcel.situs_address)
-- so a newly-seeded database gets it right from the start. This migration
-- exists only for a database that was ALREADY seeded before this fix --
-- matched against the specific old (wrong) value, not applied blindly, so
-- it is a true no-op on a database seeded from the now-corrected file.
--
--   1. source.expected_fields for ca_san_jose.parcels narrowed to the two
--      fields actually supplied.
--   2. field_definition.phase1_deferred = true, with a deferral_reason,
--      for parcel.lot_area_gis and parcel.situs_address -- §7.4's
--      mechanism for a declared, known coverage gap, not a silent one.
--      Both rows already have required_for_file = false (day4_sources.sql
--      never set it true for either), so field_deferred_not_required is
--      satisfied without touching that column.

UPDATE source
SET expected_fields = '["parcel.apn","parcel.geometry"]'::jsonb
WHERE id = 'ca_san_jose.parcels'
  AND expected_fields = '["parcel.apn","parcel.geometry","parcel.lot_area_gis","parcel.situs_address"]'::jsonb;

UPDATE field_definition
SET phase1_deferred = true,
    deferral_reason = 'ca_san_jose.parcels does not supply this field. No address-shaped property exists anywhere in the GeoJSON feature set (checked all 225,039 features). Confirmed via scripts/ingest_parcels.py Phase C, 2026-08-07.'
WHERE field_key = 'parcel.situs_address'
  AND phase1_deferred = false;

UPDATE field_definition
SET phase1_deferred = true,
    deferral_reason = 'ca_san_jose.parcels does not supply a declared lot_area_gis field. SHAPE_Area is present on every feature but is not treated as equivalent: this field is declared unit=square_feet, and SHAPE_Area''s unit and computation basis are unconfirmed against this export''s EPSG:4326 (geographic, degrees) coordinates -- asserting square_feet without confirming it would fabricate a unit. Confirmed via scripts/ingest_parcels.py Phase C, 2026-08-07.'
WHERE field_key = 'parcel.lot_area_gis'
  AND phase1_deferred = false;
