-- 0053_refusal_codes_election.sql
-- Serves: I8. README finding #35. P34.
-- Source: docs/LEDGEX_SPEC.md §9.
--
-- A CORRECTION TO THIS PACKAGE'S OWN DESIGN REPORT, made before writing
-- anything else -- CONVENTIONS.md: never silently absorb a wrong premise.
-- prompts/P33-correct-36-close-37-design-35.md section 3 names the
-- refusal-code sync target as "db/migrations/0048's own CHECK list" /
-- "0048's own REFUSALS_CODES_BEGIN/END list". Checked directly before
-- writing this migration, not assumed: build/qa_check.py's
-- check_refusal_codes_match_spec() hardcodes
-- REFUSAL_CODE_MIGRATION = MIGRATIONS_DIR / "0038_refusals_code_check.sql"
-- and has NEVER pointed at 0048 -- confirmed by grep, and by 0048's own
-- header, which says so explicitly: "Vocabulary list is byte-identical to
-- 0038's -- copied, not edited -- because build/qa_check.py's
-- check_refusal_codes_match_spec reads ITS markers from 0038's own file
-- text specifically ... never re-reading any later migration." 0048
-- REPLACED the live function (CREATE OR REPLACE, tightened NULL/shape
-- handling) but deliberately did NOT carry the REFUSAL_CODES_BEGIN/END
-- markers -- those still live only in 0038's original CREATE FUNCTION
-- text, which the sync check reads as a static source even though 0038's
-- own function body is no longer the one Postgres runs. This is the
-- FIRST migration since 0038 to actually widen the vocabulary -- every
-- migration in between (0048) kept it byte-identical specifically so this
-- pointer would never need to move. It has to move now: 0038 cannot be
-- edited (migrations are forward-only, already merged), and this
-- migration's vocabulary is genuinely new. Fixed in the same commit as
-- this migration, not deferred: build/qa_check.py's REFUSAL_CODE_MIGRATION
-- now points at THIS file, and the REFUSAL_CODES_BEGIN/END markers below
-- carry the full, current vocabulary -- the same shape 0038 originally
-- established, moved forward exactly once, by construction, the one time
-- it needs to move.
--
-- THE CHANGE. Two new codes (prompts/P34-election-parameter-build.md
-- section 0(a); prompts/P33-correct-36-close-37-design-35.md section 3
-- for the first):
--
--   ELECTION_REQUIRED -- stage L5. An election-dependent conclusion was
--   touched and no election was supplied at all. Actionable by the
--   caller: supply one on a new request (I14 -- see 0052's own header;
--   this is a refused response in the same synchronous call, never a
--   queued/resumed one).
--
--   ELECTION_NOT_SUPPORTED -- stage L5. An election WAS supplied, but
--   scripts/compose_property_file.py's own CONCLUSION_RULE_KEYS has no
--   entry for (conclusion, election) -- this composer has never been
--   taught which rule_key governs that pairing, independent of any as-of
--   date. NOT the same claim as RULE_UNAVAILABLE, which asserts a
--   rule_key WAS known and a real query against `rule`'s effective window
--   found no matching row -- a temporal claim, backed by a query that
--   ELECTION_NOT_SUPPORTED's own case never reaches at all. Collapsing
--   the two would make RULE_UNAVAILABLE mean "no rule effective OR this
--   composer doesn't know what to look for in the first place" -- exactly
--   the "subtler lie than the placeholder it replaced" shape
--   prompts/P31-l5-refuse-first-one-real-rule.md was warned against for
--   this same code. Same reasoning P29 used to split I11's own
--   recording/application halves rather than reuse one code for two
--   causes -- here, "the composer's knowledge is incomplete" (a static,
--   as-of-independent fact about this codebase) and "no rule is currently
--   effective" (a live fact about the `rule` table) are kept as two
--   codes because a customer acts on them differently: the first will
--   never resolve itself by waiting; the second might, the moment a rule
--   is seeded.
--
-- DROP+ADD, not CREATE OR REPLACE under the old constraint name -- same
-- reasoning 0048 gave: forces Postgres to re-validate every existing row
-- against the widened list, not merely swap logic under an
-- already-validated constraint. Existing rows checked before writing this
-- migration, not assumed: every property_file.refusals row on every
-- database reachable from this session today carries only
-- GEOMETRY_TIER_DISABLED and/or RIGHTS_BLOCKED codes, both already
-- present in the widened list unchanged -- zero rows would be rejected.
--
-- Vocabulary list is otherwise byte-identical to 0038's/0048's own 19
-- codes, in the same order, plus the two new ones appended -- not
-- reordered, so a future diff against either prior migration's own list
-- stays legible.

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
-- from 0038 by 0053 -- see this file's own header for why.
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
                    'ELECTION_NOT_SUPPORTED'
-- REFUSAL_CODES_END
               )
        )
    END;
$$ LANGUAGE sql IMMUTABLE;

ALTER TABLE property_file
    DROP CONSTRAINT property_file_refusal_codes_known_shape_checked;

ALTER TABLE property_file
    ADD CONSTRAINT property_file_refusal_codes_known_election
    CHECK (refusals_codes_valid(refusals));
