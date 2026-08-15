-- 0044_fact_supersession_source_match.sql
-- Fixes: fact.supersedes_fact_id (0025), fact_supersession_target_validate
-- (0042). Serves: I4, C1. P4 finding.
--
-- THE GAP. 0042 validates same (parcel_id, field_key) and that the target
-- was actually retired. It does not validate that the superseding fact
-- came from the SAME source as the fact it claims to supersede. Reproduced
-- directly, not assumed: a job_run for ca_san_jose.parcels superseded a
-- ca_san_jose.building_permits_active fact (permits.active) and a
-- ca_san_jose.zoning_districts fact (zoning.district), citing its own
-- SOURCE_ID/snapshot_id/ENDPOINT_URL/LICENCE_ID as the successor's
-- provenance -- committed cleanly, pre-fix. Nothing in the schema stopped
-- it: fact_one_current_per_source is partial-unique PER SOURCE (COALESCE
-- (source_id, '~derived') is part of the key), so a cross-source successor
-- never collides with the row it's superseding, and 0042 never looks at
-- source_id at all.
--
-- THE ARGUMENT (recorded, not just decided). Should a supersession ever
-- be allowed to cross source_id?
--
--   FOR: a genuine multi-source correction is real -- a higher-ranked
--   source, or a dedicated correction feed, later confirms a different
--   value for a field an earlier source reported. Locking supersession to
--   same-source would leave that "B corrects A" lineage with nowhere to
--   go.
--
--   AGAINST: the schema already has a mechanism for cross-source
--   disagreement that is NOT supersession -- fact.conflict
--   ('agree'/'conflicts'/'stale'/'missing') plus source_rank-driven
--   resolution in current_fact. Supersession's own documented semantics
--   (0025: world_change, source_correction, refetch_no_change,
--   ingestion_logic_change) describe ONE source's own observation stream
--   evolving -- 0025's own docstring frames source_correction as "the
--   source corrected itself," not "a different source disagreed." Every
--   existing supersession test (T68/T69/T70, db/tests/invariants.sql)
--   exercises exactly one cross-"source" shape: a derived fact
--   (source_id IS NULL) superseding a direct/bulk one -- an already
--   distinct, already-modeled lineage path via fact_input/I5's rights
--   inheritance, not a retrieved-fact-overriding-a-different-retrieved-
--   fact pattern. And concretely, this is the exact bug that shipped: had
--   cross-source supersession been schema-legal, nothing would have
--   caught it -- it would have "succeeded" with fabricated provenance,
--   silently, exactly as it did.
--
--   DECISION: against. A retrieved (method IN ('direct','bulk')) fact may
--   only supersede a retrieved fact from the SAME source_id. A derived
--   fact (source_id IS NULL) remains exempt -- T70's already-tested,
--   legitimate pattern, unbroken by this migration (verified directly,
--   not assumed -- see db/tests/invariants.sql T70 after this migration).
--
-- THE FIX. Same deferred constraint trigger 0042 created
-- (fact_supersession_target_valid), function body extended in place
-- (CREATE OR REPLACE, same precedent 0039 used for revising an existing
-- trigger function without a new trigger name) -- this is the same
-- invariant family (I4: what makes a valid supersession target), not a
-- new one. The check only fires when NEW.source_id IS NOT NULL (NEW is
-- not derived); a derived NEW is exempt regardless of the target's
-- source_id, matching the decision above.

CREATE OR REPLACE FUNCTION fact_supersession_target_validate() RETURNS trigger AS $$
DECLARE
    target_parcel_id     uuid;
    target_field_key     text;
    target_source_id     text;
    target_superseded_at timestamptz;
BEGIN
    IF NEW.supersedes_fact_id IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT parcel_id, field_key, source_id, superseded_at
      INTO target_parcel_id, target_field_key, target_source_id, target_superseded_at
      FROM public.fact
     WHERE id = NEW.supersedes_fact_id;

    IF target_parcel_id IS DISTINCT FROM NEW.parcel_id
       OR target_field_key IS DISTINCT FROM NEW.field_key
    THEN
        RAISE EXCEPTION
            'I4 violated: fact % (parcel %, field %) claims to supersede '
            'fact % (parcel %, field %) -- a fact can only supersede a '
            'prior fact for the SAME parcel and field.',
            NEW.id, NEW.parcel_id, NEW.field_key,
            NEW.supersedes_fact_id, target_parcel_id, target_field_key;
    END IF;

    IF target_superseded_at IS NULL THEN
        RAISE EXCEPTION
            'I4 violated: fact % claims to supersede fact %, but that '
            'fact''s own superseded_at was never set. Superseding a fact '
            'requires setting its superseded_at in the same transaction.',
            NEW.id, NEW.supersedes_fact_id;
    END IF;

    -- 0044: a retrieved successor (NEW.source_id IS NOT NULL) may only
    -- supersede a fact from the SAME source. A derived successor
    -- (source_id IS NULL) is exempt -- fact_input/I5 already governs
    -- whether a derivation may legitimately draw on that target.
    IF NEW.source_id IS NOT NULL AND target_source_id IS DISTINCT FROM NEW.source_id THEN
        RAISE EXCEPTION
            'I4 violated: fact % (source %) claims to supersede fact % '
            '(source %) -- a retrieved fact may only supersede a prior '
            'fact from the SAME source_id. Cross-source disagreement is '
            'fact.conflict''s job, not supersession''s.',
            NEW.id, NEW.source_id, NEW.supersedes_fact_id, target_source_id;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql SET search_path = public, pg_temp;
