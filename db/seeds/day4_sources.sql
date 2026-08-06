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
-- CC0 and CC BY 4.0 both allow all four channels (they're genuinely open).

INSERT INTO licence_channel (licence_id, channel, allowed, rationale) VALUES
  -- CC0: no restrictions at all
  ('cc0', 'free_snapshot', true, 'CC0 1.0: no restriction on use, redistribution or commercial use'),
  ('cc0', 'paid_property_file', true, 'CC0 1.0: no restriction on use, redistribution or commercial use'),
  ('cc0', 'api', true, 'CC0 1.0: no restriction on use, redistribution or commercial use'),
  ('cc0', 'bulk_export', true, 'CC0 1.0: no restriction on use, redistribution or commercial use'),

  -- CC BY 4.0: commercial use and redistribution permitted, attribution required
  ('cc_by_4_0', 'free_snapshot', true, 'CC BY 4.0: permits commercial use and redistribution with attribution'),
  ('cc_by_4_0', 'paid_property_file', true, 'CC BY 4.0: permits commercial use and redistribution with attribution'),
  ('cc_by_4_0', 'api', true, 'CC BY 4.0: permits commercial use and redistribution with attribution'),
  ('cc_by_4_0', 'bulk_export', true, 'CC BY 4.0: permits commercial use and redistribution with attribution')
ON CONFLICT (licence_id, channel) DO NOTHING;

-- ============================================================================
-- JURISDICTION (already seeded from invariant tests, but idempotent)
-- ============================================================================

INSERT INTO jurisdiction (
  id, display_name, kind, state_code, tier, pack_version, supported
) VALUES
  ('ca_san_jose', 'City of San José', 'city', 'CA', 'tier_1', 'v1.0', true)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- FIELD DEFINITIONS: Every field the three sources supply
-- ============================================================================

INSERT INTO field_definition (
  field_key, display_name, claim, value_type, unit, category, description
) VALUES
  -- From parcels source
  ('parcel.apn', 'Assessor Parcel Number', 'public_record', 'string', NULL, 'parcel',
   'Unique parcel identifier from Santa Clara County Assessor'),
  ('parcel.geometry', 'Parcel Geometry', 'public_record', 'geometry', NULL, 'parcel',
   'Parcel boundary as MultiPolygon (GIS data)'),
  ('parcel.lot_area_gis', 'Lot Area (from GIS)', 'public_record', 'number', 'square_feet', 'parcel',
   'Lot area in square feet, measured from GIS geometry'),
  ('parcel.situs_address', 'Situs Address', 'public_record', 'string', NULL, 'parcel',
   'Street address of the parcel (mailing address)'),

  -- From zoning source
  ('zoning.district', 'Zoning District', 'public_record', 'string', NULL, 'zoning',
   'Zoning classification assigned by the City of San José'),
  ('zoning.district_verbatim', 'Zoning District (Verbatim)', 'public_record', 'string', NULL, 'zoning',
   'Exact zoning designation as stored in the City''s GIS system'),

  -- From building_permits_active source
  ('permits.active', 'Active Building Permit', 'public_record', 'boolean', NULL, 'permits',
   'Whether the parcel has an active building permit'),
  ('permits.series_earliest', 'Earliest Active Permit Date', 'public_record', 'date', NULL, 'permits',
   'Date of the earliest currently-active building permit')
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
   'Licence confirmed: CC BY 4.0. Endpoint verified 2026-08-06: GET, 200, Content-Type application/json, body is a well-formed GeoJSON FeatureCollection (225,039 Polygon features).',
   'https://gisdata-csj.opendata.arcgis.com/api/download/v1/items/4bb085cb99a64eff8e83d2bf92a8d5cb/geojson?layers=270',
   'cc_by_4_0',
   true,
   '2026-08-06'::timestamptz,
   '["parcel.apn","parcel.geometry","parcel.lot_area_gis","parcel.situs_address"]'::jsonb),

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
