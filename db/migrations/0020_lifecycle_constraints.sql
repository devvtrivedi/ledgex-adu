-- 0020_lifecycle_constraints.sql
-- Serves: I12 (exception evidence), I2/C1 (provenance timing), C5 (cost telemetry).
--
-- Two existing CHECKs have the same one-way defect 0015 already fixed for
-- parcel_exception: job_run.job_terminal and
-- support_request.support_correction_consistent each constrain only one
-- direction, leaving the reverse case open to a misrepresenting row (a
-- 'running' job_run with finished_at already set; a caused_correction=false
-- support_request that still carries a correcting_fact_id). Both existing
-- constraints are already named (job_terminal, support_correction_consistent
-- -- confirmed directly from db/migrations/0011_support.sql and
-- 0012_files_and_jobs.sql, no pg_constraint lookup needed this time), so
-- each is DROPped by name and replaced with a named, two-directional
-- biconditional, same shape as 0015's parcel_exception_outcome_resolution_biconditional.
--
-- Plus five bounds nothing enforced before: a finished job that ended
-- before it started, a negative row count, a negative-cost or
-- negative-duration Property File, and an exception resolved before it was
-- ever detected. Every new constraint is explicitly named (never left for
-- Postgres to auto-name), per CLAUDE.md.

ALTER TABLE job_run
    DROP CONSTRAINT job_terminal;

ALTER TABLE job_run
    ADD CONSTRAINT job_run_status_finished_at_biconditional CHECK (
        (status = 'running' AND finished_at IS NULL)
        OR
        (status <> 'running' AND finished_at IS NOT NULL)
    );

ALTER TABLE support_request
    DROP CONSTRAINT support_correction_consistent;

ALTER TABLE support_request
    ADD CONSTRAINT support_request_correction_consistent_biconditional CHECK (
        (caused_correction = false AND correcting_fact_id IS NULL)
        OR
        (caused_correction = true AND correcting_fact_id IS NOT NULL)
    );

ALTER TABLE job_run
    ADD CONSTRAINT job_run_finished_after_started
    CHECK (finished_at IS NULL OR finished_at >= started_at);

ALTER TABLE job_run
    ADD CONSTRAINT job_run_rows_in_nonnegative
    CHECK (rows_in IS NULL OR rows_in >= 0);

ALTER TABLE job_run
    ADD CONSTRAINT job_run_rows_out_nonnegative
    CHECK (rows_out IS NULL OR rows_out >= 0);

ALTER TABLE property_file
    ADD CONSTRAINT property_file_compose_ms_nonnegative
    CHECK (compose_ms >= 0);

ALTER TABLE property_file
    ADD CONSTRAINT property_file_source_calls_nonnegative
    CHECK (source_calls >= 0);

ALTER TABLE property_file
    ADD CONSTRAINT property_file_compute_cost_micros_nonnegative
    CHECK (compute_cost_micros >= 0);

ALTER TABLE property_file
    ADD CONSTRAINT property_file_storage_cost_micros_nonnegative
    CHECK (storage_cost_micros >= 0);

ALTER TABLE parcel_exception
    ADD CONSTRAINT parcel_exception_resolved_after_detected
    CHECK (resolved_at IS NULL OR resolved_at >= detected_at);
