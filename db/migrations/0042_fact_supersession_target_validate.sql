-- 0042_fact_supersession_target_validate.sql
-- Fixes: fact.supersedes_fact_id (0025). Serves: I4, C1.
--
-- THE GAP. 0025 validates the FK (supersedes_fact_id references a real
-- fact), the pairing (supersedes_fact_id and supersession_reason are
-- both NULL or both set), and self-reference (a fact cannot supersede
-- itself). Nothing validates that the fact being superseded is the SAME
-- (parcel_id, field_key) lineage as the superseding fact, or that it was
-- actually retired. Reproduced directly, not assumed: inserted a fact
-- for parcel 1 / parcel.apn, then a second, wholly unrelated fact for
-- parcel 2 / parcel.geometry with supersedes_fact_id pointing at the
-- first -- committed cleanly, with the first fact's own superseded_at
-- never touched. Nothing in the schema distinguishes "a real correction"
-- from "a fact citing an arbitrary other fact's id as its predecessor."
--
-- THE FIX. A deferred constraint trigger, firing after the superseding
-- fact's own row exists, checking two things against the fact it claims
-- to supersede:
--   1. Same (parcel_id, field_key) -- a correction to a value can only
--      supersede a prior version of that SAME value, never a different
--      parcel's or a different field's fact entirely.
--   2. superseded_at IS NOT NULL -- the target must actually have been
--      retired. The correct two-statement shape (UPDATE the old fact's
--      superseded_at, INSERT the new fact citing it) leaves the old
--      row's superseded_at set by the time this transaction commits;
--      DEFERRABLE INITIALLY DEFERRED lets both statements land in
--      either order within one transaction, same reasoning as
--      fact_licence_inheritance (0007). A supersedes_fact_id pointing
--      at a fact that was never actually marked superseded means the
--      two-statement operation was done wrong (or only half done) --
--      catching that here is cheaper than discovering it later as two
--      simultaneously-current facts for the same parcel/field with no
--      recorded relationship between them.
--
-- Deliberately not checked here, reported instead: whether one fact may
-- ever be superseded by two different successors (a unique index on
-- supersedes_fact_id would forbid it). That's a modelling question about
-- whether supersession is a strict linear chain or can branch under
-- concurrent correctors, not a data-shape gap this migration's evidence
-- settles either way -- reported separately, not decided here.
--
-- Self-referencing lookup against fact, from inside a trigger fired by
-- an INSERT on fact -- same exposure class 0039 closed for
-- fact_licence_validate() and current_fact_at(), so the same treatment:
-- explicit public. qualification plus SET search_path = public, pg_temp
-- (confirmed directly in 0039's own header that search_path = public
-- ALONE does not stop pg_temp shadowing; the explicit pg_temp entry
-- after public is what does).

CREATE OR REPLACE FUNCTION fact_supersession_target_validate() RETURNS trigger AS $$
DECLARE
    target_parcel_id     uuid;
    target_field_key     text;
    target_superseded_at timestamptz;
BEGIN
    IF NEW.supersedes_fact_id IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT parcel_id, field_key, superseded_at
      INTO target_parcel_id, target_field_key, target_superseded_at
      FROM public.fact
     WHERE id = NEW.supersedes_fact_id;

    IF target_parcel_id IS DISTINCT FROM NEW.parcel_id
       OR target_field_key IS DISTINCT FROM NEW.field_key
    THEN
        RAISE EXCEPTION
            'I4 violated: fact % (parcel %, field %) claims to supersede '
            'fact % (parcel %, field %) -- a fact can only supersede a '
            'prior fact for the SAME parcel and field.',
            NEW.id, NEW.parcel_id, NEW.field_key,
            NEW.supersedes_fact_id, target_parcel_id, target_field_key;
    END IF;

    IF target_superseded_at IS NULL THEN
        RAISE EXCEPTION
            'I4 violated: fact % claims to supersede fact %, but that '
            'fact''s own superseded_at was never set. Superseding a fact '
            'requires setting its superseded_at in the same transaction.',
            NEW.id, NEW.supersedes_fact_id;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = public, pg_temp;

CREATE CONSTRAINT TRIGGER fact_supersession_target_valid
    AFTER INSERT OR UPDATE ON fact
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION fact_supersession_target_validate();
