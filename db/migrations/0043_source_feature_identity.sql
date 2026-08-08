-- 0043_source_feature_identity.sql
-- Serves: I2, I7. Phase A ingest reconciliation.
--
-- THE GAP. Re-running the same bulk parcel snapshot currently has no
-- durable source-feature identity to match against. PARCELID is recorded
-- as parcel.source_parcel_id (0035), but that is a fact: it supersedes,
-- participates in current_fact resolution, and is not the right structure
-- for deciding whether an incoming source feature already owns an internal
-- parcel row. The immediate operational result is duplication: the loader
-- can parse the same bytes again and insert another full parcel/fact set.
--
-- THE CHANGE. source_feature_identity is the reconciliation lookup:
-- one source feature id maps to one internal parcel id for a source. It is
-- append-and-retire operational identity state, not a public-record fact.
-- It deliberately carries snapshot lifecycle columns so later reconciles
-- can distinguish first sighting, most recent sighting and retirement
-- without rewriting the fact ledger to answer identity questions.
--
-- RENumbering boundary. This table subsumes source-feature renumbering
-- lineage: if San Jose changes PARCELID but evidence ties the new id to
-- the same physical parcel, a later reconciliation inserts a second
-- source_feature_identity row pointing at the same parcel and retires the
-- old source-feature row. C4's parcel_lineage, if ever built, therefore
-- covers only physical parcel splits and merges. It does not also carry
-- source-system row renumbering.
--
-- Weak evidence decision, recorded before writing: weak renumber evidence
-- produces an identity exception, not a new parcel. Creating a new parcel
-- on weak evidence is irreversible duplication; an exception is the honest
-- blocked state until stronger evidence exists.

CREATE TABLE source_feature_identity (
    source_id              text NOT NULL REFERENCES source(id),
    source_feature_id      text NOT NULL,
    parcel_id              uuid NOT NULL REFERENCES parcel(id),
    first_seen_snapshot_id text NOT NULL REFERENCES snapshot(id),
    first_seen_at          timestamptz NOT NULL,
    last_seen_snapshot_id  text NOT NULL REFERENCES snapshot(id),
    last_seen_at           timestamptz NOT NULL,
    retired_snapshot_id    text REFERENCES snapshot(id),
    retired_at             timestamptz,
    retirement_reason      text,
    created_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, source_feature_id),
    CONSTRAINT source_feature_identity_seen_order
        CHECK (last_seen_at >= first_seen_at),
    CONSTRAINT source_feature_identity_retirement_pairing
        CHECK (
            (retired_snapshot_id IS NULL AND retired_at IS NULL AND retirement_reason IS NULL)
            OR
            (retired_snapshot_id IS NOT NULL AND retired_at IS NOT NULL AND retirement_reason IS NOT NULL)
        ),
    CONSTRAINT source_feature_identity_retired_after_seen
        CHECK (retired_at IS NULL OR retired_at >= last_seen_at)
);

CREATE INDEX source_feature_identity_parcel
    ON source_feature_identity (parcel_id);

ALTER TABLE source_feature_identity
    ADD CONSTRAINT source_feature_identity_first_snapshot_source_fk
    FOREIGN KEY (first_seen_snapshot_id, source_id) REFERENCES snapshot (id, source_id);

ALTER TABLE source_feature_identity
    ADD CONSTRAINT source_feature_identity_last_snapshot_source_fk
    FOREIGN KEY (last_seen_snapshot_id, source_id) REFERENCES snapshot (id, source_id);

ALTER TABLE source_feature_identity
    ADD CONSTRAINT source_feature_identity_retired_snapshot_source_fk
    FOREIGN KEY (retired_snapshot_id, source_id) REFERENCES snapshot (id, source_id);
