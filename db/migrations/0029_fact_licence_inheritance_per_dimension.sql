-- 0029_fact_licence_inheritance_per_dimension.sql
-- Fixes: fact_licence_validate() (0007). Serves: I5, I6.
--
-- THE DEFECT. restriction_severity() (0007) imposed a total order --
-- unknown 0 < noncommercial 1 < no_resale 2 < attribution 3 < open 4 --
-- and fact_licence_validate() picked the single input with the lowest
-- number as "required_licence", requiring the derived fact's severity to
-- be no greater. noncommercial and no_resale restrict DIFFERENT
-- dimensions -- a licence can be no-resale while still permitting other
-- commercial use, or noncommercial while freely redistributable -- so no
-- total order over the five use_restriction values can represent both
-- correctly. Given inputs {noncommercial, no_resale}, the ORDER BY picked
-- noncommercial (severity 1, lower than no_resale's 2) as required; a
-- derived fact tagged noncommercial (severity 1) satisfied "1 <= 1" and
-- passed, silently dropping no_resale's restriction entirely. The trigger
-- also never consulted licence_channel at all, though I6 ("The composer
-- omits or refuses every fact whose licence forbids the output channel")
-- makes licence_channel the actual runtime authority (0002: "Runtime
-- channel eligibility is determined solely by licences.yaml -> licence +
-- licence_channel"; see also §7.3).
--
-- Currently unreachable, confirmed against real data, not assumed: the
-- only two live licence rows (cc0, cc_by_4_0; db/seeds/day4_sources.sql)
-- both permit all four output_channel values, so every intersection is
-- "everything" and no combination can surface the bug today. It becomes
-- reachable the moment any licence denies a channel -- sj_portal_terms
-- (designed in the licences.yaml spec text, §7.2, as deny-all pending
-- confirmation) is exactly that licence, not yet live.
--
-- THE FIX. Four independent dimensions, checked directly against their
-- own authoritative columns/table, no scalar comparison:
--   - channel: for every output_channel, the derived fact's licence may
--     permit it only if every input's licence also permits it. A licence
--     with NO licence_channel row for a channel is default-deny for that
--     channel (0002's own comment: "Absence of a row = denied. Default
--     deny (I6)."). This applies identically whether the missing row
--     belongs to the derived licence or an input's -- a licence with
--     ZERO licence_channel rows at all permits nothing, which trivially
--     (vacuously) satisfies "may only permit what every input permits",
--     since the empty set is a subset of anything. Confirmed, not
--     assumed, that this is the correct reading before writing this
--     migration.
--   - commercial_use: the derived licence may claim 'allowed' only if
--     every input's commercial_use is 'allowed'. 'unknown' and
--     'prohibited' both block identically for this purpose (I6 draws no
--     distinction between them for gating).
--   - redistribution: the same shape as commercial_use.
--   - attribution: sticky, not a permission subset. If ANY input's
--     licence has restriction = 'attribution', the derived licence's
--     restriction must be 'attribution' too. This is the one dimension
--     restriction_severity's removal doesn't fold into commercial_use/
--     redistribution or licence_channel: attribution is an OBLIGATION
--     (you must attribute), not a prohibition those columns capture.
--
-- If no existing licence satisfies all four for a given input set,
-- derivation REFUSES (the trigger raises; core/store.derive(), not yet
-- built, must not have attempted the insert). This migration deliberately
-- does NOT synthesize a composite licence row to make a refused
-- derivation succeed -- an automatically-generated licence row would have
-- no terms_url, no evidence_uri, no cleared_by, and a fabricated
-- observed_at, which is a machine making a rights determination nobody
-- reviewed. Same defect class as backdating url_verified_at = now() for a
-- source nobody actually checked (0016's whole reason for existing).
-- Supplying a suitable licence, when one doesn't already exist, is a
-- human/counsel decision, not something this migration or the trigger
-- should paper over.
--
-- RESTRICTION_SEVERITY(). Checked before writing, not assumed: grepped
-- every .sql and .py file in this repository. Its only callers were the
-- two lines inside fact_licence_validate() this migration replaces --
-- nothing else in the schema calls it. 0007's own comment described it as
-- "single source of truth for both the trigger and core/rights", but
-- core/ does not exist anywhere in this repository yet (no core/rights/
-- directory, no application code) -- that was a stated intent for code
-- that was never built, and the intent itself (a single total order
-- representing five restriction values) is exactly the premise this
-- migration proves wrong. Left in place as unused dead code, it would be
-- a landmine: a future core/rights/ implementer reading "single source of
-- truth" would be pointed at the wrong abstraction. Dropped in this same
-- migration rather than deferred.
--
-- SCHEMA IMPACT. None, confirmed: no new column, no new table, no touch
-- to any existing FK. In particular, 0022's fact_snapshot_licence_fk
-- (FOREIGN KEY (snapshot_id, licence_id) REFERENCES snapshot (id,
-- licence_observed_id)) stays exempt for derived facts under MATCH
-- SIMPLE, exactly as it already was: fact_provenance_complete (0006)
-- forces snapshot_id NULL for every derived fact, and NULL in any
-- referencing column satisfies MATCH SIMPLE regardless of licence_id.
-- This fix only changes what fact_licence_validate() checks, not what any
-- fact row is required to reference.

DROP FUNCTION restriction_severity(use_restriction);

CREATE OR REPLACE FUNCTION fact_licence_validate() RETURNS trigger AS $$
DECLARE
    target_fact_id            uuid;
    actual_licence             text;
    has_inputs                 boolean;
    over_permitted_channel     public.output_channel;
    commercial_violation       boolean;
    redistribution_violation   boolean;
    any_input_requires_attrib  boolean;
BEGIN
    target_fact_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.fact_id ELSE NEW.fact_id END;

    SELECT EXISTS (SELECT 1 FROM fact_input WHERE fact_id = target_fact_id) INTO has_inputs;
    IF NOT has_inputs THEN
        RETURN NULL;  -- I5c: no inputs recorded yet; nothing to validate against.
    END IF;

    SELECT licence_id INTO actual_licence FROM fact WHERE id = target_fact_id;

    -- Channel dimension: a channel the derived licence permits, that at
    -- least one input's licence does not permit (no matching allowed=true
    -- row for that input), is a violation.
    SELECT lc.channel INTO over_permitted_channel
      FROM licence_channel lc
     WHERE lc.licence_id = actual_licence
       AND lc.allowed = true
       AND EXISTS (
           SELECT 1
             FROM fact_input fi
             JOIN fact f ON f.id = fi.input_fact_id
            WHERE fi.fact_id = target_fact_id
              AND NOT EXISTS (
                  SELECT 1 FROM licence_channel lc2
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
    IF (SELECT commercial_use FROM licence WHERE id = actual_licence) = 'allowed' THEN
        SELECT EXISTS (
            SELECT 1
              FROM fact_input fi
              JOIN fact    f ON f.id = fi.input_fact_id
              JOIN licence l ON l.id = f.licence_id
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
    IF (SELECT redistribution FROM licence WHERE id = actual_licence) = 'allowed' THEN
        SELECT EXISTS (
            SELECT 1
              FROM fact_input fi
              JOIN fact    f ON f.id = fi.input_fact_id
              JOIN licence l ON l.id = f.licence_id
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

    -- attribution: sticky, not a permission subset. If any input requires
    -- it, the derived fact must require it too.
    SELECT EXISTS (
        SELECT 1
          FROM fact_input fi
          JOIN fact    f ON f.id = fi.input_fact_id
          JOIN licence l ON l.id = f.licence_id
         WHERE fi.fact_id = target_fact_id
           AND l.restriction = 'attribution'
    ) INTO any_input_requires_attrib;

    IF any_input_requires_attrib
       AND (SELECT restriction FROM licence WHERE id = actual_licence) <> 'attribution'
    THEN
        RAISE EXCEPTION
            'I5 violated: derived fact % licence % does not require '
            'attribution, but at least one input does.',
            target_fact_id, actual_licence;
    END IF;

    RETURN NULL;                             -- ignored for an AFTER trigger
END;
$$ LANGUAGE plpgsql;
