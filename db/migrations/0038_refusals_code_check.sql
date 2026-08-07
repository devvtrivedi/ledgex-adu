-- 0038_refusals_code_check.sql
-- Serves: I8.
--
-- THE GAP. property_file.refusals is jsonb NOT NULL DEFAULT '[]', checked
-- only for non-emptiness when status='refused' (0012's file_refusal_reason).
-- Nothing at the storage layer constrains what a refusal's "code" actually
-- says -- §9 names 19 codes (JURISDICTION_UNRESOLVED through
-- ACCESS_NOT_ENTITLED), stage-tagged L0-L8, but a typo or an invented code
-- inserts cleanly today. I8 ("refusal is a typed return value, not an
-- exception") is enforced at the shape level (jsonb array, conventional
-- code/stage/message/detail keys) but not at the vocabulary level -- a
-- second refusal-writing code path (there is currently exactly one,
-- scripts/compose_property_file.py, hardcoding one literal) could insert
-- any string with nothing here to stop it.
--
-- THE FIX. A genuinely IMMUTABLE SQL function checking every element's
-- ->>'code' against a hardcoded copy of §9's vocabulary, called from a
-- CHECK: a CHECK constraint cannot itself contain a subquery, but a
-- function that contains one internally is legal to call from one --
-- confirmed directly on a scratch database before writing this
-- (jsonb_array_elements() inside a LANGUAGE sql IMMUTABLE function body,
-- called as CHECK(fn(refusals)), accepted an empty array and a valid code,
-- and rejected an invented one with the expected constraint-violation
-- error).
--
-- WHY NOT AN ENUM. The obvious alternative: type refusal codes as a real
-- Postgres ENUM and validate jsonb ->>'code' text against enum_range() of
-- that type, so the vocabulary lives in exactly one place (the enum)
-- instead of being hand-copied into a CHECK function. Checked directly,
-- not assumed, before ruling it out:
--   * enum_range() is STABLE, not IMMUTABLE -- confirmed via
--     SELECT provolatile FROM pg_proc WHERE proname = 'enum_range' ('s',
--     not 'i').
--   * Postgres does NOT reject this at DDL time. Confirmed directly: a
--     CHECK calling enum_range() through a wrapper function hand-labeled
--     IMMUTABLE was accepted with no error by both CREATE FUNCTION and
--     ALTER TABLE ADD CONSTRAINT, and even correctly recognized a value
--     added later via ALTER TYPE ... ADD VALUE in the one case tested --
--     Postgres trusts a function's declared volatility, it does not
--     verify the body against it.
-- Acceptance is not safety, though, and that's the actual reason this
-- route was rejected: IMMUTABLE is a promise to the planner that a
-- function's result depends on nothing but its arguments and is safe to
-- precompute, cache, or fold. That promise is true for the hardcoded list
-- below -- its only legal way to change is a future CREATE OR REPLACE
-- FUNCTION, which keeps the label honest by construction -- and false for
-- enum_range(), whose real output moves underneath an unchanged call the
-- moment some future migration runs ALTER TYPE ... ADD VALUE. Labeling
-- that wrapper IMMUTABLE would be true today and a latent lie the next
-- time the vocabulary grows -- and it has grown before (§9 added
-- SOURCE_DEFERRED in v1.2) -- which is exactly the kind of silent drift
-- this migration exists to close, not reintroduce one layer down inside a
-- function's own volatility label. The hardcoded list has no equivalent
-- landmine, at the cost of needing its own drift guard instead of getting
-- one for free from the type system: build/qa_check.py's
-- check_refusal_codes_match_spec (new in this commit) fails CI if this
-- file's list and §9's vocabulary in docs/LEDGEX_SPEC.md ever diverge in
-- either direction.
--
-- Existing data checked before writing, not assumed clean: every
-- property_file.refusals entry in ledgex_schema_check today carries
-- code='RIGHTS_BLOCKED', a valid §9 code -- this CHECK validates cleanly
-- against current rows with no NOT VALID escape hatch needed.

-- REFUSAL_CODES_BEGIN -- build/qa_check.py's check_refusal_codes_match_spec
-- reads the quoted string literals between these two markers and diffs
-- them against §9's vocabulary in docs/LEDGEX_SPEC.md. Keep the list here,
-- and only here -- do not duplicate it elsewhere in this file.
CREATE FUNCTION refusals_codes_valid(refusals jsonb) RETURNS boolean AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM jsonb_array_elements(refusals) AS elem
        WHERE elem ->> 'code' NOT IN (
            'JURISDICTION_UNRESOLVED',
            'JURISDICTION_UNSUPPORTED',
            'JURISDICTION_BOUNDARY_CONFLICT',
            'PARCEL_NOT_FOUND',
            'SOURCE_UNVERIFIED',
            'SOURCE_UNAVAILABLE',
            'SOURCE_NOT_MACHINE_READABLE',
            'SOURCE_DEFERRED',
            'CROSSWALK_UNMAPPED',
            'RULE_UNAVAILABLE',
            'PERMIT_SERIES_TOO_SHALLOW',
            'GEOMETRY_TIER_DISABLED',
            'COVERAGE_GAP',
            'PERMIT_LAYER_UNAVAILABLE',
            'RIGHTS_BLOCKED',
            'LICENCE_UNKNOWN',
            'INSUFFICIENT_COVERAGE',
            'DISCLOSURE_NOT_ACCEPTED',
            'ACCESS_NOT_ENTITLED'
        )
    );
$$ LANGUAGE sql IMMUTABLE;
-- REFUSAL_CODES_END

ALTER TABLE property_file
    ADD CONSTRAINT property_file_refusal_codes_known
    CHECK (refusals_codes_valid(refusals));
