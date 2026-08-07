-- 0019_current_fact_effective_from.sql
-- current_fact (0008, tiebreak added in 0014): filter effective_from too.
--
-- The view filtered f.effective_to (a fact stops being current once its
-- valid time ends) but never f.effective_from (valid time in the future,
-- e.g. a zoning change that takes effect next month, recorded ahead of
-- time). A fact effective_from tomorrow was appearing in current_fact
-- today, immediately, before it was actually true. DROP and recreate with
-- `AND f.effective_from <= now()` added to the WHERE clause; everything
-- else -- the DISTINCT ON columns, the source_rank join, the ORDER BY
-- (including 0014's f.id tiebreak) -- is identical to 0014's definition.
-- Both indexes (current_fact_pk, current_fact_field) drop with the view
-- and are recreated identically.
--
-- current_fact is a MATERIALIZED view: now() in its query is evaluated at
-- REFRESH time, not at query time against the view's rows. A fact whose
-- effective_from arrives between two refreshes will not appear until the
-- next REFRESH MATERIALIZED VIEW CONCURRENTLY current_fact runs, even
-- though it is already true. This is inherent to a matview and applies
-- equally to the existing effective_to filter (a fact that expired five
-- minutes ago is still showing as current until the next refresh) -- it
-- is documentation of existing, unchanged behavior, not a new bug and not
-- something this migration fixes.

DROP MATERIALIZED VIEW current_fact;

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
   AND f.effective_from <= now()
 ORDER BY f.parcel_id, f.field_key,
          COALESCE(sr.rank, 999) ASC,
          f.confidence ASC,                      -- enum order: high < medium < low
          f.retrieved_at DESC NULLS LAST,
          f.id;                                  -- deterministic tiebreak; no ranking meaning

CREATE UNIQUE INDEX current_fact_pk    ON current_fact (parcel_id, field_key);
CREATE INDEX        current_fact_field ON current_fact (field_key);
