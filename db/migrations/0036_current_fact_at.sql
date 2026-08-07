-- 0036_current_fact_at.sql
-- Serves: C5 (ML review, corrected), I4, I7.
--
-- THE PROBLEM. current_fact (0008, tiebreak 0014, effective_from filter
-- 0019) is the only read path anything queries today (§3.8: "Application
-- queries read current_fact"). It is now-only -- every filter in its
-- WHERE clause compares against now(). If that stays the only read path,
-- every future consumer inherits now-only behavior by default, and
-- reconstructing "what did we believe as of date X" -- required for any
-- audit, any dispute, any as_of query (§4.1: "?as_of=<timestamp> on any
-- read replays the system's belief at that moment") -- becomes
-- structurally impossible, not just unimplemented. Doing this before the
-- ingest, not after: redefining a materialized view over 675k+ rows is
-- strictly more expensive than over the zero rows this database holds
-- right now, and the composer that would depend on this doesn't exist
-- yet to migrate.
--
-- THE ML REVIEW'S C5 PROPOSAL, corrected. C5 proposed a function as the
-- source of truth with current_fact as "a thin wrapper" (a VIEW) over it.
-- That does not work: a plain VIEW re-executes its query on every read,
-- so a VIEW wrapping a function is not materialized at all -- it would
-- silently turn every current_fact read back into the full DISTINCT
-- ON/JOIN/ORDER BY resolution, against the whole fact table, on every
-- single query. That is not a thin wrapper; it is current_fact's
-- materialization deleted while keeping its name.
--
-- THE ACTUAL FIX. Two objects, one query:
--   - current_fact_at(ts timestamptz) -- a LANGUAGE sql STABLE function,
--     RETURNS SETOF fact, owning the entire resolution query (the
--     DISTINCT ON, the source_rank join, the confidence/recency/id
--     tiebreak -- byte-identical to 0019's, with now() replaced by ts
--     and one addition, below).
--   - current_fact -- unchanged as a MATERIALIZED VIEW, but its defining
--     query becomes `SELECT * FROM current_fact_at(now())`.
-- REFRESH MATERIALIZED VIEW re-executes the ENTIRE defining query at
-- refresh time -- confirmed already true of this exact view (0008's own
-- comment: "now() in its defining query is evaluated at REFRESH time,
-- not at query time"). A query that calls a function is not an exception
-- to that: REFRESH re-evaluates now() fresh, passes it to
-- current_fact_at, and caches THAT result. current_fact stays a real,
-- indexed, REFRESH-CONCURRENTLY-capable cache -- "the cached now() case"
-- -- while owning zero resolution logic of its own. There is exactly one
-- place the DISTINCT ON / JOIN / ORDER BY exists; current_fact cannot
-- drift from current_fact_at because it has nothing left to drift with.
-- LANGUAGE sql, not plpgsql: a single-statement SQL function is a
-- candidate for inlining into the calling query's plan, so REFRESH's
-- plan at scale is not worse for the indirection -- confirmed via
-- EXPLAIN below, not assumed.
--
-- THE SEMANTIC GAP THIS SURFACES. current_fact's existing filter
-- (superseded_at IS NULL; effective_to/effective_from vs. now()) is
-- valid-time-only plus "not yet superseded, full stop." That is correct
-- for ts = now() by coincidence, not by design: recorded_at <= now() is
-- always true for an already-inserted row (recorded_at defaults to now()
-- at insert time and cannot be in the future under normal operation),
-- and superseded_at > now() is essentially impossible for a real
-- already-superseded row (superseded_at is set to an actual past
-- timestamp at UPDATE time). Neither of those is trivial once ts is an
-- arbitrary PAST timestamp. Without a transaction-time bound,
-- current_fact_at(ts) would show a fact recorded AFTER ts as if it had
-- already been known AT ts -- using information the system did not have
-- yet to reconstruct a past belief. That is look-ahead bias, concretely,
-- not an abstract risk: it is exactly the class of error C5 exists to
-- prevent. The fix is the two added conditions below, using fact's
-- existing bitemporal columns (0006: recorded_at/superseded_at are
-- transaction time; effective_from/effective_to are valid time; both
-- have existed since fact's own creation -- this migration adds no
-- column, only uses columns already there):
--   f.recorded_at <= ts
--   AND (f.superseded_at IS NULL OR f.superseded_at > ts)
-- Confirmed, not assumed, that this changes nothing for ts = now(): see
-- 0036's test pair in db/tests/invariants.sql (current_fact_at(now())
-- matches current_fact exactly on real fixture data; a second test
-- constructs a fact recorded after a fixed ts and confirms
-- current_fact_at(ts) excludes it while a naive valid-time-only filter
-- would not).
--
-- NOT changed: source_asserted_as_of (0028) is not part of this filter.
-- It is the SOURCE's own stated currency claim, a third and narrower
-- thing than either of fact's two bitemporal dimensions (0028's own
-- header); current_fact_at answers "what did the system record and
-- still consider valid as of ts," not "what did the source itself claim
-- was current as of ts." Folding it in would be a different, larger
-- question than C5 asked.
--
-- current_fact_pk and current_fact_field (both 0008) are recreated
-- identically -- REFRESH MATERIALIZED VIEW CONCURRENTLY's requirement
-- (a UNIQUE index covering the full result, no WHERE clause) does not
-- care how the defining query is built, only what its result looks like.

CREATE FUNCTION current_fact_at(ts timestamptz) RETURNS SETOF fact AS $$
    SELECT DISTINCT ON (f.parcel_id, f.field_key)
           f.*
      FROM fact f
      JOIN parcel p ON p.id = f.parcel_id
      LEFT JOIN source_rank sr
             ON sr.jurisdiction_id = p.jurisdiction_id
            AND sr.field_key       = f.field_key
            AND sr.source_id       = f.source_id
     WHERE f.recorded_at <= ts
       AND (f.superseded_at IS NULL OR f.superseded_at > ts)
       AND f.effective_from <= ts
       AND (f.effective_to IS NULL OR f.effective_to > ts)
     ORDER BY f.parcel_id, f.field_key,
              COALESCE(sr.rank, 999) ASC,
              f.confidence ASC,                      -- enum order: high < medium < low
              f.retrieved_at DESC NULLS LAST,
              f.id;                                   -- deterministic tiebreak; no ranking meaning
$$ LANGUAGE sql STABLE;

DROP MATERIALIZED VIEW current_fact;

CREATE MATERIALIZED VIEW current_fact AS
SELECT * FROM current_fact_at(now());

CREATE UNIQUE INDEX current_fact_pk    ON current_fact (parcel_id, field_key);
CREATE INDEX        current_fact_field ON current_fact (field_key);

-- Refresh with REFRESH MATERIALIZED VIEW CONCURRENTLY current_fact; at the
-- end of each ingest job (db/README.md: plain refresh first if the view
-- is not yet populated). Application queries read current_fact for "now."
-- A point-in-time read (as_of, §4.1; an audit; a dispute) queries
-- current_fact_at(ts) directly -- uncached, always correct, computed
-- against the live fact table at read time. The composer, the audit path
-- and any reconstruction still read fact directly, unchanged from §3.8.
