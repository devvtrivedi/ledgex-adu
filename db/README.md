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

## `make db-test` writes permanent rows — point it at a disposable database

Once a database's schema is up to date (via whichever of the three targets
above applied), `make db-test` (`db/tests/invariants.sql`) is very likely
the next thing run against it — and unlike the three targets above, it is
not idempotent in the way a database-drift decision needs. Every run writes
one or more new parcels plus every fact any test writes against them, and
both are permanent by construction: `fact_no_delete` (0017) blocks deleting
a fact directly (I4 — "facts are immutable; corrections supersede, never
delete" — working as designed), and `fact_parcel_id_fkey` (no `ON DELETE`
cascade) then blocks deleting the parcel too, the instant any fact cites
it. P17 added `db/tests/teardown.sql`, run unconditionally by `make
db-test` itself (pass or fail — see that target's own comment), for
everything else the suite writes (`parcel_exception`/`property_file`/
`property_file_fact`/`job_run`/`exception_evidence`/
`source_feature_identity`, plus any parcel that ends up with zero facts
against it), but the fact-bearing-parcel class has no teardown path that
doesn't mean weakening 0017/I4 itself — see `db/tests/invariants.sql`'s own
precondition comment at the top for the full argument.

`make db-test` reads its own variable, `DB_TEST_DATABASE_URL` — NOT
`DATABASE_URL` — defaulting to `postgresql://localhost/ledgex_test` (P18,
README finding #25, closed). That database does not exist on a fresh
clone, so the default invocation now fails loud (`database "ledgex_test"
does not exist`) instead of silently succeeding against
`ledgex_schema_check`, this project's shared local dev database — which is
exactly how that database ended up carrying orphaned parcels and
permanently-locked facts, twice (P14, then again by the time P17 re-queried
it — neither incident is the kind of row a migration or a `DELETE` can
reach). Create `ledgex_test` yourself first (`make schema
DATABASE_URL=postgresql://localhost/ledgex_test`) or override
`DB_TEST_DATABASE_URL` explicitly to whatever scratch database you already
have. This default is deliberately independent of `DATABASE_URL` and the
three targets above — none of `schema`/`schema-dump`/`migrate`/
`migrate-verify` read `DB_TEST_DATABASE_URL`, and `db-test` does not read
`DATABASE_URL` — so overriding one never silently affects the other. CI
never has this problem — `db.yml`'s `schema` job creates a fresh,
disposable `ledgex_ci` every run, passes it to `db-test` explicitly via
`DB_TEST_DATABASE_URL`, and discards the whole runner afterward; the risk
was entirely in local, manual invocation with no override at all.

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

## `job_run.metrics` (0051) replaced the `schema_drift`-stretching stopgap

D5 (P59): this section used to say `job_run` "has no metrics slot" and
argue for adding one. 0051 added `job_run.metrics jsonb`, and every writer
that used to reach for `schema_drift` for this purpose has migrated to it
— `ingest_zoning_permits.py`'s `load_permits`/`load_zoning`, `check_golden.py`,
`flag_invalid_geometry.py` and others all persist their own per-run
breakdown there now (blank/not-found/ambiguous splits, exception counts,
diff summaries), not in `schema_drift`.

Kept here for history, not as a live gap: every non-trivial ingest wanted
a second number beyond `rows_in`/`rows_out` (total attempted vs. total
succeeded, one axis) to describe *why* the gap between them exists — Phase
E's blank/placeholder split, zoning's zero-match/multi-match split,
permits' blank/not-found/ambiguous split (the last one originally
persisted in `job_run.schema_drift`, a real semantic reach: `schema_drift`'s
declared purpose, per 0012, is "fields expected but missing," a source
dropping an expected *column*, not a per-row match-outcome distribution).
`metrics jsonb` is the general home all of these now sit in uniformly,
instead of each ingest arguing its way into a column named for something
else.

## Stale migration header claims — corrections live here, never edited into the migration

B9 (P59C, LEDGEX-P59B-ENGINEERING-REPORT.md sec 3.2.2.9). Migrations are
forward-only (§3.13) — a migration's own header text cannot be hand-edited
after it lands, even when the prose it carries stops being true (unlike a
functional defect, which a *later* migration can fix and explain in its own
header, e.g. 0048's header explaining what was wrong with 0038). A prose-only
staleness — nothing to fix, nothing broken, just a comment describing a
process or dependency that has since changed — had no established place to
be corrected until this section. This is that place: append an entry below
whenever a migration's own comment is later found stale, in the same shape
CLAUDE.md already uses for its own inline `**Corrected (Pxx):**` paragraphs.
Never remove or renumber an entry once added — this section is itself
append-only, for the same reason the migrations it corrects are.

- **0031_output_channel_analytics_model_training.sql** — its own header
  says "This project's migration runner invokes psql -f per file with no
  explicit BEGIN/COMMIT and AUTOCOMMIT on." No longer true: the Makefile's
  `schema`/`migrate` recipes now pass `--single-transaction` to every
  `psql -f` invocation per migration file (confirmed against the Makefile's
  own recipe text, not assumed). The paragraph's own actual point — that
  0031 and 0032 must be two separate migration files because
  `ALTER TYPE ... ADD VALUE` cannot be referenced within the same
  transaction that added it — is unaffected by this and remains true either
  way (`--single-transaction` wraps one *file*, not the whole migration
  run, so the two-file split is still load-bearing).
- **0032_licence_channel_analytics_model_training.sql** — its own header
  says "db.yml never runs db/seeds/day4_sources.sql." No longer true since
  P36 (finding #38): `db.yml`'s `schema` job runs
  `db/seeds/day4_sources.sql` between `make db-test` and `make golden` —
  see CLAUDE.md's own corrected paragraph on this exact point. The
  migration's own FK-safety argument (a blind `INSERT` would raise
  `foreign_key_violation` against a migrations-only database) is
  unaffected — `p5-acceptance`/`phaseb-acceptance` still run against their
  own migrations-only databases, and this migration must still work there
  regardless of what the `schema` job's database looks like.
- **0058_fact_licence_restriction_sticky.sql** — its own header, at the
  comment directly above the attribution sticky block, says the message
  text is "UNCHANGED from 0029's original... this check itself is not new...
  db/tests/invariants.sql's own pre-existing T50/T51 assert this exact
  wording and must not need to change alongside a fix that does not touch
  this check's own behavior." That claim was true when 0058 was written and
  is superseded by `0059_fact_licence_restriction_generic.sql` (P62B, D-6.7
  Option 2, owner decision 2026-09-02): 0059 folds attribution into a fully
  generic sticky-restriction rule, and attribution's message text changes
  from `'I5 violated: ... does not require attribution, but at least one
  input does.'` to `'I5_RESTRICTION_DROPPED: ... does not carry attribution,
  but at least one input does.'` — a real, visible change, not prose drift,
  and the reason D-6.7 needed an owner decision rather than a judgment call.
  T50 was rewritten in place (not added) to assert the new wording; T51 and
  every other invariant test are unaffected (grepped, zero other assertions
  depend on either wording). 0058's own logic (which restriction values are
  sticky, and under what condition a derivation is refused) is unchanged by
  0059 — only attribution's special-cased message text and the mechanism
  (one generic block instead of four literal ones) changed. See 0059's own
  header for the full argument and P62B-LEDGER.md for the four-quadrant
  proof that this change is real and precisely targeted.
- **0018_provenance_integrity.sql** — its own header originally said a
  derived fact has "source_id, snapshot_id and method_version all NULL
  (fact_provenance_complete, 0006)." Backwards on the third: `0006`'s
  `fact_provenance_complete` CHECK requires `method_version IS NOT NULL`
  for a derived fact — it is `source_id`/`snapshot_id` that must be NULL
  there. The migration's own FK argument is unaffected either way — none
  of its composite FKs reference `method_version` at all; only this
  introductory claim about the column was wrong. **This correction was
  originally made in place, in the migration file itself** (P59 D17,
  `bc51c0b`, 2026-08-25) — before this section existed to hold it. That
  in-place edit changed the file's bytes after the real `ledgex_schema_check`
  had already recorded its original hash (during the 2026-08-23 P55
  rebuild), so `scripts/migrate.py`'s own file-hash integrity gate began
  refusing every further migration against that database from 2026-08-25
  onward (surfaced eight days later, at P62C, 2026-09-02 — see
  `P62D-DECISION-PACKET.md`). **The owner chose Option A of that packet's
  five on 2026-09-02**: P62E reverted the migration file to its original
  landing bytes (byte-identical, hash-verified) and relocated this same
  correction here. **The correction itself was right on the merits the
  whole time — only its location was wrong**; `db/README.md`'s stale-header
  convention did not exist yet when D17 was made.
- **0056_l0_gate_boundary_source.sql** — its own header originally said
  every statement in it is guarded to be "a TRUE no-op — zero rows
  touched, no FK violation possible — on a FRESH, migrations-only
  database." Overstated: steps 1–3 (the `licence` 'unknown' row, its six
  `licence_channel` rows, and the `field_definition` row) are unconditional
  `INSERT`s that write eight rows every time on a fresh database — real
  writes, not no-ops. `ON CONFLICT DO NOTHING` makes a *re-run* a no-op,
  not the first run. Only steps 4–5 (the FK-guarded source INSERT and the
  jurisdiction UPDATE) are genuine zero-row no-ops on a fresh database,
  because `ca_san_jose` does not exist yet at migration time. The
  migration's own behaviour is correct and intended either way — only the
  summary line's claim about it was wrong. **This correction was
  originally made in place, in the migration file itself** (P59 D16,
  `e83132c`, 2026-08-25) — the same day and the same class of edit as
  0018's D17 correction above, and blocking `scripts/migrate.py`'s
  integrity gate for the identical reason. **The owner chose Option A on
  2026-09-02**: P62E reverted this file to its original landing bytes
  (byte-identical, hash-verified) and relocated this same correction here.
  **Right on the merits, wrong location** — same as 0018 above.

## Known timezone-literal defects in landed migrations — not prose, tracked here until remediated

P60-4. **Deliberately a different section from "Stale migration header claims"
above, not a subsection of it.** B9's own scope is explicit: "a prose-only
staleness — nothing to fix, nothing broken." What's recorded here is the
opposite — a genuine functional defect (the timezone class: C7, AD1,
`db/seeds/day4_sources.sql`'s own P60-4(a) fix), sitting inside migration
files that are forward-only and can never be hand-edited (§3.13). A bare
`'YYYY-MM-DD'::timestamptz` literal resolves at the CONNECTING SESSION's
local midnight at the moment the migration was originally applied, not a
fixed UTC instant — meaning the actual stored value in any database this
migration has ever run against depends on that database's session TimeZone
at apply time, which this file has no way to know or assert after the fact.

This section exists because the forward-only convention's own remedy — "a
functional defect can only be corrected by a later migration, which
explains itself in its own header" — is not something to reach for
unilaterally: whether the affected rows need a corrective migration at all
depends on which table they're in (an immutable table, per CONVENTIONS'
own established escalation, has no migration-level fix at all — only a
full rebuild, an owner decision) and, for a mutable table, a corrective
migration is itself a standing pause point (never authored without the
owner's own go-ahead). Until either resolves, the honest record is here,
not silence and not a hand-edit of the migration body.

- **0023_correct_seeded_endpoint_urls.sql** — two bare literals,
  `url_verified_at = '2026-08-06'::timestamptz` (lines 41, 49). Same class
  as `day4_sources.sql`'s own pre-P60-4(a) literals (in fact the identical
  date, `2026-08-06`, that `day4_sources.sql` also carried for the same
  three sources' `url_verified_at` — not a coincidence, both trace to the
  same real verification pass). **Status: not remediated.** Affects the
  `source` table (mutable — not one of `licence`/`licence_channel`/`rule`/
  `fact`'s own immutable set, §1's own I4/I18 scope) — a corrective
  migration is possible in principle, but authoring one is P60's own pause
  point 4 (any new migration), not resolved in this pass.
- **0056_l0_gate_boundary_source.sql** — one bare literal (line 135,
  `'2026-08-22'::timestamptz`). Same class. Table affected not yet
  identified in this pass — see P60-4(b)'s own partition-by-table work for
  the specific column this literal populates and that column's mutability.
  **Status: not remediated**, same reason as above.

Both entries stay here, unedited, until a later migration (for the mutable
half) or a rebuild (for any immutable-table half, per the owner's own
decision) actually resolves the underlying stored values — at which point
the resolving migration's own header is the right place to say so, and
this entry should be updated to point at it, not deleted (this section is
append-only/update-in-place for the same reason B9 above is: the migrations
it describes are, and always will be, forward-only).

## `licence_channel` insertion practice — D1 (P63A/P63B, 2026-09-02)

P63A's investigation (~/Desktop/ledgex-p63-evidence/P63A-DESIGN-PACKET.md §7.1) found that
of the 6-value `output_channel` enum, only `paid_property_file` and `api` had ever been
granted `allowed=true` for any real licence, in this database's entire history — the P55
precedent (`db/seeds/day4_sources.sql`) minted all 6 `licence_channel` rows per licence
regardless of whether a given channel was actually in use. The owner approved D1 on
2026-09-02: **insert only the `licence_channel` rows genuinely required by the current
use/distribution model, going forward.**

What this practice changes: future `licence_channel` INSERTs, and nothing else. What it
preserves, unchanged: the six-value `output_channel` enum itself (no value is removed —
`ALTER TYPE ... DROP VALUE` does not exist in Postgres, and no case was made for wanting
one); the default-deny gate in `core/rights.py::evaluate_rights_gate` (a missing row already
reads identically to an explicit `false` — this practice makes that the normal case for an
unused channel rather than an accident of history); and every actual rights restriction any
existing `licence_channel` row already carries (no existing row is touched by this practice —
`licence_channel` is immutable, 0033, and this is a practice for new rows, not a data
migration).

Why here, before D-6.4: D-6.4 (the map-serving rights instrument, P63C or later) will mint at
least one new licence id and its `licence_channel` rows, and those rows are immutable the
moment they land — if D-6.4 reflexively minted all 6 channels the way the P55 precedent did,
and this practice were adopted afterward, the mismatched rows could not be corrected in place;
only a fresh licence id and a fresh set of rows could replace them (P63A packet §7.3(b)). D-6.4
cites this record for exactly which channels its rows should cover — decide that by reading
this entry, not by re-deriving P55's shape from scratch.

## Known pre-external-distribution decision: map-specific rights grants and stored `licence_id` (2026-09-03)

P63D investigated D-6.4 (the map-serving rights instrument) and found the mechanical question
narrower than the original proposal assumed: `evaluate_rights_gate` resolves permission from
the `licence_id` **stored on each fact**, not from the source, the field, or anything
resolvable at read time
(~/Desktop/ledgex-p63-evidence/P63D-DESIGN-PACKET.md §2). Every existing `parcel.geometry`
fact already carries `cc_by_4_0_api_2026_08`, which the internal viewer's own `api`-channel
grant already covers (`db/seeds/day4_sources.sql:186-191`, 2026-08-22).

`licence_channel`'s PK is `(licence_id, channel)` and the table is immutable (`0033`), so an
existing licence id can never gain a second row for a channel it already has. **Therefore any
future map-specific rights grant must account for the `licence_id` already stored on existing
`parcel.geometry` facts, and cannot be assumed to govern them prospectively.** Making a new
grant govern existing facts requires superseding those facts — the P55 pattern
(`prompts/P55-scoped-unblock.md`), `scripts/ingest_parcels.py:88`'s own repoint comment
("facts cite THIS constant at write time"), and the `_p55_stage6_*` replay are the precedent
for what that costs: a 225,077-fact replay, not a row insert.

The owner **deferred** this on 2026-09-03 rather than deciding it — a fresh, narrower grant
was judged premature until an internal map exists and its real serving architecture can be
evaluated (P63E, the internal-viewer-only geometry rendering, is that evaluation ground). **This
deferral is not approval for external map serving.** Default-deny remains in force for every
external/customer-facing path: no `licence` or `licence_channel` row changed as a result of
this decision or of P63E, and P63E renders geometry only through the existing gated
`GET /v1/parcels/{id}/facts` route, on the existing `api` channel, in the existing
localhost-only, no-auth internal viewer.

## `current_fact_at()` was not inlined for 24 migrations (0039-0060) — fixed by `0061` (2026-09-03)

`0039` added `SET search_path = public, pg_temp` to `current_fact_at()` as defense-in-depth
alongside its own "reliable fix" (explicit `public.` qualification on every table reference in
the body). That `SET` clause is a per-call GUC scope, and PostgreSQL will not inline a
`LANGUAGE sql` function that sets one — silently reintroducing the exact cost `0036` chose
`LANGUAGE sql` specifically to avoid, for every caller filtering by anything other than the
function's own unfiltered form: `Function Scan on current_fact_at`, the WHERE predicate applied
as a `Filter` *above* the function call rather than pushed inside it, `Rows Removed by Filter`
on the order of the whole `fact` table. Measured live, single-parcel read: ~2,500-3,600ms before,
~4.5ms after. Unnoticed for 24 migrations because nothing asserted the function stayed inlined —
`db/tests/invariants.sql`'s T57 (matview parity), T58 (point-in-time correctness) and T63
(table-shadow resistance) all pass identically whether the function is inlined or not; none of
them inspects the plan.

`0061_current_fact_at_inlining.sql` removes the `SET` clause. The table-shadow property T63
checks is unaffected — it was always carried by the explicit qualification layer, not the `SET`
clause, confirmed both by T63 continuing to pass with the clause removed and adversarially: a
session that explicitly overrides its own `search_path` to favor `pg_temp` before attempting the
same shadow still cannot make `current_fact_at` read it
(`~/Desktop/ledgex-p64-evidence/P64A2-RUN-EVIDENCE/r4-adversarial-t63.txt`). Full evidence trail:
`~/Desktop/ledgex-p64-evidence/P64A1-RUN-EVIDENCE/` (the causal A/B), `P64A2-RUN-EVIDENCE/` (four
remedies evaluated, this one selected on all five axes), `P64A3-RUN-EVIDENCE/` (the migration
itself, rehearsed, applied).

`scripts/test_current_fact_at_inlined.py` (wired into `db.yml` the same commit as `0061`) is the
regression test this defect existed without: it asserts the absence of a `Function Scan` node in
`EXPLAIN` output for a single-parcel call, deterministically (a rewrite-stage decision,
independent of table contents or statistics, so it will not flake on a small CI database the way
an assertion about which index gets chosen would).

**The operator/cast-shadowing residual is UNRESOLVED, not closed by `0061` or by anything before
it.** Whether a same-named operator or function created in `pg_temp` could be resolved by one of
`current_fact_at`'s bare comparison operators (`<=`, `>`, `=`) or the `confidence` enum's
ordering opclass was never tested — `0039` itself never claimed to close this (its own header
frames the `SET` clause as protection against an *accidental* future unqualified table
reference, never against adversarial operator shadowing), so `0061` leaves an existing,
pre-existing gap exactly where it already was. Not this record's to close; named here so it is
not mistaken for settled.
