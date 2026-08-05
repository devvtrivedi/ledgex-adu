-- Invariant tests for I2, I3, I4, I5, I13, I18, and the parcel_exception
-- outcome/resolution biconditional (0015).
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

INSERT INTO licence (
  id, display_name, restriction, commercial_use, redistribution,
  attribution_text, observed_at, cleared_by, cleared_at
) VALUES
  ('cc0', 'CC0 1.0 Universal', 'open', 'allowed', 'allowed', NULL, now(), 'test', now()),
  ('cc_by_4_0', 'CC BY 4.0', 'attribution', 'allowed', 'allowed',
   'Data © City of San José', now(), 'test', now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO jurisdiction (
  id, display_name, kind, state_code, tier, pack_version, supported
) VALUES
  ('ca_san_jose', 'City of San José', 'city', 'CA', 'tier_1', 'v1.0', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO source (
  id, jurisdiction_id, display_name, steward, method, phase_status,
  phase_status_reason, endpoint_url, licence_id, active, url_verified_at
) VALUES
  ('ca_san_jose.test_source', 'ca_san_jose', 'Test Source', 'City of San José',
   'direct', 'active', 'Test source for invariant testing',
   'https://example.com/api', 'cc0', true, now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO snapshot (
  id, source_id, object_uri, content_hash, media_type, byte_size,
  request, http_status, fetched_at, licence_observed_id
) VALUES
  ('sha256:test123', 'ca_san_jose.test_source', 's3://bucket/test',
   'abc123', 'application/json', 100,
   '{"url":"https://example.com","params":{}}'::jsonb,
   200, now(), 'cc0')
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
  ('test.i5c_field', 'Test Field I5c', 'public_record', 'string', 'test', 'I5c invariant test field')
ON CONFLICT (field_key) DO NOTHING;

-- Cross-block scratch state for this run: the fresh parcel id, and (later)
-- the I4/I18 row ids shared across their multi-block lifecycles.
CREATE TEMP TABLE test_state (key text PRIMARY KEY, value text);

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
            parcel_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'test.i3_field', '"value"'::jsonb, 'direct',
            'ca_san_jose.test_source', 'sha256:test123', now(), 'https://example.com',
            NULL, 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL I3: null licence_id was accepted';
    EXCEPTION
        WHEN not_null_violation THEN
            RAISE NOTICE 'PASS I3: null licence_id rejected (not_null_violation)';
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
            parcel_id, field_key, value, method, source_id, snapshot_id,
            method_version, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'test.i2a_field', '"derived_value"'::jsonb, 'derived',
            'ca_san_jose.test_source', 'sha256:test123',  -- both set: violates I2
            'v1.0', 'cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL I2a: derived fact with source_id and snapshot_id set was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_provenance_complete' THEN
                RAISE NOTICE 'PASS I2a: rejected by fact_provenance_complete';
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
            parcel_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'test.i2b_field', '"value"'::jsonb, 'direct',
            'ca_san_jose.test_source', NULL,  -- missing snapshot_id
            now(), 'https://example.com', 'cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL I2b: direct fact with no snapshot_id was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_provenance_complete' THEN
                RAISE NOTICE 'PASS I2b: rejected by fact_provenance_complete';
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
            parcel_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'test.i13_field', '"value"'::jsonb, 'portal',  -- invalid
            'ca_san_jose.test_source', 'sha256:test123', now(), 'https://example.com',
            'cc0', 'high', 'rule_1', now(), 'v1.0'
        );
        RAISE EXCEPTION 'FAIL I13: method=portal was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'fact_method_automated' THEN
                RAISE NOTICE 'PASS I13: rejected by fact_method_automated';
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
        parcel_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test.i4a_field', '"original_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'sha256:test123', now(), 'https://example.com',
        'cc0', 'high', 'rule_1', now(), 'v1.0'
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
        parcel_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test.i5a_field', '"input_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'sha256:test123', now(), 'https://example.com',
        'cc_by_4_0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    -- Derived: cc0, more permissive than its input -- must be rejected.
    INSERT INTO fact (
        parcel_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test.i5a_field', '"derived"'::jsonb, 'derived',
        'v1.0', 'cc0',
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
        parcel_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test.i5b_field', '"input_value"'::jsonb, 'direct',
        'ca_san_jose.test_source', 'sha256:test123', now(), 'https://example.com',
        'cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    -- Derived: cc_by_4_0, stricter than its input -- must be allowed.
    INSERT INTO fact (
        parcel_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test.i5b_field', '"derived_stricter"'::jsonb, 'derived',
        'v1.0', 'cc_by_4_0',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    INSERT INTO fact_input (fact_id, input_fact_id, ordinal, role)
    VALUES (v_derived_fact_id, v_input_fact_id, 1, 'test_input');

    -- No inner catch: if this unexpectedly raises, that's a real schema
    -- finding and should surface with its original, unwrapped error text.
    SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

    RAISE NOTICE 'PASS I5b: stricter derived fact % accepted', v_derived_fact_id;
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
        parcel_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test.i5c_field', '"ungrounded_derived"'::jsonb, 'derived',
        'v1.0', 'cc0',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

    RAISE NOTICE 'PASS (KNOWN GAP) I5c: derived fact % with zero fact_input rows committed unchecked -- I5 cannot validate a derivation that never declares its inputs', v_derived_fact_id;
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
END $$;

-- ============================================================================
-- SUMMARY
-- ============================================================================

\echo ''
\echo '=========================================='
\echo 'INVARIANT TESTS COMPLETE (17/17)'
\echo '=========================================='
\echo 'Every test above is self-asserting: reaching this line with no ERROR'
\echo 'means all 17 PASS notices printed above are real. Any wrong outcome'
\echo 'would have raised an uncaught FAIL exception and (under ON_ERROR_STOP)'
\echo 'stopped the script before this point with a nonzero exit code.'
\echo ''
