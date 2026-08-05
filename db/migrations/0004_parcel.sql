-- 0004_parcel.sql
-- Parcel identity.
-- Source: docs/LEDGEX_SPEC.md §3.4.

CREATE TABLE parcel (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction_id text NOT NULL REFERENCES jurisdiction(id),
    apn             text NOT NULL,
    situs_address   text,
    geom            geometry(MultiPolygon, 4326),
    centroid        geometry(Point, 4326),
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (jurisdiction_id, apn)          -- APNs collide across counties
);

CREATE INDEX parcel_geom_gix     ON parcel USING gist (geom);
CREATE INDEX parcel_centroid_gix ON parcel USING gist (centroid);
CREATE INDEX parcel_apn_prefix   ON parcel (apn text_pattern_ops);
