-- 0018_provenance_integrity.sql
-- Serves: I2 (provenance), I3 (rights), I6 (rights gate), C1 (provenance).
--
-- Three consistency holes the schema left open, all closable declaratively
-- via composite foreign keys rather than triggers. Every new composite FK
-- uses MATCH SIMPLE (Postgres's default -- there is no other option for a
-- plain FOREIGN KEY): the constraint is satisfied trivially whenever ANY
-- referencing column is NULL. A derived fact has source_id AND snapshot_id
-- both NULL (fact_provenance_complete, 0006), so every FK added here (all
-- keyed on source_id/snapshot_id, never method_version) is a no-op for
-- derived facts by construction -- confirmed against fact_provenance_
-- complete's own CHECK, not assumed. **Corrected (D17, P59):** this
-- paragraph previously also listed "method_version" as NULL for a derived
-- fact -- the opposite of what the CHECK actually requires:
-- fact_provenance_complete requires method_version IS NOT NULL for a
-- derived fact (it is source_id/snapshot_id that must be NULL there).
-- The FK argument above is unaffected -- none of the new composite FKs in
-- this migration reference method_version at all -- only this
-- introductory claim about the column was wrong.
--
-- (a) A fact could claim source A while citing source B's snapshot: fact
--     has independent FKs to source(id) and snapshot(id), but nothing tied
--     fact.source_id to snapshot.source_id. snapshot gets a UNIQUE(id,
--     source_id) -- redundant with its own PK on id alone in isolation,
--     but Postgres requires a unique constraint on exactly the referenced
--     column set for a composite FK to target it. fact(snapshot_id,
--     source_id) then references it: a retrieved fact's snapshot must
--     belong to the same source the fact claims.
--
-- (b) A fact's method need not match its source's declared method: fact
--     and source both have a method/access_method column, but nothing
--     compared them. source gets UNIQUE(id, method); fact(source_id,
--     method) references it. This asserts a retrieved fact always carries
--     its source's access method -- confirmed correct for the current
--     design, not just assumed: every source declares exactly one
--     access_method (0002), and a fact with a non-null source_id is
--     already restricted by fact_provenance_complete + fact_method_automated
--     to method IN ('direct','bulk') -- there is no path in the schema for
--     a source to supply facts under two different methods, and 0016
--     exists specifically because a source's method is supposed to be the
--     authoritative description of how every one of its facts arrived.
--     If a future ingestion design needs one source to supply facts via
--     more than one method, this constraint is the thing that would need
--     to change, not the ingestion code working around it.
--
-- (c) A Property File (or an exception) could cite a fact belonging to a
--     different parcel than the one it's about. property_file, fact and
--     parcel_exception each get UNIQUE(id, parcel_id) (same PK-superset
--     reasoning as (a)). property_file_fact and exception_evidence gain a
--     parcel_id column plus two composite FKs each, one against every
--     row's own parcel-scoped parent, one against the fact/exception it
--     links -- forcing both sides onto the same parcel_id value, and
--     therefore onto each other. Both tables are empty (zero fact rows
--     exist in this database, so zero rows reference them), so ADD COLUMN
--     ... NOT NULL needs no backfill and no default.
--
--     The original single-column FKs (property_file_fact.property_file_id
--     -> property_file(id), property_file_fact.fact_id -> fact(id), and
--     their exception_evidence equivalents) are left in place, not
--     dropped: the new composite FKs are strictly additional constraints,
--     satisfying one implies satisfying the single-column one it
--     overlaps, so there is no conflict, just controlled redundancy at
--     the column level.
--
--     support_request.correcting_fact_id has a related gap (a correction
--     could reference a fact for a different parcel than the file the
--     support request is about) but a messier shape: property_file_id is
--     nullable, and support_request carries no parcel_id column at all
--     today, so there is no reliable anchor to build a MATCH SIMPLE FK
--     against without first deciding how a parcel_id gets populated when
--     only one of property_file_id/correcting_fact_id is set (or neither
--     -- a general jurisdiction-level support ticket has no parcel at
--     all). Recorded as a design question, not implemented here.

ALTER TABLE snapshot
    ADD CONSTRAINT snapshot_id_source_id_unique UNIQUE (id, source_id);

ALTER TABLE fact
    ADD CONSTRAINT fact_snapshot_source_fk
    FOREIGN KEY (snapshot_id, source_id) REFERENCES snapshot (id, source_id);

ALTER TABLE source
    ADD CONSTRAINT source_id_method_unique UNIQUE (id, method);

ALTER TABLE fact
    ADD CONSTRAINT fact_source_method_fk
    FOREIGN KEY (source_id, method) REFERENCES source (id, method);

ALTER TABLE fact
    ADD CONSTRAINT fact_id_parcel_id_unique UNIQUE (id, parcel_id);

ALTER TABLE property_file
    ADD CONSTRAINT property_file_id_parcel_id_unique UNIQUE (id, parcel_id);

ALTER TABLE property_file_fact
    ADD COLUMN parcel_id uuid NOT NULL;

ALTER TABLE property_file_fact
    ADD CONSTRAINT property_file_fact_property_file_parcel_fk
    FOREIGN KEY (property_file_id, parcel_id) REFERENCES property_file (id, parcel_id);

ALTER TABLE property_file_fact
    ADD CONSTRAINT property_file_fact_fact_parcel_fk
    FOREIGN KEY (fact_id, parcel_id) REFERENCES fact (id, parcel_id);

ALTER TABLE parcel_exception
    ADD CONSTRAINT parcel_exception_id_parcel_id_unique UNIQUE (id, parcel_id);

ALTER TABLE exception_evidence
    ADD COLUMN parcel_id uuid NOT NULL;

ALTER TABLE exception_evidence
    ADD CONSTRAINT exception_evidence_exception_parcel_fk
    FOREIGN KEY (exception_id, parcel_id) REFERENCES parcel_exception (id, parcel_id);

ALTER TABLE exception_evidence
    ADD CONSTRAINT exception_evidence_fact_parcel_fk
    FOREIGN KEY (fact_id, parcel_id) REFERENCES fact (id, parcel_id);
