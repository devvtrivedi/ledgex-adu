-- 0002_registries.sql
-- Serves: C6, I3, I6, I14.
-- Source: docs/LEDGEX_SPEC.md §3.2.

CREATE TABLE jurisdiction (
    id                     text PRIMARY KEY,             -- 'ca_san_jose'
    display_name           text NOT NULL,
    kind                   text NOT NULL CHECK (kind IN ('city','county','state')),
    parent_id              text REFERENCES jurisdiction(id),
    state_code             char(2) NOT NULL,
    tier                   jurisdiction_tier NOT NULL DEFAULT 'blocked',
    pack_version           text NOT NULL,
    boundary_source_id     text,                         -- FK added after source exists
    geometry_tier_enabled  boolean NOT NULL DEFAULT false,   -- I10 / C7
    supported              boolean NOT NULL DEFAULT false,
    created_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE licence (
    id                text PRIMARY KEY,        -- 'cc0', 'cc_by_4_0', 'sj_portal_terms'
    display_name      text NOT NULL,
    restriction       use_restriction NOT NULL,
    commercial_use    permission_state NOT NULL DEFAULT 'unknown',
    redistribution    permission_state NOT NULL DEFAULT 'unknown',
    attribution_text  text,
    terms_url         text,
    evidence_uri      text,                    -- stored snapshot of the terms
    observed_at       timestamptz NOT NULL,
    cleared_by        text,                    -- counsel / written permission
    cleared_at        timestamptz,
    notes             text,
    CONSTRAINT licence_attribution_present
        CHECK (restriction <> 'attribution' OR attribution_text IS NOT NULL)
);

-- The channel matrix. Absence of a row = denied. Default deny (I6).
CREATE TABLE licence_channel (
    licence_id text NOT NULL REFERENCES licence(id) ON DELETE CASCADE,
    channel    output_channel NOT NULL,
    allowed    boolean NOT NULL,
    rationale  text NOT NULL,
    PRIMARY KEY (licence_id, channel)
);

CREATE TABLE source (
    id                  text PRIMARY KEY,    -- 'ca_san_jose.building_permits_active'
    jurisdiction_id     text NOT NULL REFERENCES jurisdiction(id),
    display_name        text NOT NULL,
    steward             text NOT NULL,
    method              access_method NOT NULL,
    phase_status        source_phase_status NOT NULL DEFAULT 'blocked_rights',
    phase_status_reason text NOT NULL,        -- v1.2: always stated, never blank
    endpoint_url        text,                 -- null only for method='manual'
    layer_item_id       text,
    query_params        jsonb NOT NULL DEFAULT '{}'::jsonb,
    licence_id          text NOT NULL REFERENCES licence(id),
    cadence_stated      text,                 -- verbatim, e.g. 'weekly, Mondays'
    cadence_observed_s  integer,              -- measured, seconds; null until measured
    earliest_record_date date,                -- measured depth of a history series
    expected_fields     jsonb NOT NULL DEFAULT '[]'::jsonb,
    url_verified_at     timestamptz,          -- null = NOT yet verified; blocks prod
    active              boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT source_endpoint_required
        CHECK (method = 'manual' OR endpoint_url IS NOT NULL),
    CONSTRAINT source_active_requires_verification
        CHECK (active = false OR url_verified_at IS NOT NULL),
    -- I14: a source a machine cannot read can never be switched on. It is recorded
    -- so its absence is a known coverage gap, not an oversight.
    CONSTRAINT source_active_requires_machine_access
        CHECK (active = false OR method IN ('direct','bulk')),
    -- v1.2: active and phase_status must agree. Prevents the §7.3 class of drift
    -- where a summary table said "Yes" while the licence said otherwise.
    CONSTRAINT source_active_matches_phase
        CHECK (active = false OR phase_status = 'active')
);

ALTER TABLE jurisdiction
    ADD CONSTRAINT jurisdiction_boundary_source_fk
    FOREIGN KEY (boundary_source_id) REFERENCES source(id);

-- Which steward wins for which field in which jurisdiction (§3.8 current_fact).
CREATE TABLE source_rank (
    jurisdiction_id text NOT NULL REFERENCES jurisdiction(id),
    field_key       text NOT NULL,
    source_id       text NOT NULL REFERENCES source(id),
    rank            smallint NOT NULL CHECK (rank > 0),
    rationale       text NOT NULL,
    PRIMARY KEY (jurisdiction_id, field_key, source_id),
    UNIQUE (jurisdiction_id, field_key, rank)
);

-- source_rank.field_key gains an FK to field_definition in migration 0003,
-- which creates that table.

-- phase_status is descriptive, not authoritative. Runtime channel eligibility
-- is determined solely by licences.yaml -> licence + licence_channel.
-- phase_status records why a source is off so a human can read the ledger;
-- source_active_matches_phase keeps the two from contradicting each other.
-- See §7.3.
