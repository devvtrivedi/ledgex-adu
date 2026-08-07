-- 0022_remaining_composite_fks.sql
-- Serves: I2, I3, C1, C2 (provenance), I6 (jurisdiction scoping).
--
-- Three more consistency holes 0018 didn't close, all the same
-- denormalize-and-composite-FK pattern already established there.
--
-- (a) A fact's declared licence need not match its snapshot's observed
--     licence: fact.licence_id and snapshot.licence_observed_id are both
--     independently FK'd to licence(id), but nothing tied one to the
--     other. This is deliberately equality, not the "at least as strict"
--     rule I5 gives a DERIVED fact: I5's stricter-or-equal rule exists for
--     composing multiple inputs' licences into one output that must never
--     be more permissive than any of them. A RETRIEVED fact isn't
--     composing anything -- its licence_id is supposed to simply restate
--     what was actually observed at fetch time, not apply a policy on top
--     of it. Allowing it to diverge (in either direction) would let a
--     fact's stated licence drift from the fetch it claims to describe.
--     Any deliberate additional restriction belongs in licence_channel
--     policy (deferred, out of scope here), not in silently letting
--     fact.licence_id disagree with the snapshot it cites. Needs
--     UNIQUE (id, licence_observed_id) on snapshot (same PK-superset
--     plumbing as 0018's other targets) and
--     fact (snapshot_id, licence_id) REFERENCES snapshot
--     (id, licence_observed_id). MATCH SIMPLE, and so a no-op for derived
--     facts: confirmed directly against a scratch database, not assumed
--     -- fact_provenance_complete (0006) already forces snapshot_id NULL
--     for every derived fact, and NULL in any FK column satisfies MATCH
--     SIMPLE regardless of the other column, licence_id included.
--
-- (b) A job_run could claim it hit one source while citing a snapshot that
--     belongs to a different one -- the same shape of hole 0018 closed for
--     fact.snapshot_id/fact.source_id, never closed for job_run's own
--     snapshot_id/source_id pair. job_run (source_id, snapshot_id)
--     REFERENCES snapshot (id, source_id) closes it; the required
--     UNIQUE (id, source_id) already exists on snapshot from 0018
--     (snapshot_id_source_id_unique), so this is just the FK, nothing
--     else to add. Both columns are nullable on job_run (a job_run isn't
--     always about one specific source/snapshot), so MATCH SIMPLE makes
--     this a no-op whenever either is NULL -- exactly right, since a
--     job_run with no declared source has nothing to check against.
--
-- (c) fact has never carried its own jurisdiction_id: it's reachable only
--     indirectly, through parcel.jurisdiction_id or source.jurisdiction_id
--     -- and nothing ever required those two to agree. A fact could
--     belong to a parcel in one jurisdiction while citing a source
--     registered under another. property_file and parcel_exception both
--     already carry their own jurisdiction_id (0010, 0012) but the same
--     gap exists one level down: nothing required it to match their own
--     parcel_id's actual jurisdiction. All three get the same treatment:
--       - fact gains a new jurisdiction_id text NOT NULL column. Zero fact
--         rows exist in this database (this migration exists specifically
--         to land before the first one does), so this needs no backfill
--         and no default -- a later database that already has fact rows
--         when this runs would need one; that is not this database's
--         problem to solve today.
--       - UNIQUE (id, jurisdiction_id) added to parcel and to source (same
--         PK-superset plumbing as 0018).
--       - fact (parcel_id, jurisdiction_id) REFERENCES parcel
--         (id, jurisdiction_id) -- parcel_id and jurisdiction_id are both
--         NOT NULL on fact, so this FK is never exempted by MATCH SIMPLE:
--         every fact, retrieved or derived, must agree with its own
--         parcel's jurisdiction.
--       - fact (source_id, jurisdiction_id) REFERENCES source
--         (id, jurisdiction_id) -- source_id is NULL for derived facts
--         (fact_provenance_complete), so MATCH SIMPLE exempts derived
--         facts here the same way it does for 0018's fact/source FKs;
--         confirmed, not assumed, the same way as (a) above.
--       - property_file (parcel_id, jurisdiction_id) REFERENCES parcel
--         (id, jurisdiction_id) and
--         parcel_exception (parcel_id, jurisdiction_id) REFERENCES parcel
--         (id, jurisdiction_id) -- both columns already NOT NULL on both
--         tables (0010, 0012), so both FKs are unconditional, no new
--         column needed.
--     The external review rated this P2 (it only bites once more than one
--     jurisdiction is live), but the NOT NULL column on fact is free right
--     now and expensive later -- it would need a real backfill against
--     live fact rows once ingestion has run, the same "cheap now, costly
--     after ingestion" argument the rest of Tier 2 was built on.
--
-- job_run.jurisdiction_id (also nullable, also independently reachable) is
-- NOT included here: the external review's finding was specifically about
-- fact, property_file and parcel_exception disagreeing with their own
-- parcel; extending the same pattern to job_run's jurisdiction/source pair
-- was not part of what was asked, and isn't added speculatively here.

ALTER TABLE snapshot
    ADD CONSTRAINT snapshot_id_licence_observed_id_unique UNIQUE (id, licence_observed_id);

ALTER TABLE fact
    ADD CONSTRAINT fact_snapshot_licence_fk
    FOREIGN KEY (snapshot_id, licence_id) REFERENCES snapshot (id, licence_observed_id);

ALTER TABLE job_run
    ADD CONSTRAINT job_run_snapshot_source_fk
    FOREIGN KEY (source_id, snapshot_id) REFERENCES snapshot (id, source_id);

ALTER TABLE parcel
    ADD CONSTRAINT parcel_id_jurisdiction_id_unique UNIQUE (id, jurisdiction_id);

ALTER TABLE source
    ADD CONSTRAINT source_id_jurisdiction_id_unique UNIQUE (id, jurisdiction_id);

ALTER TABLE fact
    ADD COLUMN jurisdiction_id text NOT NULL;

ALTER TABLE fact
    ADD CONSTRAINT fact_parcel_jurisdiction_fk
    FOREIGN KEY (parcel_id, jurisdiction_id) REFERENCES parcel (id, jurisdiction_id);

ALTER TABLE fact
    ADD CONSTRAINT fact_source_jurisdiction_fk
    FOREIGN KEY (source_id, jurisdiction_id) REFERENCES source (id, jurisdiction_id);

ALTER TABLE property_file
    ADD CONSTRAINT property_file_parcel_jurisdiction_fk
    FOREIGN KEY (parcel_id, jurisdiction_id) REFERENCES parcel (id, jurisdiction_id);

ALTER TABLE parcel_exception
    ADD CONSTRAINT parcel_exception_parcel_jurisdiction_fk
    FOREIGN KEY (parcel_id, jurisdiction_id) REFERENCES parcel (id, jurisdiction_id);
