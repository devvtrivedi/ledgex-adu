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
-- SOURCES: The three confirmed endpoints
-- ============================================================================

-- active = false, url_verified_at = NULL for all three: licence and scope
-- are confirmed (that's what phase_status='active' asserts), but nobody has
-- actually pinged these endpoints yet. Stamping now() here would only
-- record when this seed script happened to run, not that anyone contacted
-- the endpoint -- source_active_requires_verification exists precisely to
-- keep a source nobody has checked from being switched live. A real
-- liveness check should set active=true and url_verified_at to the real
-- check time once it actually happens -- and per source_active_requires_verification's
-- purpose, that check must confirm the response media type and shape
-- (e.g. actual GeoJSON/CSV matching expected_fields below), not just a 200
-- status code, since a landing page also returns 200.
--
-- endpoint_url for zoning_districts and building_permits_active corrected
-- 2026-08-06: both previously pointed at data.sanjoseca.gov dataset landing
-- pages (HTML for a human), not a machine endpoint, for method='direct'
-- sources. Verified directly (curl, following redirects) rather than
-- guessed:
--   zoning_districts:        the ArcGIS Hub GeoJSON download link off the
--                             dataset's own resource list, same download-API
--                             shape already used for parcels. Resolves
--                             (302 -> 200) to Content-Type: application/json.
--   building_permits_active: the CKAN resource's direct CSV download link.
--                             Resolves (302, to a signed S3 URL) to
--                             Content-Type: text/csv, body confirmed to be
--                             real permit rows (FOLDERNUMBER, ISSUEDATE,
--                             etc.), not HTML.
-- parcels' endpoint_url was already correct and is unchanged.
INSERT INTO source (
  id, jurisdiction_id, display_name, steward, method, phase_status,
  phase_status_reason, endpoint_url, licence_id, active, url_verified_at,
  expected_fields
) VALUES
  ('ca_san_jose.parcels',
   'ca_san_jose',
   'Parcels (Santa Clara County Assessor / City of San José GIS)',
   'City of San José',
   'direct',
   'active',
   'Licence confirmed: CC BY 4.0. Endpoint liveness not yet verified -- pending a real check before activation.',
   'https://gisdata-csj.opendata.arcgis.com/api/download/v1/items/4bb085cb99a64eff8e83d2bf92a8d5cb/geojson?layers=270',
   'cc_by_4_0',
   false,
   NULL,
   '["parcel.apn","parcel.geometry","parcel.lot_area_gis","parcel.situs_address"]'::jsonb),

  ('ca_san_jose.zoning_districts',
   'ca_san_jose',
   'Zoning Districts (City of San José)',
   'City of San José',
   'direct',
   'active',
   'Licence confirmed: CC BY 4.0. Endpoint liveness not yet verified -- pending a real check before activation.',
   'https://gisdata-csj.opendata.arcgis.com/api/download/v1/items/adf17ae739214787ad42945c5f72ccd8/geojson?layers=401',
   'cc_by_4_0',
   false,
   NULL,
   '["zoning.district","zoning.district_verbatim"]'::jsonb),

  ('ca_san_jose.building_permits_active',
   'ca_san_jose',
   'Active Building Permits (City of San José)',
   'City of San José',
   'direct',
   'active',
   'Licence confirmed: CC0. Endpoint liveness not yet verified -- pending a real check before activation.',
   'https://data.sanjoseca.gov/dataset/fd9ceb0c-75e0-402e-9fe3-3f6e04f2c23f/resource/761b7ae8-3be1-4ad6-923d-c7af6404a904/download/buildingpermitsactive.csv',
   'cc0',
   false,
   NULL,
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
\echo 'Ready for Day 5: Write missing migrations.'
\echo '';
