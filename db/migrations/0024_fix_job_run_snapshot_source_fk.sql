-- 0024_fix_job_run_snapshot_source_fk.sql
-- Fixes: job_run_snapshot_source_fk (0022).
--
-- 0022's job_run_snapshot_source_fk was written
-- FOREIGN KEY (source_id, snapshot_id) REFERENCES snapshot (id, source_id).
-- Positionally that checks job_run.source_id against snapshot.id and
-- job_run.snapshot_id against snapshot.source_id -- transposed relative to
-- every other composite FK in 0018/0022, all of which put the "this row's
-- own identity" column first and the "shared with the target" column
-- second (see fact_snapshot_source_fk in 0018, the pattern this one was
-- supposed to mirror: FOREIGN KEY (snapshot_id, source_id) REFERENCES
-- snapshot (id, source_id)).
--
-- Found for real, not by inspection: the first live ingestion run
-- (scripts/ingest_parcels.py Phase B) inserted a correct, real snapshot
-- row for ca_san_jose.parcels and then could not link job_run.snapshot_id
-- to it -- UPDATE job_run ... SET snapshot_id = ... failed with
-- job_run_snapshot_source_fk on a job_run whose source_id and the
-- snapshot's source_id were identical. As written, the constraint could
-- never be satisfied by any job_run citing a real snapshot: job_run's
-- source_id values look like 'ca_san_jose.parcels'; snapshot's id values
-- look like 'ca_san_jose.parcels:sha256:<hex>' -- they can never be equal
-- except by construction accident, so every linkage attempt failed
-- unconditionally, valid or not.
--
-- This is also why db/tests/invariants.sql's T26 (0018/0022 phase) was a
-- false-positive negative control: it asserted that a job_run citing
-- source A while pointing at source B's snapshot gets rejected, and it
-- did get rejected -- but under the transposed constraint, a job_run
-- citing source A and correctly pointing at source A's OWN snapshot would
-- ALSO have been rejected. T26 alone could not distinguish "the
-- constraint correctly discriminates on source" from "the constraint
-- rejects everything." A same-commit positive-test companion (job_run
-- citing its own source's snapshot must be ACCEPTED) closes that gap;
-- added as T31 in the same commit as this migration.
--
-- Forward-only: 0022 is merged and applied, not edited. DROP and re-ADD
-- under the same constraint name, corrected column order.

ALTER TABLE job_run
    DROP CONSTRAINT job_run_snapshot_source_fk;

ALTER TABLE job_run
    ADD CONSTRAINT job_run_snapshot_source_fk
    FOREIGN KEY (snapshot_id, source_id) REFERENCES snapshot (id, source_id);
