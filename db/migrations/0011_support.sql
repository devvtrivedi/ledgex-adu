-- 0011_support.sql
-- Support requests — post-delivery, never pre-delivery.
-- Source: docs/LEDGEX_SPEC.md §3.11.
--
-- There is no review queue, no task table and no assignee anywhere in this
-- schema. A human-review queue was designed in v1.0 and removed in v1.1
-- (see §12 and the annex in §6.7). It must not be reintroduced without
-- amending I14.
--
-- The only human-facing table that remains records contact that happens
-- after a file has already been delivered. It measures the product; it
-- never produces it.

CREATE TABLE support_request (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_file_id   uuid,                      -- FK added in 0012
    jurisdiction_id    text NOT NULL REFERENCES jurisdiction(id),
    category           support_category NOT NULL,
    field_key          text REFERENCES field_definition(field_key),
    opened_at          timestamptz NOT NULL DEFAULT now(),
    resolved_at        timestamptz,
    caused_correction  boolean NOT NULL DEFAULT false,
    correcting_fact_id uuid REFERENCES fact(id),   -- must be direct/bulk/derived
    detail             text,
    CONSTRAINT support_correction_consistent CHECK (
        caused_correction = false OR correcting_fact_id IS NOT NULL
    )
);

CREATE INDEX support_by_file  ON support_request (property_file_id);
CREATE INDEX support_rate_idx ON support_request (jurisdiction_id, opened_at);

-- A support request is not a back door for human facts. If contact reveals
-- that a value is wrong, the fix is a source, crosswalk, rule or detector
-- change that makes the pipeline produce the right answer — recorded as a
-- normal direct/bulk/derived fact. correcting_fact_id is constrained by I13
-- like any other fact. Typing a corrected value in by hand is prohibited
-- (§6.2 rule 12).
