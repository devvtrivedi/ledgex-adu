-- db/tests/teardown.sql
-- Standalone class-3 (and, now, zero-fact-orphan) teardown for
-- db/tests/invariants.sql's fixtures (P17, finding #26). Split out of
-- invariants.sql itself so `make db-test` can run it UNCONDITIONALLY,
-- after the suite, even when ON_ERROR_STOP aborts the suite before ever
-- reaching invariants.sql's own former inline teardown block -- see
-- prompts/P17-invariant-suite-hygiene.md for the full argument. A failing
-- run is exactly the run someone re-runs immediately (finding #26's own
-- point), so a teardown that only ever ran on the passing path was
-- guaranteed to accumulate fastest on the runs most likely to repeat.
--
-- SCOPE: durable namespace, not test_state's session-local v_parcel_id --
-- this script is a SEPARATE psql invocation from the suite and has no
-- access to that table's contents (dropped with the suite's own session,
-- pass or fail). Every one of this file's 7 parcel-creating INSERTs
-- (confirmed directly: grep 'INSERT INTO parcel\b' across invariants.sql,
-- not sampled) uses a 'test-'/'TEST-' prefixed apn -- 6 of the 7
-- uppercase ('TEST-', 'TEST-T4-', 'TEST-T5-', 'TEST-DUP-'), one (T68,
-- 'test-t68-' || uuid) lowercase, inconsistent with the rest and not
-- assumed away: matched with apn ILIKE 'test-%', case-insensitive,
-- specifically because that inconsistency is real, not a typo in this
-- file's own comment. Every job_run uses job_key LIKE 'test.%' (that
-- namespace IS consistently cased, confirmed the same way), same as
-- invariants.sql's own former teardown already established. This is
-- STRICTLY BROADER than v_parcel_id scoping -- it also reaches residue
-- any PREVIOUS run left behind, including a run that aborted before its
-- own teardown step (this file) ever got invoked -- which is the entire
-- reason this file exists as its own separate step rather than staying
-- inline.
--
-- Broader scope changes what "safe" requires, and this is the design
-- point worth stating explicitly rather than discovering it live. Class-3
-- tables (parcel_exception, property_file, property_file_fact, job_run,
-- exception_evidence, source_feature_identity) were always safe to delete
-- regardless of whether their associated parcel had a fact against it --
-- no trigger has ever blocked any of them, confirmed directly in P14's
-- own investigation -- so scoping those broadly by TEST-%/test.% needs no
-- new safety argument.
--
-- `parcel` itself is different, and NEW here: invariants.sql's own inline
-- teardown never attempted it, because every v_parcel_id it ever saw
-- already had a fact against it by construction (that run's own tests
-- wrote one). This file can see OTHER runs' parcels too, including a
-- genuinely fact-free one -- e.g. a run that created its fixture parcel
-- and then failed before any test got as far as writing a fact against
-- it. A fact-free TEST-% parcel is not class 2 -- I4/0017 has nothing to
-- say about a parcel no fact has ever cited -- and P14's own
-- investigation already confirmed directly that such a parcel deletes
-- cleanly. But this file does NOT rely on that -- it does not attempt the
-- delete and catch the FK error if one exists. Every parcel-level DELETE
-- below is filtered by an explicit
-- NOT EXISTS (SELECT 1 FROM fact WHERE fact.parcel_id = parcel.id)
-- clause, checked BEFORE the delete runs, not discovered by the FK
-- rejecting it. A single multi-row DELETE that hits even one FK-locked
-- row fails ENTIRELY (not partially) and returns nonzero -- an error
-- here would abort this script under ON_ERROR_STOP, and an aborted
-- teardown that the wrapper does not distinguish from "teardown ran
-- clean" is the same silently-masks-the-real-signal shape finding #26 is
-- about, just relocated into teardown instead of into db-test itself.
-- Explicit exclusion, not error recovery, is what keeps that from ever
-- being possible in the first place.
--
-- fact is NEVER a target here, on any path -- 0017/I4, unconditionally,
-- same as invariants.sql's own former teardown block already stated.
--
-- DELETION ORDER, same FK graph invariants.sql's own former teardown
-- already worked out (db/migrations/*.sql), broadened to the namespace
-- scope instead of one parcel_id:
--   exception_evidence.exception_id  REFERENCES parcel_exception(id) ON DELETE CASCADE (0010)
--   property_file_fact.property_file_id REFERENCES property_file(id) ON DELETE CASCADE (0012)
--   parcel_exception.reopened_from_id REFERENCES parcel_exception(id), no cascade,
--     self-referential (0047) -- reopened_from_id always points at a row sharing the
--     SAME parcel_id (it is part of the match key relink_reopened_exceptions() uses),
--     so nulling it across every TEST-% parcel in one UPDATE before any DELETE below
--     breaks every chain regardless of length or which parcel it lives on.
--   job_run has no incoming FK from anything in this file -- no ordering constraint.
--   source_feature_identity has no incoming FK from anything in this file either.
--   parcel is deleted LAST, after every class-3 row that could reference it -- and
--     only the rows this script's own NOT EXISTS filter admits.

\set ON_ERROR_STOP on

DO $$
DECLARE
    v_deleted int;
BEGIN
    DELETE FROM exception_evidence
     WHERE parcel_id IN (SELECT id FROM parcel WHERE apn ILIKE 'test-%');
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RAISE NOTICE 'teardown: exception_evidence % row(s)', v_deleted;

    DELETE FROM property_file_fact
     WHERE parcel_id IN (SELECT id FROM parcel WHERE apn ILIKE 'test-%');
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RAISE NOTICE 'teardown: property_file_fact % row(s)', v_deleted;

    UPDATE parcel_exception
       SET reopened_from_id = NULL
     WHERE parcel_id IN (SELECT id FROM parcel WHERE apn ILIKE 'test-%')
       AND reopened_from_id IS NOT NULL;

    DELETE FROM parcel_exception
     WHERE parcel_id IN (SELECT id FROM parcel WHERE apn ILIKE 'test-%');
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RAISE NOTICE 'teardown: parcel_exception % row(s)', v_deleted;

    DELETE FROM property_file
     WHERE parcel_id IN (SELECT id FROM parcel WHERE apn ILIKE 'test-%');
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RAISE NOTICE 'teardown: property_file % row(s)', v_deleted;

    DELETE FROM source_feature_identity
     WHERE parcel_id IN (SELECT id FROM parcel WHERE apn ILIKE 'test-%');
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RAISE NOTICE 'teardown: source_feature_identity % row(s)', v_deleted;

    DELETE FROM job_run WHERE job_key LIKE 'test.%';
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RAISE NOTICE 'teardown: job_run % row(s)', v_deleted;

    -- parcel: ONLY rows with zero facts against them, explicitly filtered
    -- above the delete, never discovered via the FK's own error. Every
    -- class-2 (fact-bearing) TEST-% parcel, from this run or any other,
    -- is excluded by construction and left exactly as it was.
    DELETE FROM parcel
     WHERE apn ILIKE 'test-%'
       AND NOT EXISTS (SELECT 1 FROM fact WHERE fact.parcel_id = parcel.id);
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RAISE NOTICE 'teardown: parcel (zero-fact only) % row(s)', v_deleted;

    RAISE NOTICE 'Namespace-scoped teardown complete -- every TEST-%%/test.%% class-3 row and every zero-fact TEST-%% parcel removed, across every run''s residue this database carries. Every fact-bearing (class-2) parcel and its facts are untouched -- permanent by design (0017/I4).';
END $$;
