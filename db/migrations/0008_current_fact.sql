-- 0008_current_fact.sql
-- Current-fact resolution.
-- Source: docs/LEDGEX_SPEC.md §3.8.

CREATE MATERIALIZED VIEW current_fact AS
SELECT DISTINCT ON (f.parcel_id, f.field_key)
       f.*
  FROM fact f
  JOIN parcel p ON p.id = f.parcel_id
  LEFT JOIN source_rank sr
         ON sr.jurisdiction_id = p.jurisdiction_id
        AND sr.field_key       = f.field_key
        AND sr.source_id       = f.source_id
 WHERE f.superseded_at IS NULL
   AND (f.effective_to IS NULL OR f.effective_to > now())
 ORDER BY f.parcel_id, f.field_key,
          COALESCE(sr.rank, 999) ASC,
          f.confidence ASC,                      -- enum order: high < medium < low
          f.retrieved_at DESC NULLS LAST;

CREATE UNIQUE INDEX current_fact_pk    ON current_fact (parcel_id, field_key);
CREATE INDEX        current_fact_field ON current_fact (field_key);

-- Refresh with REFRESH MATERIALIZED VIEW CONCURRENTLY current_fact; at the
-- end of each ingest job. Application queries read current_fact. The
-- composer, the audit path and any reconstruction read fact directly.
