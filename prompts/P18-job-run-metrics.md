## P18 — job_run gets a real metrics column: findings #12 and #16's metrics half

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Schema change — report before
writing.

---

### 0. Landed P17's own recommendation first — own commit, no new decision

P17 argued option (a) — a `db-test`-scoped `DATABASE_URL` default — and did not implement it.
Built and landed first, before anything else in this package: `db-test` now reads its own
`DB_TEST_DATABASE_URL` (default `postgresql://localhost/ledgex_test`), not `DATABASE_URL`.
`schema`/`schema-dump`/`migrate`/`migrate-verify` confirmed unchanged by grep — none read the
new variable. `ledgex_test` does not exist on a fresh clone, so the bare default now fails
loud instead of silently landing on `ledgex_schema_check`. `db.yml`'s `db-test` step updated
to pass `DB_TEST_DATABASE_URL="$DATABASE_URL"` explicitly, so CI keeps using its own
already-disposable `ledgex_ci`. Confirmed green on the real runner before continuing.

Closes README finding #25. Landed as `e42a45d`.

Why first: `db/tests/teardown.sql` (P17) reclaims class 3, but every bare `make db-test`
still adds one permanent, undeletable parcel and its facts to whatever database it targets —
the exact class 0017/the FK put beyond teardown's reach. #25 was the only remaining guard on
that half, and this package's own migration work would otherwise run `make db-test` against
scratch databases without ever re-closing that gap.

---

### 1. What `schema_drift` actually carries today — established by query, not assumed

Finding #12 names `load_permits`. Checked whether it's the only one, per instruction.

`load_zoning` (`ingest_zoning_permits.py:736`) also passes a dict into `finish_job_run`'s 6th
positional parameter, which that file's own `finish_job_run` signature
(`rows_in=None, rows_out=None, schema_drift=None`) maps straight to the `schema_drift`
column. Confirmed by reading the function signature directly, not inferred from the call
site alone.

`ingest_parcels.py`'s `phase_c` (line 508) builds a `schema_drift` dict that DOES match
0012's declared meaning field-for-field (`expected_fields`, `actual_property_keys`,
`unmatched_expected`, `notes`) — but `phase_c` calls neither `start_job_run` nor
`finish_job_run` anywhere in its body (confirmed by grep across the whole function), and
`__main__` discards its return value outright: `phase_c(path)`, no assignment. It is printed
(`"schema_drift (to be recorded on job_run): ..."`) and nothing more.

**Queried every reachable database** (`ledgex_schema_check`, the only one reachable this
session) for every `job_run` row with non-null `schema_drift`, grouped by actual top-level
key set:

```
ingest_zoning  (load_zoning,  2 rows): {diff, exceptions_written, exceptions_skipped_already_open}
ingest_permits (load_permits, 2 rows): {diff, unmatched_breakdown, _note}
```

Zero rows anywhere carry `phase_c`'s declared shape. **Two abusers, zero legitimate
writers** — stated plainly, per instruction, because it changes the shape of this package:
not "add metrics," but "add metrics and settle what `schema_drift` is even for," since
nothing legitimate is currently using it and nothing legitimate will start using it as a
side effect of this migration alone.

---

### 2. Design, settled before the migration

**(a) `metrics` contract.** Not schema-less by default, and not a fixed global shape either
— three known consumers (`phase_e`'s blank/placeholder split, `load_zoning`'s zero/
multi-match split, `load_permits`'s blank/not-found/ambiguous split) genuinely want
different key sets, so forcing one shape on all three is its own dishonesty (populating keys
a job type has no data for). The `job_run_metrics_is_object` CHECK enforces the one thing
every consumer can honestly share: `metrics`, when present, is a JSON *object* — never a
bare array, string or scalar — the same shape floor 0038/0048 already enforce for
`property_file.refusals` (`'array'` there, `'object'` here). Beyond that floor, key sets are
per-job-key by convention (documented via `COMMENT ON COLUMN`), the same established
one-column-many-shapes precedent `parcel_exception.detail` already uses successfully.

Argued explicitly why this won't repeat `schema_drift`'s mistake: `schema_drift`'s problem
was never "jsonb with no shape guarantee" — it was a narrowly-named column whose *declared
meaning* was wrong for what writers needed, forcing a choice between violating that meaning
or reaching for `error` (worse). `metrics` has no false semantic claim to violate; its name
is the neutral container every one of the three real shapes already, honestly, is.

**(b) `schema_drift`'s disposition.** Not reclaimed to its declared meaning in this package —
doing that for real means wiring `phase_c` into an actual `job_run` (`start_job_run`/
`finish_job_run`), which `phase_c` does not do today and this package was not asked to add.
Named explicitly as scope creep, not absorbed. Not dropped either — two real historical rows
carry data under it, and both scripts that wrote it are being rewritten in this same package
to stop referencing it, so the column is not silently left dangling. Left in place, its
declared meaning unchanged, its actual state now stated plainly via `COMMENT ON COLUMN job_run.schema_drift`:
zero legitimate writers as of this migration.

**(c) Existing rows.** `job_run` carries no immutability trigger, so in-place correction of
the 4 existing `schema_drift` rows into `metrics` IS mechanically available — unlike
`licence`, where 0027 made it impossible. Argued both ways, per instruction, and decided
against: a `job_run` row is a record of what a specific run, under the code that existed at
the time, actually wrote. These 4 rows correctly reflect that pre-0051 `load_zoning`/
`load_permits` wrote a diff/exception breakdown into `schema_drift` — the counts themselves
are accurate, only the column name is wrong for what 0012 declared. Moving that data would
not correct a wrong VALUE; it would rewrite historical provenance to claim these rows were
written under a contract that did not exist yet when they were. Left exactly as recorded.

---

### 3. Built, RED-first

**`db/migrations/0051_job_run_metrics.sql`** — `ALTER TABLE job_run ADD COLUMN metrics
jsonb`, `job_run_metrics_is_object` CHECK (explicit `metrics IS NULL OR jsonb_typeof(metrics)
= 'object'`, stating the NULL case up front per P10's CONVENTIONS rule — this is an ENUM
VALUE-adjacent note explicitly NOT needed here, since this constraint keys on an expression,
which the header states plainly, distinguishing it from the enum-value case P10's rule was
written for). `COMMENT ON COLUMN` for both `metrics` (the contract) and `schema_drift` (its
now-stated disposition), following 0034's own precedent for live column documentation.
Applied cleanly to a fresh scratch database; manually verified the CHECK accepts an object
and NULL, rejects an array and a bare string.

**All four `finish_job_run` variants updated**, per-script, not unified (reported, not
absorbed — unifying them would be real scope creep this package does not take):

- `ingest_zoning_permits.py`'s single `finish_job_run`: parameter renamed `schema_drift` →
  `metrics`, `UPDATE` targets the new column. `load_zoning`'s call site needed no change
  (already positional/inline). `load_permits`'s `schema_drift` dict renamed `metrics`, its
  `_note` key (which existed only to flag the reach) dropped — the reach is gone, so the
  apology is obsolete. The long comment explaining the `error`-vs-`schema_drift` tradeoff
  replaced with a short pointer at 0051.
- `ingest_parcels.py`'s `finish_job_run_full` (used by `phase_e`): gained `metrics=None`,
  writes it. `phase_e`'s own already-computed, already-printed new/changed/reappeared/
  disappeared and resolvable/unresolvable-APN breakdown now populates it.
- `ingest_parcels.py`'s plain `finish_job_run` (used by `phase_b`/`run_one_fetch`):
  deliberately **left unchanged** — a single fetch has no per-row breakdown to report, and
  adding an unused `metrics` parameter here would be speculative API surface with no real
  caller, which CONVENTIONS argues against. Stated explicitly, not a silent omission.
- `flag_invalid_geometry.py`'s single `finish_job_run` (two call sites, `flag_parcel_geometry`
  and `flag_zoning_source_geometry`): gained `metrics=None`, writes it. Both detectors
  already computed `exception_skipped` (already-open, deduped) and printed it every run with
  no durable record — now persisted as `{"exceptions_written": ..., "exceptions_skipped_already_open": ...}`.

`.venv-ingest/bin/python3 -m py_compile` on all three touched scripts: clean.
`build/check_jurisdiction_names.py` run against the real tree after editing: clean.

**End-to-end, real fixture data, not just unit-level:** `scripts/run_p5_acceptance.sh` run
in full against a fresh scratch database — every checkpoint passed — then `job_run` queried
directly:

```
ingest_parcels_full | {"new": 29, "changed": 0, "reappeared": 0, "disappeared": 0,
                        "apn_resolvable": 27, "apn_unresolvable": 2,
                        "changed_fields": {...}, "apn_unresolvable_reasons": {"blank": 2, "placeholder": 0}}
ingest_zoning        | {"diff": {...}, "exceptions_written": 8, "exceptions_skipped_already_open": 0}
ingest_permits        | {"diff": {...}, "unmatched_breakdown": {...}}
```

Every `schema_drift` column on every row: NULL. `flag_invalid_geometry.py` run directly
against the same database: `metrics = {"exceptions_written": 0, "exceptions_skipped_already_open": 0}`
on both its `job_run` rows.

**RED, real:** migration `0051` temporarily removed from `db/migrations/`, `db-test` run —

```
### TEST T90: job_run.metrics accepts a JSON object (should succeed)
ERROR:  column "metrics" of relation "job_run" does not exist
```

`ON_ERROR_STOP` aborted there, `make db-test` exited nonzero. Migration restored. GREEN
three times on the same accumulating scratch database (class-2: 4→8→12 parcels, 47→94→141
facts, linear; class-3: flat at 0 every run, P17's teardown unaffected) plus once fresh
migrations-only, no seed.

`db/tests/invariants.sql` gained T90 (metrics accepts an object, positive control) and T91
(rejects a bare array, negative control, asserts the exact constraint name) — floor 106 →
108.

---

### 4. Close-out

`db/schema.sql` regenerated from a fresh `make schema` apply; `make schema-dump` clean on
the second run.

Spec bumped 1.34 → 1.35: `text/LedgeX_Engineering_Reference_Spec_v1_34.txt` content edited
BEFORE `git mv` to `..._v1_35.txt`, re-`git add`ed after a later post-rename edit — the
staging trap checked via `git diff --cached --stat -- text/` before committing, confirmed
present, fixed. `SPEC_VERSION` bumped in `build/ledgex_source.py`. §3.12 (job_run's own
section) gained a new paragraph describing `metrics`'s contract and `schema_drift`'s
disposition — not just the change record. New §12 row for 1.35. `make docs`/`make site`
regenerated; `website/index.html`'s hardcoded version string hand-fixed (known gap, not
touched by `make site`). `qa_check.py`: clean, confirms `check_spec_references_migrations`
sees `0051`. `make check-boundary`: clean.

Finding #12 closed. Finding #16 updated: metrics half done, `parcel_lineage`
split/merge, the matching-key decision, and the `pipelines/` split remain deferred,
unchanged.
