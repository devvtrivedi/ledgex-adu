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

## `source.method` becomes immutable once any fact references it

`fact_source_method_fk` (0018) is `fact (source_id, method) REFERENCES source
(id, method)`, with no `ON UPDATE CASCADE`. That means once any fact row
carries a given `source_id`, Postgres refuses to change that source's
`method` at all, because doing so would leave the fact's FK pointing at a
`(id, method)` pair that no longer exists in `source`. Verified directly:

```sql
UPDATE source SET method = 'bulk' WHERE id = 'ca_san_jose.test_source';
```

```
ERROR:  update or delete on table "source" violates foreign key constraint "fact_source_method_fk" on table "fact"
DETAIL:  Key (id, method)=(ca_san_jose.test_source, direct) is still referenced from table "fact".
```

This is correct behaviour, not a defect: retroactively changing a source's
declared access method would falsify the provenance of every fact already
recorded under it. But it has a real consequence for operations —
`0016_source_access_method_corrections.sql` exists precisely because
`source.method` needed a plain in-place `UPDATE` correction after seeding,
and that route only works before any fact references the source. Once
ingestion has run and facts exist, the same kind of correction can no longer
be a migration that just updates the row.

**What the correction path becomes instead, once facts exist:** supersede
every fact recorded under the source's old (wrong) method first — same
mechanism I4 already requires for any fact correction, a new fact row with
`superseded_at` set on the old one, never an `UPDATE` or `DELETE` on `fact`
itself (0017 blocks the latter outright) — then update `source.method`. The
`UPDATE` on `source` will only succeed once no fact row still references the
old `(id, method)` pair, i.e. once every fact under that source has been
superseded, not merely re-ingested alongside the old rows.
