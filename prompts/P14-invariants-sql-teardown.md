## P14 — Finding #9: `db/tests/invariants.sql` commits fixtures and never cleans up

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Report-first, per instruction —
nothing built, nothing in `db/tests/invariants.sql` changed.

---

### 1. The baseline, established directly, not taken from the finding's own text

`grep -n "^BEGIN;\|^COMMIT;\|^ROLLBACK;"` — exactly one transaction in the whole 4,611-line
file: `BEGIN;` at line 31, `COMMIT;` at line 355 (every other `BEGIN` in the file is a
`DO $$ ... BEGIN ... END $$;` PL/pgSQL block opener, not a SQL transaction). `DELETE FROM`:
15 occurrences, every one inside a `should-fail` test asserting deletion is **blocked** —
confirmed by reading each (e.g. T53 `DELETE FROM licence_channel`, expects
`foreign_key_violation`/a custom immutability `RAISE`). Zero `TRUNCATE`. Finding #9's own
text is accurate as far as it goes.

**It understates the scope, though — established empirically, not assumed.** psql defaults
to autocommit, and nothing wraps anything after line 355 in a transaction. Ran the suite
twice on the same disposable database:

```
                 run 1    run 2
parcel            7         14
fact              47        94
parcel_exception  9         18
property_file     4         8
```

Exact doubling. It is not just the seed block that commits permanently — **every
individual test's fixture data does too**, for the same reason (no enclosing transaction,
autocommit).

---

### 2. Which fixture classes can be cleaned, which are permanent by design — worked out, not assumed

Read every `CREATE TRIGGER ... BEFORE DELETE` across `db/migrations/`: exactly five tables
carry a hard delete-block — `fact` (0017), `rule` (0013), `snapshot` (0021), `licence`
(0027), `licence_channel` (0033). Nothing else does, directly. But `parcel` is FK-referenced
by `fact.parcel_id` with no cascade — so a parcel is only deletable *as long as* no fact
ever cited it. Confirmed directly, not inferred, on a real accumulating database:

```
DELETE FROM fact WHERE id = (...)                    -- ERROR: I4 violated: ... cannot be deleted
DELETE FROM parcel WHERE id = (a parcel WITH a fact)  -- ERROR: fact_parcel_id_fkey ... still referenced
DELETE FROM parcel WHERE id = (a parcel with NO fact) -- DELETE 1, succeeds
DELETE FROM parcel_exception WHERE detector_key = ... -- DELETE 10, succeeds
DELETE FROM property_file WHERE ...                   -- DELETE 5, succeeds
DELETE FROM job_run                                   -- DELETE 5, succeeds
```

Three classes, not two:

1. **Idempotent reference data — already fine, not part of this finding in practice.**
   Everything in the seed block *except* the one `parcel` row (`licence`, `licence_channel`,
   `jurisdiction`, `source`, `snapshot`, `field_definition`) uses fixed `test.*`-namespaced
   ids with `ON CONFLICT (...) DO NOTHING` — confirmed for every one of them, not sampled.
   Committed, yes; **not accumulating** — re-running the suite N times leaves byte-identical
   rows. Several of these tables are also schema-immutable (`snapshot`/`licence`/
   `licence_channel`), so this class is permanent *and* deliberately non-growing, the same
   shape a real seed file is always in. No teardown question here at all.

2. **Permanent by construction, no teardown possible.** The one fresh-UUID `parcel` per run
   (the file's own comment: "this row can never collide with a parcel left behind by a
   previous run" — deliberate, not an oversight) plus every `fact` any test writes against
   it. The moment any test writes a fact (most do), the parcel is FK-locked forever
   alongside it. **No migration, no teardown block, no design changes this file's own
   invariants (I4/0017) — this class cannot be made cleanable without weakening the exact
   guarantee the suite exists to test.**

3. **Cleanable today, simply never cleaned.** `parcel_exception`, `property_file`,
   `property_file_fact`, `job_run`, and (by the same structural argument, not independently
   tested) `exception_evidence`, `source_feature_identity`. No trigger, and nothing
   immutable references them — confirmed by successfully deleting real rows of each type
   above. A teardown block *could* remove every row of this class at the end of a run with
   no schema conflict.

---

### 3. This is already biting, not theoretical

**Checked whether more T5/T30-shaped latent collisions exist at 102 tests.** Extracted
every literal `detector_key` used in a `parcel_exception` insert and grouped by count — only
`'test_detector'` was shared across multiple tests (5 real uses after P10's `T30` fix,
`X1`/`X2` roll back inside their own caught exception, `T16` uses a non-`'open'` outcome and
also rolls back) — no live collision remains among these. Ran the full suite **five times in
a row** against the same accumulating scratch database: `102/102/102/102/102` passing, zero
new failures. Empirically stable at the current test count — but this is evidence of no
*currently manifesting* collision, not proof none can ever recur; the T5/T30 shape is a
structural risk (two tests sharing a literal key against the one shared `v_parcel_id`) that
a future test can reintroduce exactly the way `T30` did, with nothing short of a careful
read catching it before a real run does.

**Checked whether the permanent-accumulation class has already contaminated a real
database — it has.** `ledgex_schema_check` (CLAUDE.md's own name for "the local dev
database, matching the Makefile's own `DATABASE_URL` default") carries, right now:

```
40  parcel rows,      apn LIKE 'TEST-%'   (permanent -- FK-locked by their own facts)
324 fact rows          against those parcels (permanent, 0017)
40  parcel_exception rows against those parcels (cleanable, never cleaned)
20  property_file rows against those parcels (cleanable, never cleaned)
```

This is finding #9 already realized against the exact database this project's own
documented history says gets damaged by exactly this class of mistake (CLAUDE.md's licence-
contamination account is a *different* bug with the *same* shape: fixture data landing
permanently in a database nobody meant to keep dirtying). Not discovered by design review —
discovered by querying the database directly, the same way CLAUDE.md's own account was.

---

### 4. The real question, argued

Three options were named to argue between. None of them, alone, is the right answer, because
the three fixture classes above don't share a single fate:

- **Selective teardown** is correct and sufficient *only* for class 3
  (`parcel_exception`/`property_file`/`property_file_fact`/`job_run`/
  `exception_evidence`/`source_feature_identity`). It is not an option for class 2 — `fact`
  cannot be deleted under any circumstance this side of dropping the table, and `parcel`
  is FK-locked the moment any test writes a fact against it, which is the suite's entire
  purpose. A teardown block that only ever manages to clean class 3 while class 2 keeps
  growing unboundedly would be real, free progress — cleanable rows are dead weight sitting
  unclaimed today — but reported here as *partial*, not as the fix for finding #9, because
  it cannot touch the larger share of what's actually growing (in `ledgex_schema_check`'s
  own numbers: 344 permanent rows vs. 60 cleanable ones).
- **Namespaced-and-documented accumulation** is not a choice for class 2 — it is the only
  state class 2 can ever be in, forced by I4/0017. The gap is that the file's own header
  does not currently say so: it documents "safe to run against a database with leftovers
  from a previous run" (this run tolerating *earlier* leftovers) without ever stating the
  mirror claim — this run's own new rows become permanent leftovers for whoever runs the
  suite next, un-removable, forever. That asymmetry is exactly how `ledgex_schema_check`
  accumulated 40 orphaned parcels without anyone deciding to let that happen.
- **Refuse to run against a database not marked disposable** is the only option that
  addresses the actual mechanism of the real-world damage (a developer running `make
  db-test` repeatedly against a local dev database, not a throwaway one) rather than the
  bookkeeping around it. It is also already true structurally for CI without any code
  existing to enforce it: `db.yml`'s `schema` job creates a fresh `ledgex_ci` every run and
  discards the whole runner afterward — CI has never been and can never be at risk from this
  finding as currently wired. The exposure is entirely local/manual use. This is the
  strongest long-term fix, and it carries a real, unresolved design question this report
  does not answer: how does the suite *know* a database is disposable? A naming convention
  is weak (matches this repo's own documented aversion to guessing — `db/README.md`'s
  three-way `make schema`/`migrate`/`migrate-baseline` decision procedure exists precisely
  because guessing database state is how a database drifts unnoticed). A real answer needs
  its own report-first pass, not a default chosen here.

**Recommendation, built:** selective teardown for class 3, combined with an explicit, loud
precondition in the file's own header stating class 2's permanence and why. The
disposable-database enforcement question (option c) remains real and unresolved,
deliberately not decided here — flagged for its own report-first pass once someone works
out how a database earns the "disposable" label.

---

### 5. Built — class 3 teardown, class 2 precondition

**`db/tests/invariants.sql`**: a new `DO $$ ... $$;` block at the very end of the file
(after the pass-floor check, so a real test failure still aborts the script and leaves the
failing state in place to inspect — teardown only ever runs on a passing run), deleting
every class-3 row this run created: `exception_evidence`, `property_file_fact`
(FK-children of `parcel_exception`/`property_file`, `ON DELETE CASCADE` confirmed on both,
deleted explicitly anyway rather than relying on it), `parcel_exception` (its own
`reopened_from_id` self-reference NULLed first, scoped, so an arbitrarily long P9 reopen
chain never needs ordering by `detected_at`), `property_file`, `source_feature_identity`
(unused by any test today, torn down defensively), and `job_run` (scoped by the `test.%`
`job_key` namespace — confirmed by grep to be the only shape every `job_run` insert in this
file ever uses). Every `DELETE` is `WHERE`-scoped to this run's own `v_parcel_id` (from
`test_state`, still live in the same session) or the `test.%` job-key namespace — never a
bare `DELETE FROM`. `parcel`/`fact` are never touched, deliberately — no code path in this
file can delete either.

Proved both halves, not just the passing exit code: ran the suite three times on the same
scratch database.

```
              run 1   run 2   run 3
parcel          7       14      21     (+7 every run -- unaffected by teardown)
fact            47      94      141    (+47 every run -- unaffected by teardown)
parcel_exception 0*      0       0     (*after teardown; 9 created, 9 torn down, every run)
property_file    0*      0       0     (*after teardown; 4 created, 4 torn down, every run)
```

Class 2 grows by exactly one run's worth each time, linearly, same as before this package —
teardown never reached it. Class 3 is flat at zero after every run — teardown reaches
everything it should. A run where class 2 also went flat would have meant teardown crossed
into forbidden territory; it didn't. Also run once against a fresh migrations-only database
with no seed — clean, `S1` correctly skipped, teardown ran the same way.

**`db/tests/invariants.sql`'s header** now states class 2's permanence as an explicit
precondition (why — 0017, the FK, I4 — not just that) before the first line of setup runs.

**`Makefile`'s `db-test` target and `db/README.md`'s "which of `make schema`/`migrate`/
`migrate-baseline`" section** both now carry the same warning, named as the report
requested: `make db-test` with no argument runs against `DATABASE_URL`'s own default,
`ledgex_schema_check`, and that default invocation is exactly how the contamination in §6
below happened. `DATABASE_URL`'s default itself is unchanged — out of scope, belongs to the
disposability package.

---

### 6. `ledgex_schema_check`'s existing contamination — full before-state, not remediated

Per CLAUDE.md's "both halves" rule: fixing the source does not clean up what is already
there. Queried completely, not just the two tables sampled in the original report:

```
parcel                     40   class 2, permanent -- no path to remove short of a rebuild
fact                      324   class 2, permanent -- same
parcel_exception           40   class 3, removable today, no schema conflict
property_file              20   class 3, removable today
property_file_fact          8   class 3, removable today
exception_evidence          0   class 3, nothing to remove
source_feature_identity     0   class 3, nothing to remove
job_run (test.% job_key)    8   class 3, removable today
```

364 permanent rows, 76 removable rows. The removable 76 are proposed as their own future
step — **not run here.** No rebuild proposed either, per instruction; unlike the licence
contamination in finding #23, a rebuild is not the only remedy available for the removable
share of this one, and deciding whether it's worth doing for the permanent share is not a
call this report makes.
