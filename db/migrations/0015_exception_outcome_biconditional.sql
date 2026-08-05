-- 0015_exception_outcome_biconditional.sql
-- parcel_exception (0010): make the outcome/resolution CHECK a biconditional.
--
-- The original CHECK (auto-named parcel_exception_check by Postgres, since
-- 0010 declared it inline with no CONSTRAINT name — confirmed live via
-- `SELECT conname FROM pg_constraint WHERE conrelid =
-- 'parcel_exception'::regclass AND contype = 'c'` before writing this
-- migration) only constrained one direction: outcome <> 'open' requires
-- resolved_at and resolved_by. Nothing stopped outcome = 'open' from also
-- carrying resolved_at/resolved_by, which would misrepresent an open
-- exception as already closed. The replacement is a named, two-directional
-- CHECK: a row is either open with no resolution recorded, or resolved (in
-- any of the non-open outcomes) with both recorded — never a mix of the two.
--
-- resolved_by is an actor identity, not necessarily a person — most
-- closures are automated and record something like
-- 'system:staleness_detector@1.2.0'.
--
-- Requiring resolved_at/resolved_by for 'unresolved' specifically (one of
-- the non-open outcomes covered by this CHECK) remains intentional, per
-- I12: a closeable outcome is required, and "looked and could not
-- determine" is itself a closure that something performed — it still has
-- to say what looked and when. This migration does not change that
-- requirement, only makes the CHECK enforce it symmetrically with 'open'.

ALTER TABLE parcel_exception
    DROP CONSTRAINT parcel_exception_check;

ALTER TABLE parcel_exception
    ADD CONSTRAINT parcel_exception_outcome_resolution_biconditional CHECK (
        (outcome = 'open' AND resolved_at IS NULL AND resolved_by IS NULL)
        OR
        (outcome <> 'open' AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL)
    );
