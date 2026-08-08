-- 0039_schema_qualify_trigger_functions.sql
-- Fixes: fact_licence_validate() (0029), current_fact_at() (0036).
-- Serves: I5, I6, C5.
--
-- THE GAP. Every table reference inside these two function bodies is
-- unqualified ("fact", "fact_input", "licence", "licence_channel",
-- "parcel", "source_rank" -- no "public." prefix). Reproduced directly,
-- not assumed: a session that runs
--   CREATE TEMP TABLE fact_input (fact_id uuid, input_fact_id uuid,
--                                  ordinal smallint, role text);
-- and then inserts a real fact_input row linking an over-permissive
-- derived fact to a restrictive input, inside the SAME transaction, gets
-- the row accepted -- fact_licence_validate() resolved "fact_input"
-- inside its body to the empty pg_temp relation, saw zero rows, and
-- returned NULL ("no inputs recorded yet") before ever touching
-- public.fact_input, which received the real row untouched by I5. The
-- INSERT into public.fact_input itself is not shadowed -- only the
-- trigger's own internal read of "fact_input" is. Same mechanism against
-- current_fact_at(): CREATE TEMP TABLE fact (LIKE public.fact INCLUDING
-- ALL) in a session, with public.fact holding real rows for a parcel,
-- makes current_fact_at(now()) return zero rows for that parcel inside
-- that session -- a caller (composer, replay, audit) would read "no
-- facts" instead of erroring or reading the real table.
--
-- Any session that can run CREATE TEMP TABLE can do this -- not a
-- privileged operation, and not something GRANT/REVOKE on public
-- tables defends against, since pg_temp is the session's own schema.
--
-- THE OTHER TWELVE FUNCTIONS. Audited every CREATE FUNCTION across
-- db/migrations before touching anything (reported in full, separately,
-- before this migration was written): restriction_severity (dropped by
-- 0029, dead), fact_no_destructive_update, rule_no_destructive_update,
-- rule_no_delete, fact_no_delete, snapshot_no_update, snapshot_no_delete,
-- licence_no_update, licence_no_delete, licence_channel_no_update,
-- licence_channel_no_delete, refusals_codes_valid. None references a
-- table by name at all -- RAISE-only, or pure NEW.col/OLD.col
-- comparison, which binds directly to the trigger's row type and never
-- touches search_path. Not touched here: there is no exploit surface to
-- close, and adding SET search_path to a function with nothing to
-- protect is precaution without a corresponding need.
--
-- THE FIX, TWO LAYERS, CONFIRMED SEPARATELY BEFORE WRITING THIS:
--   1. Explicit public. qualification on every table reference in both
--      bodies. The reliable fix -- a qualified reference cannot resolve
--      to pg_temp regardless of search_path, confirmed directly.
--   2. SET search_path = public, pg_temp on both functions, as
--      defense-in-depth for any future reference that lands unqualified
--      by mistake. Confirmed directly, not assumed, exactly what this
--      needs to say: SET search_path = public ALONE does NOT stop
--      pg_temp shadowing -- tested on a throwaway table/function pair,
--      a function with only search_path=public still read a fake
--      pg_temp row instead of the real public one. PostgreSQL implicitly
--      prepends the session's temp schema ahead of search_path UNLESS
--      pg_temp is explicitly listed in it; omitting pg_temp doesn't
--      exclude it; it just leaves the implicit behavior in place. Only
--      SET search_path = public, pg_temp (pg_temp explicitly listed,
--      after public) made the same test read the real table -- verified
--      on the same throwaway pair before writing this migration. Written
--      this way here for that reason, not search_path = public.
--
-- current_fact (0008, redefined 0036 as SELECT * FROM
-- current_fact_at(now())) needs no separate fix: a MATERIALIZED VIEW's
-- defining query resolves its table references to fixed OIDs at
-- CREATE/REFRESH time via pg_rewrite, not by re-parsing text against
-- search_path the way a function body does -- it only calls
-- current_fact_at(), already covered above.
--
-- CREATE OR REPLACE, not DROP+CREATE: same signature, same return type
-- (SETOF public.fact and SETOF fact resolve to the identical composite
-- type OID), so current_fact and its dependent objects need no rebuild.

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

    SELECT EXISTS (SELECT 1 FROM public.fact_input WHERE fact_id = target_fact_id) INTO has_inputs;
    IF NOT has_inputs THEN
        RETURN NULL;  -- I5c: no inputs recorded yet; nothing to validate against.
    END IF;

    SELECT licence_id INTO actual_licence FROM public.fact WHERE id = target_fact_id;

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

    IF any_input_requires_attrib
       AND (SELECT restriction FROM public.licence WHERE id = actual_licence) <> 'attribution'
    THEN
        RAISE EXCEPTION
            'I5 violated: derived fact % licence % does not require '
            'attribution, but at least one input does.',
            target_fact_id, actual_licence;
    END IF;

    RETURN NULL;                             -- ignored for an AFTER trigger
END;
$$ LANGUAGE plpgsql SET search_path = public, pg_temp;

CREATE OR REPLACE FUNCTION current_fact_at(ts timestamptz) RETURNS SETOF public.fact AS $$
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
$$ LANGUAGE sql STABLE SET search_path = public, pg_temp;
