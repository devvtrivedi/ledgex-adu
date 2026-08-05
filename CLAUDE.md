# CLAUDE.md

Read `docs/LEDGEX_SPEC.md` in full before making changes.

The invariants in §1 are non-negotiable and enforced in CI.

Never write jurisdiction-specific logic into `core/`. See §1.I1 and §6.2.

`docs/LEDGEX_SPEC.md` is the source of record. Changes require a version bump and a row in the change record (§12).

Every CHECK constraint in a new migration must be given an explicit `CONSTRAINT <name>` — never let Postgres invent one (`rule_check1` and friends already exist from older migrations; they are not being renamed, but nothing new should add to that list). An auto-generated name can't be targeted by a later migration without first querying `pg_constraint`, which 0015 had to do.

Ingest code refreshing `current_fact`: read `db/README.md` first. The first refresh of a given database must be a plain `REFRESH MATERIALIZED VIEW`, never `CONCURRENTLY` — that only works from the second refresh on.
