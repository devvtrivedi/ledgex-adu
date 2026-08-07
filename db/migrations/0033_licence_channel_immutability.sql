-- 0033_licence_channel_immutability.sql
-- Serves: B2, I6, §7.3.
--
-- licence has had licence_no_update/licence_no_delete since 0027, but
-- licence_channel -- the table §7.3 names as the SOLE authority for
-- runtime channel eligibility ("Channel eligibility for any fact is
-- determined solely by licences.yaml -> licence + licence_channel...
-- Nothing else grants a channel") -- never got the same protection.
-- UPDATE licence_channel SET allowed = true silently broadens rights for
-- every existing fact that cites the licence, exactly like B2 described
-- for licence itself, applied to the table that actually gates output.
-- This is more operative than licence's own commercial_use/redistribution/
-- restriction columns: I6's composer gate reads licence_channel directly,
-- not those columns.
--
-- SEQUENCING. This migration must land, and be applied, AFTER
-- 0030 (finding #3's correction of the four pre-existing channel rows)
-- and 0032 (C9's analytics/model_training rows) -- the corrected rows have
-- to be written while the table is still mutable. Applying this migration
-- before those would not break anything mechanically (0030/0032 would
-- simply need to run first in the same forward-only sequence regardless,
-- since migrations apply in file order), but the dependency is real: a
-- database that somehow applied 0033 out of order, before 0030/0032, would
-- have those two migrations' UPDATE/INSERT statements rejected by the
-- trigger below where finding #3's UPDATEs are concerned -- 0032's INSERTs
-- would still succeed, since this trigger only blocks UPDATE and DELETE.
-- Forward-only, strictly numbered migrations already guarantee the correct
-- order; this note records why the order is load-bearing, not just tidy.
--
-- SAME TRADE AS LICENCE (0027). No versioning, just an un-editable row.
-- Changing a channel decision -- flipping allowed, or correcting a
-- rationale -- means a new licence row with a new id, never an UPDATE to
-- an existing licence_channel row, for exactly the reason 0027 gives for
-- licence itself: every fact that already cites this licence depends on
-- its rights position staying exactly as recorded on the day it was
-- cited.
--
-- WORKABILITY, checked before writing, not assumed: is there a legitimate
-- operational flow that needs to flip an existing licence_channel row in
-- place once real clearance arrives? No. Clearance is recorded on
-- licence.cleared_by/cleared_at, not on licence_channel -- and those
-- columns are already frozen by 0027 with no carve-out. The moment real
-- clearance lands, a new licence row is ALREADY mandatory regardless of
-- what happens to licence_channel, so there is no path where clearance
-- arrives but the parent licence row stays the same. The new licence row
-- carries fresh licence_channel INSERTs (still legal under this lock); the
-- old row's channels stay false forever, an accurate record of what was
-- believed at the time. Unlike fact/rule, which need one narrow permitted
-- mutation (superseded_at/effective_to) because their OWN table is where
-- the lifecycle transition is recorded, licence_channel's transition is
-- recorded one level up, on licence, which already forces the new-row
-- discipline -- no permitted-transition carve-out is needed here.
--
-- INSERT stays legal: a new licence row can always declare its own
-- channels; this migration only blocks UPDATE and DELETE on existing rows.
--
-- Checked before writing, not assumed: grepped db/seeds/*.sql and
-- db/tests/invariants.sql for any UPDATE or DELETE against licence_channel.
-- None exists -- nothing needs restructuring to an INSERT for this to land
-- safely.

CREATE OR REPLACE FUNCTION licence_channel_no_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'B2/I6 violated: licence_channel row (%, %) is immutable. A '
        'changed channel decision is a new licence row with a new id, '
        'never an UPDATE to an existing licence_channel row -- every fact '
        'that already cites this licence depends on its rights position '
        'staying exactly as recorded.', OLD.licence_id, OLD.channel;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER licence_channel_no_update BEFORE UPDATE ON licence_channel
    FOR EACH ROW EXECUTE FUNCTION licence_channel_no_update();

CREATE OR REPLACE FUNCTION licence_channel_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'B2/I6 violated: licence_channel row (%, %) cannot be deleted. '
        'Every fact that cites this licence depends on it for the '
        'channel-eligibility record; deleting it would invalidate their '
        'rights history without touching them, and would also silently '
        'fall back to licence_channel''s own default-deny rather than '
        'leaving a decision on record.', OLD.licence_id, OLD.channel;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER licence_channel_no_delete BEFORE DELETE ON licence_channel
    FOR EACH ROW EXECUTE FUNCTION licence_channel_no_delete();
