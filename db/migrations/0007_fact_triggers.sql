-- 0007_fact_triggers.sql
-- Serves: I4, I5.
-- Source: docs/LEDGEX_SPEC.md §3.7.

-- Ordering of restriction severity, most restrictive first. Single source of
-- truth for both the trigger and core/rights. Raises rather than returning
-- NULL for an unhandled value so a future use_restriction addition fails
-- loudly here instead of silently breaking every ORDER BY / comparison that
-- calls this function (a NULL severity would otherwise sort unpredictably
-- and could make the fact_licence_validate() comparison below pass when it
-- shouldn't). A CASE expression can't RAISE, so this is a CASE statement in
-- plpgsql rather than the previous single SQL-language CASE expression.
CREATE OR REPLACE FUNCTION restriction_severity(r use_restriction)
RETURNS smallint AS $$
BEGIN
    CASE r
        WHEN 'unknown'       THEN RETURN 0;
        WHEN 'noncommercial' THEN RETURN 1;
        WHEN 'no_resale'     THEN RETURN 2;
        WHEN 'attribution'   THEN RETURN 3;
        WHEN 'open'          THEN RETURN 4;
        ELSE
            RAISE EXCEPTION 'restriction_severity: unhandled use_restriction value %', r;
    END CASE;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

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
--
-- Fires on UPDATE and DELETE as well as INSERT: fact_input rows can be
-- corrected or removed (e.g. a lineage row entered against the wrong input),
-- and the derived fact's licence needs re-checking against whatever input
-- set remains, not just the set as of the original insert. NEW is
-- unassigned on DELETE (and OLD is unassigned on INSERT), so the row whose
-- fact_id to validate is resolved from whichever of NEW/OLD TG_OP actually
-- supplies, instead of assuming NEW as the single-event version below did.
CREATE OR REPLACE FUNCTION fact_licence_validate() RETURNS trigger AS $$
DECLARE
    target_fact_id   uuid;
    required_licence text;
    actual_licence    text;
BEGIN
    target_fact_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.fact_id ELSE NEW.fact_id END;

    SELECT f.licence_id INTO required_licence
      FROM fact_input fi
      JOIN fact       f ON f.id = fi.input_fact_id
      JOIN licence    l ON l.id = f.licence_id
     WHERE fi.fact_id = target_fact_id
     ORDER BY restriction_severity(l.restriction) ASC, f.licence_id ASC
     LIMIT 1;

    IF required_licence IS NULL THEN
        RETURN NULL;                         -- no inputs recorded yet; ignored for an AFTER trigger
    END IF;

    SELECT licence_id INTO actual_licence FROM fact WHERE id = target_fact_id;

    IF (SELECT restriction_severity(l.restriction) FROM licence l WHERE l.id = actual_licence)
       > (SELECT restriction_severity(l.restriction) FROM licence l WHERE l.id = required_licence)
    THEN
        RAISE EXCEPTION
            'I5 violated: derived fact % carries licence %, but its inputs require % '
            '(or something at least as restrictive). Compute inheritance in '
            'core/store.derive() before insert.',
            target_fact_id, actual_licence, required_licence;
    END IF;

    RETURN NULL;                             -- ignored for an AFTER trigger
END;
$$ LANGUAGE plpgsql;

-- DEFERRABLE INITIALLY DEFERRED lets a transaction insert the derived fact
-- and all its fact_input rows in any order; validation runs once at commit,
-- when the full input set is visible. Inserting inputs one at a time under a
-- non-deferred trigger would fire on a partial set and raise spuriously.
CREATE CONSTRAINT TRIGGER fact_licence_inheritance
    AFTER INSERT OR UPDATE OR DELETE ON fact_input
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION fact_licence_validate();
