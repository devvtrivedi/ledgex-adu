-- 0027_licence_immutability.sql
-- Serves: B2 (ML review), I3 (rights).
--
-- licence has never had an immutability trigger: UPDATE licence SET
-- commercial_use = 'allowed' silently rewrites what every fact already
-- recorded under that licence_id was permitted to be used for. There is
-- no way afterward to answer "what did we believe this licence permitted
-- on the day we sold that file" -- the licence row a fact cites is
-- supposed to be a frozen statement of terms as understood at the time,
-- and an in-place UPDATE breaks that retroactively for every fact that
-- already cites it, not just future ones.
--
-- The review proposed versioning licence into (id, version), with a
-- licence_version column added to fact and snapshot. Not done here:
-- fact and snapshot's composite FKs (0018's fact_snapshot_licence_fk
-- doesn't exist yet at review time, but 0022's does now, plus
-- fact_snapshot_source_fk, fact_source_method_fk, and the rest) all
-- target licence.id as a plain, single-column reference; introducing a
-- version column would mean reworking every one of those to a licence
-- (id, version) composite target, a materially bigger change than the
-- actual problem calls for.
--
-- Same trade rule 0013 (rule) and 0021 (snapshot) already make instead:
-- no versioning, just make the row un-editable. A changed licence is a
-- NEW licence row with a new id, never an UPDATE to an existing one --
-- exactly how source.method (0016, 0023) and endpoint_url corrections
-- work today, except those are data corrections to an operational
-- record, not a legal-terms record a fact's provenance depends on
-- staying exactly as it was.
--
-- Scope: licence only.
--   - field_definition deliberately excluded: 0026 just demonstrated it
--     legitimately needs correcting in place (expected_fields/
--     phase1_deferred are declared-coverage bookkeeping, not a frozen
--     legal statement -- correcting a wrong claim about what a source
--     supplies is exactly the kind of in-place fix immutability would
--     block for no benefit).
--   - jurisdiction and source_rank are out of scope for this migration.
--     Assessed, not applied: jurisdiction.tier is designed to be mutated
--     in place as assessment status changes (this project's own history
--     includes fixing jurisdiction.tier from a wrongly-hardcoded
--     'tier_1' to 'blocked' precisely so it COULD be promoted later by
--     UPDATE once real coverage is assessed) -- immutability there would
--     block the exact workflow the column exists for. source_rank is
--     less clear-cut: it affects which source's fact wins in current_fact,
--     so a silent rank change has some of the same "what would we have
--     shown on day X" reproducibility concern as licence -- but it is a
--     ranking/config policy that is expected to evolve as sources are
--     onboarded or reassessed, not a legal permission a fact's provenance
--     depends on staying fixed. Worth a real look if reproducing a past
--     current_fact ranking ever becomes a requirement; not the same shape
--     of problem as B2, and not applied speculatively here.
--
-- Checked before writing, not assumed: grepped db/seeds/*.sql and
-- db/tests/invariants.sql for any UPDATE against licence. None exists --
-- nothing needs restructuring to an INSERT for this to land safely.

CREATE OR REPLACE FUNCTION licence_no_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'B2/I3 violated: licence % is immutable. A changed licence is a '
        'new licence row with a new id, never an UPDATE to an existing '
        'one -- every fact that already cites this licence depends on '
        'its terms staying exactly as recorded.', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER licence_no_update BEFORE UPDATE ON licence
    FOR EACH ROW EXECUTE FUNCTION licence_no_update();

CREATE OR REPLACE FUNCTION licence_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'B2/I3 violated: licence % cannot be deleted. Every fact and '
        'snapshot that cites it depends on it for provenance; deleting '
        'it would invalidate their rights history without touching '
        'them.', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER licence_no_delete BEFORE DELETE ON licence
    FOR EACH ROW EXECUTE FUNCTION licence_no_delete();
