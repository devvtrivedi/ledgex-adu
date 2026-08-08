-- 0040_whole_row_immutability.sql
-- Fixes: fact_no_destructive_update() (0007), rule_no_destructive_update()
-- (0013). Serves: I4, I18.
--
-- THE GAP. Both functions enumerate every locked column by hand in one
-- giant OR chain. Four fact columns added by later migrations were never
-- added to that chain: jurisdiction_id (0022), supersedes_fact_id and
-- supersession_reason (0025), source_asserted_as_of (0028). Reproduced
-- directly, not assumed: seeded one fact row, then
--   UPDATE fact SET superseded_at = now(), source_asserted_as_of = '2099-01-01'
--   WHERE id = '<that row>';
-- committed cleanly -- the legitimate supersession masked an
-- unauthorized rewrite of source_asserted_as_of in the same statement.
-- The trigger only ever checked the columns someone remembered to list
-- when it was written; every column added afterward defaults to
-- unprotected until someone remembers to go back and add it there too.
-- This is a structural gap, not a one-time oversight: the next new fact
-- or rule column has exactly the same exposure the moment it's added,
-- and nothing short of reading this trigger's source would reveal it.
--
-- THE FIX. Whole-row comparison minus the one permitted mutation:
--   to_jsonb(NEW) - 'superseded_at' IS DISTINCT FROM to_jsonb(OLD) - 'superseded_at'
-- for fact, and the same shape keyed on 'effective_to' for rule. Every
-- column is covered automatically, including ones that don't exist yet
-- -- there is no list to forget to update. Confirmed directly against
-- the reproduced case before writing this: the whole-row diff correctly
-- allows a supersession that changes only superseded_at, and correctly
-- rejects the same reproduction (superseded_at AND source_asserted_as_of
-- changed together) that the old column-by-column check let through.
--
-- rule_no_destructive_update gets the identical treatment for the
-- identical reason: same structure (one hand-enumerated OR chain, one
-- permitted one-way transition -- effective_to instead of
-- superseded_at), same exposure to any future rule column landing
-- unprotected by default.
--
-- No table references in either function body (both compare only
-- NEW/OLD, the trigger's own bound row values) -- neither needed the
-- public./search_path treatment 0039 gave fact_licence_validate() and
-- current_fact_at(); this migration is a different defect in the same
-- neighborhood, not a continuation of 0039's.

CREATE OR REPLACE FUNCTION fact_no_destructive_update() RETURNS trigger AS $$
BEGIN
    IF OLD.superseded_at IS NOT NULL THEN
        RAISE EXCEPTION
            'I4 violated: fact % is already superseded and cannot be '
            'modified again.', OLD.id;
    END IF;

    IF NEW.superseded_at IS NULL THEN
        RAISE EXCEPTION
            'I4 violated: fact % cannot be updated. Supersede it (set '
            'superseded_at) and insert a new fact row for a correction '
            'instead.', OLD.id;
    END IF;

    IF (to_jsonb(NEW) - 'superseded_at') IS DISTINCT FROM (to_jsonb(OLD) - 'superseded_at') THEN
        RAISE EXCEPTION
            'I4 violated: fact % is immutable. Only superseded_at may be '
            'set (NULL -> now, once). Insert a new fact row for a '
            'correction.', OLD.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION rule_no_destructive_update() RETURNS trigger AS $$
BEGIN
    -- One-way retirement: NULL -> a date is the only permitted change.
    -- Once effective_to is set, IS NOT NULL is true for every subsequent
    -- update attempt, so this single guard rejects both date -> NULL and
    -- date -> a different date; it never fires for the NULL -> date case,
    -- since OLD.effective_to is NULL there.
    IF NEW.effective_to IS DISTINCT FROM OLD.effective_to
       AND OLD.effective_to IS NOT NULL
    THEN
        RAISE EXCEPTION
            'I18 violated: rule % effective_to is already set to % and '
            'cannot be changed again (attempted %). A correction is a new '
            'rule row at version + 1, never an UPDATE.',
            OLD.id, OLD.effective_to, NEW.effective_to;
    END IF;

    IF (to_jsonb(NEW) - 'effective_to') IS DISTINCT FROM (to_jsonb(OLD) - 'effective_to') THEN
        RAISE EXCEPTION
            'I18 violated: rule % is immutable. Only effective_to may be '
            'set (NULL -> a date, once). A correction is a new rule row at '
            'version + 1, never an UPDATE.', OLD.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
