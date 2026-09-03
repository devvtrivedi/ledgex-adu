-- 0060_source_steward_classification.sql
-- Serves: D2 (P63A packet, ~/Desktop/ledgex-p63-evidence/P63A-DESIGN-PACKET.md §3/§9/§20,
-- item 2), the one genuine product/schema gap P63A found. Also carries D3's approved half
-- (exception_evidence_no_update) -- see below -- because this is the only migration slot
-- this package (P63B) has, per its own §1 scope. Decision: OWNER, 2026-09-02, approving
-- P63A's five decisions and bounding this package to exactly this migration.
--
-- THE GAP THIS CLOSES. public.source carried steward text NOT NULL and jurisdiction_id, but
-- nothing typing a source as a governmental or private publisher. P63A's investigation found
-- no existing column, anywhere in the schema, could answer that question, and confirmed it
-- from the product-output side too (GET /v1/sources returns steward verbatim, itself
-- inconsistent for the one real jurisdiction in the database -- see the normalization below).
--
-- THE REPRESENTATION: AN ENUM, NOT A BOOLEAN. A boolean cannot express "not yet
-- established" -- this repository's own convention for exactly that shape is
-- permission_state (allowed / prohibited / unknown). steward_class follows it:
-- governmental / private / unknown. One stated irreversibility: a Postgres enum value
-- cannot be removed once added (values CAN be added later -- 0031/0032 already did this
-- twice for output_channel); three values is the smallest set that is honest about a
-- classification that will sometimes genuinely be unknown.
--
-- NOT NULL IS THE POINT. An unclassified source is exactly the state D2 exists to
-- eliminate -- 'unknown' is a real, chosen value for a source genuinely not yet
-- established, never a backfill escape hatch. This migration's own backfill (below)
-- classifies every live row explicitly; ALTER COLUMN ... SET NOT NULL is written to fail
-- loudly if any row is missed, not to silently paper over one.
--
-- THE BACKFILL, DERIVED FROM THE LIVE DATA, NOT GUESSED. Queried directly against the real
-- ledgex_schema_check database before writing this (51 source rows, read-only) --
-- 4 distinct steward values present:
--   'City of San Jose'   (1 row  -- ca_san_jose.city_limits)
--   'City of San José'   (3 rows -- ca_san_jose.building_permits_active/.parcels/.zoning_districts)
--   'P40 internal test'  (3 rows -- internal_test.viewer_source_*, all active=false)
--   'Test'               (44 rows -- test.*/test_p25_*/test_p34_*/test_p53_l0_* fixtures, all active=false)
-- Classification, presented in full in P63B-LEDGER.md and P63B-RUN-EVIDENCE/ before this
-- migration was applied live, not merely asserted here:
--   'City of San Jose' / 'City of San José' -> governmental (a real government body; the
--     two spellings are the SAME entity -- see the normalization below, which runs first).
--   'P40 internal test', 'Test' -> unknown. These are synthetic test/viewer-demo fixtures,
--     not real government or private entities -- 'unknown' is the most honest value
--     available, not a default, and every one of these 47 rows has active=false (confirmed
--     live), so the invariant this migration adds (T117: no ACTIVE source has
--     steward_class='unknown') is never at risk of firing against them. If a future test
--     ever needs an ACTIVE test source, it must classify it for real, same as production.
--
-- THE NORMALIZATION, MINIMAL, PER THE OWNER'S OWN WORD. source.steward carried both
-- 'City of San Jose' and 'City of San José' for the same real government body --
-- inconsistent even within this one real jurisdiction. Normalizing the single unaccented
-- outlier (ca_san_jose.city_limits) to match the other three rows' spelling is the whole of
-- what "minimal" requires here: one UPDATE, one canonical spelling, chosen because it is
-- both the majority spelling already in use (3 of 4 real rows) and the city's own correct
-- name. This is NOT a registry, a foreign key, or a controlled vocabulary -- none of that
-- was asked for. Checked before writing: build/check_jurisdiction_names.py's BLOCKLIST
-- (which does contain the literal human-readable strings "San Jose" and "San José") is
-- scoped to core/**/*.py only, by its own docstring and by direct reading of its source --
-- this migration is db/migrations/, not core/, so there is no collision. fact carries
-- source_id, not steward text (confirmed against db/schema.sql's fact column list before
-- writing this) -- normalizing source.steward changes no fact's recorded provenance and
-- supersedes nothing. source itself carries no immutability trigger (confirmed: the ten
-- no_delete/no_update triggers in this schema are on fact, licence, licence_channel, rule,
-- snapshot only) -- this UPDATE is an ordinary correction to a plain, mutable table.
--
-- D3, APPROVED CONDITIONALLY, APPLIED PER HALF. The owner approved exception_evidence
-- immutability protection only if mechanically additive, requiring no historical
-- reconstruction/backfill, and not materially expanding this package -- otherwise deferred
-- post-MVP. Checked directly, not assumed, before writing:
--   no-update: grepped scripts/, core/, api/, db/ for any UPDATE against exception_evidence
--     -- none exists. core/exceptions.py's relink_reopened_exceptions() (the actual reopen
--     function) only UPDATEs parcel_exception; retire_stranded_exceptions()'s own docstring
--     (core/exceptions.py:316) independently confirms exception_evidence is untouched on
--     that path too. A no-update trigger here is purely additive, needs no backfill, and
--     closes exactly the risk P63A §12 item 1 named ("was this evidence later silently
--     altered") -- included below.
--   no-delete: db/tests/teardown.sql:99 runs `DELETE FROM exception_evidence` with no
--     bypass mechanism anywhere in that file (no session_replication_role, no DISABLE
--     TRIGGER -- confirmed by direct grep). A no-delete trigger would turn `make db-test`
--     red; the fix is a carve-out or a teardown restructure, both design work this
--     package's own scope forbids. NOT added here -- deferred post-MVP, recorded in
--     P63B-LEDGER.md so a later package does not have to re-derive this.
--
-- WHAT THIS MIGRATION DOES NOT TOUCH. No fact row is read, written, or superseded --
-- fact carries no steward text and this migration's WHERE clauses never reference it.
-- No historical row anywhere is treated as wrong; source rows are corrected in place
-- because source carries no immutability trigger and never has. No licence_channel row
-- is inserted, changed, or removed (D1's insertion practice is a written record, in
-- db/README.md, not a data change -- see that file's own new entry). No enforcement
-- machinery is added for D5's four-tier convention (prompts/CONVENTIONS.md gains two
-- paragraphs of prose, nothing that runs).

-- D2: source steward classification.

CREATE TYPE public.steward_class AS ENUM ('governmental', 'private', 'unknown');

ALTER TABLE public.source ADD COLUMN steward_class public.steward_class;

-- Normalization: one canonical spelling for the one real government body currently
-- represented under two spellings. No-op on a fresh (empty) database.
UPDATE public.source SET steward = 'City of San José' WHERE steward = 'City of San Jose';

-- Backfill, by exact steward text, derived from the live data above. No-op on a fresh
-- (empty) database -- both UPDATEs match zero rows there, exactly like source's other
-- data-correction migrations (0016, 0023, 0026) already do.
UPDATE public.source SET steward_class = 'governmental' WHERE steward = 'City of San José';
UPDATE public.source SET steward_class = 'unknown' WHERE steward IN ('Test', 'P40 internal test');

-- Fails loudly (NOT NULL violation) if any row -- present now or added between this
-- migration being written and applied -- was not covered by the two UPDATEs above,
-- rather than silently leaving it unclassified.
ALTER TABLE public.source ALTER COLUMN steward_class SET NOT NULL;

-- D3 (approved half only): exception_evidence gains no-update protection. No-delete is
-- deferred post-MVP -- see this migration's header and P63B-LEDGER.md.

CREATE OR REPLACE FUNCTION public.exception_evidence_no_update() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'public', 'pg_temp'
    AS $$
BEGIN
    RAISE EXCEPTION
        'D3 violated: exception_evidence row (exception_id=%, fact_id=%) is immutable once '
        'written -- it is the retained evidence behind an exception, and evidence that can '
        'be silently altered after the fact is not evidence. Deletion (not blocked by this '
        'migration -- see 0060''s own header for why) remains the only way to remove one.',
        OLD.exception_id, OLD.fact_id;
END;
$$;

CREATE TRIGGER exception_evidence_no_update BEFORE UPDATE ON public.exception_evidence
    FOR EACH ROW EXECUTE FUNCTION public.exception_evidence_no_update();
