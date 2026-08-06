-- 0016_source_access_method_corrections.sql
-- source (0002): correct method for the three active San José sources from
-- 'direct' to 'bulk'.
--
-- All three endpoints registered by db/seeds/day4_sources.sql serve the
-- ENTIRE dataset in one response and accept no per-parcel or per-record
-- query parameter:
--
--   ca_san_jose.parcels                 ArcGIS Hub download API, GeoJSON
--                                       FeatureCollection, 225,039 features
--                                       (~210 MB body).
--   ca_san_jose.zoning_districts        ArcGIS Hub download API, GeoJSON
--                                       FeatureCollection, 13,691 features.
--   ca_san_jose.building_permits_active CKAN resource download, text/csv,
--                                       17,492 rows.
--
-- 'direct' is for a source that answers a request-time query for a single
-- record. These are whole-dataset snapshots fetched on a cadence, which is
-- what 'bulk' means. access_method (0001) has carried both values since the
-- first migration, so this is a classification correction, not a schema
-- change: no new enum value, no new table, no new column.
--
-- Why a migration and not just the seed: db/seeds/day4_sources.sql inserts
-- these rows with ON CONFLICT (id) DO NOTHING. Correcting the seed alone
-- fixes new databases and silently leaves every already-seeded database on
-- the wrong value, because the conflicting INSERT is skipped rather than
-- applied. This migration is the half that reaches those databases. On a
-- database that has never run the seed it matches zero rows and is a no-op,
-- which is correct — seeds run after migrations.
--
-- What this does NOT change:
--
--   - jurisdiction.tier. ca_san_jose stays 'tier_1'. tier is a stored enum
--     column on jurisdiction; nothing anywhere derives it from
--     source.method, and spec v1.8 §5.3 now states explicitly that tier is
--     assessed on coverage, freshness, reliability and required-field
--     completeness rather than on fetch mode. Complete coverage on a stated
--     cadence is Tier 1 material whether it arrives as a snapshot or as
--     incremental queries.
--
--   - source.active. The CHECK source_active_requires_machine_access (0002)
--     admits both 'direct' and 'bulk', so all three sources stay active
--     through this update. I14 excludes 'portal' and 'manual', not 'bulk'.
--
--   - endpoint_url, url_verified_at or phase_status_reason. The endpoints
--     themselves were verified live and are unchanged; only their
--     classification was wrong.
--
-- Consequence for ingest code (not enforced here, recorded so it is not
-- re-derived): a bulk source must have its downloaded response body hashed
-- and written to snapshot (object_uri, content_hash, byte_size, media type,
-- retrieval time) BEFORE parsing, with the parsed facts referencing that
-- snapshot rather than replacing it. An unchanged content_hash means the
-- source is unchanged and the run stops before parsing —
-- job_run.status = 'skipped_unchanged'. snapshot (0005) and job_run (0012)
-- already carry every column this needs; nothing further is required.

UPDATE source
   SET method = 'bulk'
 WHERE id IN (
         'ca_san_jose.parcels',
         'ca_san_jose.zoning_districts',
         'ca_san_jose.building_permits_active'
       )
   AND method <> 'bulk';
