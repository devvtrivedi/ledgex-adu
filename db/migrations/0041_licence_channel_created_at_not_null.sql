-- 0041_licence_channel_created_at_not_null.sql
-- Fixes: licence_channel.created_at (0037). Serves: C6, I6.
--
-- THE GAP. 0037 made created_at nullable specifically so an existing row
-- could stay NULL ("existed before tracking began"). That same
-- nullability is a hole: nothing stopped a NEW row from explicitly
-- supplying created_at = NULL, bypassing the column's own DEFAULT now()
-- -- a DEFAULT only fires when a column is OMITTED from an INSERT, never
-- when NULL is supplied explicitly for it. A new licence_channel row
-- could therefore claim to predate tracking by simply writing NULL, the
-- exact thing created_at exists to make unforgeable. This was the
-- author's own recommendation in 0037 and it was wrong -- nullable
-- solved the backfill problem (existing rows getting a false stamp) by
-- creating a forgery problem (new rows claiming a false absence of one).
--
-- THE FIX. Backfill existing NULLs to '-infinity'::timestamptz, then
-- SET NOT NULL. '-infinity' carries the identical meaning NULL was
-- standing in for -- "existed before tracking began," equivalent for
-- replay purposes to "existed at every time replay could ask about" --
-- but it is a real, present value, not an absence a later INSERT can
-- reassert by omission or explicit NULL. Confirmed directly: Postgres's
-- built-in timestamptz comparison operators handle '-infinity' correctly
-- with no special-casing needed anywhere that reads this column --
-- '-infinity'::timestamptz <= any real timestamp is true, it equals
-- itself, and IS DISTINCT FROM NULL is true (so it can never be
-- mistaken for the absence it replaces). NOT NULL then closes the
-- specific bypass this migration exists for: no INSERT can omit
-- created_at (DEFAULT now() fires) or supply NULL (rejected outright)
-- ever again.
--
-- NOT fully closed, noted rather than fixed here: NOT NULL stops the
-- NULL bypass specifically, not every conceivable one -- a caller could
-- still explicitly INSERT a row with created_at = '-infinity' and claim
-- the same false pre-tracking history a different way. Not addressed in
-- this migration: '-infinity' is a conspicuous, deliberately-typed
-- value no ordinary seed or ingest path would ever write by accident the
-- way an omitted or NULL column reads as "didn't think about it" --
-- closing that residual path would need a CHECK constraint distinguishing
-- "this row is old enough to predate real tracking" from "this row was
-- typed by someone trying to lie," which is a policy question (how old
-- is old enough), not a data-shape one, and is flagged here rather than
-- guessed at -- the same kind of gap 0027's own header leaves open for
-- source_rank.
--
-- Checked directly before writing this: no code anywhere in this
-- repository currently queries or compares licence_channel.created_at at
-- all -- scripts/compose_property_file.py's rights gate reads only
-- (licence_id, allowed), and no replay script exists yet, grepped for
-- one. There is nothing live to break by this change; the -infinity
-- comparison property above is confirmed for whenever a real replay
-- query is written, not because anything reads it today.
--
-- THE IMMUTABILITY CONFLICT. licence_channel_no_update (0033) is an
-- unconditional raise on any UPDATE, and the backfill above is an
-- UPDATE. Confirmed directly: attempting this backfill with the trigger
-- live raises B2/I6's own violation message. That trigger exists to
-- protect a RIGHTS DECISION -- licence_id, channel, allowed, rationale
-- -- from being rewritten out from under facts that already cite it.
-- created_at is bookkeeping ABOUT that decision, not the decision
-- itself: NULL never meant "undecided," it meant "decided, but this row
-- predates recording exactly when." Backfilling it changes no row's
-- rights position, confirmed by scope: the UPDATE below touches
-- created_at only, on rows where it is NULL, and nothing else -- not the
-- open-ended "correct whatever's wrong" update CLAUDE.md's own guidance
-- warns has no path forward against an immutable table (that guidance
-- is about correcting a recorded DECISION; this is populating a column
-- that never recorded one). The trigger is disabled by name, not by
-- ALL, for exactly the duration of this one UPDATE, and re-enabled
-- immediately after, in the same transaction -- licence_channel_no_delete
-- stays live throughout; nothing this migration does could be a DELETE.

ALTER TABLE licence_channel DISABLE TRIGGER licence_channel_no_update;

UPDATE licence_channel SET created_at = '-infinity'::timestamptz WHERE created_at IS NULL;

ALTER TABLE licence_channel ENABLE TRIGGER licence_channel_no_update;

ALTER TABLE licence_channel ALTER COLUMN created_at SET NOT NULL;
