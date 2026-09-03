-- 0061_current_fact_at_inlining.sql
-- Serves: performance (unnamed invariant -- no §1 invariant number covers query latency).
-- Reverses one clause of db/migrations/0039_schema_qualify_trigger_functions.sql.
--
-- THE PROBLEM, MEASURED, NOT ASSUMED. 0036 (see docs/LEDGEX_SPEC.md §3.8) chose LANGUAGE sql
-- for current_fact_at() specifically to obtain inlining: "the LANGUAGE sql function body
-- inlines into the calling query's plan, so REFRESH's plan is unchanged by the indirection"
-- (0036's own header, :45-48). That was true when 0036 landed. 0039 then added
-- SET search_path = public, pg_temp to the same function as defense-in-depth against a table-
-- shadow attack its own header reproduces directly. That SET clause is a per-call GUC scope,
-- and PostgreSQL will not inline a SQL function that sets a GUC for its own call -- silently
-- reintroducing exactly the cost 0036 chose LANGUAGE sql to avoid, unnoticed for 22 migrations
-- because nothing asserted the function stayed inlined (see the regression test landing in the
-- same commit as this migration).
--
-- Reproduced mechanically, not narrated: a scratch-database A/B (P64A.1,
-- ~/Desktop/ledgex-p64-evidence/P64A1-RUN-EVIDENCE/) built two functions, bodies verbatim-
-- identical, differing only in the SET clause. With it: Function Scan on the function, ~2.9-
-- 3.0s on real data volume, WHERE parcel_id pushed down as a Filter ABOVE an opaque function
-- call, Rows Removed by Filter on the order of the whole ledger. Without it: no Function Scan
-- node, the body expands into the plan, parcel_id lands as an Index Cond on fact_lookup, 4.4ms.
-- Reproduced live against the real database (P64A.2/P64A.3): single-parcel read ~2,500-3,600ms
-- before, ~4.5ms after; ?as_of=<past> ~530ms before (an unrepresentative best case for a
-- pre-data timestamp; a realistic recent-past as_of pays the same ~2.9s the now() case does),
-- ~2.6ms after.
--
-- WHY THIS IS SAFE: LAYER 1, NOT LAYER 2, IS WHAT PROTECTS THE TABLE-SHADOW THREAT. 0039's own
-- header names TWO layers: (1) explicit public. qualification on every table reference --
-- "the reliable fix ... cannot resolve to pg_temp regardless of search_path" -- and (2) this SET
-- clause, called "defense-in-depth for any future reference that lands unqualified BY MISTAKE."
-- Layer 1 is already fully present in the body below, unchanged. This migration removes ONLY
-- layer 2. db/tests/invariants.sql's T63 (current_fact_at() resists a pg_temp.fact shadow)
-- continues to pass with layer 2 absent -- re-confirmed on a volume-matched scratch database
-- before this migration was written (P64A.2, r1-invariants.txt), and re-confirmed again in this
-- package's own rehearsal (P64A.3, p64a3_rehearsal). The property was also demonstrated
-- ADVERSARIALLY, not merely by the polite default case: a session that explicitly overrides its
-- OWN search_path to SET search_path TO pg_temp, public (pg_temp first, the ordering that would
-- favor a shadow if layer 1 were not doing the real work) still cannot make current_fact_at read
-- the shadow (P64A.2, r4-adversarial-t63.txt: "shadow did NOT succeed (count=1) even with
-- session search_path overridden"). Layer 1's protection is independent of search_path at any
-- level, session or database -- exactly why removing layer 2 costs nothing here.
--
-- WHAT THIS DOES NOT CLOSE, STATED PLAINLY, NOT CLAIMED SHUT. The operator/cast-shadowing
-- residual -- whether a same-named operator or function created in pg_temp could be resolved by
-- one of this body's bare comparison operators (<=, >, =) or the confidence enum's ordering
-- opclass -- was not settled by measurement in the P64A chain and is NOT settled here either.
-- 0039 never claimed to close it (its own header frames layer 2 as protection against an
-- ACCIDENTAL future unqualified TABLE reference, never against adversarial operator shadowing),
-- so this migration leaves an existing, pre-existing, never-addressed gap exactly where it
-- already was -- it does not introduce a new one.
--
-- fact_licence_validate() (0029, fixed by the same pass of 0039) is UNTOUCHED by this migration.
-- It is LANGUAGE plpgsql, never a candidate for inlining regardless of any SET clause -- 0039's
-- own header audited every other function in this codebase for exactly this reason and found
-- current_fact_at the only LANGUAGE sql function among them. Its SET search_path clause costs
-- it nothing and stays.
--
-- CREATE OR REPLACE, NOT DROP/CREATE. Same signature (ts timestamp with time zone), same return
-- type (SETOF public.fact) -- current_fact (0008, redefined 0036 as SELECT * FROM
-- current_fact_at(now())) and its dependent objects need no rebuild, the same precedent 0039
-- itself already established for this exact function ("CREATE OR REPLACE ... current_fact and
-- its dependent objects need no rebuild").
--
-- NO SEED-SIDE HALF NEEDED. This corrects no data -- CLAUDE.md's both-halves rule governs a
-- migration that corrects already-seeded data; this changes function code only, nothing a seed
-- file could disagree with.
--
-- REGRESSION TEST, SAME COMMIT. scripts/test_current_fact_at_inlined.py asserts the ABSENCE of
-- a Function Scan node in EXPLAIN output for a single-parcel call -- deterministic (a rewrite-
-- stage decision, not cost-based), so it will not flake on a small CI database the way an
-- assertion that parcel_id lands on a specific index would. Wired into .github/workflows/db.yml
-- as a standalone step, the same shape as the 20 (now 21) that already exist -- no new make
-- target, no new entry in ledgex_source.MAKE_TARGETS.

CREATE OR REPLACE FUNCTION public.current_fact_at(ts timestamp with time zone) RETURNS SETOF public.fact
    LANGUAGE sql STABLE
    AS $$
    SELECT DISTINCT ON (f.parcel_id, f.field_key)
           f.*
      FROM public.fact f
      JOIN public.parcel p ON p.id = f.parcel_id
      LEFT JOIN public.source_rank sr
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
$$;
