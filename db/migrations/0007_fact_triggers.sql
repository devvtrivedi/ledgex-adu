-- 0007_fact_triggers.sql
-- Serves: I4, I5.
-- Source: docs/LEDGEX_SPEC.md §3.7.

-- Ordering of restriction severity, most restrictive first. Single source of
-- truth for both the trigger and core/rights.
CREATE OR REPLACE FUNCTION restriction_severity(r use_restriction)
RETURNS smallint AS $$
    SELECT CASE r
        WHEN 'unknown'       THEN 0
        WHEN 'noncommercial' THEN 1
        WHEN 'no_resale'     THEN 2
        WHEN 'attribution'   THEN 3
        WHEN 'open'          THEN 4
    END;
$$ LANGUAGE sql IMMUTABLE;

-- I4: facts are immutable. §3.7's CREATE TRIGGER statement names this
-- function but LEDGEX_SPEC.md never actually defines a
-- fact_no_destructive_update() body anywhere — only the trigger that
-- references it. This body is authored from the spec's own prose
-- description of the rule ("This locks value, provenance, licence,
-- confidence, conflict, effective time, URLs, method and versions.
-- Supersession is the only permitted mutation and is one-way."), not copied
-- verbatim, because no verbatim source exists.
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

    IF NEW.id                       IS DISTINCT FROM OLD.id
       OR NEW.parcel_id             IS DISTINCT FROM OLD.parcel_id
       OR NEW.field_key             IS DISTINCT FROM OLD.field_key
       OR NEW.value                 IS DISTINCT FROM OLD.value
       OR NEW.unit                  IS DISTINCT FROM OLD.unit
       OR NEW.local_verbatim        IS DISTINCT FROM OLD.local_verbatim
       OR NEW.source_id             IS DISTINCT FROM OLD.source_id
       OR NEW.source_url            IS DISTINCT FROM OLD.source_url
       OR NEW.layer_item_id         IS DISTINCT FROM OLD.layer_item_id
       OR NEW.snapshot_id           IS DISTINCT FROM OLD.snapshot_id
       OR NEW.method                IS DISTINCT FROM OLD.method
       OR NEW.retrieved_at          IS DISTINCT FROM OLD.retrieved_at
       OR NEW.source_published_at   IS DISTINCT FROM OLD.source_published_at
       OR NEW.source_cadence_stated IS DISTINCT FROM OLD.source_cadence_stated
       OR NEW.effective_from        IS DISTINCT FROM OLD.effective_from
       OR NEW.effective_to          IS DISTINCT FROM OLD.effective_to
       OR NEW.recorded_at           IS DISTINCT FROM OLD.recorded_at
       OR NEW.licence_id            IS DISTINCT FROM OLD.licence_id
       OR NEW.confidence            IS DISTINCT FROM OLD.confidence
       OR NEW.confidence_rule_id    IS DISTINCT FROM OLD.confidence_rule_id
       OR NEW.conflict              IS DISTINCT FROM OLD.conflict
       OR NEW.method_version        IS DISTINCT FROM OLD.method_version
       OR NEW.ruleset_version       IS DISTINCT FROM OLD.ruleset_version
       OR NEW.pack_version          IS DISTINCT FROM OLD.pack_version
    THEN
        RAISE EXCEPTION
            'I4 violated: fact % is immutable. Only superseded_at may be '
            'set (NULL -> now, once). Insert a new fact row for a '
            'correction.', OLD.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER fact_no_update BEFORE UPDATE ON fact
    FOR EACH ROW EXECUTE FUNCTION fact_no_destructive_update();

-- I5: VALIDATE that a derived fact already carries the most restrictive
-- licence among its inputs. Does not mutate. core/store.derive() must
-- compute it.
CREATE OR REPLACE FUNCTION fact_licence_validate() RETURNS trigger AS $$
DECLARE
    required_licence text;
    actual_licence    text;
BEGIN
    SELECT f.licence_id INTO required_licence
      FROM fact_input fi
      JOIN fact       f ON f.id = fi.input_fact_id
      JOIN licence    l ON l.id = f.licence_id
     WHERE fi.fact_id = NEW.fact_id
     ORDER BY restriction_severity(l.restriction) ASC, f.licence_id ASC
     LIMIT 1;

    IF required_licence IS NULL THEN
        RETURN NEW;                         -- no inputs recorded yet
    END IF;

    SELECT licence_id INTO actual_licence FROM fact WHERE id = NEW.fact_id;

    IF (SELECT restriction_severity(l.restriction) FROM licence l WHERE l.id = actual_licence)
       > (SELECT restriction_severity(l.restriction) FROM licence l WHERE l.id = required_licence)
    THEN
        RAISE EXCEPTION
            'I5 violated: derived fact % carries licence %, but its inputs require % '
            '(or something at least as restrictive). Compute inheritance in '
            'core/store.derive() before insert.',
            NEW.fact_id, actual_licence, required_licence;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- DEFERRABLE INITIALLY DEFERRED lets a transaction insert the derived fact
-- and all its fact_input rows in any order; validation runs once at commit,
-- when the full input set is visible. Inserting inputs one at a time under a
-- non-deferred trigger would fire on a partial set and raise spuriously.
CREATE CONSTRAINT TRIGGER fact_licence_inheritance
    AFTER INSERT ON fact_input
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION fact_licence_validate();
