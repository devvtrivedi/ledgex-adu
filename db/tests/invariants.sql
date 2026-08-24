-- Invariant tests for I2, I3, I4, I5, I13, I18, the parcel_exception
-- outcome/resolution biconditional (0015), and the seeded San José source
-- access methods (0016).
-- Run with: psql -v ON_ERROR_STOP=1 -f db/tests/invariants.sql DATABASE_URL
-- (or `make db-test`)
--
-- PRECONDITION -- POINT THIS AT A DISPOSABLE DATABASE. This suite writes
-- permanent, undeletable rows on every single run: one or more fresh
-- parcels plus every fact any test writes against them (most tests do).
-- fact_no_delete (0017) blocks deleting a fact directly -- that is I4
-- ("facts are immutable; corrections supersede, never delete") working as
-- designed, not a bug -- and fact_parcel_id_fkey (no ON DELETE cascade)
-- then blocks deleting a parcel too, the moment any fact cites it.
-- `make db-test` (P17, finding #26) runs db/tests/teardown.sql
-- unconditionally afterward, pass or fail, and removes everything else
-- this file writes (parcel_exception, property_file, property_file_fact,
-- job_run, exception_evidence, source_feature_identity, plus any parcel
-- that ends up with zero facts against it) -- but a fact-bearing parcel
-- and its facts are permanent on every database this file ever runs
-- against, by construction, and there is no flag or teardown step that
-- changes that without weakening 0017/I4 itself. `make db-test` with no
-- arguments runs against DB_TEST_DATABASE_URL's own default (P18,
-- README finding #25 -- closed), postgresql://localhost/ledgex_test, a
-- database that does not exist on a fresh clone -- see that target's own
-- comment. Running this file directly via plain `psql -f`, bypassing
-- `make db-test`, still connects to whatever DATABASE_URL/connection
-- string you give it, same as always -- see db/README.md's "which of
-- make schema / migrate / migrate-baseline" section before pointing
-- either invocation at a database you did not create specifically to
-- throw away. CI never has this problem: db.yml's `schema` job creates a
-- fresh, disposable `ledgex_ci` every run and discards the whole runner
-- afterward.
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
-- them. restriction stays 'open'/'attribution' (0029: I5a/I5b now also
-- depend on real licence_channel rows added below, not just this value).
INSERT INTO licence (
  id, display_name, restriction, commercial_use, redistribution,
  attribution_text, observed_at, cleared_by, cleared_at
) VALUES
  ('test.cc0', 'Test fixture (CC0-equivalent, open)', 'open', 'allowed', 'allowed', NULL, now(), 'test', now()),
  ('test.cc_by_4_0', 'Test fixture (CC BY 4.0-equivalent, attribution)', 'attribution', 'allowed', 'allowed',
   'Test fixture attribution text', now(), 'test', now())
ON CONFLICT (id) DO NOTHING;

-- test.cc0: unrestricted on channels too, matching its "open" identity.
-- test.cc_by_4_0: narrowed to two of four channels (paid_property_file and
-- bulk_export absent -- default-deny, 0002) -- 0029's reworked I5a/I5b need
-- a real channel difference between two otherwise-fine test licences to
-- exercise the channel dimension at all; before this, the suite had zero
-- licence_channel rows anywhere and both tests only ever passed by
-- accident, via the attribution difference, never actually touching the
-- channel check.
INSERT INTO licence_channel (licence_id, channel, allowed, rationale) VALUES
  ('test.cc0', 'free_snapshot', true, 'test fixture: unrestricted'),
  ('test.cc0', 'paid_property_file', true, 'test fixture: unrestricted'),
  ('test.cc0', 'api', true, 'test fixture: unrestricted'),
  ('test.cc0', 'bulk_export', true, 'test fixture: unrestricted'),
  ('test.cc_by_4_0', 'free_snapshot', true, 'test fixture: narrowed for the channel-dimension tests'),
  ('test.cc_by_4_0', 'api', true, 'test fixture: narrowed for the channel-dimension tests')
ON CONFLICT (licence_id, channel) DO NOTHING;

-- Fixtures for 0029's per-dimension tests (T46-T51). All permit every
-- channel (full licence_channel rows below) so each pair below isolates
-- exactly one dimension -- commercial_use, redistribution, or attribution
-- -- without the channel check firing first and masking it.
INSERT INTO licence (
  id, display_name, restriction, commercial_use, redistribution,
  attribution_text, observed_at, cleared_by, cleared_at
) VALUES
  -- The original bug, reconstructed: two inputs restricting DIFFERENT
  -- dimensions (commercial_use vs redistribution). Under the old
  -- severity-based check, 'noncommercial' (severity 1) beat 'no_resale'
  -- (severity 2) as "most restrictive", so a derived fact that only
  -- picked up the noncommercial input's restriction passed, silently
  -- dropping the no_resale input's redistribution=prohibited.
  ('test.noncommercial_only', 'Test fixture: commercial use prohibited only', 'noncommercial', 'prohibited', 'allowed', NULL, now(), 'test', now()),
  ('test.no_resale_only', 'Test fixture: redistribution prohibited only', 'no_resale', 'allowed', 'prohibited', NULL, now(), 'test', now()),
  ('test.wrongly_noncommercial_derived', 'Test fixture: drops the no_resale input''s redistribution restriction', 'noncommercial', 'prohibited', 'allowed', NULL, now(), 'test', now()),
  ('test.correctly_restricted', 'Test fixture: correctly narrows both commercial_use and redistribution', 'no_resale', 'prohibited', 'prohibited', NULL, now(), 'test', now()),
  -- commercial_use dimension, isolated.
  ('test.unknown_commercial', 'Test fixture: commercial_use unknown (not prohibited, not allowed)', 'unknown', 'unknown', 'allowed', NULL, now(), 'test', now()),
  ('test.claims_commercial_allowed', 'Test fixture: wrongly claims commercial_use=allowed', 'unknown', 'allowed', 'allowed', NULL, now(), 'test', now()),
  ('test.claims_commercial_unknown', 'Test fixture: correctly does not claim commercial_use=allowed', 'unknown', 'unknown', 'allowed', NULL, now(), 'test', now()),
  -- attribution dimension, isolated.
  ('test.attribution_required', 'Test fixture: requires attribution', 'attribution', 'allowed', 'allowed', 'Test fixture attribution text', now(), 'test', now()),
  ('test.no_attribution', 'Test fixture: does not carry attribution forward', 'open', 'allowed', 'allowed', NULL, now(), 'test', now()),
  ('test.attribution_carried', 'Test fixture: correctly carries attribution forward', 'attribution', 'allowed', 'allowed', 'Test fixture attribution text', now(), 'test', now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO licence_channel (licence_id, channel, allowed, rationale)
SELECT licence_id, channel, true, 'test fixture: unrestricted on channels, isolates the non-channel dimension under test'
  FROM unnest(ARRAY[
    'test.noncommercial_only', 'test.no_resale_only', 'test.wrongly_noncommercial_derived',
    'test.correctly_restricted', 'test.unknown_commercial', 'test.claims_commercial_allowed',
    'test.claims_commercial_unknown', 'test.attribution_required', 'test.no_attribution',
    'test.attribution_carried'
  ]) AS licence_id
  CROSS JOIN unnest(ARRAY['free_snapshot', 'paid_property_file', 'api', 'bulk_export']::output_channel[]) AS channel
ON CONFLICT (licence_id, channel) DO NOTHING;

-- Two rows. tier omitted on both -- defaults to 'blocked' (0002's own column
-- default). No test here reads jurisdiction.tier (verified directly, P56
-- Phase 2 item B: grep for geometry_tier_enabled/\btier\b/supported against
-- this file's own DO blocks found no read of any of the three off a
-- parcel's own jurisdiction row).
--
-- 'ca_san_jose': kept, unchanged, still the FK parent of every fact-bearing
-- fixture this suite left behind before this pass and still shares its id
-- with db/seeds/day4_sources.sql's own jurisdiction row -- both use
-- ON CONFLICT (id) DO NOTHING, so whichever seed runs first against a
-- shared database silently wins the value, and stamping a real tier here
-- would risk defeating day4_sources.sql's own fix depending on run order.
-- This row no longer receives any NEW fixture data (P56 Phase 2, finding
-- #50) -- it stays only for FK/historical reasons, not because this suite
-- still writes under it.
--
-- 'test_ca_san_jose': NEW (P56 Phase 2, finding #50) -- this is where every
-- parcel/fact/property_file/parcel_exception/job_run/rule fixture this
-- suite creates now lives. Shares its id with nothing in day4_sources.sql,
-- so it owns this row outright and the run-order hazard above does not
-- apply to it at all -- tier is omitted here purely for behaviour parity
-- with the real row (§4.1), a deliberate choice, not an inherited
-- necessity.
INSERT INTO jurisdiction (
  id, display_name, kind, state_code, pack_version, supported
) VALUES
  ('ca_san_jose', 'City of San José', 'city', 'CA', 'v1.0', true),
  ('test_ca_san_jose', 'Test Jurisdiction (twin of ca_san_jose)', 'city', 'CA', 'v1.0', true)
ON CONFLICT (id) DO NOTHING;

-- active = false, no url_verified_at: nothing in this suite needs the
-- source live, and a test file has no business creating verified-and-active
-- source records (source_active_requires_verification exists precisely to
-- keep an unchecked source off).
INSERT INTO source (
  id, jurisdiction_id, display_name, steward, method, phase_status,
  phase_status_reason, endpoint_url, licence_id, active
) VALUES
  ('test_ca_san_jose.test_source', 'test_ca_san_jose', 'Test Source', 'City of San José',
   'direct', 'active', 'Test source for invariant testing',
   'https://example.com/api', 'test.cc0', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO snapshot (
  id, source_id, object_uri, content_hash, media_type, byte_size,
  request, http_status, fetched_at, licence_observed_id
) VALUES
  ('test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', 'test_ca_san_jose.test_source', 's3://bucket/test',
   '65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', 'application/json', 100,
   '{"url":"https://example.com","params":{}}'::jsonb,
   200, now(), 'test.cc0')
ON CONFLICT (id) DO NOTHING;

-- One snapshot per 0029 per-dimension test licence used as a RETRIEVED
-- fact's licence_id (fact_snapshot_licence_fk, 0022, forces a retrieved
-- fact's licence_id to equal exactly the snapshot it cites -- these test
-- licences need their own observing snapshot, the cc0 one above can't
-- stand in for them).
INSERT INTO snapshot (
  id, source_id, object_uri, content_hash, media_type, byte_size,
  request, http_status, fetched_at, licence_observed_id
) VALUES
  ('test_ca_san_jose.test_source:sha256:cff19b2a105a07f128fe53e3bef1b5fd2c0820dccfc0f65f94fd767418751fcb', 'test_ca_san_jose.test_source', 's3://bucket/test-noncommercial',
   'cff19b2a105a07f128fe53e3bef1b5fd2c0820dccfc0f65f94fd767418751fcb', 'application/json', 100,
   '{"url":"https://example.com","params":{}}'::jsonb, 200, now(), 'test.noncommercial_only'),
  ('test_ca_san_jose.test_source:sha256:bef91ddbcb9895f41aa49c95501153f3d1ad4f5dc2c6f532fe488693c7e49664', 'test_ca_san_jose.test_source', 's3://bucket/test-no-resale',
   'bef91ddbcb9895f41aa49c95501153f3d1ad4f5dc2c6f532fe488693c7e49664', 'application/json', 100,
   '{"url":"https://example.com","params":{}}'::jsonb, 200, now(), 'test.no_resale_only'),
  ('test_ca_san_jose.test_source:sha256:46e29d1835533f9dfef783161eba2d64f8caf1b6a7024c3e5b48aba24b74fb19', 'test_ca_san_jose.test_source', 's3://bucket/test-unknown-commercial',
   '46e29d1835533f9dfef783161eba2d64f8caf1b6a7024c3e5b48aba24b74fb19', 'application/json', 100,
   '{"url":"https://example.com","params":{}}'::jsonb, 200, now(), 'test.unknown_commercial'),
  ('test_ca_san_jose.test_source:sha256:af9a79c43ff57207f122898e73ab04eb8178f6d05ad9e9a0287566337fc68fe3', 'test_ca_san_jose.test_source', 's3://bucket/test-attribution-required',
   'af9a79c43ff57207f122898e73ab04eb8178f6d05ad9e9a0287566337fc68fe3', 'application/json', 100,
   '{"url":"https://example.com","params":{}}'::jsonb, 200, now(), 'test.attribution_required')
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
  ('test_ca_san_jose.test_source:sha256:6807ac29ca72075c1cc37bbdb1ed367c967981c0c74c969d045ab5e5664f7774', 'test_ca_san_jose.test_source', 's3://bucket/test-cc-by',
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
  ('test_ca_san_jose.test_source_b', 'test_ca_san_jose', 'Test Source B', 'City of San José',
   'bulk', 'active', 'Second test source for provenance-integrity tests',
   'https://example.com/api-b', 'test.cc0', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO snapshot (
  id, source_id, object_uri, content_hash, media_type, byte_size,
  request, http_status, fetched_at, licence_observed_id
) VALUES
  ('test_ca_san_jose.test_source_b:sha256:2892e288adb59f59419b9351ed48cbb14e45d0556547da33f3543e5e85b71c8d', 'test_ca_san_jose.test_source_b', 's3://bucket/test-b',
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
  ('test_ca_san_jose.test_source:sha256:5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37', 'test_ca_san_jose.test_source', 's3://bucket/test-throwaway',
   '5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37', 'application/json', 100,
   '{"url":"https://example.com/throwaway","params":{}}'::jsonb,
   200, now(), 'test.cc0')
ON CONFLICT (id) DO NOTHING;

-- A second jurisdiction, plus a source and snapshot registered under it:
-- 0022's fact_source_jurisdiction_fk, property_file_parcel_jurisdiction_fk
-- and parcel_exception_parcel_jurisdiction_fk all need a genuinely
-- different jurisdiction to disagree with, not just a different id string
-- that happens to share this suite's own canonical parcel's jurisdiction_id
-- (test_ca_san_jose since P56 Phase 2, finding #50 -- ca_san_jose before it).
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
  ('test.t45_field', 'Test Field T45', 'public_record', 'string', 'test', 'T45 invariant test field'),
  ('test.t46_field', 'Test Field T46', 'public_record', 'string', 'test', 'T46 invariant test field'),
  ('test.t47_field', 'Test Field T47', 'public_record', 'string', 'test', 'T47 invariant test field'),
  ('test.t48_field', 'Test Field T48', 'public_record', 'string', 'test', 'T48 invariant test field'),
  ('test.t49_field', 'Test Field T49', 'public_record', 'string', 'test', 'T49 invariant test field'),
  ('test.t50_field', 'Test Field T50', 'public_record', 'string', 'test', 'T50 invariant test field'),
  ('test.t51_field', 'Test Field T51', 'public_record', 'string', 'test', 'T51 invariant test field'),
  -- T46/T47 each cite two inputs from the SAME source; fact_one_current_per_source
  -- (parcel_id, field_key, source_id, method_version) means two retrieved facts
  -- for the same field from the same source collide, so each input needs its
  -- own field_key, distinct from the shared derived-fact field_key.
  ('test.t46_field_a', 'Test Field T46a', 'public_record', 'string', 'test', 'T46 invariant test field, input 1'),
  ('test.t46_field_b', 'Test Field T46b', 'public_record', 'string', 'test', 'T46 invariant test field, input 2'),
  ('test.t47_field_a', 'Test Field T47a', 'public_record', 'string', 'test', 'T47 invariant test field, input 1'),
  ('test.t47_field_b', 'Test Field T47b', 'public_record', 'string', 'test', 'T47 invariant test field, input 2'),
  ('test.t58_field', 'Test Field T58', 'public_record', 'string', 'test', 'T58 invariant test field'),
  ('test.t62_field', 'Test Field T62', 'public_record', 'string', 'test', 'T62 invariant test field (pg_temp.fact_input shadow)'),
  ('test.t63_field', 'Test Field T63', 'public_record', 'string', 'test', 'T63 invariant test field (pg_temp.fact shadow)'),
  ('test.t64_field', 'Test Field T64', 'public_record', 'string', 'test', 'T64 invariant test field (whole-row immutability, every column)'),
  ('test.t68_field', 'Test Field T68', 'public_record', 'string', 'test', 'T68 invariant test field (supersession parcel/field mismatch)'),
  ('test.t69_field', 'Test Field T69', 'public_record', 'string', 'test', 'T69 invariant test field (supersession target not superseded)'),
  ('test.t70_field', 'Test Field T70', 'public_record', 'string', 'test', 'T70 invariant test field (legitimate supersession, positive control)'),
  ('test.t71_field', 'Test Field T71', 'public_record', 'string', 'test', 'T71 invariant test field (cross-source supersession rejected, 0044)'),
  ('test.t72_field', 'Test Field T72', 'public_record', 'string', 'test', 'T72 invariant test field (same-source supersession still succeeds, 0044 positive control)')
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

-- Separate again from both test_pass AND known_gaps: a test whose
-- prerequisite data is conditionally absent (S1, guarded on db/seeds/
-- day4_sources.sql) is neither a pass (its assertion did not run) nor an
-- unenforceable invariant (it enforces something real, when it can run).
-- P6 finding: S1 used to INSERT INTO test_pass on its own skip branch,
-- counted in the floor -- meaning make db-test's own CI invocation (always
-- migrations-only, no seed applied yet at that point in the job -- true at
-- the time of this finding and, per P36/README finding #38's own ordering,
-- still true today: db.yml's schema job now DOES apply db/seeds/
-- day4_sources.sql, but only after make db-test has already run) ran S1
-- zero times yet recorded it passing, every run. Same defect class I5c was
-- already fixed for (a gap counted as coverage); same fix, its own table
-- so a skip is never mistaken for either a pass or a permanent gap.
CREATE TEMP TABLE test_skipped (name text PRIMARY KEY, note text);

-- P56 Phase 2 (item B, finding #50 T106/T107): this run's own start time,
-- recorded before a single fixture row exists, so T106 can scope its own
-- assertion to rows THIS run created rather than asserting over the whole
-- table (which can never pass -- permanent TEST-%% residue from every prior
-- run of this file, on every database it has ever touched, 0017/I4).
-- clock_timestamp(), not now(): now() is transaction-start, and this seed
-- block's own INSERTs commit as the transaction ends, not before it starts.
INSERT INTO test_state VALUES ('run_started_at', clock_timestamp()::text);

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    -- Fresh uuid PK + fresh apn: this row can never collide with a parcel
    -- left behind by a previous run.
    INSERT INTO parcel (jurisdiction_id, apn, situs_address)
    VALUES ('test_ca_san_jose', 'TEST-' || gen_random_uuid()::text,
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
            v_parcel_id, 'test_ca_san_jose', 'test.i3_field', '"value"'::jsonb, 'direct',
            'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
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
            v_parcel_id, 'test_ca_san_jose', 'test.i2a_field', '"derived_value"'::jsonb, 'derived',
            'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',  -- both set: violates I2
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
            v_parcel_id, 'test_ca_san_jose', 'test.i2b_field', '"value"'::jsonb, 'direct',
            'test_ca_san_jose.test_source', NULL,  -- missing snapshot_id
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
            v_parcel_id, 'test_ca_san_jose', 'test.i13_field', '"value"'::jsonb, 'portal',  -- invalid
            'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
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
        v_parcel_id, 'test_ca_san_jose', 'test.i4a_field', '"original_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
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
-- TEST I5a: derived fact permits a channel its input does not (0029)
-- ============================================================================
-- Reworked for 0029: the old severity-based version compared restriction
-- values that, before this migration, had no real licence_channel data
-- behind them anywhere in this suite -- it only ever passed by accident,
-- via the (also real) attribution difference between test.cc_by_4_0 and
-- test.cc0, never actually exercising a channel check. test.cc_by_4_0 now
-- carries real, narrower licence_channel rows (free_snapshot/api only;
-- see the fixture block above), so this is now a genuine channel-subset
-- violation, and the trigger's channel check runs before its attribution
-- check, so the error text below asserts on the channel-specific message.

\echo '### TEST I5a: derived fact permits a channel its input does not (should fail)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_input_fact_id   uuid;
    v_derived_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    -- Input: retrieved, cc_by_4_0 -- permits only free_snapshot and api.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.i5a_field', '"input_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:6807ac29ca72075c1cc37bbdb1ed367c967981c0c74c969d045ab5e5664f7774', now(), 'https://example.com',
        'test.cc_by_4_0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    -- Derived: test.cc0, permits all four channels -- over-permits
    -- paid_property_file/bulk_export relative to the input. Must be rejected.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.i5a_field', '"derived"'::jsonb, 'derived',
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

        RAISE EXCEPTION 'FAIL I5a: derived fact permitting a channel its input does not was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I5 violated:%permits channel%which at least one input does not permit%' THEN
                RAISE NOTICE 'PASS I5a: over-permissive derived fact rejected at COMMIT (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('I5a');
            ELSE
                RAISE EXCEPTION 'FAIL I5a: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST I5b: derived fact's channels are a genuine subset of its input's (0029)
-- ============================================================================
-- Reworked for 0029 alongside I5a: test.cc_by_4_0's channel set
-- (free_snapshot, api) is now a real subset of test.cc0's (all four), so
-- this is a genuine channel-subset pass, not a restriction-severity
-- coincidence.

\echo '### TEST I5b: derived fact''s channels are a subset of its input''s (should succeed)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_input_fact_id   uuid;
    v_derived_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    -- Input: retrieved, cc0 -- permits all four channels.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.i5b_field', '"input_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    -- Derived: test.cc_by_4_0, permits only free_snapshot/api -- a genuine
    -- subset of its input's four -- must be allowed.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.i5b_field', '"derived_stricter"'::jsonb, 'derived',
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
        v_parcel_id, 'test_ca_san_jose', 'test.i5c_field', '"ungrounded_derived"'::jsonb, 'derived',
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
        v_rule_id, 'test_ca_san_jose', 'test.i18a.rule.' || v_rule_id, 1, CURRENT_DATE,
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
        v_rule_id, 'test_ca_san_jose', 'test.i18b.rule.' || v_rule_id, 1, CURRENT_DATE,
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
        v_rule_id, 'test_ca_san_jose', 'test.i18c.rule.' || v_rule_id, 1, CURRENT_DATE,
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
        v_rule_id, 'test_ca_san_jose', 'test.i18d.rule.' || v_rule_id, 1, CURRENT_DATE,
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
            v_parcel_id, 'test_ca_san_jose', 'staleness', 'warning', 'test_detector',
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
            v_parcel_id, 'test_ca_san_jose', 'staleness', 'warning', 'test_detector',
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
        v_parcel_id, 'test_ca_san_jose', 'staleness', 'warning', 'test_detector',
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
-- Absence is a skip, not a failure -- recorded in test_skipped, not
-- test_pass, so a skip can never be mistaken for a pass in the floor below
-- (P6 finding: it used to be, silently, every CI run). This
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
        RAISE NOTICE 'SKIP S1: none of the three seeded sources present -- db/seeds/day4_sources.sql has not been applied to this database, so there is nothing to regress. NOT counted as a pass.';
        INSERT INTO test_skipped VALUES ('S1', 'db/seeds/day4_sources.sql not applied to this database -- assertion did not run');
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
        v_parcel_id, 'test_ca_san_jose', 'test.t1_field', '"delete_me"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
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
            v_parcel_id, 'test_ca_san_jose', 'test.t2_field', '"value"'::jsonb, 'direct',
            'test_ca_san_jose.test_source',      -- source A
            'test_ca_san_jose.test_source_b:sha256:2892e288adb59f59419b9351ed48cbb14e45d0556547da33f3543e5e85b71c8d',               -- source B's snapshot
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
            v_parcel_id, 'test_ca_san_jose', 'test.t3_field', '"value"'::jsonb, 'bulk',
            'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
    VALUES ('test_ca_san_jose', 'TEST-T4-' || gen_random_uuid()::text,
            '456 Other Parcel St, San Jose, CA 95110')
    RETURNING id INTO v_other_parcel_id;

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, payload,
        payload_hash, compose_ms
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
        'v1.0', 'v1.0', false, '{}'::jsonb, 'testhash_t4', 100
    ) RETURNING id INTO v_property_file_id;

    -- This fact belongs to the OTHER parcel, not the Property File's parcel.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_other_parcel_id, 'test_ca_san_jose', 'test.t4_field', '"other_parcel_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
    VALUES ('test_ca_san_jose', 'TEST-T5-' || gen_random_uuid()::text,
            '789 Other Parcel Ave, San Jose, CA 95110')
    RETURNING id INTO v_other_parcel_id;

    INSERT INTO parcel_exception (
        parcel_id, jurisdiction_id, type, severity, detector_key,
        detector_version, detail, outcome
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'staleness', 'warning', 'test_detector',
        'v1', '{}'::jsonb, 'open'
    ) RETURNING id INTO v_exception_id;

    -- This fact belongs to the OTHER parcel, not the exception's parcel.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_other_parcel_id, 'test_ca_san_jose', 'test.t5_field', '"other_parcel_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
        v_parcel_id, 'test_ca_san_jose', 'test.t6_field', '"future_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now() + interval '1 day', 'v1.0'
    );

    -- Present/control: effective in the past, must appear -- proving the
    -- new filter doesn't also wrongly exclude a genuinely current fact.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t6b_field', '"present_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
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
            'test_ca_san_jose', 'other', false, v_fact_id
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
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
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
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
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
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
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
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
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
            v_parcel_id, 'test_ca_san_jose', 'staleness', 'warning', 'test_detector',
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
        v_parcel_id, 'test_ca_san_jose', 'test.t17_field', '"value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    -- Supersede it -- the one legal UPDATE on a fact row (I4). If
    -- supersession released the FK reference the way the (wrong) README
    -- claim assumed, the UPDATE below would succeed; it must not.
    UPDATE fact SET superseded_at = now() WHERE id = v_fact_id;

    BEGIN
        UPDATE source SET method = 'bulk' WHERE id = 'test_ca_san_jose.test_source';
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
         WHERE id = 'test_ca_san_jose.test_source:sha256:5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37';
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
         WHERE id = 'test_ca_san_jose.test_source:sha256:5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37';
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
            'test_ca_san_jose.test_source:sha256:NOTVALIDHEX', 'test_ca_san_jose.test_source',
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
            'some-other-id-entirely', 'test_ca_san_jose.test_source',
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
            'test_ca_san_jose.test_source:sha256:781a0daece9ba3e9da7e6f0e94a2d0a9a7afa04c994d2f854188c25e5cc9f3b2',
            'test_ca_san_jose.test_source', '   ',
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
            'test_ca_san_jose.test_source:sha256:781a0daece9ba3e9da7e6f0e94a2d0a9a7afa04c994d2f854188c25e5cc9f3b2',
            'test_ca_san_jose.test_source', 's3://bucket/test-t23',
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
            'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
            v_parcel_id, 'test_ca_san_jose', 'test.t25_field', '"value"'::jsonb, 'direct',
            'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
            'test.t26_job', 'test_ca_san_jose', 'test_ca_san_jose.test_source', 'succeeded', now(), now(),
            'test_ca_san_jose.test_source_b:sha256:2892e288adb59f59419b9351ed48cbb14e45d0556547da33f3543e5e85b71c8d'
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
        -- jurisdiction_id='test_ca_san_jose' correctly matches v_parcel_id's own
        -- jurisdiction (satisfying fact_parcel_jurisdiction_fk), but
        -- source_id belongs to test_other_jurisdiction, not test_ca_san_jose --
        -- this is the OTHER composite FK (fact_source_jurisdiction_fk) this
        -- test exists to probe, and it is the one expected to reject this row.
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'test.t28_field', '"value"'::jsonb, 'direct',
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
        -- detector_key is test_t30_detector, not the shared 'test_detector'
        -- other fixtures above use (T5 leaves an open 'test_detector'/'v1'
        -- exception on this same v_parcel_id that persists past its own
        -- test) -- 0049's now-correctly-enforcing unique index would
        -- otherwise reject this INSERT on a duplicate-key unique_violation
        -- before it ever reaches the jurisdiction FK this test exists to
        -- probe, since the OLD index (bare detail->>'reason', no COALESCE)
        -- never treated two NULL-reason rows as conflicting -- exactly
        -- README finding #19's bug, silently relied upon by this fixture
        -- until 0049 closed it. A distinct detector_key is the fix, not a
        -- weaker constraint: this test has nothing to do with detector
        -- dedup, it only needs its own INSERT to reach the FK check.
        INSERT INTO parcel_exception (
            parcel_id, jurisdiction_id, type, severity, detector_key,
            detector_version, detail, outcome
        ) VALUES (
            v_parcel_id, 'test_other_jurisdiction', 'staleness', 'warning', 'test_t30_detector',
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
        'test.t31_job', 'test_ca_san_jose', 'test_ca_san_jose.test_source', 'succeeded', now(), now(),
        'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28'
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
        v_parcel_id, 'test_ca_san_jose', 'test.t32_field', '"value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
        v_parcel_id, 'test_ca_san_jose', 'test.t33_field', '"value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:6807ac29ca72075c1cc37bbdb1ed367c967981c0c74c969d045ab5e5664f7774',
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
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
        'v1.0', 'v1.0', false, '{}'::jsonb, 'testhash_t34', 100
    ) RETURNING id INTO v_property_file_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t34_field', '"value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
        v_parcel_id, 'test_ca_san_jose', 'test.t35_field', '"value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
            v_parcel_id, 'test_ca_san_jose', 'test.t36_field', '"value"'::jsonb, 'direct',
            'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
            v_parcel_id, 'test_ca_san_jose', 'test.t37_field', '"value"'::jsonb, 'direct',
            'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
        v_parcel_id, 'test_ca_san_jose', 'test.t38_field', '"value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
        v_parcel_id, 'test_ca_san_jose', 'test.t39_field', '"original_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_original_id;

    -- Supersede the original -- the one legal UPDATE on a fact row (I4).
    UPDATE fact SET superseded_at = now() WHERE id = v_original_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version, supersedes_fact_id, supersession_reason
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t39_field', '"corrected_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
            v_new_id, v_parcel_id, 'test_ca_san_jose', 'test.t40_field', '"value"'::jsonb, 'direct',
            'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
        v_parcel_id, 'test_ca_san_jose', 'test.t44_field', '"value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
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
        v_parcel_id, 'test_ca_san_jose', 'test.t45_field', '"value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        now(), 'https://example.com', 'test.cc0', 'high', 'rule_1', now(), 'v1.0',
        now() + interval '30 days'
    ) RETURNING id INTO v_fact_id;

    RAISE NOTICE 'PASS T45: fact with source_asserted_as_of set (after retrieved_at) accepted (id=%)', v_fact_id;
    INSERT INTO test_pass VALUES ('T45');
END $$;

-- ============================================================================
-- TEST T46: two inputs restricting DIFFERENT dimensions, derived matching
-- only one, silently dropping the other (0029) -- THIS IS THE ORIGINAL BUG.
-- Under the old severity-based check, 'noncommercial' (severity 1) beat
-- 'no_resale' (severity 2) as "most restrictive", so a derived fact that
-- only picked up the noncommercial input's restriction passed, silently
-- dropping the no_resale input's redistribution=prohibited. Confirmed
-- directly (not assumed) to go RED against the OLD function -- see the
-- commit message / verification output for the re-applied-old-function run.
-- ============================================================================

\echo '### TEST T46: derived matches only one of two disjoint input restrictions (should fail)'

DO $$
DECLARE
    v_parcel_id        uuid;
    v_input1_fact_id   uuid;
    v_input2_fact_id   uuid;
    v_derived_fact_id  uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    -- Input 1: commercial_use=prohibited, redistribution=allowed.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t46_field_a', '"input1_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:cff19b2a105a07f128fe53e3bef1b5fd2c0820dccfc0f65f94fd767418751fcb', now(), 'https://example.com',
        'test.noncommercial_only', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input1_fact_id;

    -- Input 2: commercial_use=allowed, redistribution=prohibited.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t46_field_b', '"input2_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:bef91ddbcb9895f41aa49c95501153f3d1ad4f5dc2c6f532fe488693c7e49664', now(), 'https://example.com',
        'test.no_resale_only', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input2_fact_id;

    -- Derived: matches input 1 only (commercial_use=prohibited), still
    -- claims redistribution=allowed -- silently drops input 2's restriction.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t46_field', '"derived"'::jsonb, 'derived',
        'v1.0', 'test.wrongly_noncommercial_derived',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    BEGIN
        INSERT INTO fact_input (fact_id, input_fact_id, ordinal, role) VALUES
            (v_derived_fact_id, v_input1_fact_id, 1, 'test_input'),
            (v_derived_fact_id, v_input2_fact_id, 2, 'test_input');

        SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

        RAISE EXCEPTION 'FAIL T46: derived fact matching only one of two disjoint restrictions was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I5 violated:%redistribution=allowed, but at least one input does not%' THEN
                RAISE NOTICE 'PASS T46: disjoint-restriction violation rejected at COMMIT (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T46');
            ELSE
                RAISE EXCEPTION 'FAIL T46: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T47: two inputs restricting different dimensions, derived correctly
-- narrowing BOTH (should succeed) -- the positive counterpart to T46.
-- ============================================================================

\echo '### TEST T47: derived correctly narrows both of two disjoint input restrictions (should succeed)'

DO $$
DECLARE
    v_parcel_id        uuid;
    v_input1_fact_id   uuid;
    v_input2_fact_id   uuid;
    v_derived_fact_id  uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t47_field_a', '"input1_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:cff19b2a105a07f128fe53e3bef1b5fd2c0820dccfc0f65f94fd767418751fcb', now(), 'https://example.com',
        'test.noncommercial_only', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input1_fact_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t47_field_b', '"input2_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:bef91ddbcb9895f41aa49c95501153f3d1ad4f5dc2c6f532fe488693c7e49664', now(), 'https://example.com',
        'test.no_resale_only', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input2_fact_id;

    -- Derived: commercial_use=prohibited AND redistribution=prohibited --
    -- correctly narrows both dimensions.
    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t47_field', '"derived"'::jsonb, 'derived',
        'v1.0', 'test.correctly_restricted',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    INSERT INTO fact_input (fact_id, input_fact_id, ordinal, role) VALUES
        (v_derived_fact_id, v_input1_fact_id, 1, 'test_input'),
        (v_derived_fact_id, v_input2_fact_id, 2, 'test_input');

    SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

    RAISE NOTICE 'PASS T47: derived fact correctly narrowing both disjoint restrictions accepted (id=%)', v_derived_fact_id;
    INSERT INTO test_pass VALUES ('T47');
END $$;

-- ============================================================================
-- TEST T48: derived claims commercial_use=allowed while an input is
-- 'unknown' (0029) -- 'unknown' blocks exactly like 'prohibited' does.
-- ============================================================================

\echo '### TEST T48: derived commercial_use=allowed with an input unknown (should fail)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_input_fact_id   uuid;
    v_derived_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t48_field', '"input_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:46e29d1835533f9dfef783161eba2d64f8caf1b6a7024c3e5b48aba24b74fb19', now(), 'https://example.com',
        'test.unknown_commercial', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t48_field', '"derived"'::jsonb, 'derived',
        'v1.0', 'test.claims_commercial_allowed',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    BEGIN
        INSERT INTO fact_input (fact_id, input_fact_id, ordinal, role)
        VALUES (v_derived_fact_id, v_input_fact_id, 1, 'test_input');

        SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

        RAISE EXCEPTION 'FAIL T48: derived commercial_use=allowed with an unknown input was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I5 violated:%commercial_use=allowed, but at least one input does not%' THEN
                RAISE NOTICE 'PASS T48: commercial_use violation rejected at COMMIT (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T48');
            ELSE
                RAISE EXCEPTION 'FAIL T48: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T49: derived correctly does not claim commercial_use=allowed when
-- its input is 'unknown' (should succeed) -- positive counterpart to T48.
-- ============================================================================

\echo '### TEST T49: derived commercial_use not allowed, matching an unknown input (should succeed)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_input_fact_id   uuid;
    v_derived_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t49_field', '"input_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:46e29d1835533f9dfef783161eba2d64f8caf1b6a7024c3e5b48aba24b74fb19', now(), 'https://example.com',
        'test.unknown_commercial', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t49_field', '"derived"'::jsonb, 'derived',
        'v1.0', 'test.claims_commercial_unknown',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    INSERT INTO fact_input (fact_id, input_fact_id, ordinal, role)
    VALUES (v_derived_fact_id, v_input_fact_id, 1, 'test_input');

    SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

    RAISE NOTICE 'PASS T49: derived fact correctly not claiming commercial_use=allowed accepted (id=%)', v_derived_fact_id;
    INSERT INTO test_pass VALUES ('T49');
END $$;

-- ============================================================================
-- TEST T50: input requires attribution, derived does not carry it forward
-- (0029) -- attribution is sticky, not a permission subset.
-- ============================================================================

\echo '### TEST T50: input requires attribution, derived does not (should fail)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_input_fact_id   uuid;
    v_derived_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t50_field', '"input_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:af9a79c43ff57207f122898e73ab04eb8178f6d05ad9e9a0287566337fc68fe3', now(), 'https://example.com',
        'test.attribution_required', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t50_field', '"derived"'::jsonb, 'derived',
        'v1.0', 'test.no_attribution',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    BEGIN
        INSERT INTO fact_input (fact_id, input_fact_id, ordinal, role)
        VALUES (v_derived_fact_id, v_input_fact_id, 1, 'test_input');

        SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

        RAISE EXCEPTION 'FAIL T50: derived fact dropping a required attribution was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I5 violated:%does not require attribution, but at least one input does%' THEN
                RAISE NOTICE 'PASS T50: attribution violation rejected at COMMIT (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T50');
            ELSE
                RAISE EXCEPTION 'FAIL T50: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T51: input requires attribution, derived carries it forward too
-- (should succeed) -- positive counterpart to T50.
-- ============================================================================

\echo '### TEST T51: input requires attribution, derived carries it forward (should succeed)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_input_fact_id   uuid;
    v_derived_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t51_field', '"input_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:af9a79c43ff57207f122898e73ab04eb8178f6d05ad9e9a0287566337fc68fe3', now(), 'https://example.com',
        'test.attribution_required', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t51_field', '"derived"'::jsonb, 'derived',
        'v1.0', 'test.attribution_carried',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    INSERT INTO fact_input (fact_id, input_fact_id, ordinal, role)
    VALUES (v_derived_fact_id, v_input_fact_id, 1, 'test_input');

    SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

    RAISE NOTICE 'PASS T51: derived fact correctly carrying required attribution accepted (id=%)', v_derived_fact_id;
    INSERT INTO test_pass VALUES ('T51');
END $$;

-- ============================================================================
-- TEST T52: a licence_channel row cannot be updated (0033) --
-- licence_channel_no_update(), an unconditional raise mirroring
-- licence_no_update/rule_no_update/snapshot_no_update. Like T41/T42/T43,
-- the licence id below carries a fresh gen_random_uuid() suffix: licence
-- is immutable (0027), so a fixed literal id would collide with a prior
-- run's row on this suite's second execution in the same database.
-- ============================================================================

\echo '### TEST T52: UPDATE licence_channel (should fail)'

DO $$
DECLARE
    v_licence_id text := 'test.t52_licence-' || gen_random_uuid()::text;
BEGIN
    INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution, observed_at)
    VALUES (v_licence_id, 'Test Licence T52', 'open', 'allowed', 'allowed', now());

    INSERT INTO licence_channel (licence_id, channel, allowed, rationale)
    VALUES (v_licence_id, 'free_snapshot', false, 'Test fixture T52: initial state, denied pending review');

    BEGIN
        UPDATE licence_channel SET allowed = true WHERE licence_id = v_licence_id AND channel = 'free_snapshot';
        RAISE EXCEPTION 'FAIL T52: UPDATE licence_channel was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'B2/I6 violated:%is immutable%' THEN
                RAISE NOTICE 'PASS T52: licence_channel update rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T52');
            ELSE
                RAISE EXCEPTION 'FAIL T52: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T53: a licence_channel row cannot be deleted (0033) --
-- licence_channel_no_delete().
-- ============================================================================

\echo '### TEST T53: DELETE FROM licence_channel (should fail)'

DO $$
DECLARE
    v_licence_id text := 'test.t53_licence-' || gen_random_uuid()::text;
BEGIN
    INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution, observed_at)
    VALUES (v_licence_id, 'Test Licence T53', 'open', 'allowed', 'allowed', now());

    INSERT INTO licence_channel (licence_id, channel, allowed, rationale)
    VALUES (v_licence_id, 'free_snapshot', false, 'Test fixture T53: initial state, denied pending review');

    BEGIN
        DELETE FROM licence_channel WHERE licence_id = v_licence_id AND channel = 'free_snapshot';
        RAISE EXCEPTION 'FAIL T53: DELETE FROM licence_channel was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'B2/I6 violated:%cannot be deleted%' THEN
                RAISE NOTICE 'PASS T53: licence_channel delete rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T53');
            ELSE
                RAISE EXCEPTION 'FAIL T53: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T54: a NEW licence_channel row can always be inserted (0033) --
-- immutability blocks editing an existing row, not creating a new one.
-- The permissive-no-op control for this trigger pair: T52/T53 alone would
-- pass equally well against a BEFORE UPDATE/DELETE trigger body that
-- raised unconditionally on every operation INCLUDING INSERT, if one had
-- mistakenly been attached to the wrong event -- a negative test alone
-- cannot distinguish "blocks only UPDATE/DELETE" from "blocks everything"
-- (the exact class of bug T31-T35 closed for the composite FKs, and the
-- reason 0027 itself carries the equivalent T43). This proves INSERT is
-- still live.
-- ============================================================================

\echo '### TEST T54: INSERT a new licence_channel row (should succeed)'

DO $$
DECLARE
    v_licence_id text := 'test.t54_licence-' || gen_random_uuid()::text;
BEGIN
    INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution, observed_at)
    VALUES (v_licence_id, 'Test Licence T54', 'open', 'allowed', 'allowed', now());

    INSERT INTO licence_channel (licence_id, channel, allowed, rationale)
    VALUES (v_licence_id, 'free_snapshot', true, 'Test fixture T54: new row, proves the lock blocks only UPDATE/DELETE, not INSERT');

    RAISE NOTICE 'PASS T54: new licence_channel row accepted (licence_id=%)', v_licence_id;
    INSERT INTO test_pass VALUES ('T54');
END $$;

-- ============================================================================
-- TEST T55: a parcel with NULL apn is accepted (0034) -- the parcel
-- identity diagnostic found 9 features in the real source with a
-- genuinely blank APN, acknowledged by the source's own reviewers
-- ("No APN, data reviewer correction."), not an ingest defect to reject.
-- Plain constraint change (apn NOT NULL dropped), no trigger/function
-- body involved -- no permissive-no-op control applies here, unlike
-- T52-T54.
-- ============================================================================

\echo '### TEST T55: parcel with NULL apn (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    INSERT INTO parcel (jurisdiction_id, apn, geom)
    VALUES ('test_ca_san_jose', NULL, ST_Multi(ST_SetSRID(ST_GeomFromText(
        'POLYGON((-121.9 37.3, -121.9 37.31, -121.89 37.31, -121.89 37.3, -121.9 37.3))'), 4326)))
    RETURNING id INTO v_parcel_id;

    RAISE NOTICE 'PASS T55: parcel with NULL apn accepted (id=%)', v_parcel_id;
    INSERT INTO test_pass VALUES ('T55');
END $$;

-- ============================================================================
-- TEST T56: two parcels sharing the same (jurisdiction_id, apn) are both
-- accepted (0034) -- the diagnostic found 49 real APN collisions across
-- 102 features in the source, none of which were the same legal parcel
-- exported twice (see 0034's header for the full evidence). Fresh
-- uuid-suffixed apn, matching this file's top-of-run convention, so this
-- test can never collide with a previous run's row -- unlike licence/
-- licence_channel, parcel carries no immutability trigger, but the shared
-- apn value itself must still be unique to THIS run to keep the test
-- meaningful (proving two DIFFERENT parcels share one apn, not that the
-- same literal string merely appears once more).
-- ============================================================================

\echo '### TEST T56: two parcels sharing one apn (should succeed)'

DO $$
DECLARE
    v_shared_apn text := 'TEST-DUP-' || gen_random_uuid()::text;
    v_parcel_id_1 uuid;
    v_parcel_id_2 uuid;
BEGIN
    INSERT INTO parcel (jurisdiction_id, apn, geom)
    VALUES ('test_ca_san_jose', v_shared_apn, ST_Multi(ST_SetSRID(ST_GeomFromText(
        'POLYGON((-121.9 37.3, -121.9 37.31, -121.89 37.31, -121.89 37.3, -121.9 37.3))'), 4326)))
    RETURNING id INTO v_parcel_id_1;

    INSERT INTO parcel (jurisdiction_id, apn, geom)
    VALUES ('test_ca_san_jose', v_shared_apn, ST_Multi(ST_SetSRID(ST_GeomFromText(
        'POLYGON((-121.5 37.5, -121.5 37.51, -121.49 37.51, -121.49 37.5, -121.5 37.5))'), 4326)))
    RETURNING id INTO v_parcel_id_2;

    RAISE NOTICE 'PASS T56: two parcels sharing apn=% accepted (id1=%, id2=%)', v_shared_apn, v_parcel_id_1, v_parcel_id_2;
    INSERT INTO test_pass VALUES ('T56');
END $$;

-- ============================================================================
-- TEST T57: current_fact_at(now()) is row-for-row identical to current_fact
-- (0036) -- proves the matview's redefinition (SELECT * FROM
-- current_fact_at(now())) produces exactly what the old inline query
-- produced, over the full, accumulated fixture set every prior test in
-- this file has built up (a global comparison, not scoped to one fixture
-- -- deliberately: the stronger claim is that the two never disagree,
-- not that they agree on one hand-picked row). REFRESH first: nothing
-- else in this file refreshes current_fact, so without it the matview
-- would still hold its CREATE-time (empty) snapshot and the comparison
-- would show a spurious mismatch that is not this test's concern.
-- ============================================================================

\echo '### TEST T57: current_fact_at(now()) matches current_fact exactly (should succeed)'

DO $$
DECLARE
    v_only_in_matview  bigint;
    v_only_in_function bigint;
BEGIN
    REFRESH MATERIALIZED VIEW current_fact;

    SELECT count(*) INTO v_only_in_matview
      FROM (SELECT * FROM current_fact EXCEPT SELECT * FROM current_fact_at(now())) x;
    SELECT count(*) INTO v_only_in_function
      FROM (SELECT * FROM current_fact_at(now()) EXCEPT SELECT * FROM current_fact) x;

    IF v_only_in_matview <> 0 OR v_only_in_function <> 0 THEN
        RAISE EXCEPTION 'FAIL T57: current_fact and current_fact_at(now()) disagree -- % rows only in current_fact, % rows only in current_fact_at(now())',
            v_only_in_matview, v_only_in_function;
    END IF;

    RAISE NOTICE 'PASS T57: current_fact_at(now()) matches current_fact exactly (0 rows differ, either direction)';
    INSERT INTO test_pass VALUES ('T57');
END $$;

-- ============================================================================
-- TEST T58: current_fact_at(ts) excludes a fact recorded AFTER ts, even
-- when that fact's valid-time window (effective_from/effective_to)
-- covers ts (0036) -- the look-ahead-bias case C5 exists to close. A
-- fact with effective_from in 2019 but recorded_at forced to 2025 must
-- NOT appear when reconstructing belief as of 2020-06-01: the system did
-- not know it yet. It DOES appear in current_fact_at(now()), proving the
-- fact itself is live and correctly resolved -- the exclusion is
-- specific to the past ts, not a broken insert.
-- ============================================================================

\echo '### TEST T58: current_fact_at(past ts) excludes a not-yet-recorded fact (should succeed)'

DO $$
DECLARE
    v_parcel_id      uuid;
    v_fact_id        uuid;
    v_seen_at_past   boolean;
    v_seen_at_now    boolean;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, recorded_at, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t58_field', '"value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28',
        '2019-01-01'::timestamptz, 'https://example.com', 'test.cc0', 'high', 'rule_1',
        '2019-01-01'::timestamptz, '2025-01-01'::timestamptz, 'v1.0'
    ) RETURNING id INTO v_fact_id;

    SELECT EXISTS (
        SELECT 1 FROM current_fact_at('2020-06-01'::timestamptz) WHERE id = v_fact_id
    ) INTO v_seen_at_past;

    SELECT EXISTS (
        SELECT 1 FROM current_fact_at(now()) WHERE id = v_fact_id
    ) INTO v_seen_at_now;

    IF v_seen_at_past THEN
        RAISE EXCEPTION 'FAIL T58: fact recorded 2025-01-01 wrongly visible in current_fact_at(2020-06-01) -- look-ahead bias';
    END IF;
    IF NOT v_seen_at_now THEN
        RAISE EXCEPTION 'FAIL T58: fact wrongly absent from current_fact_at(now()) -- not an insert problem, exclusion should be specific to the past ts';
    END IF;

    RAISE NOTICE 'PASS T58: fact excluded from current_fact_at(2020-06-01), present in current_fact_at(now()) (id=%)', v_fact_id;
    INSERT INTO test_pass VALUES ('T58');
END $$;

-- ============================================================================
-- TEST T59: a newly INSERTed licence_channel row gets created_at
-- populated from the column's DEFAULT now() (0037) -- proves the
-- two-step ALTER (ADD COLUMN, then SET DEFAULT) actually left a live
-- default in effect for new rows, not just that it left old rows NULL
-- (0037's own migration already confirmed the NULL half directly
-- against a scratch database before landing; this is the permanent,
-- rerun-safe positive half). Fresh uuid-suffixed licence id, matching
-- T52-T54's convention -- licence is immutable, so a literal id would
-- collide with a prior run's row.
-- ============================================================================

\echo '### TEST T59: new licence_channel row gets created_at from DEFAULT now() (should succeed)'

DO $$
DECLARE
    v_licence_id text := 'test.t59_licence-' || gen_random_uuid()::text;
    v_created_at timestamptz;
BEGIN
    INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution, observed_at)
    VALUES (v_licence_id, 'Test Licence T59', 'open', 'allowed', 'allowed', now());

    INSERT INTO licence_channel (licence_id, channel, allowed, rationale)
    VALUES (v_licence_id, 'free_snapshot', false, 'Test fixture T59: created_at should default to now()');

    SELECT created_at INTO v_created_at
      FROM licence_channel WHERE licence_id = v_licence_id AND channel = 'free_snapshot';

    IF v_created_at IS NULL THEN
        RAISE EXCEPTION 'FAIL T59: created_at is NULL on a newly inserted licence_channel row -- DEFAULT now() did not apply';
    END IF;
    IF v_created_at < now() - interval '1 minute' OR v_created_at > now() + interval '1 minute' THEN
        RAISE EXCEPTION 'FAIL T59: created_at (%) is not close to now() -- unexpected value', v_created_at;
    END IF;

    RAISE NOTICE 'PASS T59: new licence_channel row got created_at=% from DEFAULT now()', v_created_at;
    INSERT INTO test_pass VALUES ('T59');
END $$;

-- ============================================================================
-- TEST T60: property_file.refusals rejects a code outside §9's vocabulary
-- (0038's original vocabulary, widened by 0053 -- ELECTION_REQUIRED,
-- ELECTION_NOT_SUPPORTED, P34, README finding #35 -- and again by 0055 --
-- PARCEL_REFERENCE_UNKNOWN, PARCEL_NO_FACTS, P37, README finding #40),
-- enforced since P10 by what is now 0055's
-- property_file_refusal_codes_known_parcel. Renamed three times, same
-- DROP+ADD-with-a-new-name discipline 0020_lifecycle_constraints.sql
-- established each time: 0038's own original name,
-- property_file_refusal_codes_known, was DROPped and replaced by 0048's
-- property_file_refusal_codes_known_shape_checked (tightened NULL/shape
-- validation), which was DROPped and replaced by 0053's
-- property_file_refusal_codes_known_election (vocabulary widened), which
-- was itself DROPped and replaced by 0055's own name below (vocabulary
-- widened again; see 0055's own header for why the REFUSAL_CODES_BEGIN/END
-- sync-check markers moved here too, again).
-- Proves the CHECK is actually wired to refusals_codes_valid() and
-- actually fires, not just that the function returns false in isolation
-- (already confirmed directly against a scratch database while writing
-- 0038 -- this is the permanent, rerun-safe regression guard).
-- ============================================================================

\echo '### TEST T60: property_file.refusals with an unknown code (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, refusals,
            payload, payload_hash, compose_ms
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
            'v1.0', 'v1.0', false,
            '[{"code": "MADE_UP_CODE", "stage": "L8", "message": "not a real code", "detail": {}}]'::jsonb,
            '{}'::jsonb, 'testhash_t60', 1
        );
        RAISE EXCEPTION 'FAIL T60: property_file with an unknown refusal code was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_refusal_codes_known_parcel' THEN
                RAISE NOTICE 'PASS T60: unknown refusal code rejected';
                INSERT INTO test_pass VALUES ('T60');
            ELSE
                RAISE EXCEPTION 'FAIL T60: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T61: property_file.refusals accepts every code §9 actually names
-- (0038). The negative case (T60) alone would pass even if the CHECK
-- rejected everything unconditionally -- this is the positive control,
-- proving the vocabulary itself, not just the mechanism.
-- ============================================================================

\echo '### TEST T61: property_file.refusals with a real §9 code (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_id        uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals,
        payload, payload_hash, compose_ms
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "RIGHTS_BLOCKED", "stage": "L8", "message": "test", "detail": {}}]'::jsonb,
        '{}'::jsonb, 'testhash_t61', 1
    )
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        RAISE EXCEPTION 'FAIL T61: property_file with a valid §9 refusal code was rejected';
    END IF;

    RAISE NOTICE 'PASS T61: property_file % with a valid §9 refusal code accepted', v_id;
    INSERT INTO test_pass VALUES ('T61');
END $$;

-- ============================================================================
-- TEST T62: fact_licence_validate() resists a pg_temp.fact_input shadow
-- (0039). Reproduces the exact bypass 0039's header documents: a session
-- creates a temp table also named fact_input, then inserts the real
-- linking row into public.fact_input explicitly -- pre-0039, the
-- trigger's own internal "SELECT ... FROM fact_input" resolved to the
-- empty pg_temp relation, saw has_inputs=false, and returned NULL before
-- ever validating I5, so the over-permissive derived fact (same shape as
-- T48: claims commercial_use=allowed against an unknown-commercial
-- input) committed unchecked. Same DEFERRABLE INITIALLY DEFERRED
-- constraint as T46-T51: SET CONSTRAINTS ... IMMEDIATE forces the
-- trigger to fire inside this block instead of waiting for an outer
-- COMMIT this DO block can't issue. The CREATE TEMP TABLE is undone by
-- PL/pgSQL's implicit savepoint rollback the moment the EXCEPTION block
-- catches the expected raise -- confirmed directly before relying on it
-- (a throwaway BEGIN/EXCEPTION block with no relation to this test) --
-- so this test cannot leak a shadow into any test that runs after it.
--
-- DISCARD PLANS is load-bearing here, found by bisection, not guessed:
-- this test read as PASSING even against the pre-0039 (still vulnerable)
-- function when run after the earlier tests in this file, but reliably
-- reproduced the real bypass in isolation (this file's seed section plus
-- only this test). Cause, confirmed directly: PL/pgSQL caches a resolved
-- execution plan for each internal statement the first time it runs in a
-- session, and does not revisit that resolution just because a new
-- same-named temp table later appears -- there is no dependency from an
-- already-cached plan to an object that didn't exist when the plan was
-- built. Once ANY earlier statement in this session's history caused
-- fact_licence_validate()'s internal fact_input query to resolve and
-- cache against public.fact_input, every later call keeps using that
-- resolution regardless of a temp table created afterward -- masking the
-- exact vulnerability this test exists to catch, for a reason that has
-- nothing to do with whether 0039's fix is applied. DISCARD PLANS
-- forces a fresh resolution, matching what an actually fresh connection
-- (a new pooled worker, an attacker's own session) would see -- the
-- realistic vulnerable case, not an artifact of this file's own test
-- ordering. current_fact_at() (T63, below) needs no such treatment:
-- it's LANGUAGE sql, not plpgsql, and does not exhibit this masking --
-- confirmed directly, not assumed, by the same bisection.
-- ============================================================================

\echo '### TEST T62: fact_licence_validate() rejects an over-permissive derived fact even with pg_temp.fact_input shadowing (should fail)'

DO $$
DECLARE
    v_parcel_id       uuid;
    v_input_fact_id   uuid;
    v_derived_fact_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t62_field', '"input_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:46e29d1835533f9dfef783161eba2d64f8caf1b6a7024c3e5b48aba24b74fb19', now(), 'https://example.com',
        'test.unknown_commercial', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_input_fact_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t62_field', '"derived"'::jsonb, 'derived',
        'v1.0', 'test.claims_commercial_allowed',
        'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_derived_fact_id;

    BEGIN
        -- Force a fresh plan resolution for this session -- see the test
        -- header for why this is load-bearing, not defensive noise.
        DISCARD PLANS;

        -- The attack: shadow fact_input with an empty temp relation of the
        -- same shape, then insert the REAL linking row explicitly
        -- qualified -- an attacker wants the row to actually exist in
        -- public.fact_input, only the trigger's own internal read fooled.
        CREATE TEMP TABLE fact_input (
            fact_id uuid, input_fact_id uuid, ordinal smallint, role text
        );

        INSERT INTO public.fact_input (fact_id, input_fact_id, ordinal, role)
        VALUES (v_derived_fact_id, v_input_fact_id, 1, 'test_input');

        SET CONSTRAINTS fact_licence_inheritance IMMEDIATE;

        RAISE EXCEPTION 'FAIL T62: over-permissive derived fact was accepted despite pg_temp.fact_input shadowing -- I5 gate bypassed';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I5 violated:%commercial_use=allowed, but at least one input does not%' THEN
                RAISE NOTICE 'PASS T62: I5 violation still rejected under pg_temp.fact_input shadowing (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T62');
            ELSE
                RAISE EXCEPTION 'FAIL T62: wrong error (shadow bypass may still be live): %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T63: current_fact_at() resists a pg_temp.fact shadow (0039).
-- Reproduces the exact bypass 0039's header documents: pre-0039, a
-- session-local CREATE TEMP TABLE fact (LIKE public.fact INCLUDING ALL)
-- made current_fact_at() return zero rows for a parcel that genuinely has
-- current facts, because its internal "FROM fact f" resolved to the
-- empty temp relation instead of public.fact. Explicit DROP TABLE at the
-- end, not a caught exception -- this test expects success, not a raise,
-- so there is no EXCEPTION block to rely on for savepoint cleanup the
-- way T62 has; leaving the temp table in place would shadow "fact" for
-- every test that runs after this one in the same session.
-- ============================================================================

\echo '### TEST T63: current_fact_at() reads public.fact, not a pg_temp.fact shadow (should succeed)'

DO $$
DECLARE
    v_parcel_id    uuid;
    v_fact_id      uuid;
    v_shadowed_ct  int;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t63_field', '"real_value"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:46e29d1835533f9dfef783161eba2d64f8caf1b6a7024c3e5b48aba24b74fb19', now(), 'https://example.com',
        'test.unknown_commercial', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_id;

    CREATE TEMP TABLE fact (LIKE public.fact INCLUDING ALL);  -- empty shadow

    SELECT count(*) INTO v_shadowed_ct
      FROM current_fact_at(now())
     WHERE parcel_id = v_parcel_id AND field_key = 'test.t63_field';

    DROP TABLE fact;  -- un-shadow before anything else in this session runs

    IF v_shadowed_ct <> 1 THEN
        RAISE EXCEPTION 'FAIL T63: current_fact_at() found % rows for test.t63_field under pg_temp.fact shadowing, expected 1 -- reading the shadow instead of public.fact', v_shadowed_ct;
    END IF;

    RAISE NOTICE 'PASS T63: current_fact_at() correctly read public.fact (id=%) despite pg_temp.fact shadowing', v_fact_id;
    INSERT INTO test_pass VALUES ('T63');
END $$;

-- ============================================================================
-- TEST T64: fact_no_destructive_update() rejects a change to EVERY fact
-- column, not just the ones a hand-maintained list happened to name (0040).
-- Reproduces the exact bypass 0040's header documents: pre-0040,
-- UPDATE fact SET superseded_at = now(), source_asserted_as_of = '2099-...'
-- committed cleanly, because source_asserted_as_of (0028) was never added
-- to fact_no_destructive_update's hand-enumerated OR chain -- along with
-- jurisdiction_id (0022), supersedes_fact_id and supersession_reason
-- (0025), none of which the original trigger's author could have named,
-- since none of those columns existed yet in 0007. This test attempts
-- every column information_schema.columns actually reports for fact
-- today (excluding superseded_at, the one permitted mutation) -- driven
-- by the live catalog, not a copy of the column list that could itself
-- go stale the same way the trigger's old OR chain did. Confirmed
-- directly before writing this migration's fix: fact_no_destructive_update
-- fires as a BEFORE trigger, ahead of FK/CHECK constraint enforcement, so
-- an arbitrary (even referentially-invalid) replacement value is caught
-- by I4 first regardless of whether it would also fail some other
-- constraint -- no column needs a semantically "real" replacement value
-- for this test to be meaningful.
-- ============================================================================

\echo '### TEST T64: fact_no_destructive_update() rejects a change to every fact column while superseding (should fail, every column)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_fact_id    uuid;
    v_col        record;
    v_new_value  text;
    v_tested     int := 0;
    v_rejected   int := 0;
    v_failures   text := '';
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, unit, local_verbatim,
        source_id, source_url, layer_item_id, snapshot_id, method,
        retrieved_at, source_published_at, source_cadence_stated,
        effective_from, effective_to, licence_id, confidence,
        confidence_rule_id, conflict, method_version, ruleset_version,
        pack_version, source_asserted_as_of
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t64_field', '"initial"'::jsonb, 'unit_a', 'verbatim_a',
        'test_ca_san_jose.test_source', 'https://example.com', 'layer_a', 'test_ca_san_jose.test_source:sha256:46e29d1835533f9dfef783161eba2d64f8caf1b6a7024c3e5b48aba24b74fb19', 'direct',
        now(), now(), 'daily',
        now(), NULL, 'test.unknown_commercial', 'high',
        'rule_1', 'agree', 'v1', 'v1',
        'v1.0', now()
    ) RETURNING id INTO v_fact_id;

    FOR v_col IN
        SELECT column_name, udt_name
          FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = 'fact'
           AND column_name <> 'superseded_at'
         ORDER BY ordinal_position
    LOOP
        v_tested := v_tested + 1;
        v_new_value := CASE v_col.udt_name
            WHEN 'uuid'                 THEN quote_literal(gen_random_uuid()::text) || '::uuid'
            WHEN 'jsonb'                THEN quote_literal('"t64_mutated"') || '::jsonb'
            WHEN 'timestamptz'          THEN quote_literal((now() + interval '1 day')::text) || '::timestamptz'
            WHEN 'access_method'        THEN quote_literal('derived') || '::access_method'
            WHEN 'confidence_level'     THEN quote_literal('low') || '::confidence_level'
            WHEN 'conflict_state'       THEN quote_literal('conflicts') || '::conflict_state'
            WHEN 'supersession_reason'  THEN quote_literal('world_change') || '::supersession_reason'
            ELSE quote_literal('t64_mutated_' || v_col.column_name)
        END;

        BEGIN
            EXECUTE format(
                'UPDATE fact SET superseded_at = now(), %I = %s WHERE id = %L',
                v_col.column_name, v_new_value, v_fact_id
            );
            v_failures := v_failures || v_col.column_name || ' ';
        EXCEPTION
            WHEN raise_exception THEN
                IF SQLERRM LIKE 'I4 violated:%' THEN
                    v_rejected := v_rejected + 1;
                ELSE
                    RAISE EXCEPTION 'FAIL T64: column % raised an unexpected error: %', v_col.column_name, SQLERRM;
                END IF;
            WHEN invalid_text_representation OR undefined_column OR datatype_mismatch THEN
                RAISE EXCEPTION 'FAIL T64: test fixture itself is wrong for column % (%): %', v_col.column_name, v_col.udt_name, SQLERRM;
            WHEN OTHERS THEN
                -- Any other error class (FK violation, CHECK violation, ...)
                -- means some OTHER constraint coincidentally blocked this
                -- value, not that I4 caught it -- not the same guarantee.
                -- A different mutated value for the same column that
                -- happened not to also trip that unrelated constraint
                -- would sail through undetected. Fails loudly rather than
                -- letting an accidental block read as I4 doing its job.
                RAISE EXCEPTION 'FAIL T64: column % was not rejected by I4 -- caught only by an unrelated constraint instead (%): %', v_col.column_name, SQLSTATE, SQLERRM;
        END;
    END LOOP;

    IF v_rejected <> v_tested THEN
        RAISE EXCEPTION 'FAIL T64: % of % fact columns were NOT rejected when mutated alongside a supersede: %', (v_tested - v_rejected), v_tested, v_failures;
    END IF;

    RAISE NOTICE 'PASS T64: all % fact columns (every column except superseded_at) rejected when mutated alongside a legitimate supersede', v_tested;
    INSERT INTO test_pass VALUES ('T64');
END $$;

-- ============================================================================
-- TEST T65: rule_no_destructive_update() rejects a change to EVERY rule
-- column while retiring effective_to, the same treatment 0040 gives
-- fact_no_destructive_update -- and the identical exposure: rule's OR
-- chain would silently miss any column added to rule after 0013, exactly
-- as fact's missed jurisdiction_id/supersedes_fact_id/supersession_reason/
-- source_asserted_as_of. Driven by the live catalog for the same reason
-- as T64.
-- ============================================================================

\echo '### TEST T65: rule_no_destructive_update() rejects a change to every rule column while retiring effective_to (should fail, every column)'

DO $$
DECLARE
    v_rule_id   text := 'test-t65-' || gen_random_uuid()::text;
    v_col       record;
    v_new_value text;
    v_tested    int := 0;
    v_rejected  int := 0;
    v_failures  text := '';
BEGIN
    INSERT INTO rule (
        id, jurisdiction_id, rule_key, version, effective_from, citation,
        source_text_uri, params, pack_version, authored_by, reviewed_by,
        review_mode, reviewed_at
    ) VALUES (
        v_rule_id, 'test_ca_san_jose', 'test.t65.rule.' || v_rule_id, 1, CURRENT_DATE,
        'Test citation', 'https://example.com/rule-source', '{}'::jsonb, 'v1.0',
        'author_a', 'reviewer_b', 'independent', now()
    );

    FOR v_col IN
        SELECT column_name, udt_name
          FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = 'rule'
           AND column_name <> 'effective_to'
         ORDER BY ordinal_position
    LOOP
        v_tested := v_tested + 1;
        v_new_value := CASE v_col.udt_name
            WHEN 'jsonb'        THEN quote_literal('{"mutated": true}') || '::jsonb'
            WHEN 'date'         THEN quote_literal((CURRENT_DATE + 1)::text) || '::date'
            WHEN 'timestamptz'  THEN quote_literal((now() + interval '1 day')::text) || '::timestamptz'
            WHEN 'int4'         THEN '999'
            WHEN 'review_mode'  THEN quote_literal('solo_founder_attestation') || '::review_mode'
            ELSE quote_literal('t65_mutated_' || v_col.column_name)
        END;

        BEGIN
            EXECUTE format(
                'UPDATE rule SET effective_to = CURRENT_DATE, %I = %s WHERE id = %L',
                v_col.column_name, v_new_value, v_rule_id
            );
            v_failures := v_failures || v_col.column_name || ' ';
        EXCEPTION
            WHEN raise_exception THEN
                IF SQLERRM LIKE 'I18 violated:%' THEN
                    v_rejected := v_rejected + 1;
                ELSE
                    RAISE EXCEPTION 'FAIL T65: column % raised an unexpected error: %', v_col.column_name, SQLERRM;
                END IF;
            WHEN invalid_text_representation OR undefined_column OR datatype_mismatch THEN
                RAISE EXCEPTION 'FAIL T65: test fixture itself is wrong for column % (%): %', v_col.column_name, v_col.udt_name, SQLERRM;
            WHEN OTHERS THEN
                -- See T64's identical handler for why this is not treated
                -- as an accidental pass.
                RAISE EXCEPTION 'FAIL T65: column % was not rejected by I18 -- caught only by an unrelated constraint instead (%): %', v_col.column_name, SQLSTATE, SQLERRM;
        END;
    END LOOP;

    IF v_rejected <> v_tested THEN
        RAISE EXCEPTION 'FAIL T65: % of % rule columns were NOT rejected when mutated alongside an effective_to retirement: %', (v_tested - v_rejected), v_tested, v_failures;
    END IF;

    RAISE NOTICE 'PASS T65: all % rule columns (every column except effective_to) rejected when mutated alongside a legitimate retirement', v_tested;
    INSERT INTO test_pass VALUES ('T65');
END $$;

-- ============================================================================
-- TEST T66: meta-test -- fact_no_destructive_update() and
-- rule_no_destructive_update()'s deployed source still uses the
-- whole-row comparison, not a hand-enumerated column list. T64/T65 prove
-- every CURRENT column is covered; neither can prove the trigger would
-- stay correct if a future migration reverted to enumeration (adding a
-- new column without adding a new T64/T65-style test would still pass
-- both, silently, the exact failure mode 0040 fixes). Reads the deployed
-- function body from pg_proc directly -- the actual thing that runs, not
-- this migration file's text, which could drift from what's live the
-- same way a comment can. Asserts by count against a known ceiling, not
-- flat zero: fact_no_destructive_update's kept superseded_at special
-- case is written as NEW.superseded_at IS NULL, never as an IS DISTINCT
-- FROM comparison, so zero is the right bound there -- confirmed
-- directly by running this exact assertion, not assumed, which is also
-- how the first version of this test caught its own wrong assumption
-- about rule's bound. rule_no_destructive_update's kept effective_to
-- special case DOES use NEW.effective_to IS DISTINCT FROM
-- OLD.effective_to legitimately (it has to, to detect the one-way
-- NULL -> a date transition) -- exactly one such comparison is correct
-- and expected there, not a regression; two or more would mean a second
-- column got hand-enumerated back in. Also asserts presence of the
-- to_jsonb(...) whole-row pattern in both.
-- ============================================================================

\echo '### TEST T66: fact/rule immutability triggers still use whole-row comparison, not column enumeration (should succeed)'

DO $$
DECLARE
    v_fact_src  text;
    v_rule_src  text;
    v_fact_enum_count int;
    v_rule_enum_count int;
BEGIN
    SELECT prosrc INTO v_fact_src FROM pg_proc WHERE proname = 'fact_no_destructive_update';
    SELECT prosrc INTO v_rule_src FROM pg_proc WHERE proname = 'rule_no_destructive_update';

    IF v_fact_src IS NULL OR v_rule_src IS NULL THEN
        RAISE EXCEPTION 'FAIL T66: could not find fact_no_destructive_update or rule_no_destructive_update in pg_proc';
    END IF;

    SELECT count(*) INTO v_fact_enum_count
      FROM regexp_matches(v_fact_src, 'NEW\.[a-z_]+\s+IS DISTINCT FROM\s+OLD\.[a-z_]+', 'g');
    SELECT count(*) INTO v_rule_enum_count
      FROM regexp_matches(v_rule_src, 'NEW\.[a-z_]+\s+IS DISTINCT FROM\s+OLD\.[a-z_]+', 'g');

    IF v_fact_enum_count <> 0 THEN
        RAISE EXCEPTION 'FAIL T66: fact_no_destructive_update() contains % NEW/OLD IS DISTINCT FROM comparisons, expected 0 (its kept superseded_at special case uses IS NULL, not IS DISTINCT FROM) -- T64 only proves TODAY''s columns are covered, this regressed the whole-row guarantee', v_fact_enum_count;
    END IF;
    IF v_rule_enum_count <> 1 THEN
        RAISE EXCEPTION 'FAIL T66: rule_no_destructive_update() contains % NEW/OLD IS DISTINCT FROM comparisons, expected exactly 1 (its kept effective_to special case legitimately uses one) -- T65 only proves TODAY''s columns are covered, this regressed the whole-row guarantee', v_rule_enum_count;
    END IF;

    IF v_fact_src NOT LIKE '%to_jsonb(NEW)%' OR v_fact_src NOT LIKE '%to_jsonb(OLD)%' THEN
        RAISE EXCEPTION 'FAIL T66: fact_no_destructive_update() no longer contains the whole-row to_jsonb(NEW)/to_jsonb(OLD) comparison';
    END IF;
    IF v_rule_src NOT LIKE '%to_jsonb(NEW)%' OR v_rule_src NOT LIKE '%to_jsonb(OLD)%' THEN
        RAISE EXCEPTION 'FAIL T66: rule_no_destructive_update() no longer contains the whole-row to_jsonb(NEW)/to_jsonb(OLD) comparison';
    END IF;

    RAISE NOTICE 'PASS T66: both triggers'' deployed source uses whole-row to_jsonb comparison, zero column-by-column enumeration';
    INSERT INTO test_pass VALUES ('T66');
END $$;

-- ============================================================================
-- TEST T67: licence_channel.created_at rejects an explicit NULL (0041).
-- Reproduces the exact bypass 0041's header documents: pre-0041,
-- explicitly supplying created_at = NULL bypassed the column's own
-- DEFAULT now() (a DEFAULT only fires when a column is OMITTED, never
-- when NULL is supplied for it), letting a brand-new row falsely claim
-- to predate tracking. NOT NULL closes exactly that path. Positive
-- control immediately after: a normal INSERT that omits created_at
-- entirely still gets a real DEFAULT now() timestamp, proving this
-- migration didn't also break the legitimate case T59 already covers --
-- re-asserted here, briefly, because it's the other half of the same
-- fix, not because T59 needs duplicating.
-- ============================================================================

\echo '### TEST T67: licence_channel.created_at rejects explicit NULL (should fail)'

DO $$
DECLARE
    v_licence_id text := 'test.t67_licence-' || gen_random_uuid()::text;
    v_created_at timestamptz;
BEGIN
    INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution, observed_at)
    VALUES (v_licence_id, 'Test Licence T67', 'open', 'allowed', 'allowed', now());

    BEGIN
        INSERT INTO licence_channel (licence_id, channel, allowed, rationale, created_at)
        VALUES (v_licence_id, 'free_snapshot', false, 'Test fixture T67: explicit NULL should be rejected', NULL);
        RAISE EXCEPTION 'FAIL T67: licence_channel row with explicit created_at=NULL was accepted -- a new row can claim to predate tracking';
    EXCEPTION
        WHEN not_null_violation THEN
            RAISE NOTICE 'PASS T67: explicit created_at=NULL rejected (%)', SQLERRM;
            INSERT INTO test_pass VALUES ('T67');
    END;

    -- Positive control: omitting created_at entirely still gets a real
    -- DEFAULT now() timestamp -- the fix didn't also break the ordinary path.
    INSERT INTO licence_channel (licence_id, channel, allowed, rationale)
    VALUES (v_licence_id, 'api', false, 'Test fixture T67: omitted created_at should still default')
    RETURNING created_at INTO v_created_at;

    IF v_created_at IS NULL THEN
        RAISE EXCEPTION 'FAIL T67: omitting created_at no longer defaults to now() -- got NULL';
    END IF;
END $$;

-- ============================================================================
-- TEST T68: fact_supersession_target_validate() rejects a supersession
-- across different (parcel_id, field_key) (0042). Reproduces the exact
-- bypass 0042's header documents: a fact for one parcel/field claiming
-- supersedes_fact_id against a fact for a completely different
-- parcel/field committed with no error at all, pre-0042.
-- ============================================================================

\echo '### TEST T68: fact supersession across different parcel/field is rejected (should fail)'

DO $$
DECLARE
    v_parcel_a  uuid;
    v_parcel_b  uuid := gen_random_uuid();
    v_fact_a_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_a FROM test_state WHERE key = 'parcel_id';
    INSERT INTO parcel (id, jurisdiction_id, apn) VALUES (v_parcel_b, 'test_ca_san_jose', 'test-t68-' || v_parcel_b::text);

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_a, 'test_ca_san_jose', 'test.t68_field', '"original"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_fact_a_id;

    BEGIN
        -- Different parcel (v_parcel_b, not v_parcel_a) AND a different
        -- field_key -- claims to supersede fact_a anyway.
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
            confidence, confidence_rule_id, effective_from, pack_version,
            supersedes_fact_id, supersession_reason
        ) VALUES (
            v_parcel_b, 'test_ca_san_jose', 'test.t68_field', '"unrelated"'::jsonb, 'derived',
            'v1', 'test.cc0', 'high', 'rule_1', now(), 'v1.0',
            v_fact_a_id, 'world_change'
        );

        SET CONSTRAINTS fact_supersession_target_valid IMMEDIATE;

        RAISE EXCEPTION 'FAIL T68: fact superseding a different parcel''s fact was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I4 violated:%SAME parcel and field%' THEN
                RAISE NOTICE 'PASS T68: cross-parcel supersession rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T68');
            ELSE
                RAISE EXCEPTION 'FAIL T68: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T69: fact_supersession_target_validate() rejects a supersession
-- whose target's own superseded_at was never set (0042). Same-parcel,
-- same-field, but the correct two-statement shape (UPDATE the old fact's
-- superseded_at, THEN/AND insert the new one citing it) never happened
-- -- only the INSERT did. Uses a different method/source than the
-- target so fact_one_current_per_source (0008) doesn't independently
-- block two simultaneously-live facts for the same field before this
-- test can even reach the check it's isolating.
-- ============================================================================

\echo '### TEST T69: fact supersession whose target was never actually superseded is rejected (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_target_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t69_field', '"still_live"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_target_id;

    BEGIN
        -- Same parcel, same field, DIFFERENT method (derived, no source_id)
        -- -- avoids fact_one_current_per_source entirely, isolating the
        -- superseded_at check. Deliberately does NOT set v_target_id's
        -- superseded_at first.
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
            confidence, confidence_rule_id, effective_from, pack_version,
            supersedes_fact_id, supersession_reason
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'test.t69_field', '"claimed_successor"'::jsonb, 'derived',
            'v1', 'test.cc0', 'high', 'rule_1', now(), 'v1.0',
            v_target_id, 'world_change'
        );

        SET CONSTRAINTS fact_supersession_target_valid IMMEDIATE;

        RAISE EXCEPTION 'FAIL T69: fact superseding a still-live (never-retired) target was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I4 violated:%superseded_at was never set%' THEN
                RAISE NOTICE 'PASS T69: supersession of a not-yet-retired target rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T69');
            ELSE
                RAISE EXCEPTION 'FAIL T69: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T70: the correct two-statement supersession (same parcel/field,
-- target's superseded_at set in the same transaction) still succeeds
-- (0042) -- positive control proving T68/T69 reject the right thing,
-- not everything.
-- ============================================================================

\echo '### TEST T70: correct same-parcel/field supersession with target properly retired succeeds (should succeed)'

DO $$
DECLARE
    v_parcel_id    uuid;
    v_target_id    uuid;
    v_successor_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t70_field', '"original"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_target_id;

    UPDATE fact SET superseded_at = now() WHERE id = v_target_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, method_version, licence_id,
        confidence, confidence_rule_id, effective_from, pack_version,
        supersedes_fact_id, supersession_reason
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t70_field', '"corrected"'::jsonb, 'derived',
        'v1', 'test.cc0', 'high', 'rule_1', now(), 'v1.0',
        v_target_id, 'source_correction'
    ) RETURNING id INTO v_successor_id;

    SET CONSTRAINTS fact_supersession_target_valid IMMEDIATE;

    RAISE NOTICE 'PASS T70: fact % correctly supersedes properly-retired fact %', v_successor_id, v_target_id;
    INSERT INTO test_pass VALUES ('T70');
END $$;

-- ============================================================================
-- TEST T71: fact_supersession_target_validate() rejects a RETRIEVED
-- successor superseding a fact from a DIFFERENT source_id (0044).
-- Reproduces the exact bug P4 found: ingest_parcels.py's disappearance
-- cascade superseded a ca_san_jose.building_permits_active fact with a
-- successor citing ca_san_jose.parcels' own provenance -- committed
-- cleanly pre-0044, because fact_one_current_per_source is partial-unique
-- PER SOURCE (a cross-source successor never collides) and 0042 never
-- checked source_id at all.
-- ============================================================================

\echo '### TEST T71: cross-source RETRIEVED supersession is rejected (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_target_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t71_field', '"original"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_target_id;

    UPDATE fact SET superseded_at = now() WHERE id = v_target_id;

    BEGIN
        -- Same parcel, same field, target correctly retired -- but the
        -- successor is RETRIEVED (not derived) and comes from a DIFFERENT
        -- source (test_source_b, not test_source).
        INSERT INTO fact (
            parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
            retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
            effective_from, pack_version, supersedes_fact_id, supersession_reason
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'test.t71_field', '"claimed_successor"'::jsonb, 'bulk',
            'test_ca_san_jose.test_source_b', 'test_ca_san_jose.test_source_b:sha256:2892e288adb59f59419b9351ed48cbb14e45d0556547da33f3543e5e85b71c8d', now(), 'https://example.com/b',
            'test.cc0', 'high', 'rule_1', now(), 'v1.0',
            v_target_id, 'unknown'
        );

        SET CONSTRAINTS fact_supersession_target_valid IMMEDIATE;

        RAISE EXCEPTION 'FAIL T71: cross-source retrieved supersession was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM LIKE 'I4 violated:%SAME source_id%' THEN
                RAISE NOTICE 'PASS T71: cross-source retrieved supersession rejected (%)', SQLERRM;
                INSERT INTO test_pass VALUES ('T71');
            ELSE
                RAISE EXCEPTION 'FAIL T71: wrong error: %', SQLERRM;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T72: same-source RETRIEVED supersession still succeeds (0044
-- positive control -- proves T71 rejects cross-source specifically, not
-- every retrieved-supersedes-retrieved supersession).
-- ============================================================================

\echo '### TEST T72: same-source RETRIEVED supersession still succeeds (should succeed)'

DO $$
DECLARE
    v_parcel_id    uuid;
    v_target_id    uuid;
    v_successor_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t72_field', '"original"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0'
    ) RETURNING id INTO v_target_id;

    UPDATE fact SET superseded_at = now() WHERE id = v_target_id;

    INSERT INTO fact (
        parcel_id, jurisdiction_id, field_key, value, method, source_id, snapshot_id,
        retrieved_at, source_url, licence_id, confidence, confidence_rule_id,
        effective_from, pack_version, supersedes_fact_id, supersession_reason
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'test.t72_field', '"corrected"'::jsonb, 'direct',
        'test_ca_san_jose.test_source', 'test_ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28', now(), 'https://example.com',
        'test.cc0', 'high', 'rule_1', now(), 'v1.0',
        v_target_id, 'unknown'
    ) RETURNING id INTO v_successor_id;

    SET CONSTRAINTS fact_supersession_target_valid IMMEDIATE;

    RAISE NOTICE 'PASS T72: fact % (same source as its target) correctly supersedes fact %', v_successor_id, v_target_id;
    INSERT INTO test_pass VALUES ('T72');
END $$;

-- ============================================================================
-- TEST T73: a second OPEN exception for the same (parcel_id, detector_key,
-- detector_version, reason) is rejected. Originally 0045's index
-- (parcel_exception_one_open_per_detector_reason); DROPped and replaced by
-- 0049's parcel_exception_one_open_per_detector_reason_coalesced (P10,
-- README finding #19) -- COALESCE has no effect on this test's own probe
-- (a real, non-null 'reason' value), so the behavior T73 checks is
-- unchanged, only the constraint name enforcing it. P5 finding:
-- insert_exceptions() is a bare INSERT with no dedup, and parcel_exception
-- had no uniqueness of any kind -- a second reconcile of an unchanged
-- snapshot would double every open exception it produced. Positive control
-- below (T74) proves a DIFFERENT reason for the same parcel/detector/version
-- is NOT blocked.
-- ============================================================================

\echo '### TEST T73: duplicate open exception, same parcel/detector/version/reason (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail)
    VALUES (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t73_detector', '1.0', '{"reason":"t73_probe"}'::jsonb);

    BEGIN
        INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail)
        VALUES (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t73_detector', '1.0', '{"reason":"t73_probe"}'::jsonb);
        RAISE EXCEPTION 'FAIL T73: duplicate open exception was accepted';
    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'parcel_exception_one_open_per_detector_reason_coalesced' THEN
                RAISE NOTICE 'PASS T73: duplicate open exception rejected';
                INSERT INTO test_pass VALUES ('T73');
            ELSE
                RAISE EXCEPTION 'FAIL T73: unique_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T74: a DIFFERENT reason, same parcel/detector/version, still succeeds
-- (0045 positive control -- proves T73 rejects the exact duplicate, not
-- every open exception for the same parcel/detector).
-- ============================================================================

\echo '### TEST T74: different reason, same parcel/detector/version (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail)
    VALUES (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t73_detector', '1.0', '{"reason":"t74_different_reason"}'::jsonb);

    RAISE NOTICE 'PASS T74: second open exception with a different reason accepted';
    INSERT INTO test_pass VALUES ('T74');
END $$;

-- ============================================================================
-- TEST T75: reopened_from_id rejects a reference to a nonexistent
-- parcel_exception row (0047, P9: prompts/P9-exception-resolution.md).
-- Positive control below (T76) proves a REAL reference is accepted, so
-- T75 is proven to be the FK firing, not some unrelated failure.
-- ============================================================================

\echo '### TEST T75: reopened_from_id FK rejects a nonexistent row (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail, reopened_from_id)
        VALUES (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t75_detector', '1.0', '{"reason":"t75_probe"}'::jsonb, gen_random_uuid());
        RAISE EXCEPTION 'FAIL T75: reopened_from_id pointing at a nonexistent row was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'parcel_exception_reopened_from_fk' THEN
                RAISE NOTICE 'PASS T75: reopened_from_id FK rejected a nonexistent row';
                INSERT INTO test_pass VALUES ('T75');
            ELSE
                RAISE EXCEPTION 'FAIL T75: foreign_key_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T76: reopened_from_id accepts a reference to a REAL parcel_exception
-- row (0047 positive control -- proves T75 rejects a genuinely dangling
-- reference, not every non-NULL reopened_from_id).
-- ============================================================================

\echo '### TEST T76: reopened_from_id FK accepts a real row (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_target_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail)
    VALUES (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t76_detector', '1.0', '{"reason":"t76_original"}'::jsonb)
    RETURNING id INTO v_target_id;

    UPDATE parcel_exception
       SET outcome = 'condition_cleared', resolved_at = clock_timestamp(), resolved_by = 'test_t76_detector'
     WHERE id = v_target_id;

    INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail, reopened_from_id)
    VALUES (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t76_detector', '1.0', '{"reason":"t76_original"}'::jsonb, v_target_id);

    RAISE NOTICE 'PASS T76: reopened_from_id % (real prior row) accepted', v_target_id;
    INSERT INTO test_pass VALUES ('T76');
END $$;

-- ============================================================================
-- TEST T77: outcome='condition_cleared' with resolved_at/resolved_by both
-- set satisfies parcel_exception_outcome_resolution_biconditional (0015)
-- with NO change to that constraint (0047's own header: the biconditional
-- is already generic over any non-open outcome). Negative control below
-- (T78) proves the SAME constraint still rejects condition_cleared without
-- a resolution -- the new enum value doesn't get a free pass.
-- ============================================================================

\echo '### TEST T77: condition_cleared with resolution set satisfies 0015 (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail, outcome, resolved_at, resolved_by)
    VALUES (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t77_detector', '1.0', '{"reason":"t77_probe"}'::jsonb,
            'condition_cleared', clock_timestamp(), 'test_t77_detector');

    RAISE NOTICE 'PASS T77: condition_cleared with resolved_at/resolved_by accepted';
    INSERT INTO test_pass VALUES ('T77');
END $$;

-- ============================================================================
-- TEST T78: outcome='condition_cleared' with resolved_at/resolved_by NULL
-- is rejected by the SAME pre-existing 0015 biconditional, unchanged by
-- 0047 (0047 negative control).
-- ============================================================================

\echo '### TEST T78: condition_cleared without a resolution is rejected (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail, outcome)
        VALUES (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t78_detector', '1.0', '{"reason":"t78_probe"}'::jsonb,
                'condition_cleared');
        RAISE EXCEPTION 'FAIL T78: condition_cleared with no resolved_at/resolved_by was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'parcel_exception_outcome_resolution_biconditional' THEN
                RAISE NOTICE 'PASS T78: unresolved condition_cleared rejected by the pre-existing 0015 biconditional';
                INSERT INTO test_pass VALUES ('T78');
            ELSE
                RAISE EXCEPTION 'FAIL T78: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T79: refusals containing an element with no 'code' key at all is
-- rejected (0048, P10, README finding #8). Before 0048, elem ->> 'code'
-- evaluated SQL NULL and NULL NOT IN (...) evaluated NULL, not true -- the
-- CHECK silently accepted this. Positive control below (T83) proves a
-- genuinely valid refusals array is still accepted.
-- ============================================================================

\echo '### TEST T79: refusals element with no code key (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, refusals, payload,
            payload_hash, compose_ms
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
            'v1.0', 'v1.0', false, '[{}]'::jsonb, '{}'::jsonb, 'testhash_t79', 100
        );
        RAISE EXCEPTION 'FAIL T79: refusals element with no code key was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_refusal_codes_known_parcel' THEN
                RAISE NOTICE 'PASS T79: refusals element with no code key rejected';
                INSERT INTO test_pass VALUES ('T79');
            ELSE
                RAISE EXCEPTION 'FAIL T79: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T80: refusals containing {"code": null} (key present, value JSON
-- null) is rejected -- the SAME NULL-producing mechanism as T79 (elem ->>
-- 'code' returns NULL whether the key is absent or its value is null), a
-- separate test because they are two different JSON shapes a real caller
-- could produce.
-- ============================================================================

\echo '### TEST T80: refusals element with code: null (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, refusals, payload,
            payload_hash, compose_ms
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
            'v1.0', 'v1.0', false, '[{"code": null}]'::jsonb, '{}'::jsonb, 'testhash_t80', 100
        );
        RAISE EXCEPTION 'FAIL T80: refusals element with code: null was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_refusal_codes_known_parcel' THEN
                RAISE NOTICE 'PASS T80: refusals element with code: null rejected';
                INSERT INTO test_pass VALUES ('T80');
            ELSE
                RAISE EXCEPTION 'FAIL T80: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T81: a refusals array element that is not a JSON object at all (a
-- bare string) is rejected. elem ->> 'code' on a non-object also evaluates
-- NULL, not an error -- confirmed directly before 0048 was written, not
-- assumed; this test pins that specific shape down permanently.
-- ============================================================================

\echo '### TEST T81: refusals element is not an object (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, refusals, payload,
            payload_hash, compose_ms
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
            'v1.0', 'v1.0', false, '["not-an-object"]'::jsonb, '{}'::jsonb, 'testhash_t81', 100
        );
        RAISE EXCEPTION 'FAIL T81: non-object refusals element was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_refusal_codes_known_parcel' THEN
                RAISE NOTICE 'PASS T81: non-object refusals element rejected';
                INSERT INTO test_pass VALUES ('T81');
            ELSE
                RAISE EXCEPTION 'FAIL T81: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T82: refusals itself not an array at all (a JSON object) is rejected
-- by a clean constraint violation, not a raw jsonb_array_elements() runtime
-- error. Before 0048, this shape crashed the INSERT outright ("cannot
-- extract elements from an object") -- confirmed directly -- a worse
-- failure mode than a typed CHECK violation a caller can distinguish from
-- any other bug. 0048's CASE guard (jsonb_typeof(refusals) IS DISTINCT FROM
-- 'array' THEN false) is what turns this into a normal rejection.
-- ============================================================================

\echo '### TEST T82: refusals is not an array (should fail cleanly, not error)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, refusals, payload,
            payload_hash, compose_ms
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'composed', now(), 'v1.0',
            'v1.0', 'v1.0', false, '{}'::jsonb, '{}'::jsonb, 'testhash_t82', 100
        );
        RAISE EXCEPTION 'FAIL T82: non-array refusals was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_refusal_codes_known_parcel' THEN
                RAISE NOTICE 'PASS T82: non-array refusals rejected cleanly (no raw jsonb error)';
                INSERT INTO test_pass VALUES ('T82');
            ELSE
                RAISE EXCEPTION 'FAIL T82: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T83: a genuinely valid refusals array (0048 positive control) --
-- proves T79-T82 reject the specific broken shapes, not every refusals
-- array.
-- ============================================================================

\echo '### TEST T83: valid refusals array (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals, payload,
        payload_hash, compose_ms
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "RIGHTS_BLOCKED", "stage": "L8", "message": "test"}]'::jsonb,
        '{}'::jsonb, 'testhash_t83', 100
    );

    RAISE NOTICE 'PASS T83: valid refusals array accepted';
    INSERT INTO test_pass VALUES ('T83');
END $$;

-- ============================================================================
-- TEST T84: a second OPEN zoning_source_geometry_invalid-shaped exception
-- (no 'reason' key in detail -- that detector's real shape) for the same
-- parcel is rejected (0049, P10, README finding #19). Before 0049,
-- detail->>'reason' evaluated SQL NULL for every row this shape produces,
-- and a unique index never treats NULL as conflicting with NULL -- 0045's
-- original index silently never fired for it. Positive control below (T85)
-- proves a DIFFERENT detector_key with the same no-reason shape is not
-- blocked -- detector_key is still part of the key, not swallowed by the
-- COALESCE.
-- ============================================================================

\echo '### TEST T84: duplicate open exception with no reason key (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail)
    VALUES (v_parcel_id, 'test_ca_san_jose', 'record_to_ground', 'info', 'test_t84_detector', '1.0',
            '{"zoning_source_reason":"t84_probe","zoning_value_assigned":"R-1","note":"no reason key"}'::jsonb);

    BEGIN
        INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail)
        VALUES (v_parcel_id, 'test_ca_san_jose', 'record_to_ground', 'info', 'test_t84_detector', '1.0',
                '{"zoning_source_reason":"t84_probe_again","zoning_value_assigned":"R-2","note":"still no reason key"}'::jsonb);
        RAISE EXCEPTION 'FAIL T84: duplicate no-reason-key exception was accepted';
    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'parcel_exception_one_open_per_detector_reason_coalesced' THEN
                RAISE NOTICE 'PASS T84: duplicate no-reason-key exception rejected';
                INSERT INTO test_pass VALUES ('T84');
            ELSE
                RAISE EXCEPTION 'FAIL T84: unique_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T85: a DIFFERENT detector_key, same parcel, same no-reason-key shape,
-- still succeeds (0049 positive control -- proves T84 rejects the exact
-- (parcel, detector, version) duplicate, not every no-reason-key exception
-- for the parcel regardless of detector).
-- ============================================================================

\echo '### TEST T85: different detector, same no-reason shape (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail)
    VALUES (v_parcel_id, 'test_ca_san_jose', 'record_to_ground', 'info', 'test_t85_other_detector', '1.0',
            '{"zoning_source_reason":"t85_probe","zoning_value_assigned":"R-1","note":"different detector"}'::jsonb);

    RAISE NOTICE 'PASS T85: different detector_key with the same no-reason shape accepted';
    INSERT INTO test_pass VALUES ('T85');
END $$;

-- ============================================================================
-- TEST T86: outcome='version_retired' (0050, P16, README finding #18) with
-- resolved_at/resolved_by both set satisfies parcel_exception_outcome_
-- resolution_biconditional (0015) with NO change to that constraint --
-- 0050's own header, following 0047's precedent, notes the biconditional is
-- already generic over any non-open outcome. Negative control below (T87)
-- proves the SAME constraint still rejects version_retired without a
-- resolution -- the new enum value doesn't get a free pass either.
-- ============================================================================

\echo '### TEST T86: version_retired with resolution set satisfies 0015 (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail, outcome, resolved_at, resolved_by, resolution_notes)
    VALUES (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t86_detector', '1.0', '{"reason":"t86_probe"}'::jsonb,
            'version_retired', clock_timestamp(), 'system:detector_version_retired', 'detector_version 1.0 retired');

    RAISE NOTICE 'PASS T86: version_retired with resolved_at/resolved_by accepted';
    INSERT INTO test_pass VALUES ('T86');
END $$;

-- ============================================================================
-- TEST T87: outcome='version_retired' with resolved_at/resolved_by NULL is
-- rejected by the SAME pre-existing 0015 biconditional, unchanged by 0050
-- (0047/T78's shape, repeated for the new value).
-- ============================================================================

\echo '### TEST T87: version_retired without a resolution is rejected (should fail)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail, outcome)
        VALUES (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t87_detector', '1.0', '{"reason":"t87_probe"}'::jsonb,
                'version_retired');
        RAISE EXCEPTION 'FAIL T87: version_retired with no resolved_at/resolved_by was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'parcel_exception_outcome_resolution_biconditional' THEN
                RAISE NOTICE 'PASS T87: unresolved version_retired rejected by the pre-existing 0015 biconditional';
                INSERT INTO test_pass VALUES ('T87');
            ELSE
                RAISE EXCEPTION 'FAIL T87: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T88: core/exceptions.retire_stranded_exceptions()'s UPDATE, run
-- inline (identical SQL text, checked by direct comparison against
-- core/exceptions.py at the time this test was written -- not merely
-- assumed to match), retires ONLY open rows at the exact (detector_key,
-- retired_version) targeted -- a same-detector, different-version open row
-- is untouched, and an already-resolved row is untouched. Three rows: two
-- open at '1.0' (the stranded population's shape), one open at '2.0' (the
-- current rule's shape) for the SAME detector_key and parcel.
-- ============================================================================

\echo '### TEST T88: retirement UPDATE targets only the exact stranded version (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
    v_retired_count int;
    v_still_open_v2 int;
    v_resolved_by_check text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO parcel_exception (parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail, outcome)
    VALUES
        (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t88_detector', '1.0', '{"reason":"t88_a"}'::jsonb, 'open'),
        (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t88_detector', '1.0', '{"reason":"t88_b"}'::jsonb, 'open'),
        (v_parcel_id, 'test_ca_san_jose', 'coverage_gap', 'info', 'test_t88_detector', '2.0', '{"reason":"t88_c"}'::jsonb, 'open');

    UPDATE parcel_exception
       SET outcome = 'version_retired',
           resolved_at = clock_timestamp(),
           resolved_by = 'system:detector_version_retired',
           resolution_notes = 'detector_version ' || '1.0' || ' retired'
     WHERE detector_key = 'test_t88_detector'
       AND detector_version = '1.0'
       AND outcome = 'open';
    GET DIAGNOSTICS v_retired_count = ROW_COUNT;

    IF v_retired_count <> 2 THEN
        RAISE EXCEPTION 'FAIL T88: expected exactly 2 rows retired, got %', v_retired_count;
    END IF;

    SELECT count(*) INTO v_still_open_v2 FROM parcel_exception
     WHERE detector_key = 'test_t88_detector' AND detector_version = '2.0' AND outcome = 'open';
    IF v_still_open_v2 <> 1 THEN
        RAISE EXCEPTION 'FAIL T88: v2.0 open row was touched -- expected 1 still open, got %', v_still_open_v2;
    END IF;

    SELECT resolved_by INTO v_resolved_by_check FROM parcel_exception
     WHERE detector_key = 'test_t88_detector' AND detector_version = '1.0' AND detail->>'reason' = 't88_a';
    IF v_resolved_by_check <> 'system:detector_version_retired' THEN
        RAISE EXCEPTION 'FAIL T88: resolved_by mismatch, got %', v_resolved_by_check;
    END IF;

    RAISE NOTICE 'PASS T88: retirement UPDATE retired exactly the 2 targeted v1.0 rows, left the v2.0 row open';
    INSERT INTO test_pass VALUES ('T88');
END $$;

-- ============================================================================
-- TEST T89: a second run of the SAME retirement UPDATE, same (detector_key,
-- retired_version), is a no-op -- every previously-open row at that key is
-- now version_retired (outcome <> 'open'), so the WHERE clause matches
-- nothing. Runs against T88's own rows, immediately after it.
-- ============================================================================

\echo '### TEST T89: a second retirement run is a no-op (should succeed)'

DO $$
DECLARE
    v_second_run_count int;
BEGIN
    UPDATE parcel_exception
       SET outcome = 'version_retired',
           resolved_at = clock_timestamp(),
           resolved_by = 'system:detector_version_retired',
           resolution_notes = 'detector_version ' || '1.0' || ' retired'
     WHERE detector_key = 'test_t88_detector'
       AND detector_version = '1.0'
       AND outcome = 'open';
    GET DIAGNOSTICS v_second_run_count = ROW_COUNT;

    IF v_second_run_count <> 0 THEN
        RAISE EXCEPTION 'FAIL T89: second retirement run was not a no-op, retired % rows', v_second_run_count;
    END IF;

    RAISE NOTICE 'PASS T89: second retirement run touched 0 rows';
    INSERT INTO test_pass VALUES ('T89');
END $$;

-- ============================================================================
-- TEST T90: job_run.metrics accepts a JSON object (0051, P18, README
-- findings #12/#16). Negative control below (T91) proves the same
-- constraint rejects a bare array/scalar -- metrics is not a free-for-all
-- jsonb slot, only the shape floor every real writer (phase_e, load_
-- zoning, load_permits, flag_invalid_geometry.py's two detectors) already
-- honestly satisfies.
-- ============================================================================

\echo '### TEST T90: job_run.metrics accepts a JSON object (should succeed)'

DO $$
BEGIN
    INSERT INTO job_run (job_key, status, finished_at, metrics)
    VALUES ('test.t90_job', 'succeeded', clock_timestamp(), '{"exceptions_written": 3, "exceptions_skipped_already_open": 1}'::jsonb);

    RAISE NOTICE 'PASS T90: job_run.metrics accepted a JSON object';
    INSERT INTO test_pass VALUES ('T90');
END $$;

-- ============================================================================
-- TEST T91: job_run.metrics rejects a bare JSON array (job_run_metrics_is_object,
-- 0051). Same shape-floor argument 0038/0048 already established for
-- property_file.refusals (jsonb_typeof(...) = 'array' there; 'object'
-- here) -- a metrics value that isn't a keyed object can't carry the
-- self-describing top-level keys every real writer's own shape depends on.
-- ============================================================================

\echo '### TEST T91: job_run.metrics rejects a bare array (should fail)'

DO $$
DECLARE
    v_constraint text;
BEGIN
    BEGIN
        INSERT INTO job_run (job_key, status, finished_at, metrics)
        VALUES ('test.t91_job', 'succeeded', clock_timestamp(), '[1, 2, 3]'::jsonb);
        RAISE EXCEPTION 'FAIL T91: a bare JSON array in metrics was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'job_run_metrics_is_object' THEN
                RAISE NOTICE 'PASS T91: bare array rejected by job_run_metrics_is_object';
                INSERT INTO test_pass VALUES ('T91');
            ELSE
                RAISE EXCEPTION 'FAIL T91: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T92: property_file_election_known (0052, P35, README finding #35)
-- rejects a non-NULL election outside ('city','state'). Exact constraint-
-- violation text captured and printed, not just the constraint name --
-- 0052's own header reasons carefully about what NULL means but never
-- tested any of it; this is that gap closed.
-- ============================================================================

\echo '### TEST T92: property_file.election rejects a bogus value (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
    v_message    text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, refusals,
            payload, payload_hash, compose_ms, election
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
            'v1.0', 'v1.0', false,
            '[{"code": "RIGHTS_BLOCKED", "stage": "L8", "message": "test"}]'::jsonb,
            '{}'::jsonb, 'testhash_t92', 1, 'bogus'
        );
        RAISE EXCEPTION 'FAIL T92: election=''bogus'' was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME, v_message = MESSAGE_TEXT;
            IF v_constraint = 'property_file_election_known' THEN
                RAISE NOTICE 'PASS T92: election=''bogus'' rejected -- %', v_message;
                INSERT INTO test_pass VALUES ('T92');
            ELSE
                RAISE EXCEPTION 'FAIL T92: check_violation on unexpected constraint % (%)', v_constraint, v_message;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T93: property_file_election_known ACCEPTS NULL (0052). Not skipped
-- as obvious -- findings #8 and #19 are both cases where a NULL branch was
-- assumed to behave as written and did not (elem ->> 'code' IS NULL
-- silently excluded from the offending set; a NULL-keyed unique index
-- never conflicts with itself). 0052's own header invokes that precedent
-- in prose ("NULL is a real, handled case ... not an unconstrained gap")
-- without ever testing it; this is that gap closed. election IS NULL OR
-- election IN (...) is the explicit guard CONVENTIONS' NULL-inside-a-
-- constraint rule requires naming -- this proves the guard's OR actually
-- lets NULL through, not merely that the migration compiled.
-- ============================================================================

\echo '### TEST T93: property_file.election accepts NULL (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals,
        payload, payload_hash, compose_ms, election
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "RIGHTS_BLOCKED", "stage": "L8", "message": "test"}]'::jsonb,
        '{}'::jsonb, 'testhash_t93', 1, NULL
    );

    RAISE NOTICE 'PASS T93: election=NULL accepted';
    INSERT INTO test_pass VALUES ('T93');
END $$;

-- ============================================================================
-- TEST T94: property_file_election_known ACCEPTS 'city' (0052) -- the one
-- real, seeded regime (P31). Positive control alongside T92/T95: the CHECK
-- constrains the vocabulary, it does not reject every non-NULL value.
-- ============================================================================

\echo '### TEST T94: property_file.election accepts ''city'' (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals,
        payload, payload_hash, compose_ms, election
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "RIGHTS_BLOCKED", "stage": "L8", "message": "test"}]'::jsonb,
        '{}'::jsonb, 'testhash_t94', 1, 'city'
    );

    RAISE NOTICE 'PASS T94: election=''city'' accepted';
    INSERT INTO test_pass VALUES ('T94');
END $$;

-- ============================================================================
-- TEST T95: property_file_election_known ACCEPTS 'state' (0052) -- not yet
-- reachable through compose() today (README finding #35: no State-standards
-- rule_key is mapped in CONCLUSION_RULE_KEYS), but the column and its CHECK
-- do not themselves know that -- the schema must accept the full vocabulary
-- Bulletin #210 names, independent of which half compose() currently uses.
-- ============================================================================

\echo '### TEST T95: property_file.election accepts ''state'' (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals,
        payload, payload_hash, compose_ms, election
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "RIGHTS_BLOCKED", "stage": "L8", "message": "test"}]'::jsonb,
        '{}'::jsonb, 'testhash_t95', 1, 'state'
    );

    RAISE NOTICE 'PASS T95: election=''state'' accepted';
    INSERT INTO test_pass VALUES ('T95');
END $$;

-- ============================================================================
-- TEST T96: refusals_codes_valid ACCEPTS ELECTION_REQUIRED (0053, P35).
-- Positive control -- proves the widened vocabulary actually admits the new
-- code, not merely that the migration's own DDL compiled.
-- ============================================================================

\echo '### TEST T96: refusals accepts ELECTION_REQUIRED (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals,
        payload, payload_hash, compose_ms, election
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "ELECTION_REQUIRED", "stage": "L5", "message": "test"}]'::jsonb,
        '{}'::jsonb, 'testhash_t96', 1, NULL
    );

    RAISE NOTICE 'PASS T96: refusals containing ELECTION_REQUIRED accepted';
    INSERT INTO test_pass VALUES ('T96');
END $$;

-- ============================================================================
-- TEST T97: refusals_codes_valid ACCEPTS ELECTION_NOT_SUPPORTED (0053, P35).
-- Same positive-control reasoning as T96, the second of the two codes 0053
-- added.
-- ============================================================================

\echo '### TEST T97: refusals accepts ELECTION_NOT_SUPPORTED (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals,
        payload, payload_hash, compose_ms, election
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "ELECTION_NOT_SUPPORTED", "stage": "L5", "message": "test"}]'::jsonb,
        '{}'::jsonb, 'testhash_t97', 1, 'state'
    );

    RAISE NOTICE 'PASS T97: refusals containing ELECTION_NOT_SUPPORTED accepted';
    INSERT INTO test_pass VALUES ('T97');
END $$;

-- ============================================================================
-- TEST T98: refusals_codes_valid, POST-WIDENING, still REJECTS a genuinely
-- unknown code (0053, P35). T60 already covers this in general and predates
-- 0053, but T60's own code literal is not specific to 0053's widening --
-- a widening that accidentally turned into "accept everything" (an OR
-- chain wired wrong, a stray TRUE) would leave T60 green too, since T60
-- never asserts anything about the SIZE of the accepted vocabulary, only
-- that its own one literal is rejected. This test uses its own, fresh
-- literal and exists specifically to regression-guard the widening itself,
-- not merely re-prove the pre-existing mechanism. RED proof (not left live
-- in this file, per T60's own precedent for 0038): a scratch database with
-- refusals_codes_valid() temporarily replaced by a body returning TRUE
-- unconditionally -- simulating exactly the "widening accidentally accepts
-- everything" failure mode -- let this exact INSERT succeed; reverted to
-- 0053's real function, confirmed rejected again. See
-- prompts/P35-election-invariants-and-fk-report.md section 2 for the full
-- transcript.
-- ============================================================================

\echo '### TEST T98: refusals still rejects an unknown code after widening (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, refusals,
            payload, payload_hash, compose_ms, election
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
            'v1.0', 'v1.0', false,
            '[{"code": "STILL_NOT_A_REAL_CODE_T98", "stage": "L5", "message": "test"}]'::jsonb,
            '{}'::jsonb, 'testhash_t98', 1, NULL
        );
        RAISE EXCEPTION 'FAIL T98: an unknown code was accepted after the 0053 widening';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_refusal_codes_known_parcel' THEN
                RAISE NOTICE 'PASS T98: unknown code still rejected after widening';
                INSERT INTO test_pass VALUES ('T98');
            ELSE
                RAISE EXCEPTION 'FAIL T98: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T99: property_file_election_refusal_consistent (0054, P36, README
-- finding #39) rejects election='city' co-occurring with an
-- ELECTION_REQUIRED refusal -- self-contradictory (ELECTION_REQUIRED means
-- "none was supplied"). Exact constraint-violation text not merely relied
-- on to exist -- the constraint name asserted, same shape T92 already
-- established for property_file_election_known.
-- ============================================================================

\echo '### TEST T99: election=''city'' with ELECTION_REQUIRED rejected (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, refusals,
            payload, payload_hash, compose_ms, election
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
            'v1.0', 'v1.0', false,
            '[{"code": "ELECTION_REQUIRED", "stage": "L5", "message": "test"}]'::jsonb,
            '{}'::jsonb, 'testhash_t99', 1, 'city'
        );
        RAISE EXCEPTION 'FAIL T99: election=''city'' with ELECTION_REQUIRED was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_election_refusal_consistent' THEN
                RAISE NOTICE 'PASS T99: election=''city'' with ELECTION_REQUIRED rejected';
                INSERT INTO test_pass VALUES ('T99');
            ELSE
                RAISE EXCEPTION 'FAIL T99: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T100: property_file_election_refusal_consistent rejects election IS
-- NULL co-occurring with an ELECTION_NOT_SUPPORTED refusal -- self-
-- contradictory the other direction (ELECTION_NOT_SUPPORTED means "one WAS
-- supplied, just unmapped").
-- ============================================================================

\echo '### TEST T100: election IS NULL with ELECTION_NOT_SUPPORTED rejected (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, refusals,
            payload, payload_hash, compose_ms, election
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
            'v1.0', 'v1.0', false,
            '[{"code": "ELECTION_NOT_SUPPORTED", "stage": "L5", "message": "test"}]'::jsonb,
            '{}'::jsonb, 'testhash_t100', 1, NULL
        );
        RAISE EXCEPTION 'FAIL T100: election IS NULL with ELECTION_NOT_SUPPORTED was accepted';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_election_refusal_consistent' THEN
                RAISE NOTICE 'PASS T100: election IS NULL with ELECTION_NOT_SUPPORTED rejected';
                INSERT INTO test_pass VALUES ('T100');
            ELSE
                RAISE EXCEPTION 'FAIL T100: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T101: the LEGITIMATE combination election IS NULL with
-- ELECTION_REQUIRED is still accepted (0054 does not reject everything --
-- T98's own lesson, one package old: a constraint proven to reject is not
-- proven correct until the legitimate shape is proven to still pass).
-- ============================================================================

\echo '### TEST T101: election IS NULL with ELECTION_REQUIRED accepted (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals,
        payload, payload_hash, compose_ms, election
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "ELECTION_REQUIRED", "stage": "L5", "message": "test"}]'::jsonb,
        '{}'::jsonb, 'testhash_t101', 1, NULL
    );

    RAISE NOTICE 'PASS T101: election IS NULL with ELECTION_REQUIRED accepted';
    INSERT INTO test_pass VALUES ('T101');
END $$;

-- ============================================================================
-- TEST T102: the LEGITIMATE combination election='state' with
-- ELECTION_NOT_SUPPORTED is still accepted -- same reasoning as T101, the
-- other direction.
-- ============================================================================

\echo '### TEST T102: election=''state'' with ELECTION_NOT_SUPPORTED accepted (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals,
        payload, payload_hash, compose_ms, election
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "ELECTION_NOT_SUPPORTED", "stage": "L5", "message": "test"}]'::jsonb,
        '{}'::jsonb, 'testhash_t102', 1, 'state'
    );

    RAISE NOTICE 'PASS T102: election=''state'' with ELECTION_NOT_SUPPORTED accepted';
    INSERT INTO test_pass VALUES ('T102');
END $$;

-- ============================================================================
-- TEST T103: refusals_codes_valid ACCEPTS PARCEL_REFERENCE_UNKNOWN (0055,
-- P37, README finding #40). Positive control -- proves the widened
-- vocabulary admits the code, independent of whether compose() itself ever
-- writes a row carrying it (it does not -- see 0055's own header: this
-- code is returned as a typed Result directly, never persisted). The
-- schema-level vocabulary and the one real writer's own usage pattern are
-- two different claims; this test is about the former only.
-- ============================================================================

\echo '### TEST T103: refusals accepts PARCEL_REFERENCE_UNKNOWN (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals,
        payload, payload_hash, compose_ms, election
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "PARCEL_REFERENCE_UNKNOWN", "stage": "L0", "message": "test"}]'::jsonb,
        '{}'::jsonb, 'testhash_t103', 1, NULL
    );

    RAISE NOTICE 'PASS T103: refusals containing PARCEL_REFERENCE_UNKNOWN accepted';
    INSERT INTO test_pass VALUES ('T103');
END $$;

-- ============================================================================
-- TEST T104: refusals_codes_valid ACCEPTS PARCEL_NO_FACTS (0055, P37,
-- README finding #40). Positive control, the second of the two codes 0055
-- added -- this one IS a real, reachable shape (compose() writes it).
-- ============================================================================

\echo '### TEST T104: refusals accepts PARCEL_NO_FACTS (should succeed)'

DO $$
DECLARE
    v_parcel_id uuid;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    INSERT INTO property_file (
        parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
        ruleset_version, composer_version, geometry_tier_used, refusals,
        payload, payload_hash, compose_ms, election
    ) VALUES (
        v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
        'v1.0', 'v1.0', false,
        '[{"code": "PARCEL_NO_FACTS", "stage": "L8", "message": "test"}]'::jsonb,
        '{}'::jsonb, 'testhash_t104', 1, NULL
    );

    RAISE NOTICE 'PASS T104: refusals containing PARCEL_NO_FACTS accepted';
    INSERT INTO test_pass VALUES ('T104');
END $$;

-- ============================================================================
-- TEST T105: refusals_codes_valid, POST-0055-WIDENING, still REJECTS a
-- genuinely unknown code. Own fresh literal (not T60's or T98's) -- T98's
-- own lesson, repeated: a widening that accidentally turned into "accept
-- everything" would leave every earlier rejection test green too, since
-- none of them assert anything about the SIZE of the accepted vocabulary,
-- only that their own one literal is rejected.
-- ============================================================================

\echo '### TEST T105: refusals still rejects an unknown code after the 0055 widening (should fail)'

DO $$
DECLARE
    v_parcel_id  uuid;
    v_constraint text;
BEGIN
    SELECT value::uuid INTO v_parcel_id FROM test_state WHERE key = 'parcel_id';

    BEGIN
        INSERT INTO property_file (
            parcel_id, jurisdiction_id, channel, status, as_of, pack_version,
            ruleset_version, composer_version, geometry_tier_used, refusals,
            payload, payload_hash, compose_ms, election
        ) VALUES (
            v_parcel_id, 'test_ca_san_jose', 'free_snapshot', 'refused', now(), 'v1.0',
            'v1.0', 'v1.0', false,
            '[{"code": "STILL_NOT_A_REAL_CODE_T105", "stage": "L0", "message": "test"}]'::jsonb,
            '{}'::jsonb, 'testhash_t105', 1, NULL
        );
        RAISE EXCEPTION 'FAIL T105: an unknown code was accepted after the 0055 widening';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint = 'property_file_refusal_codes_known_parcel' THEN
                RAISE NOTICE 'PASS T105: unknown code still rejected after the 0055 widening';
                INSERT INTO test_pass VALUES ('T105');
            ELSE
                RAISE EXCEPTION 'FAIL T105: check_violation on unexpected constraint %', v_constraint;
            END IF;
    END;
END $$;

-- ============================================================================
-- TEST T106: no parcel row created BY THIS RUN carries
-- jurisdiction_id='ca_san_jose' (P56 Phase 2, finding #50). Scoped by
-- first_seen_at >= this run's own start (recorded above, before any
-- fixture existed) rather than asserted over the whole table -- a
-- whole-table assertion can never pass: every prior run of this file, on
-- every database it has ever touched, left permanent TEST-%-apn parcels
-- under the real jurisdiction (fact-bearing, 0017/I4, cannot be removed).
--
-- Sufficient for fact, property_file AND parcel_exception too, with no
-- separate test for any of them: each carries its own composite FK forcing
-- its jurisdiction_id to equal its parcel's (fact_parcel_jurisdiction_fk,
-- property_file_parcel_jurisdiction_fk,
-- parcel_exception_parcel_jurisdiction_fk -- 0022:107-121). If no
-- run-scoped parcel is under ca_san_jose, no run-scoped row in those three
-- tables can be either -- the database enforces it, so this test only
-- needs to check the one table the other three all point back to.
-- ============================================================================

\echo '### TEST T106: no parcel created this run carries jurisdiction_id=ca_san_jose (should succeed)'

DO $$
DECLARE
    v_run_started_at timestamptz;
    v_bad_count       int;
BEGIN
    SELECT value::timestamptz INTO v_run_started_at FROM test_state WHERE key = 'run_started_at';

    SELECT count(*) INTO v_bad_count FROM parcel
     WHERE first_seen_at >= v_run_started_at
       AND jurisdiction_id = 'ca_san_jose';

    IF v_bad_count > 0 THEN
        RAISE EXCEPTION 'FAIL T106: % parcel row(s) created this run still carry jurisdiction_id=ca_san_jose', v_bad_count;
    END IF;

    RAISE NOTICE 'PASS T106: no parcel created this run carries jurisdiction_id=ca_san_jose';
    INSERT INTO test_pass VALUES ('T106');
END $$;

-- ============================================================================
-- TEST T107: no job_run or rule row created BY THIS RUN carries
-- jurisdiction_id='ca_san_jose' either (P56 Phase 2, finding #50). Neither
-- table has a composite FK tying it to a parcel, so T106 does not cover
-- them -- checked directly here instead.
--
-- CORRECTED before this test ever shipped, recorded here rather than
-- silently fixed: the first draft scoped this by job_key/rule_key LIKE
-- 'test.%' alone, no timing filter, reasoning that the namespace prefix
-- already identifies this suite's own rows. Run once against a database
-- with real prior-run residue (rule is immutable, 0013 -- every previous
-- run's own test.*.rule.* rows are permanent and can never be cleaned):
-- it found 45 pre-existing rule rows and failed on THEM, not on anything
-- this run created, and would fail identically forever after, on every
-- future run, on any database this suite has ever touched -- the exact
-- "test that can never pass" trap T106's own header warns against, in a
-- second table. Fixed by scoping both checks to this run's own
-- first_seen_at-equivalent instead: job_run.started_at (DEFAULT now()) and
-- rule.reviewed_at (verified set to now() at INSERT time by all five rule
-- fixtures -- I18a/b/c/d and T65 -- not a fixed literal), both
-- >= run_started_at. The namespace filter stays, narrowing to this suite's
-- own rows specifically rather than any row that merely happens to be
-- recent.
--
-- support_request (the third non-parcel table finding #50 named) is
-- deliberately NOT checked here: its own T8 fixture is a negative control
-- whose INSERT always raises check_violation and is caught before it
-- commits (confirmed by direct read of T8) -- no row from it, or from any
-- other support_request test in this file, is ever left behind to check.
-- ============================================================================

\echo '### TEST T107: no job_run or rule row created this run carries jurisdiction_id=ca_san_jose (should succeed)'

DO $$
DECLARE
    v_run_started_at timestamptz;
    v_bad_job_runs    int;
    v_bad_rules       int;
BEGIN
    SELECT value::timestamptz INTO v_run_started_at FROM test_state WHERE key = 'run_started_at';

    SELECT count(*) INTO v_bad_job_runs FROM job_run
     WHERE job_key LIKE 'test.%'
       AND started_at >= v_run_started_at
       AND jurisdiction_id = 'ca_san_jose';

    SELECT count(*) INTO v_bad_rules FROM rule
     WHERE rule_key LIKE 'test.%'
       AND reviewed_at >= v_run_started_at
       AND jurisdiction_id = 'ca_san_jose';

    IF v_bad_job_runs > 0 OR v_bad_rules > 0 THEN
        RAISE EXCEPTION 'FAIL T107: % job_run row(s) and % rule row(s) created this run still carry jurisdiction_id=ca_san_jose', v_bad_job_runs, v_bad_rules;
    END IF;

    RAISE NOTICE 'PASS T107: no job_run or rule row created this run carries jurisdiction_id=ca_san_jose';
    INSERT INTO test_pass VALUES ('T107');
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
--
-- test_skipped is ALSO not part of this floor, for a related but distinct
-- reason (P6 finding). S1's assertion is real and enforceable -- unlike
-- I5c, it is not a permanent gap -- but it only RUNS when db/seeds/
-- day4_sources.sql has been applied BEFORE this suite runs. CORRECTED, P36
-- (README finding #38): this used to read "CI never applies seeds (this
-- suite's own standard path is migrations-only)" -- true when written, no
-- longer true of db.yml's schema job as a whole, which now DOES apply
-- db/seeds/day4_sources.sql (finding #38, closing finding #36's own
-- cross-seeder-drift gap) -- but still true of db-test's OWN invocation
-- specifically: the seed step runs strictly after make db-test in that
-- job's step order (see db.yml's own comment at that step for why), so
-- every CI run of make db-test itself still sees a migrations-only
-- database, S1 still does not run there, and the floor below is
-- unaffected. A local, standalone `make db-test` run against a database
-- where day4_sources.sql was applied first (as this file's own header
-- already documented as possible) is the only path where S1 actually
-- executes. The floor below is 95, not 96: the guaranteed count when S1
-- does not run (the common case, including every CI run of make db-test
-- itself), not the optimistic count from a seeded environment. A seeded
-- run where S1 executes for real still satisfies `>= 95` -- the floor is a
-- minimum, not an exact match -- so this is not environment-conditional
-- logic, just an honest floor. Previously S1 inserted into test_pass on ITS
-- OWN skip branch, counted in a floor of 92 -- meaning CI recorded S1
-- passing on every single run without its assertion ever executing.
-- Raised 91 -> 95 by 0047/P9 (T75-T78: reopened_from_id FK negative/
-- positive, condition_cleared satisfies/violates the pre-existing 0015
-- biconditional). Raised 95 -> 102 by 0048/0049 (P10, findings #8/#19:
-- T79-T82 refusals shape negatives + T83 positive control;
-- T84 duplicate no-reason-key exception negative + T85 positive control).
-- Raised 102 -> 106 by 0050 (P16, finding #18: T86-T87 version_retired
-- satisfies/violates the pre-existing 0015 biconditional; T88 the
-- retirement UPDATE targets only the exact stranded version; T89 a second
-- run of it is a no-op). Raised 106 -> 108 by 0051 (P18, findings #12/#16:
-- T90 job_run.metrics accepts a JSON object; T91 rejects a bare array).
-- Raised 108 -> 115 by 0052/0053 (P35, README finding #35 -- P34 added
-- both migrations but no invariant tests; P35 is the DB-layer half P34
-- skipped): T92 property_file_election_known rejects a bogus value;
-- T93-T95 accepts NULL, 'city', 'state'; T96-T97 refusals_codes_valid
-- accepts ELECTION_REQUIRED, ELECTION_NOT_SUPPORTED; T98 still rejects a
-- genuinely unknown code after the widening (its own fresh literal, not
-- T60's -- guards the widening itself, not merely the pre-existing
-- mechanism T60 already covered before 0053 existed).
-- Raised 115 -> 119 by 0054 (P36, README finding #39):
-- T99 rejects election='city' co-occurring with ELECTION_REQUIRED;
-- T100 rejects election IS NULL co-occurring with ELECTION_NOT_SUPPORTED;
-- T101-T102 the two legitimate combinations are still accepted (T98's own
-- lesson: a rejection proof alone does not prove a constraint isn't
-- rejecting everything).
-- Raised 119 -> 122 by 0055 (P37, README finding #40, re-graded):
-- T103 refusals_codes_valid accepts PARCEL_REFERENCE_UNKNOWN (schema-level
-- vocabulary, not a shape compose() itself ever persists); T104 accepts
-- PARCEL_NO_FACTS (a real, reachable shape); T105 still rejects a
-- genuinely unknown code after this widening, its own fresh literal
-- (T98's lesson, repeated).
-- Raised 122 -> 124 by P56 Phase 2 (finding #50): T106 no parcel created
-- this run carries jurisdiction_id='ca_san_jose'; T107 the same for
-- job_run/rule rows created this run, which T106's own composite-FK
-- argument does not reach.
DO $$
DECLARE
    v_pass_count int;
BEGIN
    SELECT count(*) INTO v_pass_count FROM test_pass;
    IF v_pass_count < 124 THEN
        RAISE EXCEPTION 'FAIL: coverage dropped -- expected at least 124 passing tests, got %', v_pass_count;
    END IF;
END $$;

SELECT count(*) AS pass_count FROM test_pass
\gset

SELECT count(*) AS known_gap_count FROM known_gaps
\gset

SELECT coalesce(string_agg(name || ' (' || note || ')', E'\n  '), '(none)') AS known_gap_detail FROM known_gaps
\gset

SELECT count(*) AS skipped_count FROM test_skipped
\gset

SELECT coalesce(string_agg(name || ' (' || note || ')', E'\n  '), '(none)') AS skipped_detail FROM test_skipped
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
\echo 'SKIPPED --' :skipped_count 'test(s) whose assertion did not run this pass'
\echo '  ' :skipped_detail
\echo 'Also excluded from the pass floor: unlike a known gap, these enforce'
\echo 'something real when their prerequisite data exists -- they are just'
\echo 'not counted as having passed when it does not, so a skip can never'
\echo 'silently read as coverage.'
\echo ''

-- ============================================================================
-- TEARDOWN -- moved to db/tests/teardown.sql (P17, finding #26)
-- ============================================================================
-- P14 placed teardown here, inline, AFTER the pass-floor check above --
-- deliberately, so a real failure aborts the script before ever reaching
-- it. That placement had a real cost finding #26 named: ON_ERROR_STOP
-- means ANY failing test, anywhere above, aborts this whole psql
-- invocation before this point, and teardown inline in the SAME
-- invocation can therefore never run on a failing suite -- exactly the
-- run someone is most likely to re-run immediately, compounding the
-- accumulation on every retry.
--
-- Teardown now lives in db/tests/teardown.sql, a separate file `make
-- db-test` invokes as its own, second psql call, UNCONDITIONALLY, after
-- capturing this suite's own exit code -- so it runs whether this file
-- passed or failed, and its own exit status never overwrites this
-- suite's. See that file's own header for the full class-3 (and, now,
-- zero-fact-orphan class-2-lookalike) teardown argument, and
-- prompts/P17-invariant-suite-hygiene.md for why the split was necessary
-- and what changed about teardown's own safety argument as a result
-- (durable-namespace scoping instead of this run's own v_parcel_id, and
-- an explicit zero-fact filter on any `parcel` row it now also reaches,
-- rather than relying on 0017/the FK to reject one it shouldn't touch).
--
-- Running this file directly via psql, bypassing `make db-test` (the
-- other invocation this file's own header documents): teardown does not
-- run automatically. Run db/tests/teardown.sql yourself afterward, or use
-- `make db-test`, which always does.
\echo ''
