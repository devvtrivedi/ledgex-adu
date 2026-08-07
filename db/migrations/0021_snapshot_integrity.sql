-- 0021_snapshot_integrity.sql
-- Serves: C2 (reconstruction backbone).
--
-- snapshot (0002) is what every fact's provenance and every reconstruction
-- ultimately points at, yet the row itself has always been freely mutable
-- and deletable: nothing stopped UPDATE snapshot SET content_hash = ... or
-- DELETE FROM snapshot WHERE id = ... on a row that facts already cite by
-- id. Either one invalidates every fact's provenance without touching the
-- fact at all -- a hole one level upstream of the fact-immutability work
-- 0007/0017 already closed. This must land before the first real snapshot
-- row exists: the format CHECKs added below require every existing row to
-- already comply, and there are currently zero (this is the last migration
-- before ingestion is expected to start writing them).
--
-- snapshot_no_update / snapshot_no_delete: unlike fact (which permits
-- exactly one mutation, superseded_at NULL -> now, via
-- fact_no_destructive_update) and rule (which permits exactly one mutation,
-- effective_to NULL -> a date, via rule_no_destructive_update), no
-- mutation of any snapshot column is ever legal. There is no supersession
-- concept for a snapshot the way there is for a fact or a rule: a snapshot
-- is a record of one specific fetch, not a belief that can be corrected in
-- place. A wrong or stale snapshot is fixed by fetching again and inserting
-- a new snapshot row (a new fetch has its own id, timestamp and content
-- hash by construction); the old row stays exactly as it was fetched. So
-- both triggers raise unconditionally -- no NEW/OLD column comparison, no
-- permitted exception -- mirroring the *shape* of fact_no_destructive_update
-- and rule_no_delete/fact_no_delete's unconditional raises, but simpler
-- than the fact/rule UPDATE triggers, which both have to carve out their
-- one legal transition.
--
-- id format, per the content-addressing design question this migration
-- had to resolve first: the original proposal was id = 'sha256:' ||
-- content_hash, purely content-addressed. But snapshot already carries
-- UNIQUE (content_hash, source_id) (0002), which permits the same hash
-- under two different sources -- two sources both returning an empty
-- result set would do it, and a byte-identical GeoJSON FeatureCollection
-- with zero features is a realistic way to hit that, not just a
-- theoretical edge case. A purely content-addressed id would collide on
-- the primary key exactly there. Chose id = source_id || ':sha256:' ||
-- content_hash (option (ii) of three considered; see commit message for
-- the other two and why they were rejected) -- this keeps the existing
-- UNIQUE (content_hash, source_id) semantics exactly as they are (a
-- snapshot row still means "this source's fetch produced this content",
-- not "this content exists"), while still giving re-fetching unchanged
-- content by the SAME source a stable, deterministic id -- the property
-- that makes ON CONFLICT (id) DO NOTHING skip re-storing an unchanged
-- ~210 MB body, which is the entire point of content-addressing here (see
-- db/seeds/day4_sources.sql's own comment on this). snapshot_id_format
-- below is an equality CHECK against source_id and content_hash directly,
-- not a regex against id alone -- it enforces the binding, not just the
-- shape. Once it and snapshot_content_hash_format both hold,
-- UNIQUE (content_hash, source_id) (0002) becomes provably implied by the
-- primary key on id (two rows can only share an id if they share both
-- source_id and content_hash, since content_hash is fixed-width and the
-- separator is fixed). Left in place rather than dropped here: proven
-- redundant is not the same as wrong, and removing an existing constraint
-- is a separate, deliberate decision this migration doesn't need to make.
--
-- byte_size >= 0 (0002's snapshot_byte_size_check) is NOT tightened to > 0
-- here. A zero-byte response body is a legitimate observation, not an
-- error: an HTTP 200 with an empty body is what some sources return for a
-- query that genuinely matches nothing, and the whole purpose of a
-- snapshot is to record what was actually observed, including "nothing
-- was there" -- that is a fact about the source, not a sign that
-- something went wrong in the fetch. A negative byte count is the only
-- value that can't correspond to any real response, which is exactly what
-- >= 0 already rules out.

CREATE OR REPLACE FUNCTION snapshot_no_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'C2 violated: snapshot % is immutable. There is no supersession '
        'concept for a snapshot -- fetch again and insert a new snapshot '
        'row instead of editing this one.', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER snapshot_no_update BEFORE UPDATE ON snapshot
    FOR EACH ROW EXECUTE FUNCTION snapshot_no_update();

CREATE OR REPLACE FUNCTION snapshot_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'C2 violated: snapshot % cannot be deleted. Every fact that cites '
        'it depends on it for reconstruction; deleting it would '
        'invalidate those facts'' provenance without touching them.', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER snapshot_no_delete BEFORE DELETE ON snapshot
    FOR EACH ROW EXECUTE FUNCTION snapshot_no_delete();

ALTER TABLE snapshot
    ADD CONSTRAINT snapshot_content_hash_format
    CHECK (content_hash ~ '^[0-9a-f]{64}$');

ALTER TABLE snapshot
    ADD CONSTRAINT snapshot_id_format
    CHECK (id = source_id || ':sha256:' || content_hash);

ALTER TABLE snapshot
    ADD CONSTRAINT snapshot_object_uri_not_blank
    CHECK (length(trim(object_uri)) > 0);

ALTER TABLE snapshot
    ADD CONSTRAINT snapshot_media_type_not_blank
    CHECK (length(trim(media_type)) > 0);
