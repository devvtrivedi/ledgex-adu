-- Invariant tests for I2, I3, I4, I5, I13, I18, the parcel_exception
-- outcome/resolution biconditional (0015), and the seeded San José source
-- access methods (0016).
-- Run with: psql -v ON_ERROR_STOP=1 -f db/tests/invariants.sql DATABASE_URL
-- (or `make db-test`)
--
-- Every test is a self-asserting DO block. A should-fail test catches the
-- ONE specific expected condition (SQLSTATE condition name, and for custom
-- RAISE EXCEPTION messages that share SQLSTATE P0001/raise_exception, the
-- exact message text) and only then prints PASS. Any other outcome -- the
-- wrong error, no error, or an unexpected error on a should-succeed test --
-- raises an uncaught 'FAIL ...' exception. Combined with ON_ERROR_STOP, that
-- aborts the script and returns a nonzero exit code, so a misleading
-- "test complete" line can never print for a test that didn't actually pass.
--
-- Isolation: reference rows (licence, jurisdiction, source, snapshot,
-- field_definition) are seeded with ON CONFLICT DO NOTHING, so this file is
-- safe to run against a database with leftovers from a previous run. A
-- brand-new parcel (fresh uuid PK, fresh apn) is created at the top of every
-- run and every fact is scoped to it. Every test also gets its own
-- field_key (test.i3_field, test.i4a_field, ...) or, for rule/parcel_exception
-- rows that have no field_key, a fresh uuid-suffixed id/rule_key. No test
-- ever references a row it did not create in that same run.

\set ON_ERROR_STOP on

-- ============================================================================
-- SEED DATA: idempotent reference rows + a fresh parcel for this run
-- ============================================================================

BEGIN;

-- Namespaced ids ('test.cc0' / 'test.cc_by_4_0'), NOT the real 'cc0' /
-- 'cc_by_4_0' licence rows. licence.cleared_by is rights provenance I6
-- consults at compose time; a test file seeding the real licence ids with
-- cleared_by='test' would leave production-shaped rows with fabricated
-- provenance sitting in the database, and ON CONFLICT DO NOTHING means a
-- later, real seed of those same ids would silently decline to correct
-- them. restriction stays 'open'/'attribution' -- the severity ordering
-- I5a/I5b/I5c depend on is about the restriction value, not the id.
INSERT INTO licence (
  id, display_name, restriction, commercial_use, redistribution,
  attribution_text, observed_at, cleared_by, cleared_at
) VALUES
  ('test.cc0', 'Test fixture (CC0-equivalent, open)', 'open', 'allowed', 'allowed', NULL, now(), 'test', now()),
  ('test.cc_by_4_0', 'Test fixture (CC BY 4.0-equivalent, attribution)', 'attribution', 'allowed', 'allowed',
   'Test fixture attribution text', now(), 'test', now())
ON CONFLICT (id) DO NOTHING;

-- tier omitted -- defaults to 'blocked' (0002's own column default). No test
-- here reads jurisdiction.tier, and this row shares its id with
-- db/seeds/day4_sources.sql's jurisdiction row: both use ON CONFLICT (id) DO
-- NOTHING, so whichever seed runs first against a shared database silently
-- wins the value. Explicitly stamping 'tier_1' here would risk defeating
-- day4_sources.sql's own fix (tier is unassessable with zero facts in the
-- database) depending on run order. Letting both agree on the column
-- default removes that risk instead of relying on run order to hide it.
INSERT INTO jurisdiction (
  id, display_name, kind, state_code, pack_version, supported
) VALUES
  ('ca_san_jose', 'City of San José', 'city', 'CA', 'v1.0', true)
ON CONFLICT (id) DO NOTHING;

-- active = false, no url_verified_at: nothing in this suite needs the
-- source live, and a test file has no business creating verified-and-active
-- source records (source_active_requires_verification exists precisely to
-- keep an unchecked source off).
INSERT INTO source (
  id, jurisdiction_id, display_name, steward, method, phase_status,
  phase_status_reason, endpoint_url, licence_id, active
) VALUES
  ('ca_san_jose.test_source', 'ca_san_jose', 'Test Source', 'City of San José',
   'direct', 'active', 'Test source for invariant testing',
   'https://example.com/api', 'test.cc0', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO snapshot (
  id, source_id, object_uri, content_hash, media_type, byte_size,
  request, http_status, fetched_at, licence_observed_id
) VALUES
  ('ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', 'ca_san_jose.test_source', 's3://bucket/test',
   '65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', 'application/json', 100,
   '{"url":"https://example.com","params":{}}'::jsonb,
   200, now(), 'test.cc0')
ON CONFLICT (id) DO NOTHING;

-- Third snapshot, same source, licence_observed_id='test.cc_by_4_0' (0022's
-- fact_snapshot_licence_fk now requires a retrieved fact's licence_id to
-- equal exactly the snapshot it cites -- I5a/I5b need a retrieved input
-- fact under cc_by_4_0, which the cc0 snapshot above can no longer stand
-- in for).
INSERT INTO snapshot (
  id, source_id, object_uri, content_hash, media_type, byte_size,
  request, http_status, fetched_at, licence_observed_id
) VALUES
  ('ca_san_jose.test_source:sha256:6807ac29ca72075c1cc37bbdb1ed367c967981c0c74c969d045ab5e5664f7774', 'ca_san_jose.test_source', 's3://bucket/test-cc-by',
   '6807ac29ca72075c1cc37bbdb1ed367c967981c0c74c969d045ab5e5664f7774', 'application/json', 100,
   '{"url":"https://example.com","params":{}}'::jsonb,
   200, now(), 'test.cc_by_4_0')
ON CONFLICT (id) DO NOTHING;

-- Second source + snapshot, method='bulk' (deliberately different from
-- test_source's 'direct'): T2 needs a snapshot that belongs to a
-- DIFFERENT source than the one a fact claims (0018's
-- fact_snapshot_source_fk), and T3 needs a second source with a different
-- declared method to prove fact_source_method_fk (0018's other composite
-- FK) actually discriminates on method, not just on source identity.
INSERT INTO source (
  id, jurisdiction_id, display_name, steward, method, phase_status,
  phase_status_reason, endpoint_url, licence_id, active
) VALUES
  ('ca_san_jose.test_source_b', 'ca_san_jose', 'Test Source B', 'City of San José',
   'bulk', 'active', 'Second test source for provenance-integrity tests',
   'https://example.com/api-b', 'test.cc0', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO snapshot (
  id, source_id, object_uri, content_hash, media_type, byte_size,
  request, http_status, fetched_at, licence_observed_id
) VALUES
  ('ca_san_jose.test_source_b:sha256:2892e288adb59f59419b9351ed48cbb14e45d0556547da33f3543e5e85b71c8d', 'ca_san_jose.test_source_b', 's3://bucket/test-b',
   '2892e288adb59f59419b9351ed48cbb14e45d0556547da33f3543e5e85b71c8d', 'application/json', 100,
   '{"url":"https://example.com/b","params":{}}'::jsonb,
   200, now(), 'test.cc0')
ON CONFLICT (id) DO NOTHING;

-- Throwaway snapshot, own row, cited by nothing: T18/T19 need to
-- UPDATE/DELETE a snapshot without also tripping fact_snapshot_source_fk
-- or fact_snapshot_licence_fk on some other fact that cites it -- mirrors
-- T1's dedicated fresh fact for the same isolation reason.
INSERT INTO snapshot (
  id, source_id, object_uri, content_hash, media_type, byte_size,
  request, http_status, fetched_at, licence_observed_id
) VALUES
  ('ca_san_jose.test_source:sha256:5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37', 'ca_san_jose.test_source', 's3://bucket/test-throwaway',
   '5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37', 'application/json', 100,
   '{"url":"https://example.com/throwaway","params":{}}'::jsonb,
   200, now(), 'test.cc0')
ON CONFLICT (id) DO NOTHING;

-- A second jurisdiction, plus a source and snapshot registered under it:
-- 0022's fact_source_jurisdiction_fk, property_file_parcel_jurisdiction_fk
-- and parcel_exception_parcel_jurisdiction_fk all need a genuinely
-- different jurisdiction to disagree with, not just a different id string
-- that happens to share ca_san_jose's own jurisdiction_id.
INSERT INTO jurisdiction (
  id, display_name, kind, state_code, pack_version, supported
) VALUES
  ('test_other_jurisdiction', 'Test Other Jurisdiction', 'city', 'CA', 'v1.0', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO source (
  id, jurisdiction_id, display_name, steward, method, phase_status,
  phase_status_reason, endpoint_url, licence_id, active
) VALUES
  ('test_other_jurisdiction.test_source', 'test_other_jurisdiction', 'Test Source (Other Jurisdiction)',
   'Test Steward', 'direct', 'active', 'Test source under a different jurisdiction, for jurisdiction-consistency tests',
   'https://example.com/api-other', 'test.cc0', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO snapshot (
  id, source_id, object_uri, content_hash, media_type, byte_size,
  request, http_status, fetched_at, licence_observed_id
) VALUES
  ('test_other_jurisdiction.test_source:sha256:ea9ca0e4800afb999739746f473257ee491bc425f267ef6046b4a016d234184a', 'test_other_jurisdiction.test_source', 's3://bucket/test-other',
   'ea9ca0e4800afb999739746f473257ee491bc425f267ef6046b4a016d234184a', 'application/json', 100,
   '{"url":"https://example.com/other","params":{}}'::jsonb,
   200, now(), 'test.cc0')
ON CONFLICT (id) DO NOTHING;

-- One field_key per test group -- see header note on isolation.
INSERT INTO field_definition (
  field_key, display_name, claim, value_type, category, description
) VALUES
  ('test.i3_field',  'Test Field I3',  'public_record', 'string', 'test', 'I3 invariant test field'),
  ('test.i2a_field', 'Test Field I2a', 'public_record', 'string', 'test', 'I2a invariant test field'),
  ('test.i2b_field', 'Test Field I2b', 'public_record', 'string', 'test', 'I2b invariant test field'),
  ('test.i13_field', 'Test Field I13', 'public_record', 'string', 'test', 'I13 invariant test field'),
  ('test.i4a_field', 'Test Field I4a', 'public_record', 'string', 'test', 'I4a/I4b/I4c invariant test field'),
  ('test.i5a_field', 'Test Field I5a', 'public_record', 'string', 'test', 'I5a invariant test field'),
  ('test.i5b_field', 'Test Field I5b', 'public_record', 'string', 'test', 'I5b invariant test field'),
  ('test.i5c_field', 'Test Field I5c', 'public_record', 'string', 'test', 'I5c invariant test field'),
  ('test.t1_field',  'Test Field T1',  'public_record', 'string', 'test', 'T1 invariant test field'),
  ('test.t2_field',  'Test Field T2',  'public_record', 'string', 'test', 'T2 invariant test field'),
  ('test.t3_field',  'Test Field T3',  'public_record', 'string', 'test', 'T3 invariant test field'),
  ('test.t4_field',  'Test Field T4',  'public_record', 'string', 'test', 'T4 invariant test field'),
  ('test.t5_field',  'Test Field T5',  'public_record', 'string', 'test', 'T5 invariant test field'),
  ('test.t6_field',  'Test Field T6',  'public_record', 'string', 'test', 'T6 invariant test field (future effective_from)'),
  ('test.t6b_field', 'Test Field T6b', 'public_record', 'string', 'test', 'T6 invariant test field (present effective_from, control)'),
  ('test.t17_field', 'Test Field T17', 'public_record', 'string', 'test', 'T17 invariant test field'),
  ('test.t24_field', 'Test Field T24', 'public_record', 'string', 'test', 'T24 invariant test field'),
  ('test.t25_field', 'Test Field T25', 'public_record', 'string', 'test', 'T25 invariant test field'),
  ('test.t27_field', 'Test Field T27', 'public_record', 'string', 'test', 'T27 invariant test field'),
  ('test.t28_field', 'Test Field T28', 'public_record', 'string', 'test', 'T28 invariant test field'),
  ('test.t32_field', 'Test Field T32', 'public_record', 'string', 'test', 'T32 invariant test field'),
  ('test.t33_field', 'Test Field T33', 'public_record', 'string', 'test', 'T33 invariant test field'),
  ('test.t34_field', 'Test Field T34', 'public_record', 'string', 'test', 'T34 invariant test field'),
  ('test.t35_field', 'Test Field T35', 'public_record', 'string', 'test', 'T35 invariant test field'),
  ('test.t36_field', 'Test Field T36', 'public_record', 'string', 'test', 'T36 invariant test field'),
  ('test.t37_field', 'Test Field T37', 'public_record', 'string', 'test', 'T37 invariant test field'),
  ('test.t38_field', 'Test Field T38', 'public_record', 'string', 'test', 'T38 invariant test field'),
  ('test.t39_field', 'Test Field T39', 'public_record', 'string', 'test', 'T39 invariant test field'),
  ('test.t40_field', 'Test Field T40', 'public_record', 'string', 'test', 'T40 invariant test field'),
  ('test.t44_field', 'Test Field T44', 'public_record', 'string', 'test', 'T44 invariant test field'),
  ('test.t45_field', 'Test Field T45', 'public_record', 'string', 'test', 'T45 invariant test field')
ON CONFLICT (field_key) DO NOTHING;

-- Cross-block scratch state for this run: the fresh parcel id, and (later)
-- the I4/I18 row ids shared across their multi-block lifecycles.
CREATE TEMP TABLE test_state (key text PRIMARY KEY, value text);

-- Every test inserts its own name here on the PASS path only (never on the
-- FAIL path, and never unconditionally) -- the summary's count comes from
-- this table, not a literal, so it can't drift from what the file actually
-- contains the way a hand-maintained "N/N" string could.
CREATE TEMP TABLE test_pass (name text PRIMARY KEY);

-- Separate from test_pass: a test that documents an UNENFORCED invariant
-- (I5c) is not the same claim as a test that documents an enforced one.
-- Counting I5c into test_pass and the floor would let "coverage" include a
-- known gap -- inflating the number with a test that, by design, can never
-- go red no matter what the schema does. known_gaps is reported separately
-- in the summary and never contributes to the floor.
CREATE TEMP TABLE known_gaps (name text PRIMARY KEY, note text);

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    -- Fresh uuid PK + fresh apn: this row can never collide with a parcel
    -- left behind by a previous run.
    INSERT INTO parcel (jurisdiction_id, apn, situs_address)
    VALUES ('ca_san_jose', 'TEST-' || gen_random_uuid()::text,
            '123 Test St, San Jose, CA 95110')
    RETURNING id INTO v_parcel_id;

    INSERT INTO test_state VALUES ('parcel_id', v_parcel_id::text);

    RAISE NOTICE 'Seeded. This run''s parcel_id: %', v_parcel_id;
END $$;

COMMIT;

-- ============================================================================
-- TEST I3: Fact must have non-null licence_id
-- ============================================================================

\echo '### TEST I3: fact.licence_id is NOT NULL'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'test.i3_field', '"value"'::jsonb, 'direct',
            'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
            NULL, 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL I3: null licence_id was accepted';
    EXCEPTION
        WHEN not_null_violation THEN
            RAISE NOTICE 'PASS I3: null licence_id rejected (not_null_violation)';
            INSERT INTO test_pass VALUES ('I3');
    END;
END $$;

-- ============================================================================
-- TEST I2a: Derived fact cannot have source_id
-- ============================================================================

\echo '### TEST I2a: derived fact with source_id (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            method_version, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'test.i2a_field', '"derived_value"'::jsonb, 'derived',
            'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',  -- both set: violates I2
            'v1.0', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL I2a: derived fact with source_id and snapshot_id set was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_provenance_complete' THEN
                RAISE NOTICE 'PASS I2a: rejected by fact_provenance_complete';
                INSERT INTO test_pass VALUES ('I2a');
            ELSE
                RAISE EXCEPTION 'FAIL I2a: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST I2b: Direct fact must have snapshot_id
-- ============================================================================

\echo '### TEST I2b: direct fact without snapshot_id (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'test.i2b_field', '"value"'::jsonb, 'direct',
            'ca_san_jose.test_source', NULL,  -- missing snapshot_id
            now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL I2b: direct fact with no snapshot_id was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_provenance_complete' THEN
                RAISE NOTICE 'PASS I2b: rejected by fact_provenance_complete';
                INSERT INTO test_pass VALUES ('I2b');
            ELSE
                RAISE EXCEPTION 'FAIL I2b: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST I13: Fact method must be automated (not portal, manual, etc)
-- ============================================================================

\echo '### TEST I13: fact.method must be direct, bulk, or derived'

DO $$
DECLARE
    v_parcel_id uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'test.i13_field', '"value"'::jsonb, 'portal',  -- invalid
            'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
            'test.cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL I13: method=portal was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_method_automated' THEN
                RAISE NOTICE 'PASS I13: rejected by fact_method_automated';
                INSERT INTO test_pass VALUES ('I13');
            ELSE
                RAISE EXCEPTION 'FAIL I13: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST I4a: Fact is immutable (cannot UPDATE value)
-- 0007_fact_triggers.sql fact_no_destructive_update(), the
-- "NEW.superseded_at IS NULL" branch (line 10 of the function body,
-- counting CREATE OR REPLACE FUNCTION as line 1).
-- ============================================================================

\echo '### TEST I4a: fact immutability - cannot change value'

DO $$
DECLARE
    v_parcel_id uuid;
    v_fact_id   uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.i4a_field', '"original_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    -- I4b and I4c reuse this exact fact -- they're stages of the same
    -- fact's lifecycle, not independent facts.
    INSERT INTO test_state VALUES ('i4_fact_id', v_fact_id::text)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

    BEGIN
        UPDATE fact SET value = '"changed_value"'::jsonb WHERE id = v_fact_id;
        RAISE EXCEPTION 'FAIL I4a: value change on a non-superseded fact was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I4 violated:%cannot be updated%' THEN
                RAISE NOTICE 'PASS I4a: value change rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('I4a');
            ELSE
                RAISE EXCEPTION 'FAIL I4a: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST I4b: Fact CAN be superseded (set only superseded_at)
-- ============================================================================

\echo '### TEST I4b: fact can be superseded (set superseded_at only)'

DO $$
DECLARE
    v_fact_id uuid;
    v_rows    int;
BEGIN
    SELECT value::uuid INTO v_fact_id FROM test_state WHERE key = 'i4_fact_id';

    -- Target the exact fact I4a created, by id -- not by re-filtering on
    -- superseded_at, which would silently match zero (or the wrong) rows if
    -- the database already had other current facts lying around.
    UPDATE fact SET superseded_at = now()
     WHERE id = v_fact_id AND superseded_at IS NULL;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF v_rows = 1 THEN
        RAISE NOTICE 'PASS I4b: fact % superseded (1 row updated)', v_fact_id;
        INSERT INTO test_pass VALUES ('I4b');
    ELSE
        RAISE EXCEPTION 'FAIL I4b: expected 1 row updated, got %', v_rows;
    END IF;
END $$;

-- ============================================================================
-- TEST I4c: Cannot update an already-superseded fact
-- fact_no_destructive_update(), the "OLD.superseded_at IS NOT NULL" branch
-- (line 4 of the function body).
-- ============================================================================

\echo '### TEST I4c: an already-superseded fact cannot be changed'

DO $$
DECLARE
    v_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_fact_id FROM test_state WHERE key = 'i4_fact_id';

    BEGIN
        UPDATE fact SET value = '"another_change"'::jsonb WHERE id = v_fact_id;
        RAISE EXCEPTION 'FAIL I4c: update on an already-superseded fact was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I4 violated:%already superseded%' THEN
                RAISE NOTICE 'PASS I4c: update on superseded fact rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('I4c');
            ELSE
                RAISE EXCEPTION 'FAIL I4c: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST I5a: Derived fact cannot have weaker licence than its inputs
-- ============================================================================

\echo '### TEST I5a: derived fact more permissive than its input (should fail)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_input_fact_id   uuid;
    v_derived_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    -- Input: retrieved, cc_by_4_0 (more restrictive).
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.i5a_field', '"input_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:6807ac29ca72075c1cc37bbdb1ed367c967981c0c74c969d045ab5e5664f7774', now(), 'https://example.com',
        'test.cc_by_4_0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    -- Derived: test.cc0, more permissive than its input -- must be rejected.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.i5a_field', '"derived"'::jsonb, 'derived',
        'v1.0', 'test.cc0',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    BEGIN
        INSERT INTO fact_input (fact_id, input_fact_id, ordinal, role)
        VALUES (v_derived_fact_id, v_input_fact_id, 1, 'test_input');

        -- fact_licence_inheritance is DEFERRABLE INITIALLY DEFERRED: it
        -- normally fires at COMMIT. A DO block can't COMMIT internally, so
        -- force the pending check to run now, where this block can catch it.
        SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

        RAISE EXCEPTION 'FAIL I5a: derived fact more permissive than its input was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I5 violated:%' THEN
                RAISE NOTICE 'PASS I5a: over-permissive derived fact rejected at COMMIT (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('I5a');
            ELSE
                RAISE EXCEPTION 'FAIL I5a: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST I5b: Derived fact CAN have stricter licence than inputs
-- ============================================================================

\echo '### TEST I5b: derived fact stricter than its input (should succeed)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_input_fact_id   uuid;
    v_derived_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    -- Input: retrieved, cc0 (permissive).
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.i5b_field', '"input_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    -- Derived: test.cc_by_4_0, stricter than its input -- must be allowed.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.i5b_field', '"derived_stricter"'::jsonb, 'derived',
        'v1.0', 'test.cc_by_4_0',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    INSERT INTO fact_input (fact_id, input_fact_id, ordinal, role)
    VALUES (v_derived_fact_id, v_input_fact_id, 1, 'test_input');

    -- No inner catch: if this unexpectedly raises, that's a real schema
    -- finding and should surface with its original, unwrapped error text.
    SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

    RAISE NOTICE 'PASS I5b: stricter derived fact % accepted', v_derived_fact_id;
    INSERT INTO test_pass VALUES ('I5b');
END $$;

-- ============================================================================
-- TEST I5c: Derived fact with NO fact_input rows is not checked (known gap)
-- ============================================================================

\echo '### TEST I5c: derived fact with zero inputs is unchecked (known gap, not a bug)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_derived_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    -- No input fact and no fact_input row: fact_licence_validate's
    -- required_licence lookup returns NULL, and per 0007_fact_triggers.sql
    -- ("no inputs recorded yet") the trigger returns without checking
    -- anything. A derived fact with ANY licence therefore commits unchecked.
    -- Per the hard rule for this suite, the trigger is not to be changed to
    -- close this gap -- this test only documents that it exists.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.i5c_field', '"ungrounded_derived"'::jsonb, 'derived',
        'v1.0', 'test.cc0',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

    RAISE NOTICE 'PASS (KNOWN GAP) I5c: derived fact % with zero fact_input rows committed unchecked -- I5 cannot validate a derivation that never declares its inputs', v_derived_fact_id;
    INSERT INTO known_gaps VALUES ('I5c', 'derived fact with zero fact_input rows commits unchecked -- I5 cannot validate a derivation that never declares its inputs');
END $$;

-- ============================================================================
-- TEST I18a: rule review evidence is immutable (reviewed_by)
-- 0013_rule_triggers.sql rule_no_destructive_update(), the generic
-- "rule % is immutable" branch (any locked column, not just effective_to).
-- ============================================================================

\echo '### TEST I18a: UPDATE rule SET reviewed_by (should fail)'

DO $$
DECLARE
    v_rule_id text := 'test-i18a-' || gen_random_uuid()::text;
BEGIN
    INSERT INTO rule (
        id, jurisdiction_id, rule_key, version, effective_from, citation,
        source_text_uri, params, pack_version, authored_by, reviewed_by,
        review_mode, reviewed_at
    ) VALUES (
        v_rule_id, 'ca_san_jose', 'test.i18a.rule.' || v_rule_id, 1, CURRENT_DATE,
        'Test citation', 'https://example.com/rule-source', '{}'::jsonb, 'v1.0',
        'author_a', 'reviewer_b', 'independent', now()
    );

    BEGIN
        UPDATE rule SET reviewed_by = 'someone_else' WHERE id = v_rule_id;
        RAISE EXCEPTION 'FAIL I18a: UPDATE reviewed_by was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I18 violated:%is immutable%' THEN
                RAISE NOTICE 'PASS I18a: reviewed_by change rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('I18a');
            ELSE
                RAISE EXCEPTION 'FAIL I18a: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST I18b: rule immutability covers ALL columns, not just review evidence
-- ============================================================================

\echo '### TEST I18b: UPDATE rule SET params (should fail -- proves every column is locked)'

DO $$
DECLARE
    v_rule_id text := 'test-i18b-' || gen_random_uuid()::text;
BEGIN
    INSERT INTO rule (
        id, jurisdiction_id, rule_key, version, effective_from, citation,
        source_text_uri, params, pack_version, authored_by, reviewed_by,
        review_mode, reviewed_at
    ) VALUES (
        v_rule_id, 'ca_san_jose', 'test.i18b.rule.' || v_rule_id, 1, CURRENT_DATE,
        'Test citation', 'https://example.com/rule-source', '{"threshold": 1}'::jsonb, 'v1.0',
        'author_a', 'reviewer_b', 'independent', now()
    );

    BEGIN
        UPDATE rule SET params = '{"threshold": 2}'::jsonb WHERE id = v_rule_id;
        RAISE EXCEPTION 'FAIL I18b: UPDATE params was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I18 violated:%is immutable%' THEN
                RAISE NOTICE 'PASS I18b: params change rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('I18b');
            ELSE
                RAISE EXCEPTION 'FAIL I18b: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST I18c: rule row cannot be deleted (retirement is effective_to, not removal)
-- ============================================================================

\echo '### TEST I18c: DELETE FROM rule (should fail)'

DO $$
DECLARE
    v_rule_id text := 'test-i18c-' || gen_random_uuid()::text;
BEGIN
    INSERT INTO rule (
        id, jurisdiction_id, rule_key, version, effective_from, citation,
        source_text_uri, params, pack_version, authored_by, reviewed_by,
        review_mode, reviewed_at
    ) VALUES (
        v_rule_id, 'ca_san_jose', 'test.i18c.rule.' || v_rule_id, 1, CURRENT_DATE,
        'Test citation', 'https://example.com/rule-source', '{}'::jsonb, 'v1.0',
        'author_a', 'reviewer_b', 'independent', now()
    );

    BEGIN
        DELETE FROM rule WHERE id = v_rule_id;
        RAISE EXCEPTION 'FAIL I18c: DELETE FROM rule was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I18 violated:%cannot be deleted%' THEN
                RAISE NOTICE 'PASS I18c: delete rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('I18c');
            ELSE
                RAISE EXCEPTION 'FAIL I18c: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST I18d: rule retirement (effective_to: NULL -> a date) SUCCEEDS
-- ============================================================================

\echo '### TEST I18d: UPDATE rule SET effective_to (NULL -> date) should succeed'

DO $$
DECLARE
    v_rule_id text := 'test-i18d-' || gen_random_uuid()::text;
BEGIN
    INSERT INTO rule (
        id, jurisdiction_id, rule_key, version, effective_from, citation,
        source_text_uri, params, pack_version, authored_by, reviewed_by,
        review_mode, reviewed_at
    ) VALUES (
        v_rule_id, 'ca_san_jose', 'test.i18d.rule.' || v_rule_id, 1, CURRENT_DATE,
        'Test citation', 'https://example.com/rule-source', '{}'::jsonb, 'v1.0',
        'author_a', 'reviewer_b', 'independent', now()
    );

    -- I18e reuses this exact row to prove the transition is one-way.
    INSERT INTO test_state VALUES ('i18_rule_id', v_rule_id)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

    UPDATE rule SET effective_to = CURRENT_DATE + 365 WHERE id = v_rule_id;

    RAISE NOTICE 'PASS I18d: rule % retired (effective_to NULL -> date accepted)', v_rule_id;
    INSERT INTO test_pass VALUES ('I18d');
END $$;

-- ============================================================================
-- TEST I18e: a SECOND effective_to change on the same rule is rejected (one-way)
-- ============================================================================

\echo '### TEST I18e: a second effective_to change on the same rule (should fail)'

DO $$
DECLARE
    v_rule_id text;
BEGIN
    SELECT value INTO v_rule_id FROM test_state WHERE key = 'i18_rule_id';

    BEGIN
        UPDATE rule SET effective_to = CURRENT_DATE + 400 WHERE id = v_rule_id;
        RAISE EXCEPTION 'FAIL I18e: second effective_to change was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I18 violated:%already set to%cannot be changed again%' THEN
                RAISE NOTICE 'PASS I18e: second effective_to change rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('I18e');
            ELSE
                RAISE EXCEPTION 'FAIL I18e: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST X1: parcel_exception outcome='open' cannot carry resolution fields
-- 0015_exception_outcome_biconditional.sql
-- ============================================================================

\echo '### TEST X1: parcel_exception outcome=open WITH resolved_at set (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO parcel_exception (
            parcel_id, jurisdiction_id, type, severity, detector_key,
            detector_version, detail, outcome, resolved_at, resolved_by
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'staleness', 'warning', 'test_detector',
            'v1', '{}'::jsonb, 'open', now(), 'test_operator'
        );
        RAISE EXCEPTION 'FAIL X1: outcome=open with resolved_at/resolved_by set was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'parcel_exception_outcome_resolution_biconditional' THEN
                RAISE NOTICE 'PASS X1: open exception with resolution fields rejected';
                INSERT INTO test_pass VALUES ('X1');
            ELSE
                RAISE EXCEPTION 'FAIL X1: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST X2: a resolved outcome requires BOTH resolved_at and resolved_by
-- ============================================================================

\echo '### TEST X2: parcel_exception outcome=confirmed WITHOUT resolved_by (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO parcel_exception (
            parcel_id, jurisdiction_id, type, severity, detector_key,
            detector_version, detail, outcome, resolved_at, resolved_by
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'staleness', 'warning', 'test_detector',
            'v1', '{}'::jsonb, 'confirmed', now(), NULL
        );
        RAISE EXCEPTION 'FAIL X2: outcome=confirmed with resolved_by NULL was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'parcel_exception_outcome_resolution_biconditional' THEN
                RAISE NOTICE 'PASS X2: resolved outcome missing resolved_by rejected';
                INSERT INTO test_pass VALUES ('X2');
            ELSE
                RAISE EXCEPTION 'FAIL X2: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST X3: outcome='unresolved' WITH both resolution fields set SUCCEEDS
-- ============================================================================

\echo '### TEST X3: parcel_exception outcome=unresolved WITH both resolution fields set (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_exception_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO parcel_exception (
        parcel_id, jurisdiction_id, type, severity, detector_key,
        detector_version, detail, outcome, resolved_at, resolved_by
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'staleness', 'warning', 'test_detector',
        'v1', '{}'::jsonb, 'unresolved', now(), 'test_operator'
    ) RETURNING id INTO v_exception_id;

    RAISE NOTICE 'PASS X3: unresolved exception % with both resolution fields accepted', v_exception_id;
    INSERT INTO test_pass VALUES ('X3');
END $$;

-- ============================================================================
-- TEST S1: the three active San José sources are method='bulk' (0016)
-- ============================================================================
-- Deliberate exception to this file's isolation rule ("no test ever
-- references a row it did not create in that same run"). This one checks
-- three REAL seeded rows, because what it guards is exactly a seed-data
-- fact: db/seeds/day4_sources.sql originally registered parcels, zoning
-- districts and active building permits as method='direct' when all three
-- are whole-dataset downloads. The schema cannot enforce this -- 'direct'
-- and 'bulk' are both legal access_method values and both satisfy
-- source_active_requires_machine_access -- so nothing but a test catches a
-- regression here.
--
-- It creates nothing and modifies nothing; it only reads.
--
-- Absence is a skip, not a failure, and the skip is labelled as one. This
-- suite is normally run against a migrations-only database (`make schema`
-- then `make db-test`); there is no seed target, so on that path the three
-- rows do not exist and there is nothing to check. Asserting presence would
-- make `make db-test` fail on the standard workflow for a reason that has
-- nothing to do with correctness. The guard has teeth when the suite is run
-- against a seeded database -- which is where a regression could exist.
--
-- What is NOT tolerated in either case is a partial set: three rows all
-- present or three rows all absent are both coherent states, but one or two
-- present means the seed half-applied, and that is reported as a failure
-- rather than skipped past.

\echo '### TEST S1: ca_san_jose parcels/zoning/permits are method=bulk (0016)'

DO $$
DECLARE
    v_ids text[] := ARRAY[
        'ca_san_jose.parcels',
        'ca_san_jose.zoning_districts',
        'ca_san_jose.building_permits_active'
    ];
    v_present int;
    v_wrong   text;
BEGIN
    SELECT count(*) INTO v_present FROM source WHERE id = ANY(v_ids);

    IF v_present = 0 THEN
        RAISE NOTICE 'PASS S1 (skipped): none of the three seeded sources present -- db/seeds/day4_sources.sql has not been applied to this database, so there is nothing to regress';
        INSERT INTO test_pass VALUES ('S1');
        RETURN;
    END IF;

    IF v_present <> array_length(v_ids, 1) THEN
        RAISE EXCEPTION 'FAIL S1: % of % seeded sources present -- the seed half-applied; expected all three or none', v_present, array_length(v_ids, 1);
    END IF;

    SELECT string_agg(id || '=' || method::text, ', ' ORDER BY id) INTO v_wrong
      FROM source
     WHERE id = ANY(v_ids) AND method <> 'bulk';

    IF v_wrong IS NOT NULL THEN
        RAISE EXCEPTION 'FAIL S1: expected method=bulk for all three seeded San José sources, got %. Apply db/migrations/0016_source_access_method_corrections.sql -- the seed uses ON CONFLICT DO NOTHING and will not correct an already-seeded database', v_wrong;
    END IF;

    RAISE NOTICE 'PASS S1: all three seeded San José sources are method=bulk';
    INSERT INTO test_pass VALUES ('S1');
END $$;

-- ============================================================================
-- TEST T1: a fact cannot be deleted (0017)
-- fact_no_delete(), an unconditional raise mirroring rule_no_delete.
-- ============================================================================

\echo '### TEST T1: DELETE FROM fact (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_fact_id   uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t1_field', '"delete_me"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    BEGIN
        DELETE FROM fact WHERE id = v_fact_id;
        RAISE EXCEPTION 'FAIL T1: DELETE FROM fact was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I4 violated:%cannot be deleted%' THEN
                RAISE NOTICE 'PASS T1: fact delete rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T1');
            ELSE
                RAISE EXCEPTION 'FAIL T1: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T2: a fact cannot cite one source but another source's snapshot (0018a)
-- fact_snapshot_source_fk: FOREIGN KEY (snapshot_id, source_id) REFERENCES
-- snapshot (id, source_id).
-- ============================================================================

\echo '### TEST T2: fact citing source A with source B''s snapshot (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'test.t2_field', '"value"'::jsonb, 'direct',
            'ca_san_jose.test_source',      -- source A
            'ca_san_jose.test_source_b:sha256:2892e288adb59f59419b9351ed48cbb14e45d0556547da33f3543e5e85b71c8d',               -- source B's snapshot
            now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL T2: fact citing source A with source B''s snapshot was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_snapshot_source_fk' THEN
                RAISE NOTICE 'PASS T2: source/snapshot mismatch rejected by fact_snapshot_source_fk';
                INSERT INTO test_pass VALUES ('T2');
            ELSE
                RAISE EXCEPTION 'FAIL T2: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T3: a fact's method must match its source's declared method (0018b)
-- fact_source_method_fk: FOREIGN KEY (source_id, method) REFERENCES
-- source (id, method).
-- ============================================================================

\echo '### TEST T3: fact method mismatched with its source''s declared method (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        -- ca_san_jose.test_source declares method='direct'; this fact claims 'bulk'.
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'test.t3_field', '"value"'::jsonb, 'bulk',
            'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
            now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL T3: fact method mismatched with its source''s declared method was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_source_method_fk' THEN
                RAISE NOTICE 'PASS T3: method mismatch rejected by fact_source_method_fk';
                INSERT INTO test_pass VALUES ('T3');
            ELSE
                RAISE EXCEPTION 'FAIL T3: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T4: a Property File cannot cite another parcel's fact (0018c)
-- property_file_fact_fact_parcel_fk: FOREIGN KEY (fact_id, parcel_id)
-- REFERENCES fact (id, parcel_id).
-- ============================================================================

\echo '### TEST T4: property_file_fact linking a fact from a different parcel (should fail)'

DO $$
DECLARE
    v_parcel_id        uuid;
    v_other_parcel_id  uuid;
    v_property_file_id uuid;
    v_other_fact_id    uuid;
    v_constraint       text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    -- A second, different parcel -- scoped to this test only, never stored
    -- in test_state, so nothing else can accidentally pick it up.
    INSERT INTO parcel (jurisdiction_id, apn, situs_address)
    VALUES ('ca_san_jose', 'TEST-T4-' || gen_random_uuid()::text,
            '456 Other Parcel St, San Jose, CA 95110')
    RETURNING id INTO v_other_parcel_id;

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, payload,
        payload_hash, compose_ms
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
        'v1.0', 'v1.0', false, '{}'::jsonb, 'testhash_t4', 100
    ) RETURNING id INTO v_property_file_id;

    -- This fact belongs to the OTHER parcel, not the Property File's parcel.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_other_parcel_id, 'ca_san_jose', 'test.t4_field', '"other_parcel_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_other_fact_id;

    BEGIN
        -- parcel_id here matches the Property File's own parcel (satisfying
        -- property_file_fact_property_file_parcel_fk), isolating the failure
        -- to the fact/parcel mismatch specifically.
        INSERT INTO property_file_fact (property_file_id, fact_id, parcel_id)
        VALUES (v_property_file_id, v_other_fact_id, v_parcel_id);
        RAISE EXCEPTION 'FAIL T4: property_file_fact linking a different parcel''s fact was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_fact_fact_parcel_fk' THEN
                RAISE NOTICE 'PASS T4: cross-parcel fact link rejected by property_file_fact_fact_parcel_fk';
                INSERT INTO test_pass VALUES ('T4');
            ELSE
                RAISE EXCEPTION 'FAIL T4: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T5: a parcel_exception cannot cite another parcel's fact as evidence (0018c)
-- exception_evidence_fact_parcel_fk: FOREIGN KEY (fact_id, parcel_id)
-- REFERENCES fact (id, parcel_id).
-- ============================================================================

\echo '### TEST T5: exception_evidence linking a fact from a different parcel (should fail)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_other_parcel_id uuid;
    v_exception_id    uuid;
    v_other_fact_id   uuid;
    v_constraint      text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO parcel (jurisdiction_id, apn, situs_address)
    VALUES ('ca_san_jose', 'TEST-T5-' || gen_random_uuid()::text,
            '789 Other Parcel Ave, San Jose, CA 95110')
    RETURNING id INTO v_other_parcel_id;

    INSERT INTO parcel_exception (
        parcel_id, jurisdiction_id, type, severity, detector_key,
        detector_version, detail, outcome
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'staleness', 'warning', 'test_detector',
        'v1', '{}'::jsonb, 'open'
    ) RETURNING id INTO v_exception_id;

    -- This fact belongs to the OTHER parcel, not the exception's parcel.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_other_parcel_id, 'ca_san_jose', 'test.t5_field', '"other_parcel_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_other_fact_id;

    BEGIN
        INSERT INTO exception_evidence (exception_id, fact_id, role, parcel_id)
        VALUES (v_exception_id, v_other_fact_id, 'test_role', v_parcel_id);
        RAISE EXCEPTION 'FAIL T5: exception_evidence linking a different parcel''s fact was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'exception_evidence_fact_parcel_fk' THEN
                RAISE NOTICE 'PASS T5: cross-parcel fact link rejected by exception_evidence_fact_parcel_fk';
                INSERT INTO test_pass VALUES ('T5');
            ELSE
                RAISE EXCEPTION 'FAIL T5: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T6: current_fact excludes a fact whose effective_from is in the
-- future (0019)
-- ============================================================================

\echo '### TEST T6: current_fact filters on effective_from, not just effective_to'

DO $$
DECLARE
    v_parcel_id     uuid;
    v_future_count  int;
    v_present_count int;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    -- Future: effective tomorrow, must NOT appear yet.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t6_field', '"future_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now() + interval '1 day', 'v1.0'
    );

    -- Present/control: effective in the past, must appear -- proving the
    -- new filter doesn't also wrongly exclude a genuinely current fact.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t6b_field', '"present_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now() - interval '1 day', 'v1.0'
    );

    REFRESH MATERIALIZED VIEW current_fact;

    SELECT count(*) INTO v_future_count FROM current_fact
     WHERE parcel_id = v_parcel_id AND field_key = 'test.t6_field';

    SELECT count(*) INTO v_present_count FROM current_fact
     WHERE parcel_id = v_parcel_id AND field_key = 'test.t6b_field';

    IF v_future_count <> 0 THEN
        RAISE EXCEPTION 'FAIL T6: future-effective_from fact appeared in current_fact (% rows)', v_future_count;
    END IF;

    IF v_present_count <> 1 THEN
        RAISE EXCEPTION 'FAIL T6: present-effective_from control fact did not appear in current_fact (expected 1, got %)', v_present_count;
    END IF;

    RAISE NOTICE 'PASS T6: future-effective_from fact excluded, present-effective_from control fact included';
    INSERT INTO test_pass VALUES ('T6');
END $$;

-- ============================================================================
-- TEST T7: job_run cannot be 'running' with finished_at already set (0020)
-- job_run_status_finished_at_biconditional -- the direction the old
-- one-way job_terminal check never covered.
-- ============================================================================

\echo '### TEST T7: job_run status=running with finished_at set (should fail)'

DO $$
DECLARE
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO job_run (job_key, status, started_at, finished_at)
        VALUES ('test.t7_job', 'running', now(), now());
        RAISE EXCEPTION 'FAIL T7: job_run status=running with finished_at set was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'job_run_status_finished_at_biconditional' THEN
                RAISE NOTICE 'PASS T7: running job_run with finished_at set rejected';
                INSERT INTO test_pass VALUES ('T7');
            ELSE
                RAISE EXCEPTION 'FAIL T7: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T8: support_request cannot carry correcting_fact_id without
-- caused_correction=true (0020)
-- support_request_correction_consistent_biconditional -- the direction the
-- old one-way support_correction_consistent check never covered.
-- ============================================================================

\echo '### TEST T8: support_request caused_correction=false with correcting_fact_id set (should fail)'

DO $$
DECLARE
    v_fact_id    uuid;
    v_constraint text;
BEGIN
    -- Reuses the I4 lifecycle fact (immutable, never deleted per T1/0017) --
    -- any existing valid fact id works here, this test isn't about which
    -- fact, only about the caused_correction/correcting_fact_id pairing.
    SELECT value::uuid INTO v_fact_id FROM test_state WHERE key = 'i4_fact_id';

    BEGIN
        INSERT INTO support_request (
            jurisdiction_id, category, caused_correction, correcting_fact_id
        ) VALUES (
            'ca_san_jose', 'other', false, v_fact_id
        );
        RAISE EXCEPTION 'FAIL T8: caused_correction=false with correcting_fact_id set was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'support_request_correction_consistent_biconditional' THEN
                RAISE NOTICE 'PASS T8: caused_correction=false with a correcting_fact_id rejected';
                INSERT INTO test_pass VALUES ('T8');
            ELSE
                RAISE EXCEPTION 'FAIL T8: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T9: job_run.finished_at cannot precede started_at (0020)
-- job_run_finished_after_started.
-- ============================================================================

\echo '### TEST T9: job_run finished_at before started_at (should fail)'

DO $$
DECLARE
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO job_run (job_key, status, started_at, finished_at)
        VALUES ('test.t9_job', 'succeeded', now(), now() - interval '1 hour');
        RAISE EXCEPTION 'FAIL T9: job_run with finished_at before started_at was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'job_run_finished_after_started' THEN
                RAISE NOTICE 'PASS T9: finished_at before started_at rejected';
                INSERT INTO test_pass VALUES ('T9');
            ELSE
                RAISE EXCEPTION 'FAIL T9: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T10: job_run.rows_in cannot be negative (0020)
-- job_run_rows_in_nonnegative.
-- ============================================================================

\echo '### TEST T10: job_run rows_in negative (should fail)'

DO $$
DECLARE
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO job_run (job_key, status, started_at, finished_at, rows_in)
        VALUES ('test.t10_job', 'succeeded', now(), now(), -1);
        RAISE EXCEPTION 'FAIL T10: job_run with negative rows_in was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'job_run_rows_in_nonnegative' THEN
                RAISE NOTICE 'PASS T10: negative rows_in rejected';
                INSERT INTO test_pass VALUES ('T10');
            ELSE
                RAISE EXCEPTION 'FAIL T10: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T11: job_run.rows_out cannot be negative (0020)
-- job_run_rows_out_nonnegative.
-- ============================================================================

\echo '### TEST T11: job_run rows_out negative (should fail)'

DO $$
DECLARE
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO job_run (job_key, status, started_at, finished_at, rows_out)
        VALUES ('test.t11_job', 'succeeded', now(), now(), -1);
        RAISE EXCEPTION 'FAIL T11: job_run with negative rows_out was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'job_run_rows_out_nonnegative' THEN
                RAISE NOTICE 'PASS T11: negative rows_out rejected';
                INSERT INTO test_pass VALUES ('T11');
            ELSE
                RAISE EXCEPTION 'FAIL T11: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T12: property_file.compose_ms cannot be negative (0020)
-- property_file_compose_ms_nonnegative.
-- ============================================================================

\echo '### TEST T12: property_file compose_ms negative (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, payload,
            payload_hash, compose_ms
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
            'v1.0', 'v1.0', false, '{}'::jsonb, 'testhash_t12', -1
        );
        RAISE EXCEPTION 'FAIL T12: property_file with negative compose_ms was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_compose_ms_nonnegative' THEN
                RAISE NOTICE 'PASS T12: negative compose_ms rejected';
                INSERT INTO test_pass VALUES ('T12');
            ELSE
                RAISE EXCEPTION 'FAIL T12: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T13: property_file.source_calls cannot be negative (0020)
-- property_file_source_calls_nonnegative.
-- ============================================================================

\echo '### TEST T13: property_file source_calls negative (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, payload,
            payload_hash, compose_ms, source_calls
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
            'v1.0', 'v1.0', false, '{}'::jsonb, 'testhash_t13', 100, -1
        );
        RAISE EXCEPTION 'FAIL T13: property_file with negative source_calls was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_source_calls_nonnegative' THEN
                RAISE NOTICE 'PASS T13: negative source_calls rejected';
                INSERT INTO test_pass VALUES ('T13');
            ELSE
                RAISE EXCEPTION 'FAIL T13: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T14: property_file.compute_cost_micros cannot be negative (0020)
-- property_file_compute_cost_micros_nonnegative.
-- ============================================================================

\echo '### TEST T14: property_file compute_cost_micros negative (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, payload,
            payload_hash, compose_ms, compute_cost_micros
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
            'v1.0', 'v1.0', false, '{}'::jsonb, 'testhash_t14', 100, -1
        );
        RAISE EXCEPTION 'FAIL T14: property_file with negative compute_cost_micros was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_compute_cost_micros_nonnegative' THEN
                RAISE NOTICE 'PASS T14: negative compute_cost_micros rejected';
                INSERT INTO test_pass VALUES ('T14');
            ELSE
                RAISE EXCEPTION 'FAIL T14: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T15: property_file.storage_cost_micros cannot be negative (0020)
-- property_file_storage_cost_micros_nonnegative.
-- ============================================================================

\echo '### TEST T15: property_file storage_cost_micros negative (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, payload,
            payload_hash, compose_ms, storage_cost_micros
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
            'v1.0', 'v1.0', false, '{}'::jsonb, 'testhash_t15', 100, -1
        );
        RAISE EXCEPTION 'FAIL T15: property_file with negative storage_cost_micros was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_storage_cost_micros_nonnegative' THEN
                RAISE NOTICE 'PASS T15: negative storage_cost_micros rejected';
                INSERT INTO test_pass VALUES ('T15');
            ELSE
                RAISE EXCEPTION 'FAIL T15: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T16: parcel_exception.resolved_at cannot precede detected_at (0020)
-- parcel_exception_resolved_after_detected.
-- ============================================================================

\echo '### TEST T16: parcel_exception resolved_at before detected_at (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO parcel_exception (
            parcel_id, jurisdiction_id, type, severity, detector_key,
            detector_version, detail, detected_at, outcome, resolved_at, resolved_by
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'staleness', 'warning', 'test_detector',
            'v1', '{}'::jsonb, now(), 'confirmed', now() - interval '1 hour', 'test_operator'
        );
        RAISE EXCEPTION 'FAIL T16: parcel_exception resolved before detected was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'parcel_exception_resolved_after_detected' THEN
                RAISE NOTICE 'PASS T16: resolved_at before detected_at rejected';
                INSERT INTO test_pass VALUES ('T16');
            ELSE
                RAISE EXCEPTION 'FAIL T16: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T17: source.method remains immutable even after every fact that
-- references it has been superseded (0018) -- db/README.md previously and
-- wrongly documented supersession as a way to release the FK reference and
-- allow the UPDATE; that claim was never actually run. PostgreSQL FK
-- enforcement does not look at superseded_at or any other column when
-- deciding whether a referenced key is "still referenced" -- a superseded
-- row references (source_id, method) exactly as much as a live one does.
-- ============================================================================

\echo '### TEST T17: UPDATE source.method after superseding its only referencing fact (should still fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_fact_id    uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t17_field', '"value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    -- Supersede it -- the one legal UPDATE on a fact row (I4). If
    -- supersession released the FK reference the way the (wrong) README
    -- claim assumed, the UPDATE below would succeed; it must not.
    UPDATE fact SET superseded_at = now() WHERE id = v_fact_id;

    BEGIN
        UPDATE source SET method = 'bulk' WHERE id = 'ca_san_jose.test_source';
        RAISE EXCEPTION 'FAIL T17: source.method UPDATE succeeded after superseding its only referencing fact';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_source_method_fk' THEN
                RAISE NOTICE 'PASS T17: source.method remains immutable after supersession (rejected by fact_source_method_fk)';
                INSERT INTO test_pass VALUES ('T17');
            ELSE
                RAISE EXCEPTION 'FAIL T17: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T18: a snapshot cannot be updated (0021)
-- snapshot_no_update(), an unconditional raise -- unlike fact/rule, no
-- column of a snapshot is ever legally mutable.
-- ============================================================================

\echo '### TEST T18: UPDATE snapshot (should fail)'

DO $$
BEGIN
    BEGIN
        UPDATE snapshot SET media_type = 'text/csv'
         WHERE id = 'ca_san_jose.test_source:sha256:5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37';
        RAISE EXCEPTION 'FAIL T18: UPDATE snapshot was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'C2 violated:%is immutable%' THEN
                RAISE NOTICE 'PASS T18: snapshot update rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T18');
            ELSE
                RAISE EXCEPTION 'FAIL T18: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T19: a snapshot cannot be deleted (0021)
-- snapshot_no_delete(), an unconditional raise, mirroring
-- rule_no_delete/fact_no_delete.
-- ============================================================================

\echo '### TEST T19: DELETE FROM snapshot (should fail)'

DO $$
BEGIN
    BEGIN
        DELETE FROM snapshot
         WHERE id = 'ca_san_jose.test_source:sha256:5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37';
        RAISE EXCEPTION 'FAIL T19: DELETE FROM snapshot was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'C2 violated:%cannot be deleted%' THEN
                RAISE NOTICE 'PASS T19: snapshot delete rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T19');
            ELSE
                RAISE EXCEPTION 'FAIL T19: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T20: snapshot.content_hash must be 64 lowercase hex characters (0021)
-- snapshot_content_hash_format.
-- ============================================================================

\echo '### TEST T20: snapshot with malformed content_hash (should fail)'

DO $$
DECLARE
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO snapshot (
            id, source_id, object_uri, content_hash, media_type, byte_size,
            request, http_status, fetched_at, licence_observed_id
        ) VALUES (
            'ca_san_jose.test_source:sha256:NOTVALIDHEX', 'ca_san_jose.test_source',
            's3://bucket/test-t20', 'NOTVALIDHEX', 'application/json', 100,
            '{"url":"https://example.com/t20","params":{}}'::jsonb,
            200, now(), 'test.cc0'
        );
        RAISE EXCEPTION 'FAIL T20: snapshot with malformed content_hash was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'snapshot_content_hash_format' THEN
                RAISE NOTICE 'PASS T20: malformed content_hash rejected';
                INSERT INTO test_pass VALUES ('T20');
            ELSE
                RAISE EXCEPTION 'FAIL T20: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T21: snapshot.id must equal source_id || ':sha256:' || content_hash
-- (0021) -- snapshot_id_format.
-- ============================================================================

\echo '### TEST T21: snapshot with id not matching source_id/content_hash (should fail)'

DO $$
DECLARE
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO snapshot (
            id, source_id, object_uri, content_hash, media_type, byte_size,
            request, http_status, fetched_at, licence_observed_id
        ) VALUES (
            'some-other-id-entirely', 'ca_san_jose.test_source',
            's3://bucket/test-t21', '781a0daece9ba3e9da7e6f0e94a2d0a9a7afa04c994d2f854188c25e5cc9f3b2',
            'application/json', 100,
            '{"url":"https://example.com/t21","params":{}}'::jsonb,
            200, now(), 'test.cc0'
        );
        RAISE EXCEPTION 'FAIL T21: snapshot with mismatched id was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'snapshot_id_format' THEN
                RAISE NOTICE 'PASS T21: id/source_id/content_hash mismatch rejected';
                INSERT INTO test_pass VALUES ('T21');
            ELSE
                RAISE EXCEPTION 'FAIL T21: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T22: snapshot.object_uri cannot be blank (0021)
-- snapshot_object_uri_not_blank.
-- ============================================================================

\echo '### TEST T22: snapshot with blank object_uri (should fail)'

DO $$
DECLARE
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO snapshot (
            id, source_id, object_uri, content_hash, media_type, byte_size,
            request, http_status, fetched_at, licence_observed_id
        ) VALUES (
            'ca_san_jose.test_source:sha256:781a0daece9ba3e9da7e6f0e94a2d0a9a7afa04c994d2f854188c25e5cc9f3b2',
            'ca_san_jose.test_source', '   ',
            '781a0daece9ba3e9da7e6f0e94a2d0a9a7afa04c994d2f854188c25e5cc9f3b2',
            'application/json', 100,
            '{"url":"https://example.com/t22","params":{}}'::jsonb,
            200, now(), 'test.cc0'
        );
        RAISE EXCEPTION 'FAIL T22: snapshot with blank object_uri was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'snapshot_object_uri_not_blank' THEN
                RAISE NOTICE 'PASS T22: blank object_uri rejected';
                INSERT INTO test_pass VALUES ('T22');
            ELSE
                RAISE EXCEPTION 'FAIL T22: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T23: snapshot.media_type cannot be blank (0021)
-- snapshot_media_type_not_blank.
-- ============================================================================

\echo '### TEST T23: snapshot with blank media_type (should fail)'

DO $$
DECLARE
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO snapshot (
            id, source_id, object_uri, content_hash, media_type, byte_size,
            request, http_status, fetched_at, licence_observed_id
        ) VALUES (
            'ca_san_jose.test_source:sha256:781a0daece9ba3e9da7e6f0e94a2d0a9a7afa04c994d2f854188c25e5cc9f3b2',
            'ca_san_jose.test_source', 's3://bucket/test-t23',
            '781a0daece9ba3e9da7e6f0e94a2d0a9a7afa04c994d2f854188c25e5cc9f3b2',
            '  ', 100,
            '{"url":"https://example.com/t23","params":{}}'::jsonb,
            200, now(), 'test.cc0'
        );
        RAISE EXCEPTION 'FAIL T23: snapshot with blank media_type was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'snapshot_media_type_not_blank' THEN
                RAISE NOTICE 'PASS T23: blank media_type rejected';
                INSERT INTO test_pass VALUES ('T23');
            ELSE
                RAISE EXCEPTION 'FAIL T23: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T24: fact.jurisdiction_id is NOT NULL (0022)
-- ============================================================================

\echo '### TEST T24: fact with null jurisdiction_id (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, NULL, 'test.t24_field', '"value"'::jsonb, 'direct',
            'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
            now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL T24: null jurisdiction_id was accepted';
    EXCEPTION
        WHEN not_null_violation THEN
            RAISE NOTICE 'PASS T24: null jurisdiction_id rejected (not_null_violation)';
            INSERT INTO test_pass VALUES ('T24');
    END;
END $$;

-- ============================================================================
-- TEST T25: a fact's licence must equal its snapshot's observed licence
-- (0022) -- fact_snapshot_licence_fk: FOREIGN KEY (snapshot_id, licence_id)
-- REFERENCES snapshot (id, licence_observed_id).
-- ============================================================================

\echo '### TEST T25: fact licence differing from its snapshot''s observed licence (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        -- The cc0 snapshot's observed licence is 'test.cc0'; this fact
        -- claims 'test.cc_by_4_0' -- a real, valid licence, just not the
        -- one this snapshot was actually observed under.
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'test.t25_field', '"value"'::jsonb, 'direct',
            'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
            now(), 'https://example.com', 'test.cc_by_4_0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL T25: fact licence mismatched with its snapshot''s observed licence was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_snapshot_licence_fk' THEN
                RAISE NOTICE 'PASS T25: licence mismatch rejected by fact_snapshot_licence_fk';
                INSERT INTO test_pass VALUES ('T25');
            ELSE
                RAISE EXCEPTION 'FAIL T25: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T26: a job_run cannot cite one source but another source's snapshot
-- (0022) -- job_run_snapshot_source_fk: FOREIGN KEY (source_id, snapshot_id)
-- REFERENCES snapshot (id, source_id).
-- ============================================================================

\echo '### TEST T26: job_run citing source A with source B''s snapshot (should fail)'

DO $$
DECLARE
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO job_run (job_key, jurisdiction_id, source_id, status, started_at, finished_at, snapshot_id)
        VALUES (
            'test.t26_job', 'ca_san_jose', 'ca_san_jose.test_source', 'succeeded', now(), now(),
            'ca_san_jose.test_source_b:sha256:2892e288adb59f59419b9351ed48cbb14e45d0556547da33f3543e5e85b71c8d'
        );
        RAISE EXCEPTION 'FAIL T26: job_run citing source A with source B''s snapshot was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'job_run_snapshot_source_fk' THEN
                RAISE NOTICE 'PASS T26: source/snapshot mismatch rejected by job_run_snapshot_source_fk';
                INSERT INTO test_pass VALUES ('T26');
            ELSE
                RAISE EXCEPTION 'FAIL T26: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T27: a fact's jurisdiction must match its own parcel's jurisdiction
-- (0022) -- fact_parcel_jurisdiction_fk: FOREIGN KEY (parcel_id, jurisdiction_id)
-- REFERENCES parcel (id, jurisdiction_id). Uses a DERIVED fact (source_id
-- NULL) specifically so fact_source_jurisdiction_fk is exempted by MATCH
-- SIMPLE and cannot also fire here -- isolates this FK alone.
-- ============================================================================

\echo '### TEST T27: fact jurisdiction_id disagreeing with its own parcel''s jurisdiction (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
            confidence, confidence_rule_id, effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'test_other_jurisdiction', 'test.t27_field', '"value"'::jsonb, 'derived',
            'v1.0', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL T27: fact jurisdiction_id disagreeing with its own parcel''s jurisdiction was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_parcel_jurisdiction_fk' THEN
                RAISE NOTICE 'PASS T27: parcel/jurisdiction mismatch rejected by fact_parcel_jurisdiction_fk';
                INSERT INTO test_pass VALUES ('T27');
            ELSE
                RAISE EXCEPTION 'FAIL T27: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T28: a fact's declared jurisdiction must match its source's
-- jurisdiction too, not just its parcel's (0022) -- the specific "parcel
-- and source disagree on jurisdiction" violation.
-- fact_source_jurisdiction_fk: FOREIGN KEY (source_id, jurisdiction_id)
-- REFERENCES source (id, jurisdiction_id).
-- ============================================================================

\echo '### TEST T28: fact whose parcel and source disagree on jurisdiction (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        -- jurisdiction_id='ca_san_jose' correctly matches v_parcel_id's own
        -- jurisdiction (satisfying fact_parcel_jurisdiction_fk), but
        -- source_id belongs to test_other_jurisdiction, not ca_san_jose.
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'test.t28_field', '"value"'::jsonb, 'direct',
            'test_other_jurisdiction.test_source',
            'test_other_jurisdiction.test_source:sha256:ea9ca0e4800afb999739746f473257ee491bc425f267ef6046b4a016d234184a',
            now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL T28: fact whose parcel and source disagree on jurisdiction was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_source_jurisdiction_fk' THEN
                RAISE NOTICE 'PASS T28: parcel/source jurisdiction disagreement rejected by fact_source_jurisdiction_fk';
                INSERT INTO test_pass VALUES ('T28');
            ELSE
                RAISE EXCEPTION 'FAIL T28: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T29: a Property File's jurisdiction must match its own parcel's
-- jurisdiction (0022) -- property_file_parcel_jurisdiction_fk:
-- FOREIGN KEY (parcel_id, jurisdiction_id) REFERENCES parcel
-- (id, jurisdiction_id).
-- ============================================================================

\echo '### TEST T29: property_file jurisdiction_id disagreeing with its own parcel''s jurisdiction (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, payload,
            payload_hash, compose_ms
        ) VALUES (
            v_parcel_id, 'test_other_jurisdiction', 'free_snapshot', 'composed', now(), 'v1.0',
            'v1.0', 'v1.0', false, '{}'::jsonb, 'testhash_t29', 100
        );
        RAISE EXCEPTION 'FAIL T29: property_file jurisdiction_id disagreeing with its own parcel''s jurisdiction was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_parcel_jurisdiction_fk' THEN
                RAISE NOTICE 'PASS T29: parcel/jurisdiction mismatch rejected by property_file_parcel_jurisdiction_fk';
                INSERT INTO test_pass VALUES ('T29');
            ELSE
                RAISE EXCEPTION 'FAIL T29: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T30: a parcel_exception's jurisdiction must match its own parcel's
-- jurisdiction (0022) -- parcel_exception_parcel_jurisdiction_fk:
-- FOREIGN KEY (parcel_id, jurisdiction_id) REFERENCES parcel
-- (id, jurisdiction_id).
-- ============================================================================

\echo '### TEST T30: parcel_exception jurisdiction_id disagreeing with its own parcel''s jurisdiction (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO parcel_exception (
            parcel_id, jurisdiction_id, type, severity, detector_key,
            detector_version, detail, outcome
        ) VALUES (
            v_parcel_id, 'test_other_jurisdiction', 'staleness', 'warning', 'test_detector',
            'v1', '{}'::jsonb, 'open'
        );
        RAISE EXCEPTION 'FAIL T30: parcel_exception jurisdiction_id disagreeing with its own parcel''s jurisdiction was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'parcel_exception_parcel_jurisdiction_fk' THEN
                RAISE NOTICE 'PASS T30: parcel/jurisdiction mismatch rejected by parcel_exception_parcel_jurisdiction_fk';
                INSERT INTO test_pass VALUES ('T30');
            ELSE
                RAISE EXCEPTION 'FAIL T30: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- POSITIVE TESTS for the composite FKs above (T2/T3/T25-T30 etc. all prove
-- a violation is rejected; none of them proves a correctly-formed row is
-- ACCEPTED). That gap is not hypothetical: job_run_snapshot_source_fk
-- shipped in 0022 with its two columns transposed -- FOREIGN KEY
-- (source_id, snapshot_id) REFERENCES snapshot (id, source_id) instead of
-- (snapshot_id, source_id) -- and rejected every job_run, valid or
-- invalid, unconditionally. T26 (which only ever inserts an INVALID
-- combination and asserts rejection) passed against the transposed
-- version exactly as well as it passes against the fixed one in 0024;
-- a negative control alone cannot tell "rejects only invalid rows" apart
-- from "rejects everything." Found for real during the first live
-- ingestion run (scripts/ingest_parcels.py), not by inspection. These five
-- tests close that blind spot: each inserts a row every column of which
-- correctly agrees with its target, and asserts the INSERT succeeds.
-- ============================================================================

-- ============================================================================
-- TEST T31: a job_run citing its own source's own snapshot succeeds (0022,
-- corrected by 0024) -- job_run_snapshot_source_fk.
-- ============================================================================

\echo '### TEST T31: job_run citing its own source''s own snapshot (should succeed)'

DO $$
DECLARE
    v_job_run_id uuid;
BEGIN
    INSERT INTO job_run (job_key, jurisdiction_id, source_id, status, started_at, finished_at, snapshot_id)
    VALUES (
        'test.t31_job', 'ca_san_jose', 'ca_san_jose.test_source', 'succeeded', now(), now(),
        'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28'
    ) RETURNING id INTO v_job_run_id;

    RAISE NOTICE 'PASS T31: job_run citing its own source''s own snapshot accepted (id=%)', v_job_run_id;
    INSERT INTO test_pass VALUES ('T31');
END $$;

-- ============================================================================
-- TEST T32: a fact citing its own source's own snapshot succeeds (0018) --
-- fact_snapshot_source_fk.
-- ============================================================================

\echo '### TEST T32: fact citing its own source''s own snapshot (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_fact_id   uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t32_field', '"value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    RAISE NOTICE 'PASS T32: fact citing its own source''s own snapshot accepted (id=%)', v_fact_id;
    INSERT INTO test_pass VALUES ('T32');
END $$;

-- ============================================================================
-- TEST T33: a fact whose licence matches its snapshot's observed licence
-- succeeds (0022) -- fact_snapshot_licence_fk. Uses the cc_by_4_0
-- snapshot/licence pairing (T32 uses cc0) to prove the FK accepts any
-- correctly-matched pair, not just one specific licence value.
-- ============================================================================

\echo '### TEST T33: fact licence matching its snapshot''s observed licence (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_fact_id   uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t33_field', '"value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:6807ac29ca72075c1cc37bbdb1ed367c967981c0c74c969d045ab5e5664f7774',
        now(), 'https://example.com', 'test.cc_by_4_0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    RAISE NOTICE 'PASS T33: fact licence matching its snapshot''s observed licence accepted (id=%)', v_fact_id;
    INSERT INTO test_pass VALUES ('T33');
END $$;

-- ============================================================================
-- TEST T34: a property_file_fact whose fact shares the file's parcel
-- succeeds (0018) -- property_file_fact_property_file_parcel_fk and
-- property_file_fact_fact_parcel_fk together.
-- ============================================================================

\echo '### TEST T34: property_file_fact whose fact shares the file''s parcel (should succeed)'

DO $$
DECLARE
    v_parcel_id        uuid;
    v_property_file_id uuid;
    v_fact_id          uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, payload,
        payload_hash, compose_ms
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
        'v1.0', 'v1.0', false, '{}'::jsonb, 'testhash_t34', 100
    ) RETURNING id INTO v_property_file_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t34_field', '"value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    INSERT INTO property_file_fact (property_file_id, fact_id, parcel_id)
    VALUES (v_property_file_id, v_fact_id, v_parcel_id);

    RAISE NOTICE 'PASS T34: property_file_fact whose fact shares the file''s parcel accepted';
    INSERT INTO test_pass VALUES ('T34');
END $$;

-- ============================================================================
-- TEST T35: a fact whose parcel and source share a jurisdiction succeeds
-- (0022) -- fact_parcel_jurisdiction_fk and fact_source_jurisdiction_fk
-- together.
-- ============================================================================

\echo '### TEST T35: fact whose parcel and source share a jurisdiction (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_fact_id   uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t35_field', '"value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    RAISE NOTICE 'PASS T35: fact whose parcel and source share a jurisdiction accepted (id=%)', v_fact_id;
    INSERT INTO test_pass VALUES ('T35');
END $$;

-- ============================================================================
-- TEST T36: supersedes_fact_id set without supersession_reason is rejected
-- (0025) -- fact_supersession_reason_biconditional.
-- ============================================================================

\echo '### TEST T36: supersedes_fact_id set with supersession_reason NULL (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_target_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';
    SELECT value::uuid INTO v_target_id FROM test_state WHERE key = 'i4_fact_id';

    BEGIN
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version, supersedes_fact_id
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'test.t36_field', '"value"'::jsonb, 'direct',
            'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
            now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0', v_target_id
        );
        RAISE EXCEPTION 'FAIL T36: supersedes_fact_id set with supersession_reason NULL was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_supersession_reason_biconditional' THEN
                RAISE NOTICE 'PASS T36: supersedes_fact_id without supersession_reason rejected';
                INSERT INTO test_pass VALUES ('T36');
            ELSE
                RAISE EXCEPTION 'FAIL T36: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T37: supersession_reason set without supersedes_fact_id is rejected
-- (0025) -- fact_supersession_reason_biconditional.
-- ============================================================================

\echo '### TEST T37: supersession_reason set with supersedes_fact_id NULL (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version, supersession_reason
        ) VALUES (
            v_parcel_id, 'ca_san_jose', 'test.t37_field', '"value"'::jsonb, 'direct',
            'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
            now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0', 'world_change'
        );
        RAISE EXCEPTION 'FAIL T37: supersession_reason set with supersedes_fact_id NULL was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_supersession_reason_biconditional' THEN
                RAISE NOTICE 'PASS T37: supersession_reason without supersedes_fact_id rejected';
                INSERT INTO test_pass VALUES ('T37');
            ELSE
                RAISE EXCEPTION 'FAIL T37: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T38: a fact with supersedes_fact_id AND supersession_reason both
-- NULL succeeds (0025) -- the ordinary case, a fact that supersedes
-- nothing.
-- ============================================================================

\echo '### TEST T38: fact with supersedes_fact_id and supersession_reason both NULL (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_fact_id   uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t38_field', '"value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    RAISE NOTICE 'PASS T38: fact with both supersession columns NULL accepted (id=%)', v_fact_id;
    INSERT INTO test_pass VALUES ('T38');
END $$;

-- ============================================================================
-- TEST T39: a fact with supersedes_fact_id AND supersession_reason both
-- set, validly, succeeds (0025).
-- ============================================================================

\echo '### TEST T39: fact with both supersedes_fact_id and supersession_reason set, valid (should succeed)'

DO $$
DECLARE
    v_parcel_id      uuid;
    v_original_id    uuid;
    v_superseding_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t39_field', '"original_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_original_id;

    -- Supersede the original -- the one legal UPDATE on a fact row (I4).
    UPDATE fact SET superseded_at = now() WHERE id = v_original_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version, supersedes_fact_id, supersession_reason
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t39_field', '"corrected_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0',
        v_original_id, 'source_correction'
    ) RETURNING id INTO v_superseding_id;

    RAISE NOTICE 'PASS T39: fact superseding another, with a stated reason, accepted (superseding=%, original=%)',
        v_superseding_id, v_original_id;
    INSERT INTO test_pass VALUES ('T39');
END $$;

-- ============================================================================
-- TEST T40: a fact cannot supersede itself (0025) -- fact_supersedes_not_self.
-- ============================================================================

\echo '### TEST T40: supersedes_fact_id = own id (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_new_id     uuid := gen_random_uuid();
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO fact (
            id, parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version, supersedes_fact_id, supersession_reason
        ) VALUES (
            v_new_id, v_parcel_id, 'ca_san_jose', 'test.t40_field', '"value"'::jsonb, 'direct',
            'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
            now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0',
            v_new_id, 'world_change'
        );
        RAISE EXCEPTION 'FAIL T40: fact with supersedes_fact_id = own id was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_supersedes_not_self' THEN
                RAISE NOTICE 'PASS T40: self-supersession rejected';
                INSERT INTO test_pass VALUES ('T40');
            ELSE
                RAISE EXCEPTION 'FAIL T40: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T41: a licence cannot be updated (0027) -- licence_no_update(), an
-- unconditional raise mirroring rule_no_update/snapshot_no_update.
-- T41/T42/T43's licence ids carry a fresh gen_random_uuid() suffix, unlike
-- most other throwaway ids in this file: licence is now immutable, so a
-- test row created under a literal id can never be deleted or updated on
-- a later run either -- reusing 'test.t41_licence' verbatim would collide
-- on licence_pkey the second time this suite runs against the same
-- database (confirmed directly: it did, before this fix).
-- ============================================================================

\echo '### TEST T41: UPDATE licence (should fail)'

DO $$
DECLARE
    v_licence_id text := 'test.t41_licence-' || gen_random_uuid()::text;
BEGIN
    INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution, observed_at)
    VALUES (v_licence_id, 'Test Licence T41', 'open', 'allowed', 'allowed', now());

    BEGIN
        UPDATE licence SET commercial_use = 'prohibited' WHERE id = v_licence_id;
        RAISE EXCEPTION 'FAIL T41: UPDATE licence was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'B2/I3 violated:%is immutable%' THEN
                RAISE NOTICE 'PASS T41: licence update rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T41');
            ELSE
                RAISE EXCEPTION 'FAIL T41: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T42: a licence cannot be deleted (0027) -- licence_no_delete(), an
-- unconditional raise mirroring rule_no_delete/fact_no_delete/snapshot_no_delete.
-- ============================================================================

\echo '### TEST T42: DELETE FROM licence (should fail)'

DO $$
DECLARE
    v_licence_id text := 'test.t42_licence-' || gen_random_uuid()::text;
BEGIN
    INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution, observed_at)
    VALUES (v_licence_id, 'Test Licence T42', 'open', 'allowed', 'allowed', now());

    BEGIN
        DELETE FROM licence WHERE id = v_licence_id;
        RAISE EXCEPTION 'FAIL T42: DELETE FROM licence was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'B2/I3 violated:%cannot be deleted%' THEN
                RAISE NOTICE 'PASS T42: licence delete rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T42');
            ELSE
                RAISE EXCEPTION 'FAIL T42: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T43: a NEW licence row can always be inserted (0027) -- immutability
-- blocks editing an existing row, not creating a new one when terms change.
-- ============================================================================

\echo '### TEST T43: INSERT a new licence row (should succeed)'

DO $$
DECLARE
    v_licence_id text := 'test.t43_licence-' || gen_random_uuid()::text;
BEGIN
    INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution, observed_at)
    VALUES (v_licence_id, 'Test Licence T43', 'open', 'allowed', 'allowed', now());

    RAISE NOTICE 'PASS T43: new licence row accepted (id=%)', v_licence_id;
    INSERT INTO test_pass VALUES ('T43');
END $$;

-- ============================================================================
-- TEST T44: a fact with source_asserted_as_of NULL succeeds (0028) -- the
-- ordinary case, a source that states no as-of date.
-- ============================================================================

\echo '### TEST T44: fact with source_asserted_as_of NULL (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_fact_id   uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t44_field', '"value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    RAISE NOTICE 'PASS T44: fact with source_asserted_as_of NULL accepted (id=%)', v_fact_id;
    INSERT INTO test_pass VALUES ('T44');
END $$;

-- ============================================================================
-- TEST T45: a fact with source_asserted_as_of set succeeds (0028), including
-- a value AFTER retrieved_at -- no CHECK ties the two, a source can state an
-- as-of date ahead of its own publication date.
-- ============================================================================

\echo '### TEST T45: fact with source_asserted_as_of set (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_fact_id   uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version, source_asserted_as_of
    ) VALUES (
        v_parcel_id, 'ca_san_jose', 'test.t45_field', '"value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0',
        now() + interval '30 days'
    ) RETURNING id INTO v_fact_id;

    RAISE NOTICE 'PASS T45: fact with source_asserted_as_of set (after retrieved_at) accepted (id=%)', v_fact_id;
    INSERT INTO test_pass VALUES ('T45');
END $$;

-- ============================================================================
-- SUMMARY
-- ============================================================================
-- The count below is real, not a maintained literal: it's
-- SELECT count(*) FROM test_pass, and test_pass only ever gains a row on a
-- test's PASS path (see each test above). Add, remove, or break a test and
-- this number changes with it -- it cannot silently go stale the way a
-- hardcoded "N/N" string did before.
--
-- The floor below IS a maintained literal, deliberately: count(*) alone
-- reports honestly but never fails, so deleting a test (or a test silently
-- stopping short of its INSERT INTO test_pass) would still print a lower
-- number and still exit 0 -- coverage shrinking in total silence. Unlike the
-- "17/17" banner this replaced, a wrong floor fails loudly and immediately,
-- on the very run that made it wrong, in exactly the same self-asserting
-- style as every test above -- not a display string nothing checks. Bump
-- this number in the same commit that adds or removes a test.
--
-- known_gaps is deliberately NOT part of this floor. I5c documents an
-- invariant (I5: a derivation formula's declared inputs must actually be
-- cited) that the schema cannot enforce -- a derived fact with zero
-- fact_input rows commits unchecked, because nothing requires a derivation
-- to declare any inputs at all. That test can never go red no matter what
-- the schema does, so counting it toward "coverage" would misrepresent it
-- as an enforced invariant. It is reported separately below, by name, so a
-- reader sees it without it inflating the enforced-invariant number.
DO $$
DECLARE
    v_pass_count int;
BEGIN
    SELECT count(*) INTO v_pass_count FROM test_pass;
    IF v_pass_count < 63 THEN
        RAISE EXCEPTION 'FAIL: coverage dropped -- expected at least 63 passing tests, got %', v_pass_count;
    END IF;
END $$;

SELECT count(*) AS pass_count FROM test_pass
\gset

SELECT count(*) AS known_gap_count FROM known_gaps
\gset

SELECT string_agg(name || ' (' || note || ')', E'\n  ') AS known_gap_detail FROM known_gaps
\gset

\echo ''
\echo '=========================================='
\echo 'INVARIANT TESTS COMPLETE --' :pass_count 'tests recorded PASS in test_pass'
\echo '=========================================='
\echo 'Every test above is self-asserting: reaching this line with no ERROR'
\echo 'means every PASS notice printed above, and counted in test_pass, is'
\echo 'real. Any wrong outcome would have raised an uncaught FAIL exception'
\echo 'and (under ON_ERROR_STOP) stopped the script before this point with a'
\echo 'nonzero exit code.'
\echo ''
\echo 'KNOWN GAPS --' :known_gap_count 'invariant(s) documented but NOT enforced'
\echo '  ' :known_gap_detail
\echo 'These are excluded from the pass floor above: they cannot fail no'
\echo 'matter what the schema does, so counting them would misrepresent an'
\echo 'unenforced invariant as covered.'
\echo ''
