-- 0046_schema_migrations_ledger.sql
-- Serves: P6.
--
-- THE GAP. `make schema` applies every migration in order with no ledger of
-- what ran. It only works against an empty database -- rerunning it against
-- one that already has migration N applied fails outright on N's own
-- CREATE TABLE. There was no supported way to bring a long-lived database
-- forward, and no record distinguishing "never applied" from "applied by
-- hand, unrecorded" -- which is exactly how ledgex_schema_check drifted six
-- migrations behind, silently, until a P5 session needed the trigger 0042
-- installs and found it missing.
--
-- THE SHAPE. One row per migration that has actually run against THIS
-- database, recorded atomically with the migration itself (scripts/
-- migrate.py runs a migration's SQL and this table's INSERT in the same
-- transaction, same commit -- never one without the other). file_sha256 is
-- not decoration: migrations are forward-only and immutable once merged
-- (CLAUDE.md, prompts/README.md's own discipline), so recording the hash at
-- apply time turns "was this file edited after landing" from an assumption
-- into something scripts/migrate.py checks on every run and refuses to
-- proceed past if it ever fails. baselined distinguishes a row that was
-- recorded because this database's schema was verified byte-identical to a
-- freshly-built reference (scripts/migrate_baseline.py, a one-time adoption
-- path for a database that predates this table) from a row recorded because
-- the migration actually ran here -- a real distinction, not a guess either
-- way could paper over.
--
-- NOT itself covered by the ledger it creates: this migration is applied
-- specially, before the normal ordered loop, by scripts/migrate.py, exactly
-- once, whenever schema_migrations does not yet exist and the database is
-- otherwise empty -- see that script for why (schema_migrations has no
-- foreign key to anything else in this schema, so it carries no ordering
-- dependency on 0001-0045 and can safely be created first regardless of its
-- own number).

CREATE TABLE schema_migrations (
    version      text NOT NULL,
    file_sha256  text NOT NULL,
    applied_at   timestamptz NOT NULL DEFAULT now(),
    baselined    boolean NOT NULL DEFAULT false,
    CONSTRAINT schema_migrations_pkey PRIMARY KEY (version),
    CONSTRAINT schema_migrations_version_format CHECK (version ~ '^[0-9]{4}$'),
    CONSTRAINT schema_migrations_file_sha256_format CHECK (file_sha256 ~ '^[0-9a-f]{64}$')
);
