-- 0006_fact.sql
-- The fact ledger.
-- Serves: C1-C5, C8, I2, I3, I13.
-- Source: docs/LEDGEX_SPEC.md §3.6.

CREATE TABLE fact (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id      uuid NOT NULL REFERENCES parcel(id),
    field_key      text NOT NULL REFERENCES field_definition(field_key),
    value          jsonb NOT NULL,
    unit           text,
    local_verbatim text,                      -- the source's own string. NEVER discard.

    -- provenance (C1)
    source_id      text REFERENCES source(id),
    source_url     text,
    layer_item_id  text,
    snapshot_id    text REFERENCES snapshot(id),
    method         access_method NOT NULL,

    -- time, three separate facts (C8 / I7)
    retrieved_at           timestamptz,
    source_published_at    timestamptz,
    source_cadence_stated  text,
    effective_from timestamptz NOT NULL,      -- valid time
    effective_to   timestamptz,
    recorded_at    timestamptz NOT NULL DEFAULT now(),   -- transaction time
    superseded_at  timestamptz,

    -- rights (C6 / I3)
    licence_id     text NOT NULL REFERENCES licence(id),

    -- judgement (C4, C5)
    confidence         confidence_level NOT NULL,
    confidence_rule_id text NOT NULL,
    conflict           conflict_state NOT NULL DEFAULT 'agree',

    -- lineage (C3)
    method_version  text,
    ruleset_version text,
    pack_version    text NOT NULL,

    CONSTRAINT fact_valid_time CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT fact_txn_time   CHECK (superseded_at IS NULL OR superseded_at >= recorded_at),

    -- I2: retrieved facts need a source and a snapshot; derived facts need a method version
    CONSTRAINT fact_provenance_complete CHECK (
        (method = 'derived'
            AND source_id IS NULL AND snapshot_id IS NULL
            AND method_version IS NOT NULL)
        OR
        (method <> 'derived'
            AND source_id IS NOT NULL AND snapshot_id IS NOT NULL
            AND retrieved_at IS NOT NULL AND source_url IS NOT NULL)
    ),

    -- I13: no human observation ever becomes a fact. Every fact in the system is
    -- machine-retrieved or deterministically derived, so there is no "unverified"
    -- class of fact to reason about, label, or accidentally price into a file.
    CONSTRAINT fact_method_automated CHECK (
        method IN ('direct','bulk','derived')
    )
);

-- One current belief per (parcel, field, source). Corrections supersede.
CREATE UNIQUE INDEX fact_one_current_per_source
    ON fact (parcel_id, field_key, COALESCE(source_id, '~derived'), COALESCE(method_version, '~'))
    WHERE superseded_at IS NULL;

CREATE INDEX fact_lookup    ON fact (parcel_id, field_key, recorded_at DESC);
CREATE INDEX fact_current   ON fact (parcel_id, field_key) WHERE superseded_at IS NULL;
CREATE INDEX fact_by_source ON fact (source_id, retrieved_at DESC);
CREATE INDEX fact_conflicts ON fact (conflict) WHERE conflict <> 'agree';

-- Lineage as a junction table: FK integrity + clean recursive CTE.
CREATE TABLE fact_input (
    fact_id       uuid NOT NULL REFERENCES fact(id) ON DELETE CASCADE,
    input_fact_id uuid NOT NULL REFERENCES fact(id),
    ordinal       smallint NOT NULL,
    role          text NOT NULL,        -- 'lot_area', 'setback_rule', ...
    PRIMARY KEY (fact_id, input_fact_id),
    CONSTRAINT fact_input_not_self CHECK (fact_id <> input_fact_id)
);

-- v1.2 change to fact_one_current_per_source. The v1.1 index keyed derived
-- facts on the literal '~derived', which made two derived facts for the same
-- (parcel, field) under different method_versions collide. method_version is
-- now part of the key. Retrieved facts are unaffected (method_version is null
-- for them and coalesces to '~').
