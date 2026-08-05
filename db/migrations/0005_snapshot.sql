-- 0005_snapshot.sql
-- Snapshots - the reconstruction backbone (C2).
-- Source: docs/LEDGEX_SPEC.md §3.5.

CREATE TABLE snapshot (
    id                  text PRIMARY KEY,         -- 'sha256:...' content address
    source_id           text NOT NULL REFERENCES source(id),
    object_uri          text NOT NULL,            -- s3://bucket/sha256/...
    content_hash        text NOT NULL,
    media_type          text NOT NULL,
    byte_size           bigint NOT NULL CHECK (byte_size >= 0),
    request             jsonb NOT NULL,           -- exact URL, params, headers sent
    http_status         integer,
    fetched_at          timestamptz NOT NULL,
    licence_observed_id text NOT NULL REFERENCES licence(id),   -- at the moment of fetch
    UNIQUE (content_hash, source_id)
);

CREATE INDEX snapshot_source_time ON snapshot (source_id, fetched_at DESC);

-- Change detection is free. Identical content_hash for a source means the
-- source did not change, regardless of what cadence_stated claims. This is
-- the mechanism behind I7.
