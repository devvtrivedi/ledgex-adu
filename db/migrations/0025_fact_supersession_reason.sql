-- 0025_fact_supersession_reason.sql
-- Serves: C1 (ML review) -- the target-variable / contamination distinction
-- for any future model trained on supersession events.
--
-- Landing now, specifically: supersession_reason distinguishes four causes
-- that currently produce an identical database transition (the old fact's
-- superseded_at set, a new fact row inserted) -- the world changed, the
-- source corrected itself, a re-fetch returned the same meaning under
-- different bytes, or our own parsing/mapping logic changed. The first is
-- the target variable for any model trying to predict real-world change;
-- the second is contamination that would poison it. Today the database
-- cannot tell them apart after the fact -- there is nothing on the fact
-- row that says which one happened, and there never will be for any
-- supersession written before this column exists.
--
-- This database has 40 facts and zero supersessions. Nothing has been
-- superseded yet -- the first ingest loaded 20 parcels once. The SECOND
-- ingest of the same 20 parcels is what creates the first supersessions,
-- and at that moment the ingest script already knows which case it's in
-- (unchanged content_hash vs. a changed one, same source vs. a corrected
-- registration, same ingest code vs. changed mapping logic). Every
-- supersession written before this migration lands would have an
-- unrecoverable cause; every one written after can be given the real one
-- by the code that causes it. The window is exactly this one ingest.
--
-- Both columns nullable, added together: a fact that supersedes nothing
-- carries neither, a fact that supersedes something must state why.
-- fact_supersession_reason_biconditional enforces that pairing -- named,
-- not left for Postgres to auto-name, per CLAUDE.md. This means the 40
-- existing fact rows need no backfill: they supersede nothing, so NULL/NULL
-- is already their correct, honest state under the biconditional.
--
-- fact_supersedes_not_self mirrors fact_input_not_self (0006): a fact
-- cannot supersede itself.
--
-- The reason is recorded on the SUPERSEDING fact (the new row), never on
-- the superseded one. Deliberate: the old row already has its one legal
-- mutation spent (superseded_at, NULL -> now, per fact_no_destructive_update,
-- 0007). Writing the cause onto the OLD row would require a second legal
-- mutation on an already-superseded fact, which is exactly what I4 exists
-- to forbid -- fact_no_destructive_update already raises on any UPDATE to
-- a fact whose superseded_at is already set, cause-recording included.
-- Putting it on the new row instead needs no second mutation and no new
-- exception to I4.
--
-- 'unknown' is a real, permitted value, not a placeholder to be designed
-- away later. A supersession whose cause genuinely isn't known yet (an
-- ingest job that can't yet distinguish source_correction from
-- refetch_no_change, say) should record 'unknown' honestly rather than
-- have calling code guess at one of the other four to satisfy a NOT NULL
-- that isn't there anyway -- the column is nullable specifically so
-- "supersedes nothing" and "supersedes something, cause unknown" both have
-- a truthful representation.

CREATE TYPE supersession_reason AS ENUM (
    'world_change',
    'source_correction',
    'refetch_no_change',
    'ingestion_logic_change',
    'unknown'
);

ALTER TABLE fact
    ADD COLUMN supersedes_fact_id uuid,
    ADD COLUMN supersession_reason supersession_reason;

ALTER TABLE fact
    ADD CONSTRAINT fact_supersedes_fact_fk
    FOREIGN KEY (supersedes_fact_id) REFERENCES fact (id);

ALTER TABLE fact
    ADD CONSTRAINT fact_supersedes_not_self
    CHECK (supersedes_fact_id <> id);

ALTER TABLE fact
    ADD CONSTRAINT fact_supersession_reason_biconditional
    CHECK (
        (supersedes_fact_id IS NULL AND supersession_reason IS NULL)
        OR
        (supersedes_fact_id IS NOT NULL AND supersession_reason IS NOT NULL)
    );
