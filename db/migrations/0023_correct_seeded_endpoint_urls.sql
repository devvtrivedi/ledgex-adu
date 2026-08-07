-- 0023_correct_seeded_endpoint_urls.sql
-- Serves: operational correctness of already-seeded databases; no invariant.
--
-- db/seeds/day4_sources.sql originally registered
-- ca_san_jose.zoning_districts and ca_san_jose.building_permits_active
-- with data.sanjoseca.gov dataset LANDING pages (HTML for a human) as
-- their endpoint_url -- not a machine endpoint. That was corrected in the
-- seed file itself (commit f8291b7) to the real GeoJSON/CSV download
-- links, and 2300f8c later recorded live verification against the
-- corrected URLs. 0016 (a later migration) corrected source.method for
-- these same three rows, but never touched endpoint_url -- it was already
-- fixed in the seed file by then, so 0016 had nothing to do there.
--
-- None of that helps a database that was already seeded from the seed
-- file's ORIGINAL content, before f8291b7. Unlike source.method (which
-- 0016 could correct because no fact referenced source at the time), an
-- old endpoint_url sitting in an already-seeded row is not something a
-- fresh seed re-run fixes either: the seed's INSERT uses
-- ON CONFLICT (id) DO NOTHING, so re-running it against an
-- already-seeded database is a silent no-op, old broken URLs and all.
-- This migration is the only thing that can still reach that row.
--
-- GUARDED, not a blind UPDATE: matches the specific old broken URL as
-- part of the WHERE clause, not just the row id. A database seeded AFTER
-- f8291b7 already has the corrected endpoint_url, so the WHERE clause
-- matches zero rows there -- this migration is a true no-op on any
-- database seeded from the current or any already-corrected seed file,
-- and a real correction only on one still carrying the original landing
-- page URLs. ca_san_jose.parcels is not touched at all: its endpoint_url
-- was correct from the start and was never part of this defect.
--
-- Sets endpoint_url, phase_status_reason, url_verified_at and active to
-- exactly what the current seed file has for these two rows, so an old
-- database converges on the same state a fresh seed would produce,
-- regardless of which historical version of the seed file it was
-- actually seeded from.

UPDATE source
SET endpoint_url = 'https://gisdata-csj.opendata.arcgis.com/api/download/v1/items/adf17ae739214787ad42945c5f72ccd8/geojson?layers=401',
    phase_status_reason = 'Licence confirmed: CC BY 4.0. Endpoint verified 2026-08-06: GET, 200, Content-Type application/json, body is a well-formed GeoJSON FeatureCollection (13,691 Polygon features).',
    url_verified_at = '2026-08-06'::timestamptz,
    active = true
WHERE id = 'ca_san_jose.zoning_districts'
  AND endpoint_url = 'https://data.sanjoseca.gov/dataset/zoning-districts';

UPDATE source
SET endpoint_url = 'https://data.sanjoseca.gov/dataset/fd9ceb0c-75e0-402e-9fe3-3f6e04f2c23f/resource/761b7ae8-3be1-4ad6-923d-c7af6404a904/download/buildingpermitsactive.csv',
    phase_status_reason = 'Licence confirmed: CC0. Endpoint verified 2026-08-06: GET, 200, Content-Type text/csv, body is 17,492 real permit rows (not HTML).',
    url_verified_at = '2026-08-06'::timestamptz,
    active = true
WHERE id = 'ca_san_jose.building_permits_active'
  AND endpoint_url = 'https://data.sanjoseca.gov/dataset/active-building-permits';
