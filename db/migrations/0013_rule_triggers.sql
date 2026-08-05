-- 0013_rule_triggers.sql
-- Serves: I18.
--
-- rule (0009) has never had an immutability trigger: fact has
-- fact_no_destructive_update (0007), but nothing stopped
-- UPDATE rule SET reviewed_by = ..., review_mode = ..., attestation_uri = ...
-- on an existing row, which is a direct hole against I18 ("Rule and
-- disclosure review evidence is immutable"). This mirrors
-- fact_no_destructive_update's structure: every column is locked except
-- effective_to, which may transition NULL -> a date exactly once — the
-- same one-way shape as fact.superseded_at — to retire a rule version when
-- a newer version supersedes it. Locking effective_to itself would make
-- rule supersession impossible, so it stays mutable for that one
-- transition only.

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

    IF NEW.id                IS DISTINCT FROM OLD.id
       OR NEW.jurisdiction_id IS DISTINCT FROM OLD.jurisdiction_id
       OR NEW.rule_key        IS DISTINCT FROM OLD.rule_key
       OR NEW.version         IS DISTINCT FROM OLD.version
       OR NEW.effective_from  IS DISTINCT FROM OLD.effective_from
       OR NEW.citation        IS DISTINCT FROM OLD.citation
       OR NEW.source_text_uri IS DISTINCT FROM OLD.source_text_uri
       OR NEW.params          IS DISTINCT FROM OLD.params
       OR NEW.pack_version    IS DISTINCT FROM OLD.pack_version
       OR NEW.authored_by     IS DISTINCT FROM OLD.authored_by
       OR NEW.reviewed_by     IS DISTINCT FROM OLD.reviewed_by
       OR NEW.review_mode     IS DISTINCT FROM OLD.review_mode
       OR NEW.reviewed_at     IS DISTINCT FROM OLD.reviewed_at
       OR NEW.attestation_uri IS DISTINCT FROM OLD.attestation_uri
    THEN
        RAISE EXCEPTION
            'I18 violated: rule % is immutable. Only effective_to may be '
            'set (NULL -> a date, once). A correction is a new rule row at '
            'version + 1, never an UPDATE.', OLD.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER rule_no_update BEFORE UPDATE ON rule
    FOR EACH ROW EXECUTE FUNCTION rule_no_destructive_update();
