-- 0003_fields.sql
-- Serves: I7 (stale_after_days), I9 (claim), §8.
-- Source: docs/LEDGEX_SPEC.md §3.3.

CREATE TABLE field_definition (
    field_key         text PRIMARY KEY,           -- 'zoning.district'
    display_name      text NOT NULL,
    claim             claim_type NOT NULL,
    value_type        text NOT NULL CHECK (value_type IN
                        ('string','number','boolean','date','geometry','enum','object')),
    unit              text,
    enum_values       text[],
    category          text NOT NULL,              -- checklist section, e.g. 'zoning'
    stale_after_days  integer,                    -- null = never stale (I7)
    required_for_file boolean NOT NULL DEFAULT false,
    -- v1.2: a field with no Phase 1 supplier. Declared, never silent (§7.4).
    phase1_deferred   boolean NOT NULL DEFAULT false,
    deferral_reason   text,
    description       text NOT NULL,
    CONSTRAINT field_enum_values_present
        CHECK (value_type <> 'enum' OR enum_values IS NOT NULL),
    CONSTRAINT field_unit_for_number
        CHECK (value_type <> 'number' OR unit IS NOT NULL),
    CONSTRAINT field_deferral_reason_present
        CHECK (phase1_deferred = false OR deferral_reason IS NOT NULL),
    -- A deferred field cannot also be required. Requiring a field nothing
    -- supplies would refuse every file.
    CONSTRAINT field_deferred_not_required
        CHECK (phase1_deferred = false OR required_for_file = false)
);

ALTER TABLE source_rank
    ADD CONSTRAINT source_rank_field_fk
    FOREIGN KEY (field_key) REFERENCES field_definition(field_key);
