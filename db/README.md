# db/ operational notes

Things that are true about this schema but aren't obvious from the migrations
themselves, or that only bite the first time a given operation runs.

## Which of `make schema` / `make migrate` / `make migrate-baseline` to run

Three ways to bring a database's schema up to date exist (P6). Exactly one is
correct for any given database, decided by what's already there, not by
preference:

- **Empty database** (nothing in it at all) → `make schema`. Applies every
  migration from nothing and records each one in `schema_migrations` as it
  goes. Fails outright if the database turns out not to be empty — that
  failure is correct, not a bug to work around.
- **Existing database, no `schema_migrations` table** (migrations were
  applied by hand, or by an older checkout of this repo from before P6) →
  `make migrate-baseline`, once, then `make migrate`. Baselining builds a
  disposable reference database from empty and only records this database's
  ledger if a full schema diff against that reference is byte-identical —
  it never guesses which migrations already ran.
- **Existing database with a `schema_migrations` table already** → `make
  migrate`. Applies whatever's missing, records each one atomically with its
  own row. Safe to run repeatedly; a fully caught-up database is a no-op.

Run `make migrate-verify` after any of the three if there's real doubt —
it independently checks the database's live schema against what its own
ledger claims, which none of the three targets above can see going wrong in
themselves.

Picking wrong is not silently safe: `make schema` against a non-empty
database refuses outright (the only failure mode that's actually harmless —
nothing applies). Applying `make migrate-baseline`'s baseline assertion to a
database that ISN'T actually schema-equivalent to a fresh build is the
dangerous direction, and the reason baselining verifies by full diff instead
of taking that on faith — see its own docstring. This decision procedure
existing at all is the point: guessing which of the three to run, the same
way `ledgex_schema_check` did before P6, is exactly how a database drifts
six migrations behind without anyone noticing.

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
ingestion has run and facts exist, the same kind of correction is no longer
available at all — not merely harder.

**Supersession does not release the FK reference.** An earlier version of
this note claimed superseding every fact under the source first would free
`source.method` up for a plain `UPDATE`. That is wrong, and was never
actually run before being written down. Supersession sets `superseded_at`;
the fact row itself stays exactly where it is, `(source_id, method)` and
all, and PostgreSQL FK enforcement does not look at `superseded_at` or any
other column when deciding whether a referenced key is "still referenced" —
a superseded row counts exactly the same as a live one. Verified directly:

```sql
-- insert a fact under ca_san_jose.test_source (method='direct'), then
-- supersede it -- the one legal UPDATE on a fact row (I4)
UPDATE fact SET superseded_at = now() WHERE id = '<the fact just inserted>';

UPDATE source SET method = 'bulk' WHERE id = 'ca_san_jose.test_source';
```

```
ERROR:  update or delete on table "source" violates foreign key constraint "fact_source_method_fk" on table "fact"
DETAIL:  Key (id, method)=(ca_san_jose.test_source, direct) is still referenced from table "fact".
```

Identical error, before and after superseding. `source.method` is
**permanently** immutable once any fact references the source — not
immutable-until-superseded. The only thing that would release the FK
reference is removing the fact row outright, and 0017 forbids that
unconditionally; there is no path from "fact exists under this source" back
to "source.method can change" once a fact has ever been inserted.

`ON UPDATE CASCADE` would not fix this either, so don't reach for it as a
patch: the cascade works by issuing an `UPDATE` against every referencing row
in `fact`, and `fact_no_destructive_update` (0007) rejects any `UPDATE` on
`fact` that isn't setting `superseded_at` from `NULL` — a cascaded method
change is exactly the kind of destructive update that trigger exists to
block. Adding the cascade would just move the failure from the FK to the
trigger.

**The actual correction path is a new `source` row**, not a correction to
the existing one: a new `id` with the right `method`, ingestion re-pointed
at it going forward. That drags real cost with it, not just a rename —
new `source_rank` rows for every jurisdiction/field pairing the old source
participated in, a seed change, and a decision about what the old source id
means going forward (retired but still the accurate provenance record for
every fact recorded under it, presumably — never deleted, since deleting it
would orphan those facts' `source_id` FK).

## An unresolvable `parcel.apn` is an exception, not a fact

The parcel identity diagnostic (2026-08) found 9 features in
`ca_san_jose.parcels` with a genuinely blank APN and 9 more duplicate-APN
groups where the APN itself is a literal `'???'` placeholder substring
(e.g. `'27704???'`) — not a real value, just an unresolved suffix marker
the source never replaced. Neither is a value.

Ingest code (Phase D today; `core/store.derive()`/L4 once it exists) must
**not** write a `parcel.apn` fact for either case. Recording `'27704???'`
or an empty string as a `public_record` observation would store a
non-value as if it were one — the exact thing I2/claim types exist to
prevent. Instead, raise one `parcel_exception` per affected parcel:
`type='coverage_gap'`, a stable `detector_key`/`detector_version`, and
`detail` carrying the raw source value (or its absence) and which case it
is (`blank` vs. `placeholder`).

This needs no schema change — `parcel_exception` (0010) and its
outcome/resolution biconditional (0015) already accept this shape exactly
as written. Verified directly, not assumed:

```sql
INSERT INTO parcel_exception (
    parcel_id, jurisdiction_id, type, severity, detector_key, detector_version, detail
) VALUES (
    '<parcel id>', 'ca_san_jose', 'coverage_gap', 'info',
    'parcel_apn_unresolvable', '1.0',
    '{"raw_apn": "27704???", "reason": "placeholder"}'::jsonb
);
```

succeeds with `outcome='open'`, `resolved_at`/`resolved_by` both `NULL` —
0015's biconditional already requires exactly that combination for an open
exception. `parcel.apn` (the column) is left `NULL` for that parcel too
(0034: no fact means no cache value either), which is itself informative —
a `NULL` `parcel.apn` with an open `coverage_gap` exception on file reads
differently from a `NULL` that just hasn't been looked at yet.

## Whether a parcel's absence from a source means anything depends on `source.method`

`fact` records what a parcel HAS. Nothing in its own columns records what a
parcel's *absence* from a particular source's results means — that has to be
read off `source.method`, and the rule is not written down anywhere else, so
it lives here.

**`method='bulk'`** (parcels, zoning_districts, building_permits_active,
today): the source publishes its complete dataset in one snapshot, and that
snapshot is retained (`snapshot.object_uri`, content-addressed). A parcel
absent from a bulk source's results is itself an observation: the source, as
of that snapshot, does not consider this parcel to have whatever the source
describes (an active permit, a zoning classification, and so on). This is
exactly why `building_permits_active`'s ingest (`scripts/ingest_zoning_permits.py`
`load_permits`) writes no `permits.active` fact at all for a parcel that
never appears in the file, rather than writing `permits.active=false` — the
absence is *itself* the signal, already fully recorded by the snapshot that
exists and the fact that doesn't. Writing an explicit `false` fact would
claim a redundant second observation for something the absence already says.

**`method='direct'`** (per-record query APIs; none live yet, but declared in
`access_method`, 0001): a parcel's absence from what you happened to query
means only that you didn't ask about it, or the query missed it — not that
the source has no answer. There is no complete-dataset snapshot to reason
against. Absence is ambiguous and must never be read as a fact the way it can
be for `method='bulk'`.

Someone reading `fact` alone, for a parcel with no `permits.*` rows, cannot
tell these two situations apart without also checking the relevant
`source.method` — the table itself does not carry this distinction. Any
future code that infers something from a parcel's absence from a source's
results (a "no active permits" badge, a coverage metric, anything) must
gate on `method='bulk'` first, or it will silently misread a `method='direct'`
source's incomplete query as a confirmed negative.

## `fact.retrieved_at` belongs to the snapshot, not a later deduped re-fetch

`snapshot.id` is deterministic for `(source_id, content_hash)`, and 0021 makes
the row immutable. If a later fetch returns bytes that hash to an existing
snapshot, that later observation may produce a new `job_run`, but it does not
produce a new snapshot row and must not rewrite the existing snapshot's
`fetched_at`.

Rule for facts: a fact inserted from a snapshot uses that snapshot row's
`fetched_at` as `fact.retrieved_at`. That timestamp is the first retained
observation of the bytes whose immutable `snapshot.id` the fact cites. A
deduped re-fetch time belongs on `job_run.started_at`/`finished_at` for the
new attempt, not on facts tied to the older snapshot.

In Phase A reconciliation, a deduped re-run of identical bytes writes no new
facts at all. If a future phase intentionally records observation-level
metadata for repeated identical content, that metadata needs its own
observation/job shape; overloading `fact.retrieved_at` would make one fact
claim it was retrieved from a snapshot at a time different from the snapshot's
own immutable fetch time.

## `job_run` has no metrics slot, and stretching `schema_drift` for one is a stopgap

Every non-trivial ingest so far has wanted a second number beyond
`rows_in`/`rows_out` (total attempted vs. total succeeded, one axis) to
describe *why* the gap between them exists: Phase E's blank/placeholder
split, zoning's zero-match/multi-match split, permits' blank/not-found/
ambiguous split (the last one persisted in `job_run.schema_drift`, by
`ingest_zoning_permits.py`'s `load_permits`, with an explicit comment at
that call site — `schema_drift`'s declared purpose, per 0012, is "fields
expected but missing," a source dropping an expected *column*, not a
per-row match-outcome distribution; using it for the latter is a real
semantic reach, done because the alternative (`job_run.error`, a text
column with no shape contract, used on a `status='succeeded'` row) is
worse, not because it's a good fit).

The honest fix is a general `metrics jsonb` column on `job_run` — every one
of these breakdowns would sit there uniformly instead of each new ingest
arguing its way into a column named for something else. Not added: it's a
schema change, and every ingest pass so far has run under a no-schema-
changes rule. Recorded here so the next one doesn't have to rediscover the
need from scratch, or add a fourth thing to `schema_drift` that has even
less to do with schema drift than the third did.
