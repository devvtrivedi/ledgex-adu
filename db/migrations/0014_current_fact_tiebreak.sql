-- 0014_current_fact_tiebreak.sql
-- current_fact (0008): add a final ORDER BY tiebreak.
--
-- Without one, DISTINCT ON picks arbitrarily whenever rank, confidence and
-- retrieved_at all tie between two facts for the same (parcel_id,
-- field_key) — the same underlying data could then produce a different
-- current_fact row on different runs (or after REFRESH MATERIALIZED VIEW
-- CONCURRENTLY), breaking reconstructability. f.id, as the last ORDER BY
-- term, makes the choice deterministic without changing which fact wins
-- whenever the existing terms already disagree.
--
-- This migration deliberately changes nothing else. In particular, per
-- explicit decision, it does NOT add a derived-vs-retrieved precedence
-- tier. That decision is recorded here, in full, so it stays a decision
-- rather than becoming an unexplained gap the next reader has to
-- re-derive:
--
--   - A derived fact and a retrieved fact CAN exist for the same
--     field_key. field_definition.claim (0003) types the FIELD
--     (public_record / derived_conclusion / etc), but fact.method is
--     independent of that, so nothing in the schema prevents both. Example:
--     a lot area published by the City (retrieved) and one computed from
--     parcel geometry (derived), both stored under the same field_key.
--
--   - Derived facts currently sort last in this view: a derived fact has
--     source_id NULL (fact_provenance_complete, 0006), so it never matches
--     a source_rank row and falls to COALESCE(sr.rank, 999); it also has
--     retrieved_at NULL, which sorts last under NULLS LAST. This is a side
--     effect of reusing source_rank/retrieved_at as the sort key for both
--     retrieved and derived facts, not a policy stated anywhere — §3.8
--     does not contain one either way.
--
--   - This view does not decide customer output. Application queries read
--     current_fact; the composer, the audit path and any reconstruction
--     read fact directly (§3.8's own text says so). Precedence between a
--     derived and a retrieved fact for a *delivered* file is a composer
--     decision (§5, L8) — deferred until that layer exists, not decided
--     here as a side effect of a materialized view's sort key.
--
--   - When a derived and a retrieved fact disagree, the designed path
--     already exists and this migration does not duplicate or bypass it:
--     set fact.conflict = 'conflicts' and raise a parcel_exception of type
--     'cross_source' (I12). No parallel mechanism belongs here.
--
--   - Presenting both values to the customer is permitted and already
--     supported by the schema: property_file_fact is keyed
--     (property_file_id, fact_id) with no uniqueness on field_key, so one
--     file can link both the derived and the retrieved fact. I9 requires
--     they render with distinct treatment when it does.
--
--   - CRITICAL: "let the user decide" means the delivered file SHOWS BOTH
--     VALUES. It never means the pipeline pauses, queues or waits for a
--     human answer — that would violate I14. No stage may block on, queue
--     for, or be supplemented by a person.

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
 ORDER BY f.parcel_id, f.field_key,
          COALESCE(sr.rank, 999) ASC,
          f.confidence ASC,                      -- enum order: high < medium < low
          f.retrieved_at DESC NULLS LAST,
          f.id;                                  -- deterministic tiebreak; no ranking meaning

CREATE UNIQUE INDEX current_fact_pk    ON current_fact (parcel_id, field_key);
CREATE INDEX        current_fact_field ON current_fact (field_key);
