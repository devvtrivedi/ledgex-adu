-- 0058_fact_licence_restriction_sticky.sql
-- Serves: I5. C11 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md).
--
-- THE PROBLEM. fact_licence_validate() (0029) makes exactly ONE restriction
-- value sticky on derivation: attribution. No check ties `no_resale`,
-- `noncommercial` or `unknown` to a derived fact's inputs at all -- a
-- derived fact over an input tagged no_resale (or noncommercial, or
-- unknown) can claim restriction='open' and pass every existing check.
-- The channel/commercial_use/redistribution checks are unaffected by this
-- gap (they gate different columns); what launders is specifically the
-- `restriction` obligation itself disappearing from the rights record.
--
-- THIS MIGRATION generalizes the EXISTING attribution-stickiness shape
-- ("if any input carries restriction X, the derived fact must carry X
-- too") to no_resale, noncommercial and unknown -- the full enum
-- (SELECT enum_range(NULL::use_restriction) on the live type: {open,
-- attribution, noncommercial, no_resale, unknown}, confirmed live before
-- writing this, not assumed from the audit's prose).
--
-- unknown IS a peer of the other three sticky values in THIS trigger, not
-- a special case: I6 (the channel gate, evaluate_rights_gate) is what
-- actually blocks an unknown-rights fact from reaching an output channel;
-- this trigger governs a DIFFERENT, earlier question -- whether a
-- DERIVED fact is honest about inheriting an "we don't know the
-- restriction" state from its inputs, at derivation time, independent of
-- and prior to any channel decision. Making it sticky here closes the
-- same laundering shape one dimension over: an unknown-restriction input
-- silently becoming a restriction='open' derived fact.
--
-- THE REPRESENTABILITY LIMIT, MADE A DELIBERATE REFUSAL, NOT AN ACCIDENT
-- OF BLOCK ORDER. licence.restriction is a SINGLE-VALUED enum. I5
-- requires a derived licence be no broader than the INTERSECTION of
-- every input on every dimension -- but if input A carries `no_resale`
-- and input B carries `noncommercial`, no single restriction value can
-- represent "both simultaneously," and three independent equality checks
-- would raise on whichever one happened to run first, with a caller-
-- confusing message that doesn't say why. Detected explicitly, first,
-- before any of the three sticky checks below run: a derivation whose
-- inputs carry MORE THAN ONE distinct non-open restriction is refused
-- outright, by name (I5_RESTRICTION_UNREPRESENTABLE), with the actual
-- distinct restriction set in the message. This is I8's refuse-first
-- posture applied to a real representability gap in this schema, not a
-- new value invented to paper over it -- CONVENTIONS: "if something turns
-- out to be impossible as specified, that is a finding." An alternative
-- (a severity lattice over the enum so "no_resale AND noncommercial"
-- collapses to whichever is deemed stricter) is a real design decision
-- about what these values mean relative to each other and belongs to the
-- owner -- NOT adopted here. PRESENTED to the owner as the alternative
-- (this refuse-first shape vs. a "no vanishing to open, but any non-open
-- value legal" shape that would keep T47's own no_resale+noncommercial
-- pairing legal); the owner explicitly chose refuse-first -- confirmed
-- and this migration implements exactly that, not the alternative.
--
-- NULL SEMANTICS (CONVENTIONS' own requirement). licence.restriction is
-- NOT NULL (schema-enforced) -- no input or derived-fact restriction
-- value is ever NULL, so no comparison here can silently no-op on a NULL
-- restriction. has_inputs=false (I5c: a derived fact with zero declared
-- inputs) is unaffected -- unchanged, still returns NULL early (a known,
-- documented, unenforced gap, not this migration's job).
--
-- NOT DONE HERE, ON PURPOSE: no CHECK constraint on `licence` itself
-- tying `restriction` to commercial_use/redistribution (C24.12's own
-- root). That is a real, separate question, and adding it here would be
-- a trap: a CHECK is validated against every EXISTING row at ALTER time,
-- and this repo's own fixtures already seed no_resale +
-- commercial_use='allowed' (confirmed live). Such a CHECK would fail
-- outright on any database carrying them, and `licence` has been
-- immutable since 0027, so the offending rows could never be corrected
-- in place. Recorded under C24.12 in this pass's own annex,
-- cross-referenced here, not attempted in this migration.
--
-- PRE-EXISTING ROWS ARE GRANDFATHERED, STATED HONESTLY, NOT DISCOVERED
-- LATER. CREATE OR REPLACE FUNCTION changes behavior only for FUTURE
-- trigger firings -- it does not retroactively re-validate any row
-- already committed (the same class of gap 0048 closed for
-- refusals_codes_valid via DROP+ADD; a trigger function has no
-- equivalent "re-run against every existing row" mechanism, and this
-- migration does not attempt to invent one). Checked live before writing
-- this migration, not assumed:
--   SELECT count(*) FROM fact WHERE method = 'derived';
--   -> ledgex_schema_check: 0, ledgex_golden: 0, ledgex_smoke: 0,
--      ledgex_smoke_pre_p55_20260822: 0, ledgex_test: 132,
--      ledgex_schema_check_pre_p55_20260823: 91.
-- Of ledgex_test's 132 and the pre-p55 copy's 91, a real, non-hypothetical
-- multi-restriction laundering shape already exists -- 12 rows on
-- ledgex_test and 8 on the pre-p55 copy, each a derived fact with
-- restriction='no_resale' over inputs carrying BOTH noncommercial and
-- no_resale (the test suite's own I5-dimension fixtures, T47's own
-- pre-fix shape). These rows are NOT retroactively caught by this
-- migration -- grandfathered, permanently, on those two databases
-- specifically. Any FUTURE derivation reaching the same shape is refused
-- by I5_RESTRICTION_UNREPRESENTABLE above.
--
-- FORWARD-ONLY, STANDALONE. CREATE OR REPLACE FUNCTION applies cleanly to
-- an empty (migrations-only) database -- the function is simply
-- (re)defined, no data to validate. Applied to and verified against a
-- seeded database too (ledgex_schema_check, day4-seeded) -- see the P59
-- deliverable for both transcripts.

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
    any_input_requires_attrib  boolean;
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

    -- C11 (0058): representability check, BEFORE any of the four sticky
    -- restriction checks below -- see this migration's own header for
    -- the full argument. A derivation whose inputs carry more than one
    -- distinct non-open restriction cannot be represented by this
    -- single-valued column; refuse explicitly rather than let whichever
    -- sticky check below happens to run first raise an unrelated-looking
    -- error.
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

    -- attribution: sticky, not a permission subset. If any input requires
    -- it, the derived fact must require it too.
    SELECT EXISTS (
        SELECT 1
          FROM public.fact_input fi
          JOIN public.fact    f ON f.id = fi.input_fact_id
          JOIN public.licence l ON l.id = f.licence_id
         WHERE fi.fact_id = target_fact_id
           AND l.restriction = 'attribution'
    ) INTO any_input_requires_attrib;

    -- Message text UNCHANGED from 0029's original ("I5 violated:", no new
    -- prefix) -- this check itself is not new, only the three below it
    -- are; db/tests/invariants.sql's own pre-existing T50/T51 assert this
    -- exact wording and must not need to change alongside a fix that
    -- does not touch this check's own behavior.
    IF any_input_requires_attrib AND actual_restriction <> 'attribution' THEN
        RAISE EXCEPTION
            'I5 violated: derived fact % licence % does not require '
            'attribution, but at least one input does.',
            target_fact_id, actual_licence;
    END IF;

    -- C11 (0058): no_resale, sticky, same shape as attribution.
    IF EXISTS (
        SELECT 1
          FROM public.fact_input fi
          JOIN public.fact    f ON f.id = fi.input_fact_id
          JOIN public.licence l ON l.id = f.licence_id
         WHERE fi.fact_id = target_fact_id
           AND l.restriction = 'no_resale'
    ) AND actual_restriction <> 'no_resale' THEN
        RAISE EXCEPTION
            'I5_RESTRICTION_DROPPED: derived fact % licence % does not carry '
            'no_resale, but at least one input does.',
            target_fact_id, actual_licence;
    END IF;

    -- C11 (0058): noncommercial, sticky, same shape.
    IF EXISTS (
        SELECT 1
          FROM public.fact_input fi
          JOIN public.fact    f ON f.id = fi.input_fact_id
          JOIN public.licence l ON l.id = f.licence_id
         WHERE fi.fact_id = target_fact_id
           AND l.restriction = 'noncommercial'
    ) AND actual_restriction <> 'noncommercial' THEN
        RAISE EXCEPTION
            'I5_RESTRICTION_DROPPED: derived fact % licence % does not carry '
            'noncommercial, but at least one input does.',
            target_fact_id, actual_licence;
    END IF;

    -- C11 (0058): unknown, sticky, same shape -- see this migration's own
    -- header for why `unknown` is a peer here, not a special case.
    IF EXISTS (
        SELECT 1
          FROM public.fact_input fi
          JOIN public.fact    f ON f.id = fi.input_fact_id
          JOIN public.licence l ON l.id = f.licence_id
         WHERE fi.fact_id = target_fact_id
           AND l.restriction = 'unknown'
    ) AND actual_restriction <> 'unknown' THEN
        RAISE EXCEPTION
            'I5_RESTRICTION_DROPPED: derived fact % licence % does not carry '
            'unknown, but at least one input does.',
            target_fact_id, actual_licence;
    END IF;

    RETURN NULL;                             -- ignored for an AFTER trigger
END;
$$;
