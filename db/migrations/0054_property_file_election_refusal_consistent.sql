-- 0054_property_file_election_refusal_consistent.sql
-- Serves: I8. README finding #39. P36.
-- Source: docs/LEDGEX_SPEC.md §3.12.
--
-- THE GAP (P35, finding #39). Nothing ties property_file.election (0052) to
-- ELECTION_REQUIRED/ELECTION_NOT_SUPPORTED in refusals (0053). A row could
-- carry election='city' AND an ELECTION_REQUIRED refusal, or election IS
-- NULL AND an ELECTION_NOT_SUPPORTED refusal -- both mutually contradictory
-- on their own terms (ELECTION_REQUIRED means "none was supplied";
-- ELECTION_NOT_SUPPORTED means "one was supplied, but unmapped") and both
-- currently permitted at the storage layer.
--
-- IS THIS PREMATURE -- decided explicitly, not inherited from P35's own
-- recommendation. finding #11 (loaders not jurisdiction-scoped) is this
-- repo's own precedent for a latent, single-consumer gap staying open,
-- "forced by need, not anticipated" -- and the same question applies here:
-- finding #39 itself says the contradiction is unreachable through
-- property_file.election's only writer today (scripts/compose_property_
-- file.py). The two cases are NOT the same shape, on inspection:
--   - #11's fix requires real, un-testable-today design work: a second
--     jurisdiction that does not exist, deciding how loaders should be
--     parameterized, with no way to prove the parameterization correct
--     against real data until that jurisdiction is real. Building it now
--     would be speculative in the way CONVENTIONS warns against.
--   - #39's fix is a mechanical generalization of a pattern this schema
--     already has three working instances of (0038/0048/0053's own
--     refusals_codes_valid), fully testable RIGHT NOW against the one
--     real writer that exists, with both the violating and the legitimate
--     shapes constructible today (see T99-T102 below). There is nothing to
--     anticipate -- the CHECK enforces a fact that is already, provably,
--     always true of every row compose() can produce; it costs nothing
--     operationally and closes a real, cheap-to-close gap.
--   - Unlike #11, this repo has already lived through the counter-scenario
--     for THIS exact shape: job_run.schema_drift (0012) had exactly one
--     documented meaning and, for a long time, the closest thing to "one
--     writer" load_permits alone -- by the time 0051 investigated (README
--     finding #12), TWO real writers (load_zoning too) were stretching it
--     to carry something it was never meant to, undetected until someone
--     went looking. property_file.election is in the identical position
--     today: one writer, zero enforcement, and the exact class of gap that
--     has already bitten this repo once. That precedent, not #11's, is the
--     one that transfers.
-- Decided: BUILD, now, for this package.
--
-- THE TWO EXCLUSIONS -- narrow, not the full biconditional. P35 (section 3)
-- showed the full biconditional (election IS NULL IFF ELECTION_REQUIRED
-- present) holds today only by the coincidence that "placement" is the
-- sole, always-election-dependent conclusion compose() evaluates -- the
-- same "coincidence masks it" shape README finding #22 already named.
-- Enforcing the full biconditional would require loosening the moment a
-- second, non-election-dependent conclusion exists and a composition
-- touches only that one (a legitimate election-IS-NULL row with no
-- ELECTION_REQUIRED refusal). Only the two directions that are
-- STRUCTURALLY guaranteed -- not contingent on how many conclusions
-- exist, only on "one parameter, read once, echoed once" -- are enforced
-- here:
--   ELECTION_REQUIRED present in refusals      => election IS NULL
--   ELECTION_NOT_SUPPORTED present in refusals => election IS NOT NULL
-- Do NOT widen this to the full biconditional later just because it
-- happens to keep passing -- that would be re-deriving #22's mistake by
-- hand. Widening requires a new, separate argument that a future
-- conclusion genuinely cannot exist without an election, not merely that
-- no test has failed yet.
--
-- MECHANISM -- a CHECK backed by a LANGUAGE sql IMMUTABLE function, the
-- identical single-row shape refusals_codes_valid() already is (0038,
-- widened 0048/0053), not a trigger. Both exclusions read only the
-- current row's own election/refusals columns -- no OLD/NEW comparison,
-- no cross-row query -- exactly what a CHECK is for; a trigger (like
-- 0013's rule_no_destructive_update, which genuinely needs to compare NEW
-- against OLD across an UPDATE) would be the wrong tool here, where there
-- is no history to consult.
--
-- P37 record fix: this function has TWO NULL-sensitive operands, and this
-- header (unlike 0052's own, which reasons about election's NULL branch at
-- length) never named the other one. refusals is NOT NULL DEFAULT '[]'::jsonb
-- (0012; confirmed here directly, not assumed from the dump alone --
-- `\d property_file` against ledgex_schema_check shows the identical
-- "not null" on the live column) -- so `refusals @> ...` is total, never
-- itself produces SQL NULL, and the surrounding NOT (... OR ...) can never
-- evaluate to NULL either. Both operands are covered: election's NULL
-- branch is the real, handled, documented case the exclusions are built
-- around; refusals has no NULL branch to handle at all. A CHECK function
-- reduces to SQL NULL only when an operand genuinely can be NULL and isn't
-- guarded -- neither risk exists here.
--
-- EXISTING ROWS -- every reachable database re-queried before writing
-- this migration, not assumed clean from P35's own count (P35 found 0
-- across 7 rows; re-checked fresh here in case P35's or P36's own runs
-- had added more). make migrate-verify run first: ledgex_schema_check, 53
-- migrations, MATCH. Still 7 property_file rows, 2 with non-NULL
-- election, 0 violating either exclusion -- unchanged since P35, because
-- nothing between P35 and this migration wrote to that database (every
-- intermediate check in both packages ran against disposable scratch
-- databases instead, per this repo's own standing discipline). The ~30
-- other databases reachable on this host (p22_*-p26_* scratch databases,
-- leftover from packages that predate 0052/0053 entirely) were checked
-- for the election column's mere existence, not assumed absent: none of
-- them have it, so none can violate a constraint on a column they do not
-- have. This migration applies cleanly, with no remediation step, on
-- every real database this session can reach.

CREATE FUNCTION public.property_file_election_refusal_consistent(election text, refusals jsonb) RETURNS boolean AS $$
    SELECT NOT (
        (refusals @> '[{"code":"ELECTION_REQUIRED"}]'::jsonb AND election IS NOT NULL)
        OR
        (refusals @> '[{"code":"ELECTION_NOT_SUPPORTED"}]'::jsonb AND election IS NULL)
    );
$$ LANGUAGE sql IMMUTABLE;

ALTER TABLE property_file
    ADD CONSTRAINT property_file_election_refusal_consistent
    CHECK (property_file_election_refusal_consistent(election, refusals));

COMMENT ON FUNCTION public.property_file_election_refusal_consistent(text, jsonb) IS
    'README finding #39 / P36. Two one-way exclusions only, not the full election-IS-NULL-IFF-ELECTION_REQUIRED biconditional -- see this migration''s own header for why the biconditional is deliberately not enforced (it holds today only by the coincidence that every conclusion this composer evaluates currently needs an election, the same shape as finding #22).';
