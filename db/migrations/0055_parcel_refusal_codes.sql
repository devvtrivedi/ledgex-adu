-- 0055_parcel_refusal_codes.sql
-- Serves: I8. README finding #40. P37.
-- Source: docs/LEDGEX_SPEC.md §9.
--
-- THE GAP (P36, finding #40; re-graded P37). compose_property_file.py raised
-- Python exceptions (SystemExit) for two genuine, deterministic runtime
-- conditions instead of returning a typed refusal -- an I8 violation TODAY,
-- for any caller, independent of whether api/ exists (P36 had graded this
-- "latent, pending api/" for all four of finding #40's members; re-examined
-- against I8's actual text -- "Refusal is a typed return value, not an
-- exception. Every runtime stage can refuse deterministically" -- two of the
-- four are live now, not latent: see prompts/P37-parcel-refusal-codes.md
-- section 2 for the full re-grade, including the two members that stay
-- correctly latent).
--
-- TWO NEW CODES, NOT ONE, AND NOT PARCEL_NOT_FOUND. §9's existing
-- PARCEL_NOT_FOUND is scoped, verbatim, to stage L0 with the text "APN not
-- present in any parcel layer" -- checked directly in docs/LEDGEX_SPEC.md
-- before reusing it, not assumed from the name. That is an ADDRESS/APN
-- resolution failure (the same L0 family as JURISDICTION_UNRESOLVED/
-- JURISDICTION_UNSUPPORTED/JURISDICTION_BOUNDARY_CONFLICT). compose()'s own
-- read at line 258 (pre-fix) is a BY-ID lookup of an already-internal
-- parcel.id uuid -- a caller supplying a stale, mistyped or fabricated
-- reference is a different condition from "this APN is not in our parcel
-- layer at all": the former presupposes L0 already succeeded once (or was
-- bypassed entirely, e.g. a direct --parcel-id); the latter is L0 itself
-- failing. Reusing PARCEL_NOT_FOUND for both would make one code carry two
-- claims a customer would act on differently (supply a different APN vs.
-- re-check a stored reference) -- the same reasoning 0053 used to keep
-- ELECTION_REQUIRED/ELECTION_NOT_SUPPORTED separate from RULE_UNAVAILABLE
-- rather than folding them in because the name was adjacent.
--
--   PARCEL_REFERENCE_UNKNOWN -- stage L0. No parcel row exists for a
--   caller-supplied parcel_id. Structurally CANNOT be written to a
--   property_file row: parcel_id is NOT NULL REFERENCES parcel(id), and
--   there is no parcel to attach one to. compose() returns
--   Result.refuse(Refusal(code="PARCEL_REFERENCE_UNKNOWN", ...)) directly --
--   an in-memory typed return value, not a database row, not an exception.
--
--   PARCEL_NO_FACTS -- stage L8. The parcel row exists (a real, resolvable
--   identity), but current_fact_at() returns zero rows as of the given
--   as_of -- nothing for this composer to gate or deliver. Unlike
--   PARCEL_REFERENCE_UNKNOWN, a property_file row CAN be written here
--   (parcel_id/jurisdiction_id are both real, satisfying every FK) and IS,
--   the same refuse-first pattern GEOMETRY_TIER_DISABLED/RIGHTS_BLOCKED/
--   ELECTION_REQUIRED already use -- refusals accumulate (P25), so this
--   code can co-occur with L5/L7's own refusals exactly like any other.
--   L8, not L4 or COVERAGE_GAP/INSUFFICIENT_COVERAGE (both considered):
--   COVERAGE_GAP/INSUFFICIENT_COVERAGE presuppose a "required fields"
--   mechanism this minimal composer has never built (unmet_fields is
--   written NULL/empty by every caller today) -- reusing either would
--   assert a mechanism that does not exist, the same invented-semantics
--   risk finding #35/#36 warned against elsewhere. Zero facts is a
--   distinct, prior condition -- not "some coverage, insufficient" but "no
--   coverage attempted or recorded at all" -- and gets its own code rather
--   than either of those two by default, per instruction.
--
-- Vocabulary list otherwise byte-identical to 0038/0048/0053's own 21
-- codes, in the same order, plus these two appended.
--
-- POINTER MOVE (same discipline 0053 established over 0038/0048).
-- build/qa_check.py's REFUSAL_CODE_MIGRATION, hardcoded to one migration
-- file's own REFUSAL_CODES_BEGIN/END markers, moves from 0053 to this file
-- -- 0053 is not edited (forward-only, already merged), and this is the
-- next real widening.
--
-- EXISTING ROWS -- re-queried fresh, not assumed. make migrate-verify run
-- first: ledgex_schema_check, 54 migrations, MATCH. 7 property_file rows,
-- none carrying either new code (neither existed before this migration) --
-- zero rows would be rejected by the widened CHECK.

CREATE OR REPLACE FUNCTION public.refusals_codes_valid(refusals jsonb) RETURNS boolean AS $$
    SELECT CASE
        WHEN jsonb_typeof(refusals) IS DISTINCT FROM 'array' THEN false
        ELSE NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(refusals) AS elem
            WHERE jsonb_typeof(elem) IS DISTINCT FROM 'object'
               OR elem ->> 'code' IS NULL
               OR elem ->> 'code' NOT IN (
-- REFUSAL_CODES_BEGIN -- build/qa_check.py's check_refusal_codes_match_spec
-- reads the quoted string literals between these two markers and diffs
-- them against §9's vocabulary in docs/LEDGEX_SPEC.md. Keep the list here,
-- and only here -- do not duplicate it elsewhere in this file. Moved here
-- from 0053 by 0055 -- see this file's own header for why.
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
                    'ACCESS_NOT_ENTITLED',
                    'ELECTION_REQUIRED',
                    'ELECTION_NOT_SUPPORTED',
                    'PARCEL_REFERENCE_UNKNOWN',
                    'PARCEL_NO_FACTS'
-- REFUSAL_CODES_END
               )
        )
    END;
$$ LANGUAGE sql IMMUTABLE;

ALTER TABLE property_file
    DROP CONSTRAINT property_file_refusal_codes_known_election;

ALTER TABLE property_file
    ADD CONSTRAINT property_file_refusal_codes_known_parcel
    CHECK (refusals_codes_valid(refusals));
