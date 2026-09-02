-- 0059_fact_licence_restriction_generic.sql
-- Serves: I5. D-6.7 (P62A packet, ~/Desktop/ledgex-p62-evidence/P62A-VERIFICATION-PACKET.md
-- Group D §5.3-§5.5). Decision: OWNER, 2026-09-02, Option 2 -- decided in the chat that
-- designed this package, against that packet, which presented both options and made no
-- recommendation.
--
-- THE PROBLEM 0058 LEFT BEHIND. 0058 closed A-N10's coverage gap (no_resale,
-- noncommercial and unknown made sticky, alongside attribution) but did so as
-- FOUR literal, near-identical IF blocks -- one per restriction value. A-N10's
-- own argument (LEDGEX-P59B-ENGINEERING-REPORT.md sec 2.3) is that this is
-- fragile: a future `use_restriction` enum value added by `ALTER TYPE ...
-- ADD VALUE` would silently miss all four blocks and pass through
-- unenforced, exactly the laundering shape 0058 itself closed for the
-- four values that existed when it was written.
--
-- THE GENERIC RULE, AND WHY IT IS CORRECT GIVEN WHAT ALREADY RUNS ABOVE IT.
-- 0058's own representability check (unchanged below, still immediately
-- above this migration's one generic block) already guarantees, before any
-- sticky check runs, that a derivation's inputs carry AT MOST ONE distinct
-- non-open restriction -- `distinct_sticky_restrictions` is either NULL (no
-- non-open input) or a one-element array (exactly one distinct non-open
-- value; more than one raises I5_RESTRICTION_UNREPRESENTABLE and never
-- reaches this point). Given that guarantee, "the derived fact's
-- restriction must equal the one non-open restriction carried by its
-- inputs, if any" is a SINGLE comparison against
-- `distinct_sticky_restrictions[1]`, covering every current and future enum
-- value automatically -- no future migration needs to add a fifth literal
-- block. **This correctness depends entirely on the representability check
-- still running immediately before this block, unchanged, in the same
-- function.** A later session that reorders these two sections, or that
-- adds a new check between them capable of letting more than one distinct
-- non-open restriction through, silently breaks this migration's own
-- premise -- the guarantee this block relies on lives in the check above
-- it, not restated here.
--
-- D-6.7's ACTUAL DECISION: OPTION 2, ONE MESSAGE, ATTRIBUTION FOLDED IN.
-- P62A's packet presented two shapes: Option 1 kept attribution as a
-- special case preserving 0029's exact wording ("I5 violated: ... does not
-- require attribution, but at least one input does."), changing zero
-- tests; Option 2 folds attribution into the fully generic block, changing
-- its message text and requiring T50's rewrite. **The owner chose Option
-- 2.** This is the point of that decision, not an accident of
-- implementation: the trigger is now genuinely one rule with one message
-- shape for all five enum values, at the cost of a real, visible wording
-- change for attribution violations specifically:
--
--     from   'I5 violated: derived fact % licence % does not require
--             attribution, but at least one input does.'      (0029, 0058)
--     to     'I5_RESTRICTION_DROPPED: derived fact % licence % does not
--             carry attribution, but at least one input does.'  (0059)
--
-- CONSEQUENCE 1 -- db/tests/invariants.sql T50 REWRITTEN, NOT ADDED. T50's
-- own `SQLERRM LIKE` pattern asserted 0029's exact wording; this migration
-- lands together with T50's rewrite to the new wording, in the same
-- package, proven by a four-quadrant cycle (old function x old T50 GREEN,
-- old function x new T50 RED, new function x old T50 RED, new function x
-- new T50 GREEN) recorded in P62B-LEDGER.md and
-- ~/Desktop/ledgex-p62-evidence/P62B-RUN-EVIDENCE/ -- not merely asserted.
-- T51 (attribution's positive control) and T109-T113/T115/T116 (no wording
-- dependency on any of these strings, confirmed by grep against every
-- `scripts/test_*.py` and `tests/core/test_*.py` file, zero hits) are
-- unaffected. The invariant floor at db/tests/invariants.sql:6024 does NOT
-- move -- T50 is rewritten in place, no test is added or removed by this
-- migration.
--
-- CONSEQUENCE 2 -- 0058's OWN HEADER BECOMES A STALE CLAIM, NOT AN ERROR TO
-- FIX IN 0058. 0058:228-232 said the attribution message text is
-- "UNCHANGED from 0029's original ... must not need to change alongside a
-- fix that does not touch this check's own behavior." That claim was true
-- when 0058 was written and is superseded by this migration.
-- **`db/migrations/0058_fact_licence_restriction_sticky.sql` is NOT edited
-- -- migrations are forward-only and bodies are never edited after
-- landing.** The correction is recorded in `db/README.md`'s append-only
-- "Stale migration header claims" section instead, per that section's own
-- established convention (the same shape used for 0031/0032's own stale
-- claims).
--
-- `any_input_requires_attrib` (0058's DECLARE) is removed -- it existed
-- only to feed attribution's now-folded-in special case and has no other
-- reader. Verified: `grep -n any_input_requires_attrib` inside this
-- function body, after this migration, returns nothing.
--
-- THE ENUM-EXTENSION PROOF THIS MIGRATION EXISTS TO SATISFY IS DELIBERATELY
-- NOT A PERMANENT TEST. Proving A-N10's own argument for real means adding
-- a sixth `use_restriction` value (`ALTER TYPE ... ADD VALUE`) to a
-- throwaway scratch database, seeding a licence carrying it and a derived
-- fact dropping it, and showing 0058's four literal blocks miss it while
-- this migration's generic block catches it. That proof is real and is
-- recorded in P62B-LEDGER.md and P62B-RUN-EVIDENCE/ -- it is NOT added to
-- db/tests/invariants.sql as a standing case, because `ALTER TYPE ... ADD
-- VALUE` mutates a live enum irreversibly (PostgreSQL cannot drop an enum
-- value) and the standing suite must remain safe to run repeatedly against
-- a disposable database without leaving behind an enum value nothing else
-- will ever clean up. Same shape as A-N8's own recorded decision not to
-- extend closure to `zoning_source_geometry_invalid` (P59C-LEDGER.md) --
-- the reasoning is recorded here and in the ledger so a future session
-- finds an answer, not a gap it has to re-derive.
--
-- WHAT THIS MIGRATION DOES NOT TOUCH. The representability check
-- (I5_RESTRICTION_UNREPRESENTABLE, immediately above the generic block
-- below, unchanged) and everything above it in the function body (the
-- `has_inputs` early return, the channel/commercial_use/redistribution
-- checks) are carried forward byte-for-byte from 0058. The trigger
-- definition itself (`fact_licence_inheritance`, `db/migrations/
-- 0007_fact_triggers.sql:140` -- confirmed live via `pg_get_triggerdef`
-- before writing this migration: `AFTER INSERT OR DELETE OR UPDATE ON
-- fact_input DEFERRABLE INITIALLY DEFERRED FOR EACH ROW`) is untouched --
-- neither 0058 nor this migration ever issues `CREATE CONSTRAINT TRIGGER`;
-- both only replace the function body the existing trigger already calls.
--
-- **Correction to the record, made here rather than silently carried
-- forward: P62A's own Group D packet (§5.4) stated this trigger fires on
-- INSERT and DELETE only, not UPDATE. Reconfirmed live before writing this
-- migration (`pg_get_triggerdef`, and `db/migrations/0007_fact_triggers.sql`
-- itself): the trigger is `AFTER INSERT OR DELETE OR UPDATE`. P62A's claim
-- was wrong; noted here and in P62B-LEDGER.md so the correction is on
-- record rather than left standing. This does not change anything this
-- migration does -- a `CREATE OR REPLACE FUNCTION` does not re-fire
-- validation against any already-committed row regardless of which
-- statement types the trigger is declared for.**
--
-- FORWARD-ONLY, STANDALONE, NO DATA HALF. This migration is a function
-- replacement only -- `CREATE OR REPLACE FUNCTION` changes behavior for
-- FUTURE trigger firings alone, exactly as 0058 itself was. There is no
-- data to migrate and no seed-side counterpart: applying this to a
-- migrations-only (empty) database is a no-op beyond redefining the
-- function, and applying it to a seeded database revalidates nothing
-- already committed (see the trigger-firing note above) -- any
-- already-existing fact_input population that would newly violate this
-- rule sits there undisturbed until something touches it. That population
-- was queried directly, not inferred, against a `ledgex_test` clone before
-- this migration was written -- see P62B-LEDGER.md for the count and the
-- query. The live database's own `fact_input` and `fact WHERE
-- method='derived'` populations are both 0 (P62A §5.4, live, read-only) --
-- this migration's live apply, when it happens (P62C, a separate,
-- not-yet-approved task), affects a population of zero existing rows.
--
-- No new CHECK constraint is added by this migration.

CREATE OR REPLACE FUNCTION public.fact_licence_validate() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'public', 'pg_temp'
    AS $$
DECLARE
    target_fact_id            uuid;
    actual_licence             text;
    actual_restriction         public.use_restriction;
    has_inputs                 boolean;
    over_permitted_channel     public.output_channel;
    commercial_violation       boolean;
    redistribution_violation   boolean;
    distinct_sticky_restrictions text[];
BEGIN
    target_fact_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.fact_id ELSE NEW.fact_id END;

    SELECT EXISTS (SELECT 1 FROM public.fact_input WHERE fact_id = target_fact_id) INTO has_inputs;
    IF NOT has_inputs THEN
        RETURN NULL;  -- I5c: no inputs recorded yet; nothing to validate against.
    END IF;

    SELECT licence_id INTO actual_licence FROM public.fact WHERE id = target_fact_id;
    SELECT restriction INTO actual_restriction FROM public.licence WHERE id = actual_licence;

    -- Channel dimension: a channel the derived licence permits, that at
    -- least one input's licence does not permit (no matching allowed=true
    -- row for that input), is a violation.
    SELECT lc.channel INTO over_permitted_channel
      FROM public.licence_channel lc
     WHERE lc.licence_id = actual_licence
       AND lc.allowed = true
       AND EXISTS (
           SELECT 1
             FROM public.fact_input fi
             JOIN public.fact f ON f.id = fi.input_fact_id
            WHERE fi.fact_id = target_fact_id
              AND NOT EXISTS (
                  SELECT 1 FROM public.licence_channel lc2
                   WHERE lc2.licence_id = f.licence_id
                     AND lc2.channel = lc.channel
                     AND lc2.allowed = true
              )
       )
     LIMIT 1;

    IF over_permitted_channel IS NOT NULL THEN
        RAISE EXCEPTION
            'I5 violated: derived fact % licence % permits channel %, which at '
            'least one input does not permit. A derived fact''s licence may '
            'permit a channel only if every input''s licence also permits it.',
            target_fact_id, actual_licence, over_permitted_channel;
    END IF;

    -- commercial_use: derived may claim 'allowed' only if every input does.
    IF (SELECT commercial_use FROM public.licence WHERE id = actual_licence) = 'allowed' THEN
        SELECT EXISTS (
            SELECT 1
              FROM public.fact_input fi
              JOIN public.fact    f ON f.id = fi.input_fact_id
              JOIN public.licence l ON l.id = f.licence_id
             WHERE fi.fact_id = target_fact_id
               AND l.commercial_use <> 'allowed'
        ) INTO commercial_violation;

        IF commercial_violation THEN
            RAISE EXCEPTION
                'I5 violated: derived fact % licence % claims commercial_use='
                'allowed, but at least one input does not.',
                target_fact_id, actual_licence;
        END IF;
    END IF;

    -- redistribution: same shape as commercial_use.
    IF (SELECT redistribution FROM public.licence WHERE id = actual_licence) = 'allowed' THEN
        SELECT EXISTS (
            SELECT 1
              FROM public.fact_input fi
              JOIN public.fact    f ON f.id = fi.input_fact_id
              JOIN public.licence l ON l.id = f.licence_id
             WHERE fi.fact_id = target_fact_id
               AND l.redistribution <> 'allowed'
        ) INTO redistribution_violation;

        IF redistribution_violation THEN
            RAISE EXCEPTION
                'I5 violated: derived fact % licence % claims redistribution='
                'allowed, but at least one input does not.',
                target_fact_id, actual_licence;
        END IF;
    END IF;

    -- C11 (0058): representability check, BEFORE the sticky restriction
    -- check below -- see this migration's own header for the full
    -- argument, and note the generic block below depends on this check
    -- having already run, unchanged, immediately above it. A derivation
    -- whose inputs carry more than one distinct non-open restriction
    -- cannot be represented by this single-valued column; refuse
    -- explicitly rather than let the sticky check below raise an
    -- unrelated-looking error, or silently pick one.
    SELECT array_agg(DISTINCT l2.restriction::text ORDER BY l2.restriction::text)
      INTO distinct_sticky_restrictions
      FROM public.fact_input fi
      JOIN public.fact    f2 ON f2.id = fi.input_fact_id
      JOIN public.licence l2 ON l2.id = f2.licence_id
     WHERE fi.fact_id = target_fact_id
       AND l2.restriction <> 'open';

    IF distinct_sticky_restrictions IS NOT NULL AND array_length(distinct_sticky_restrictions, 1) > 1 THEN
        RAISE EXCEPTION
            'I5_RESTRICTION_UNREPRESENTABLE: derived fact % has inputs carrying more '
            'than one non-open restriction (%) -- licence.restriction is a single-'
            'valued column and cannot represent their intersection (e.g. both '
            'no_resale AND noncommercial simultaneously, at once). Refusing the '
            'derivation rather than silently dropping one obligation.',
            target_fact_id, distinct_sticky_restrictions;
    END IF;

    -- D-6.7 (0059, Option 2): the single generic sticky-restriction rule,
    -- replacing 0058's four literal blocks (attribution, no_resale,
    -- noncommercial, unknown). Given the representability check above has
    -- already run and not raised, `distinct_sticky_restrictions` is either
    -- NULL (no non-open input at all -- nothing sticky to enforce) or a
    -- one-element array (exactly one distinct non-open restriction value
    -- among the inputs, whatever it is, present or future). If the derived
    -- fact's own restriction does not equal that one value, the obligation
    -- was dropped. This covers attribution the same as every other value
    -- -- the owner's decision (D-6.7, Option 2) folds attribution's
    -- previously-special-cased 0029 wording into this one shape; see this
    -- migration's own header for the exact before/after text and why that
    -- visible change is the decision's point, not an oversight.
    IF distinct_sticky_restrictions IS NOT NULL
       AND actual_restriction::text <> distinct_sticky_restrictions[1] THEN
        RAISE EXCEPTION
            'I5_RESTRICTION_DROPPED: derived fact % licence % does not carry '
            '%, but at least one input does.',
            target_fact_id, actual_licence, distinct_sticky_restrictions[1];
    END IF;

    RETURN NULL;                             -- ignored for an AFTER trigger
END;
$$;
