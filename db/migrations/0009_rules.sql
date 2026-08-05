-- 0009_rules.sql (v1.6 replacement for review columns)
-- Rules — review-mode contract.
-- Source: docs/LEDGEX_SPEC.md §3.9.
--
-- Independent review remains preferred. Phase 1 may use a controlled
-- solo-founder attestation only when the same identity authors and reviews
-- and an immutable evidence URI is stored.

CREATE TYPE public.review_mode AS ENUM ('independent','solo_founder_attestation');

CREATE TABLE rule (
    id              text PRIMARY KEY,
    jurisdiction_id text NOT NULL REFERENCES jurisdiction(id),
    rule_key        text NOT NULL,
    version         integer NOT NULL CHECK (version > 0),
    effective_from  date NOT NULL,
    effective_to    date,
    citation        text NOT NULL,
    source_text_uri text NOT NULL,
    params          jsonb NOT NULL,
    pack_version    text NOT NULL,
    authored_by     text NOT NULL,
    reviewed_by     text NOT NULL,
    review_mode     public.review_mode NOT NULL DEFAULT 'independent',
    reviewed_at     timestamptz NOT NULL,
    attestation_uri text,
    UNIQUE (jurisdiction_id, rule_key, version),
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    CHECK (
        (review_mode = 'independent' AND reviewed_by <> authored_by
            AND attestation_uri IS NULL)
        OR
        (review_mode = 'solo_founder_attestation' AND reviewed_by = authored_by
            AND attestation_uri IS NOT NULL AND length(trim(attestation_uri)) > 0)
    )
);

-- authored/reviewed identities, mode, time and URI are immutable.
-- A correction creates a new rule version; it never updates review evidence.
-- (§3.9's prose asserts this but, unlike fact/I4, the spec does not define
-- an enforcing trigger for it — application code and code review are the
-- only enforcement named for this table.)

-- Deployment policy may allow solo-founder mode only during the documented
-- bootstrap period. Existing attested rows remain historical when
-- independent review becomes available.
