-- 0048_refusals_codes_valid_reject_null_shapes.sql
-- Serves: I8. P10, README finding #8.
--
-- THE GAP. 0038's refusals_codes_valid(refusals) is
--   WHERE elem ->> 'code' NOT IN (...)
-- elem ->> 'code' evaluates SQL NULL whenever 'code' is absent ({}), present
-- with a JSON null value ({"code": null}), or elem itself is not an object
-- (a bare string element) -- the ->> operator returns NULL, not an error,
-- for all three. NULL NOT IN (...) evaluates NULL, not true; a WHERE clause
-- only ever includes rows where the condition is TRUE, so a NULL-producing
-- row is silently excluded from the offending set NOT EXISTS checks for.
-- Confirmed directly against a real database before writing this, not
-- assumed: property_file rows with refusals = '[{}]', '[{"code": null}]'
-- and '["not-an-object"]' were all ACCEPTED by the CHECK that exists
-- specifically to reject an invalid code. This is CONVENTIONS.md's
-- "NULL inside a constraint silently disables it" class, a second instance
-- of the same defect 0045 has (README finding #19, fixed alongside this one
-- in 0049) -- argued together as one package, P10.
--
-- A FOURTH SHAPE, established the same way: refusals itself not an array at
-- all (a jsonb object or scalar). jsonb_array_elements(refusals) does NOT
-- return NULL or silently accept this -- it raises a hard runtime error
-- ("cannot extract elements from an object" / "... from a scalar"),
-- confirmed directly. That is a worse failure mode than a clean CHECK
-- violation, not a better one: an uncaught function error is not a typed
-- constraint-violation a caller can distinguish from any other bug, and it
-- fires regardless of file status (file_refusal_reason's own
-- jsonb_array_length(refusals) call hits the identical error first whenever
-- status='refused', for the same reason, an existing and unrelated
-- crash-instead-of-reject this migration also closes as a direct
-- consequence of guarding the shape up front).
--
-- THE FIX. CREATE OR REPLACE the same function (property_file_refusal_codes_known
-- already calls it by name; no reason to fork the name when the vocabulary
-- and purpose are unchanged -- only the shape validation is being
-- tightened), guarded by an explicit CASE so the non-array check is
-- guaranteed to short-circuit before jsonb_array_elements ever runs on a
-- non-array value (CASE WHEN/THEN branches are evaluated only when
-- selected, an SQL-standard guarantee AND/OR does not share -- confirmed
-- directly before relying on it here, same reasoning P13's changed_rows fix
-- already used for its own CASE). Vocabulary list is byte-identical to
-- 0038's -- copied, not edited -- because build/qa_check.py's
-- check_refusal_codes_match_spec reads ITS markers from 0038's own file
-- text specifically (REFUSAL_CODE_MIGRATION = ".../0038_refusals_code_check.sql",
-- hardcoded), never re-reading any later migration. 0038 is not edited here
-- (migrations are forward-only) and its vocabulary has not changed, so that
-- check keeps passing unchanged -- confirmed by running it after this
-- migration, not assumed.
--
-- Existing rows checked before writing this migration, not assumed clean:
-- every property_file row on every database reachable from this session
-- (ledgex_schema_check plus seven tier-2 scratch databases) already has
-- jsonb_typeof(refusals) = 'array' with every element a well-formed
-- {"code": <valid>, ...} object -- confirmed by direct query, zero rows
-- would be rejected by the tightened CHECK. ALTER TABLE ... ADD CONSTRAINT
-- validates existing rows (the DROP+ADD below deliberately re-triggers that
-- validation, not sidestepped via a bare CREATE OR REPLACE FUNCTION left
-- under the OLD, already-validated constraint) -- had any offending row
-- existed anywhere reachable, this migration would have failed on
-- application there and remediation would have been its own step, reported
-- separately, not silently absorbed here.
--
-- DROP + ADD, not left as a silent CREATE OR REPLACE under the old
-- constraint name: same shape 0020_lifecycle_constraints.sql already
-- established for replacing a defective CHECK (DROP CONSTRAINT by name,
-- ADD CONSTRAINT with a new explicit name) -- explicit CONSTRAINT names on
-- every new constraint, per CLAUDE.md, and DROP+ADD is what forces Postgres
-- to actually re-validate every existing row against the tightened logic,
-- which a same-named CREATE OR REPLACE FUNCTION underneath an unchanged
-- constraint would not have done.

CREATE OR REPLACE FUNCTION public.refusals_codes_valid(refusals jsonb) RETURNS boolean AS $$
    SELECT CASE
        WHEN jsonb_typeof(refusals) IS DISTINCT FROM 'array' THEN false
        ELSE NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(refusals) AS elem
            WHERE jsonb_typeof(elem) IS DISTINCT FROM 'object'
               OR elem ->> 'code' IS NULL
               OR elem ->> 'code' NOT IN (
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
        )
    END;
$$ LANGUAGE sql IMMUTABLE;

ALTER TABLE property_file
    DROP CONSTRAINT property_file_refusal_codes_known;

ALTER TABLE property_file
    ADD CONSTRAINT property_file_refusal_codes_known_shape_checked
    CHECK (refusals_codes_valid(refusals));
