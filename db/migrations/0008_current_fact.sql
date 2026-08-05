-- 0008_current_fact.sql
-- Current-fact resolution.
-- Source: docs/LEDGEX_SPEC.md §3.8.
--
-- Derived-fact ranking, recorded as observed behaviour, not a stated
-- policy — comment only, no change to the ORDER BY below:
--   - a derived fact has source_id NULL (fact_provenance_complete, 0006),
--     so it can never match a source_rank row (source_rank.source_id is
--     NOT NULL) and always falls to COALESCE(sr.rank, 999), the worst rank
--   - a derived fact also has retrieved_at NULL, which sorts last under
--     NULLS LAST
--   - net effect: a derived fact never wins current_fact for a field_key
--     where any retrieved fact exists, regardless of that retrieved fact's
--     own confidence or staleness
--   - this is a side effect of reusing source_rank/retrieved_at as the sort
--     key for both retrieved and derived facts, not something either the
--     spec or this migration states as an intended rule
--   - it should rarely matter in practice, because field_definition.claim
--     (0003) types a FIELD as public_record / derived_conclusion / etc, so
--     a derived conclusion normally has its own field_key and isn't
--     competing with a retrieved fact for the same current_fact row
--   - flagged for the next spec revision of §3.8 to state explicitly one
--     way or the other, rather than leaving it implicit in sort order

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
