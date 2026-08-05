# db/ operational notes

Things that are true about this schema but aren't obvious from the migrations
themselves, or that only bite the first time a given operation runs.

## Refreshing `current_fact`: the first refresh must NOT be CONCURRENTLY

`current_fact` (0008, tiebreak added in 0014) is a materialized view. 0008's
own trailing comment says:

> Refresh with `REFRESH MATERIALIZED VIEW CONCURRENTLY current_fact;` at the
> end of each ingest job.

That is correct for steady state, but **not** for the very first refresh, and
whether it bites depends on how the database was bootstrapped:

- **Bootstrapped by replaying `db/migrations/*.sql` in order** (`make
  schema`, or any fresh environment that applies the migrations directly):
  `CREATE MATERIALIZED VIEW` with no `WITH NO DATA` clause runs the query and
  populates the view immediately — even if it matches zero rows, zero rows
  still counts as populated. `REFRESH ... CONCURRENTLY` works the very first
  time. Verified directly: applied all 15 migrations to an empty PostgreSQL
  16 database, confirmed `SELECT ispopulated FROM pg_matviews WHERE
  matviewname = 'current_fact'` was already `t`, then ran `REFRESH
  MATERIALIZED VIEW CONCURRENTLY current_fact;` with zero rows in `fact` —
  it succeeded.

- **Bootstrapped by restoring `db/schema.sql`** (a `pg_dump --schema-only`
  dump, e.g. loading it into a new environment instead of replaying
  migrations): a schema-only dump can never carry a materialized view's data,
  so pg_dump always emits `... WITH NO DATA;` for `current_fact` regardless
  of whether the live source database had ever refreshed it. Restoring that
  dump leaves `current_fact` unpopulated (`ispopulated = f`), and Postgres
  categorically refuses `CONCURRENTLY` against an unpopulated view. Verified
  directly: restored `db/schema.sql` into an empty PostgreSQL 16 database and
  ran `REFRESH MATERIALIZED VIEW CONCURRENTLY current_fact;` immediately —
  it failed with:

  ```
  ERROR:  CONCURRENTLY cannot be used when the materialized view is not populated
  ```

  A plain refresh first fixed it, and `CONCURRENTLY` then worked:

  ```sql
  REFRESH MATERIALIZED VIEW current_fact;              -- first refresh ever, no CONCURRENTLY
  REFRESH MATERIALIZED VIEW CONCURRENTLY current_fact;  -- every refresh after that
  ```

**Rule for ingest code:** always do a plain (non-`CONCURRENTLY`) refresh the
first time a given database's `current_fact` is refreshed, and `CONCURRENTLY`
every time after that. Since ingest code generally can't assume which way the
database in front of it was bootstrapped, the safe pattern is to check
`pg_matviews.ispopulated` (or just catch the "not populated" error once) and
fall back to a plain refresh before retrying with `CONCURRENTLY`, rather than
assuming migrations-in-order bootstrapping and always going straight to
`CONCURRENTLY`.

`REFRESH ... CONCURRENTLY` additionally requires at least one UNIQUE index
covering the whole view with no WHERE clause. `current_fact_pk` (0008), a
unique index on `(parcel_id, field_key)`, satisfies this and already exists —
nothing further is needed there.

0008's own comment is not being changed (migrations are forward-only and this
one is applied); this file is where the first-refresh caveat lives instead.
