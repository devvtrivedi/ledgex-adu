-- Day 4: Register the three confirmed San José sources
-- Run with: psql "$DATABASE_URL" < db/seeds/day4_sources.sql

\set ON_ERROR_STOP on

BEGIN;

-- ============================================================================
-- LICENCES (idempotent: ON CONFLICT DO NOTHING)
-- ============================================================================
-- observed_at = 2026-07-31, the Municipal Data & API Audit v1.1's own stated
-- research baseline / access date for these three datasets ("RESEARCH
-- BASELINE 31 JULY 2026"; per-city evidence register entry J-SCC-12 for San
-- Jose lists GIS Open Data / City data portal / Zoning districts / Active
-- building permits all "Accessed 31 Jul 2026"; the licence table on p.17-18
-- records Parcels=CC BY, Zoning Districts=CC BY, Active Building Permits=CC0
-- as of that same pass). NOT a fabricated now() -- this is a real, sourced
-- date, not the date this seed script happens to run.
--
-- cleared_by / cleared_at are NULL, not 'Devin'/now(): the audit's own
-- diligence register (p.36, Evidence Index) lists "San José licence
-- confirmations -- Per-resource channel posture and counsel/owner sign-off"
-- as status "Pending", and separately "Source and licence ledger -- URL/item
-- ID, snapshot, retrieval date, observed terms" also "Pending". Nobody --
-- Devin included -- has performed that sign-off yet. NULL is the honest
-- value until a specific actor and date can be named for it.
--
-- terms_url is the canonical CC deed for each licence. evidence_uri is NULL:
-- no stored snapshot of the actual terms page exists yet (the audit recorded
-- the licence position, not a retained copy of the terms text) -- a real gap
-- in the rights position, recorded here rather than papered over.
INSERT INTO licence (
  id, display_name, restriction, commercial_use, redistribution,
  attribution_text, terms_url, evidence_uri, observed_at, cleared_by, cleared_at
) VALUES
  ('cc0', 'CC0 1.0 Universal', 'open', 'allowed', 'allowed',
   NULL, 'https://creativecommons.org/publicdomain/zero/1.0/', NULL,
   '2026-07-31'::timestamptz, NULL, NULL),
  ('cc_by_4_0', 'CC BY 4.0', 'attribution', 'allowed', 'allowed',
   'Data © City of San José', 'https://creativecommons.org/licenses/by/4.0/', NULL,
   '2026-07-31'::timestamptz, NULL, NULL)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- LICENCE CHANNELS: Which output channels each licence permits
-- ============================================================================
-- Default deny: if a channel row is missing, output is denied.
--
-- Corrected 2026-08-07 (finding #3): this seed originally opened all four
-- channels for both cc0 and cc_by_4_0 with allowed=true, while cleared_by,
-- cleared_at and evidence_uri above are all NULL -- the audit's own
-- diligence register (p.36, Evidence Index) lists "San José licence
-- confirmations -- Per-resource channel posture and counsel/owner sign-off"
-- as status "Pending", the same Pending status already noted above for
-- cleared_by/cleared_at. Opening every channel while sign-off is Pending
-- was wrong: the original advice to open them was reviewed and reversed by
-- a second, independent pass. Licence IDENTIFICATION is evidenced --
-- Municipal Data & API Audit v1.1, observed 2026-07-31, records
-- Parcels/Zoning Districts as CC BY and Active Building Permits as CC0 --
-- but identification is not sign-off, and I6 blocks on unknown/uncleared
-- rights, not merely on unknown licence identity. No channel is cleared
-- for output until counsel/owner sign-off actually completes.
--
-- allowed=false, not a deleted row: default-deny already denies an absent
-- row, but an explicit false with a rationale records the decision and
-- preserves the audit trail; absence records nothing. Nothing composes or
-- outputs today (no ingestion has run), so this costs nothing now and
-- forces a conscious per-channel decision, with a written rationale, when
-- the composer arrives and sign-off has actually happened.
--
-- See db/migrations/0030_licence_channel_pending_clearance.sql for the
-- correction on any database already seeded from the original version of
-- this file.

INSERT INTO licence_channel (licence_id, channel, allowed, rationale) VALUES
  -- CC0 (Active Building Permits): licence identification confirmed
  -- (Municipal Data & API Audit v1.1, observed 2026-07-31), but
  -- counsel/owner sign-off is Pending per the audit's Evidence Index
  -- (p.36). No channel is cleared for output until sign-off completes.
  ('cc0', 'free_snapshot', false, 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'),
  ('cc0', 'paid_property_file', false, 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'),
  ('cc0', 'api', false, 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'),
  ('cc0', 'bulk_export', false, 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'),

  -- CC BY 4.0 (Parcels, Zoning Districts): same posture -- identification
  -- confirmed, sign-off Pending.
  ('cc_by_4_0', 'free_snapshot', false, 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'),
  ('cc_by_4_0', 'paid_property_file', false, 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'),
  ('cc_by_4_0', 'api', false, 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'),
  ('cc_by_4_0', 'bulk_export', false, 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.')
ON CONFLICT (licence_id, channel) DO NOTHING;

-- C9: analytics and model_training (db/migrations/0031). Same
-- Pending-clearance posture as the eight rows above for the two
-- pre-existing channels -- both new channels start denied for both
-- licences. model_training in particular stays denied until someone
-- actually reads CC0/CC BY 4.0's terms as applied to training use and
-- records a rationale; "open licence text usually implies open training
-- use" is exactly the kind of assumption this seed correction (finding #3)
-- exists to stop making without evidence.
INSERT INTO licence_channel (licence_id, channel, allowed, rationale) VALUES
  ('cc0', 'analytics', false, 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'),
  ('cc0', 'model_training', false, 'Denied pending review: no one has yet read cc0''s terms as applied specifically to model-training use, separately from counsel/owner sign-off on the licence generally. Requires its own rationale before this can flip.'),
  ('cc_by_4_0', 'analytics', false, 'Licence identification confirmed (Municipal Data & API Audit v1.1, observed 2026-07-31); counsel/owner sign-off Pending per the audit''s diligence register, Evidence Index p.36. No channel cleared for output until sign-off completes.'),
  ('cc_by_4_0', 'model_training', false, 'Denied pending review: no one has yet read cc_by_4_0''s terms as applied specifically to model-training use, separately from counsel/owner sign-off on the licence generally. Requires its own rationale before this can flip.')
ON CONFLICT (licence_id, channel) DO NOTHING;

-- ============================================================================
-- JURISDICTION (already seeded from invariant tests, but idempotent)
-- ============================================================================
-- tier = 'blocked' (the column's own default), not 'tier_1'. Spec v1.8 §5.3
-- assesses tier on coverage, freshness, reliability and required-field
-- completeness -- but only NAMES those four criteria and gives a qualitative
-- table (e.g. Tier 1 = "Complete core + permit feed; reliable refresh"). It
-- defines no concrete threshold for any of the four: no coverage percentage,
-- no freshness SLA, no reliability metric. There are zero fact rows for
-- ca_san_jose in the database -- no ingestion has ever run -- so none of the
-- four criteria has actually been assessed, let alone met. Not even Tier 3's
-- "partial coverage" is evidenced: zero is not partial, it is none.
-- 'tier_1' would be exactly the defect already fixed for
-- source.url_verified_at and licence.observed_at/cleared_at elsewhere in
-- this file -- a field recording an assessment, set before the assessment
-- happened. A real assessment against §5.3's four criteria, once ingestion
-- exists and has actually run against these sources, should set this
-- properly. Until then 'blocked' is the honest value, not a placeholder to
-- be quietly upgraded later without evidence.
INSERT INTO jurisdiction (
  id, display_name, kind, state_code, tier, pack_version, supported
) VALUES
  ('ca_san_jose', 'City of San José', 'city', 'CA', 'blocked', 'v1.0', true)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- FIELD DEFINITIONS: Every field the three sources supply
-- ============================================================================

-- parcel.lot_area_gis and parcel.situs_address: phase1_deferred = true.
-- scripts/ingest_parcels.py's Phase C inspection (real ~210MB GeoJSON,
-- 225,039 features, every property key enumerated) found ca_san_jose.parcels
-- supplies neither. No address-shaped property exists anywhere in the
-- feature set. A SHAPE_Area property is present but is NOT treated as
-- lot_area_gis: this field is declared unit=square_feet, and SHAPE_Area's
-- actual unit and computation basis are unconfirmed against this export's
-- EPSG:4326 (geographic, degrees) coordinates -- asserting square_feet
-- without confirming it would fabricate a unit, not record an observation.
-- Both fields already have required_for_file = false (the default, never
-- set true below), so field_deferred_not_required is satisfied. See
-- db/migrations/0026_correct_parcels_expected_fields.sql for the
-- companion correction on databases seeded before this fix existed.
INSERT INTO field_definition (
  field_key, display_name, claim, value_type, unit, category, description,
  phase1_deferred, deferral_reason
) VALUES
  -- From parcels source
  ('parcel.apn', 'Assessor Parcel Number', 'public_record', 'string', NULL, 'parcel',
   'Unique parcel identifier from Santa Clara County Assessor', false, NULL),
  ('parcel.geometry', 'Parcel Geometry', 'public_record', 'geometry', NULL, 'parcel',
   'Parcel boundary as MultiPolygon (GIS data)', false, NULL),
  ('parcel.lot_area_gis', 'Lot Area (from GIS)', 'public_record', 'number', 'square_feet', 'parcel',
   'Lot area in square feet, measured from GIS geometry', true,
   'ca_san_jose.parcels does not supply a declared lot_area_gis field. SHAPE_Area is present on every feature but is not treated as equivalent: unit and computation basis unconfirmed against this export''s EPSG:4326 coordinates. Confirmed via scripts/ingest_parcels.py Phase C, 2026-08-07.'),
  ('parcel.situs_address', 'Situs Address', 'public_record', 'string', NULL, 'parcel',
   'Street address of the parcel (mailing address)', true,
   'ca_san_jose.parcels does not supply this field. No address-shaped property exists anywhere in the GeoJSON feature set (checked all 225,039 features). Confirmed via scripts/ingest_parcels.py Phase C, 2026-08-07.'),
  -- parcel.source_parcel_id (PARCELID) is NOT seeded here: unlike the
  -- fields above, it did not exist in any earlier version of this file
  -- to correct. db/migrations/0035_parcel_source_parcel_id_field.sql
  -- INSERTs it directly, per §6.1 task shape B step 1 ("Add to
  -- field_definition (migration)") -- migrations always run before any
  -- seed, so that INSERT alone is sufficient for every future install;
  -- duplicating it here would only be a second place its description
  -- text could drift out of sync.

  -- From zoning source
  ('zoning.district', 'Zoning District', 'public_record', 'string', NULL, 'zoning',
   'Zoning classification assigned by the City of San José', false, NULL),
  ('zoning.district_verbatim', 'Zoning District (Verbatim)', 'public_record', 'string', NULL, 'zoning',
   'Exact zoning designation as stored in the City''s GIS system', false, NULL),

  -- From building_permits_active source
  ('permits.active', 'Active Building Permit', 'public_record', 'boolean', NULL, 'permits',
   'Whether the parcel has an active building permit', false, NULL),
  ('permits.series_earliest', 'Earliest Active Permit Date', 'public_record', 'date', NULL, 'permits',
   'Date of the earliest currently-active building permit', false, NULL)
ON CONFLICT (field_key) DO NOTHING;

-- ============================================================================
-- SOURCES: The three confirmed bulk downloads
-- ============================================================================
-- method='bulk', not 'direct'. All three endpoints serve the ENTIRE dataset in
-- a single response -- 225,039 parcel features, 13,691 zoning features, 17,492
-- permit rows -- and none of them accepts a per-parcel or per-record query
-- parameter. 'direct' is for a source that answers a request-time query for one
-- record; that is not what these are. The enum has carried both values since
-- 0001, so this is a classification fix, not a schema change.
--
-- This is NOT a tier signal. Spec v1.8 §5.3 assesses tier on coverage,
-- freshness, reliability and required-field completeness, not on fetch mode:
-- complete coverage refreshed on a stated cadence is Tier 1 material whether it
-- arrives as a snapshot or as incremental queries. jurisdiction.tier stays
-- 'tier_1' and nothing derives it from source.method.
--
-- Consequence for ingest: the downloaded response body must be hashed and
-- retained as a snapshot row (object_uri, content_hash, byte_size, media type,
-- retrieval time) BEFORE parsing, and the parsed rows reference that snapshot
-- rather than replacing it -- the parcels body alone is ~210 MB. An unchanged
-- content_hash means the source is unchanged and the job stops before parsing
-- (job_run.status = 'skipped_unchanged'). No new table or enum value is needed
-- for any of this; snapshot and job_run already carry it.

-- endpoint_url for zoning_districts and building_permits_active corrected
-- 2026-08-06: both previously pointed at data.sanjoseca.gov dataset landing
-- pages (HTML for a human), not a machine endpoint. Corrected to:
--   zoning_districts:        the ArcGIS Hub GeoJSON download link off the
--                             dataset's own resource list, same download-API
--                             shape already used for parcels.
--   building_permits_active: the CKAN resource's direct CSV download link.
-- parcels' endpoint_url was already correct and is unchanged.
--
-- All three verified live 2026-08-06 (curl, following redirects, GET --
-- not HEAD, since building_permits_active's CKAN link 302s to a
-- presigned S3 URL that 403s on HEAD but serves normally on GET; this is
-- a property of that specific endpoint, not a failure):
--   parcels:                 200, Content-Type: application/json. Body is
--                             a well-formed GeoJSON FeatureCollection,
--                             225,039 features, geometry type Polygon,
--                             real APN/PARCELID property values (e.g.
--                             APN "23712112").
--   zoning_districts:        200, Content-Type: application/json. Body is
--                             a well-formed GeoJSON FeatureCollection,
--                             13,691 features, geometry type Polygon, real
--                             ZONING/ZONINGABBREV property values.
--   building_permits_active: 200, Content-Type: text/csv. Body is 17,492
--                             real permit rows under the header row
--                             (FOLDERNUMBER, ISSUEDATE, PERMITVALUATION,
--                             etc.), not HTML or an error page.
-- All three: status code AND response media type AND body shape were
-- checked, not status code alone -- a landing page also returns 200.
-- url_verified_at is the literal date this check was run, not now().
INSERT INTO source (
  id, jurisdiction_id, display_name, steward, method, phase_status,
  phase_status_reason, endpoint_url, licence_id, active, url_verified_at,
  expected_fields
) VALUES
  ('ca_san_jose.parcels',
   'ca_san_jose',
   'Parcels (Santa Clara County Assessor / City of San José GIS)',
   'City of San José',
   'bulk',
   'active',
   'Licence confirmed: CC BY 4.0. Endpoint verified 2026-08-06: GET, 200, Content-Type application/json, body is a well-formed GeoJSON FeatureCollection (225,039 Polygon features). expected_fields corrected 2026-08-07: scripts/ingest_parcels.py Phase C found the source supplies neither parcel.lot_area_gis nor parcel.situs_address -- see field_definition.deferral_reason on both. parcel.source_parcel_id added 2026-08-07 (0035): PARCELID confirmed unique and fully populated across all 225,039 features by the parcel identity diagnostic.',
   'https://gisdata-csj.opendata.arcgis.com/api/download/v1/items/4bb085cb99a64eff8e83d2bf92a8d5cb/geojson?layers=270',
   'cc_by_4_0',
   true,
   '2026-08-06'::timestamptz,
   '["parcel.apn","parcel.geometry","parcel.source_parcel_id"]'::jsonb),

  ('ca_san_jose.zoning_districts',
   'ca_san_jose',
   'Zoning Districts (City of San José)',
   'City of San José',
   'bulk',
   'active',
   'Licence confirmed: CC BY 4.0. Endpoint verified 2026-08-06: GET, 200, Content-Type application/json, body is a well-formed GeoJSON FeatureCollection (13,691 Polygon features).',
   'https://gisdata-csj.opendata.arcgis.com/api/download/v1/items/adf17ae739214787ad42945c5f72ccd8/geojson?layers=401',
   'cc_by_4_0',
   true,
   '2026-08-06'::timestamptz,
   '["zoning.district","zoning.district_verbatim"]'::jsonb),

  ('ca_san_jose.building_permits_active',
   'ca_san_jose',
   'Active Building Permits (City of San José)',
   'City of San José',
   'bulk',
   'active',
   'Licence confirmed: CC0. Endpoint verified 2026-08-06: GET, 200, Content-Type text/csv, body is 17,492 real permit rows (not HTML).',
   'https://data.sanjoseca.gov/dataset/fd9ceb0c-75e0-402e-9fe3-3f6e04f2c23f/resource/761b7ae8-3be1-4ad6-923d-c7af6404a904/download/buildingpermitsactive.csv',
   'cc0',
   true,
   '2026-08-06'::timestamptz,
   '["permits.active","permits.series_earliest"]'::jsonb)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- SOURCE RANK: Which source wins for which field
-- ============================================================================
-- With three non-overlapping sources, this is straightforward:
-- - parcels provides parcel.* fields
-- - zoning provides zoning.* fields
-- - building_permits_active provides permits.* fields

INSERT INTO source_rank (jurisdiction_id, field_key, source_id, rank, rationale) VALUES
  -- Parcels wins for parcel.* fields
  ('ca_san_jose', 'parcel.apn', 'ca_san_jose.parcels', 1,
   'Parcels source is the authoritative county assessor record'),
  ('ca_san_jose', 'parcel.geometry', 'ca_san_jose.parcels', 1,
   'Parcels source provides GIS geometry directly'),
  ('ca_san_jose', 'parcel.lot_area_gis', 'ca_san_jose.parcels', 1,
   'Parcels source geometry is primary measurement'),
  ('ca_san_jose', 'parcel.situs_address', 'ca_san_jose.parcels', 1,
   'Parcels source has authoritative address record'),

  -- Zoning wins for zoning.* fields
  ('ca_san_jose', 'zoning.district', 'ca_san_jose.zoning_districts', 1,
   'Zoning Districts source is authoritative for city zoning'),
  ('ca_san_jose', 'zoning.district_verbatim', 'ca_san_jose.zoning_districts', 1,
   'Zoning Districts source provides exact designation'),

  -- Building permits wins for permits.* fields
  ('ca_san_jose', 'permits.active', 'ca_san_jose.building_permits_active', 1,
   'Building Permits source is authoritative for active permits'),
  ('ca_san_jose', 'permits.series_earliest', 'ca_san_jose.building_permits_active', 1,
   'Building Permits source tracks all active permits by date')
ON CONFLICT (jurisdiction_id, field_key, source_id) DO NOTHING;

-- ============================================================================
-- L0 GATE (P53): a real runtime representation for the LD-1 jurisdiction
-- gate, prompts/P53-l0-gate.md design D-C. THIS SEED CLEARS NOTHING -- see
-- that document and db/migrations/0056_l0_gate_boundary_source.sql's own
-- header for the full argument. Byte-identical to that migration's own
-- INSERTs (both must converge regardless of which runs first against an
-- already-existing database -- see that migration's header, and
-- prompts/P53-l0-gate.md sec 6 for why seeding-order convergence here is a
-- real requirement, the same class of bug findings #32/#36 already found
-- and fixed for source/rule rows). This is the copy every install gets
-- from this point on; 0056 is only for a database that was already seeded
-- before this pass landed.
-- ============================================================================

INSERT INTO licence (
  id, display_name, restriction, commercial_use, redistribution,
  attribution_text, terms_url, evidence_uri, observed_at, cleared_by, cleared_at, notes
) VALUES (
  'unknown',
  'Licence not yet observed',
  'unknown', 'unknown', 'unknown',
  NULL, NULL, NULL,
  '2026-08-22'::timestamptz,
  NULL, NULL,
  'LD-1 gate source (jurisdictions/ca_san_jose/sources.yaml: ca_san_jose.city_limits). '
  'Licence text never observed -- id, display_name and every restriction/commercial_use/'
  'redistribution value match jurisdictions/ca_san_jose/licences.yaml (docs/LEDGEX_SPEC.md '
  'sec 7.2, id=unknown) verbatim, not independently invented. '
  'observed_at records the date this row was created (the date its UNKNOWN-NESS was '
  'recorded), never a date on which the licence''s actual terms were read -- no such '
  'reading has ever happened. See prompts/P53-l0-gate.md.'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO licence_channel (licence_id, channel, allowed, rationale) VALUES
  ('unknown', 'free_snapshot', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.'),
  ('unknown', 'paid_property_file', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.'),
  ('unknown', 'api', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.'),
  ('unknown', 'bulk_export', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.'),
  ('unknown', 'analytics', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.'),
  ('unknown', 'model_training', false,
   'LD-1: gate source unconfirmed, licence text never observed (sec 1.1). No channel is '
   'ever cleared for an unidentified licence -- identifying it requires a new licence row '
   '(0027), never an UPDATE to this one.')
ON CONFLICT (licence_id, channel) DO NOTHING;

INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description)
VALUES (
  'jurisdiction.incorporated', 'Jurisdiction incorporated', 'public_record', 'boolean',
  'jurisdiction',
  'Whether this parcel resolves within the jurisdiction''s incorporated boundary, per '
  'jurisdictions/ca_san_jose/sources.yaml''s own ca_san_jose.city_limits declaration '
  '(the L0 gate, sec 1.1). No source currently supplies this field as a fact -- see '
  'prompts/P53-l0-gate.md; the field is declared so the composer''s absence-check has a '
  'real field_key to require, not so a value exists yet.'
) ON CONFLICT (field_key) DO NOTHING;

-- method='manual', not sources.yaml's own declared method: direct -- no
-- real, verified San Jose city-limits endpoint exists (P53-l0-gate.md
-- Obstacle 2). This row exists as jurisdiction.boundary_source_id's FK
-- target only, never as an ingest path (I13 forbids a manual source from
-- ever producing a fact -- P53-l0-gate.md Obstacle 3).
INSERT INTO source (
  id, jurisdiction_id, display_name, steward, method, phase_status, phase_status_reason,
  endpoint_url, licence_id, active
) VALUES (
  'ca_san_jose.city_limits', 'ca_san_jose', 'City limits / jurisdiction boundary',
  'City of San José', 'manual', 'blocked_rights',
  'Licence not observed. Supplies the L0 gate, so under I6 this blocks ALL channels '
  'including free_snapshot. Launch dependency LD-1. Plan App K: "Blocked for paid output '
  '-- required for the jurisdiction gate; confirm licence." method=''manual'' here, not '
  'sources.yaml''s own declared method: direct -- no real, verified endpoint exists yet '
  '(P53-l0-gate.md Obstacle 2); this row exists as jurisdiction.boundary_source_id''s FK '
  'target, never as an ingest path (I13 forbids a manual source from ever producing a '
  'fact, by design -- see P53-l0-gate.md Obstacle 3).',
  NULL, 'unknown', false
) ON CONFLICT (id) DO UPDATE SET
  jurisdiction_id = EXCLUDED.jurisdiction_id,
  display_name = EXCLUDED.display_name,
  steward = EXCLUDED.steward,
  method = EXCLUDED.method,
  phase_status = EXCLUDED.phase_status,
  phase_status_reason = EXCLUDED.phase_status_reason,
  endpoint_url = EXCLUDED.endpoint_url,
  licence_id = EXCLUDED.licence_id,
  active = EXCLUDED.active;

-- Activation switch (D-C): NULL for every jurisdiction except ca_san_jose --
-- do not set this for any other jurisdiction row this file or any test
-- fixture ever creates. Guarded (matches the specific old value, IS NULL,
-- in the WHERE clause), same 0023/0026/0030 pattern, not a blind UPDATE --
-- safe to re-run this file any number of times.
UPDATE jurisdiction
   SET boundary_source_id = 'ca_san_jose.city_limits'
 WHERE id = 'ca_san_jose'
   AND boundary_source_id IS NULL;

-- ============================================================================
-- RULES (P31): one real rule, sourced from a City guidance bulletin, not
-- the ordinance text itself -- see this row's own citation and finding #34
-- (prompts/README.md) for why SJMC §20.80.175 could not be read directly
-- from any environment reachable so far. effective_from is the date the
-- City PUBLISHED this standard (the bulletin's own "UPDATED" date), not a
-- claim about the ordinance's own legal effective date, which remains
-- unknown -- when the ordinance text becomes readable, this version is
-- retired (effective_to set, 0013's one-way supersession) and a new
-- version, citing the Code directly, replaces it. source_text_uri and
-- attestation_uri are both commit-pinned into this repository's own git
-- history (jurisdictions/ca_san_jose/evidence/) -- I17's "read verbatim
-- from the filesystem" made literally true, no external service required.
-- rule_key names the CITY Development Standards regime explicitly
-- (.city_standards) -- see finding #35: the City and State standards give
-- materially different answers (25 ft vs 18 ft max height) for the same
-- conclusion, and a property file has no input recording which an
-- applicant elected. This rule is NOT the universal answer to "ADU max
-- height" and must never be read as one.
INSERT INTO rule (
  id, jurisdiction_id, rule_key, version, effective_from, effective_to,
  citation, source_text_uri, params, pack_version,
  authored_by, reviewed_by, review_mode, reviewed_at, attestation_uri
) VALUES (
  'ca_san_jose.adu_detached_max_height_city_standards.v1', 'ca_san_jose',
  'adu.detached.max_height.city_standards', 1, '2026-03-05'::date, NULL,
  'City of San José Bulletin #210, "ADU Universal Checklist," updated 03/05/2026, '
    || 'Part 3 (Single-Family Properties, City Development Standards, Detached ADU) -- '
    || 'summarizing San José Municipal Code Section 20.80.175, not its verbatim text.',
  'https://github.com/devvtrivedi/ledgex-adu/blob/6dca93c330e80cb91571bc24955e71eb6fb95954/jurisdictions/ca_san_jose/evidence/bulletin-210-adu-universal-checklist-2026-03-05.pdf',
  '{"first_story_max_ft": 18, "second_story_max_ft": 25, "max_stories": 2}'::jsonb,
  'ca_san_jose_rules@0.1.0',
  'devtrivedi06@gmail.com', 'devtrivedi06@gmail.com', 'solo_founder_attestation',
  '2026-08-18'::timestamptz,
  'https://github.com/devvtrivedi/ledgex-adu/blob/6dca93c330e80cb91571bc24955e71eb6fb95954/jurisdictions/ca_san_jose/evidence/attestation-adu-detached-max-height-city-standards.md'
)
ON CONFLICT (id) DO NOTHING;

COMMIT;

-- ============================================================================
-- VERIFICATION: Show what we just loaded
-- ============================================================================

\echo ''
\echo '=========================================='
\echo 'DAY 4 SOURCES LOADED'
\echo '=========================================='

SELECT '## Licences' AS status;
SELECT id, restriction, commercial_use, redistribution FROM licence ORDER BY id;

\echo ''
SELECT '## Sources' AS status;
SELECT id, display_name, active, url_verified_at FROM source WHERE jurisdiction_id = 'ca_san_jose' ORDER BY id;

\echo ''
SELECT '## Fields' AS status;
SELECT field_key, claim, value_type, category FROM field_definition WHERE field_key LIKE 'parcel.%' OR field_key LIKE 'zoning.%' OR field_key LIKE 'permits.%' ORDER BY field_key;

\echo ''
SELECT '## Source Rank (field winners)' AS status;
SELECT field_key, source_id, rank FROM source_rank WHERE jurisdiction_id = 'ca_san_jose' ORDER BY field_key;

\echo ''
\echo 'Sources registered with method=bulk. Existing databases seeded before'
\echo '0016 keep the old direct value -- this seed is ON CONFLICT DO NOTHING.'
\echo 'Apply db/migrations/0016_source_access_method_corrections.sql to those.'
\echo '';
