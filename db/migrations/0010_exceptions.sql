-- 0010_exceptions.sql
-- Exceptions.
-- Source: docs/LEDGEX_SPEC.md §3.10.
--
-- Track A outcomes are recorded internally after delivery. They never gate,
-- delay or supplement a customer file and never create a human delivery
-- queue.

CREATE TABLE parcel_exception (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id        uuid NOT NULL REFERENCES parcel(id),
    jurisdiction_id  text NOT NULL REFERENCES jurisdiction(id),
    -- Spec text types both `type` and `severity` as exception_severity,
    -- leaving exception_type (§3.1) declared but never referenced anywhere
    -- in the schema. `type` is corrected to exception_type here — that enum
    -- exists for exactly this column (record_to_ground / cross_source /
    -- staleness / rule_boundary / coverage_gap / rights_gap) and has no
    -- other use.
    type             exception_type NOT NULL,
    severity         exception_severity NOT NULL,
    detector_key     text NOT NULL,
    detector_version text NOT NULL,
    ruleset_version  text,
    detail           jsonb NOT NULL,
    detected_at      timestamptz NOT NULL DEFAULT now(),
    outcome          exception_outcome NOT NULL DEFAULT 'open',
    resolved_at      timestamptz,
    -- An actor identity, not necessarily a person — most closures are
    -- automated and record something like
    -- 'system:staleness_detector@1.2.0'. Requiring resolved_at and
    -- resolved_by for every non-open outcome, including 'unresolved', is
    -- intentional, not an oversight: I12 requires a closeable outcome, and
    -- "looked and could not determine" is itself a closure that something
    -- performed — it still needs to say what looked and when.
    resolved_by      text,
    resolution_notes text,
    CHECK (outcome = 'open' OR (resolved_at IS NOT NULL AND resolved_by IS NOT NULL))
);

CREATE TABLE exception_evidence (
    exception_id uuid NOT NULL REFERENCES parcel_exception(id) ON DELETE CASCADE,
    fact_id      uuid NOT NULL REFERENCES fact(id),
    role         text NOT NULL,
    PRIMARY KEY (exception_id, fact_id)
);
