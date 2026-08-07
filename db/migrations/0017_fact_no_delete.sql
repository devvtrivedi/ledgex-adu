-- 0017_fact_no_delete.sql
-- Serves: I4.
--
-- fact_no_update (0007) only intercepts UPDATE. Nothing stopped
-- DELETE FROM fact WHERE id = ... on an unreferenced row -- I4 says facts
-- are immutable, and a row that can be deleted outright is not immutable,
-- it is just harder to overwrite in place. Mirrors 0013's rule_no_delete
-- exactly: an unconditional raise, same structure as the UPDATE trigger's
-- own error shape.
--
-- fact_input.fact_id (0006) carries ON DELETE CASCADE. That FK behavior
-- becomes unreachable the moment this trigger exists: fact_no_delete fires
-- BEFORE DELETE and raises before Postgres ever gets to the point of
-- cascading into fact_input. This migration does NOT change that FK --
-- forward-only, and the FK is otherwise harmless dead weight, not a bug --
-- it now simply documents an intent (deleting a fact cleans up its
-- lineage rows) that can no longer occur. Left as a note for a later
-- cleanup pass, not fixed here.

CREATE OR REPLACE FUNCTION fact_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'I4 violated: fact % cannot be deleted. Corrections supersede, '
        'never delete.', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER fact_no_delete BEFORE DELETE ON fact
    FOR EACH ROW EXECUTE FUNCTION fact_no_delete();
