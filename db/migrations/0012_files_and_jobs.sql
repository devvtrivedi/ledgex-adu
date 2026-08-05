-- 0012_files_and_jobs.sql
-- Property files and jobs.
-- Source: docs/LEDGEX_SPEC.md §3.12.

CREATE TABLE property_file (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id            uuid NOT NULL REFERENCES parcel(id),
    jurisdiction_id      text NOT NULL REFERENCES jurisdiction(id),
    channel              output_channel NOT NULL,
    status               file_status NOT NULL,
    composed_at          timestamptz NOT NULL DEFAULT now(),
    as_of                timestamptz NOT NULL,
    pack_version         text NOT NULL,
    ruleset_version      text NOT NULL,
    composer_version     text NOT NULL,
    geometry_tier_used   boolean NOT NULL,
    assumptions          jsonb NOT NULL DEFAULT '{}'::jsonb,
    refusals             jsonb NOT NULL DEFAULT '[]'::jsonb,
    omitted_for_rights   jsonb NOT NULL DEFAULT '[]'::jsonb,   -- I6, visible not silent
    attribution          text[] NOT NULL DEFAULT '{}',
    payload              jsonb NOT NULL,
    payload_hash         text NOT NULL,           -- v1.2: sha256 of the delivered payload
    delivered_at         timestamptz,

    -- automated unit economics; replaces v1.0 manual-hour instrumentation (§10)
    compose_ms           integer NOT NULL,
    source_calls         integer NOT NULL DEFAULT 0,
    compute_cost_micros  bigint NOT NULL DEFAULT 0,   -- metered, not estimated
    storage_cost_micros  bigint NOT NULL DEFAULT 0,   -- v1.2: Plan §15 measure 5
    unmet_fields         text[] NOT NULL DEFAULT '{}', -- required fields not retrieved

    CONSTRAINT file_refusal_reason CHECK (
        status <> 'refused' OR jsonb_array_length(refusals) > 0
    ),
    -- a partial file must say what is missing; silence is not permitted
    CONSTRAINT file_partial_declares_gap CHECK (
        status <> 'partial'
        OR cardinality(unmet_fields) > 0
        OR jsonb_array_length(refusals) > 0
    ),
    -- v1.2: a refused file is never delivered as a product artifact
    CONSTRAINT file_refused_not_delivered CHECK (
        status <> 'refused' OR delivered_at IS NULL
    )
);

-- v1.6: Property File rows carry delivery outcome and cost telemetry only.
-- Commercial access lives in commerce.access_entitlement and
-- commerce.subscription; no accepted price or per-file settlement field
-- exists.

CREATE TABLE property_file_fact (
    property_file_id uuid NOT NULL REFERENCES property_file(id) ON DELETE CASCADE,
    fact_id          uuid NOT NULL REFERENCES fact(id),
    -- v1.2: I6 applies to every fact TOUCHED, not only every fact rendered.
    -- 'gate' facts resolve jurisdiction and never appear in the payload;
    -- they are still recorded here and still pass through the licence gate.
    use              text NOT NULL DEFAULT 'rendered'
                     CHECK (use IN ('rendered','gate','input')),
    PRIMARY KEY (property_file_id, fact_id)
);

CREATE TABLE job_run (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_key         text NOT NULL,
    jurisdiction_id text REFERENCES jurisdiction(id),
    source_id       text REFERENCES source(id),
    status          job_status NOT NULL DEFAULT 'running',
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    snapshot_id     text REFERENCES snapshot(id),
    rows_in         integer,
    rows_out        integer,
    schema_drift    jsonb,                          -- fields expected but missing
    error           text,
    CONSTRAINT job_terminal CHECK (
        status = 'running' OR finished_at IS NOT NULL
    )
);

CREATE INDEX job_run_recent ON job_run (job_key, started_at DESC);

-- deferred FK: support_request was created in 0011, before property_file existed
ALTER TABLE support_request
    ADD CONSTRAINT support_property_file_fk
    FOREIGN KEY (property_file_id) REFERENCES property_file(id);
