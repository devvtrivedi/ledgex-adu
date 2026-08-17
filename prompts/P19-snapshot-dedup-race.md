## P19 — Finding #10: snapshot dedup is check-then-insert

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)).

---

### 1. The part that is not just "add ON CONFLICT"

`already_had_snapshot` (from `snapshot_exists()`'s plain `SELECT`) drove two decisions in
both scripts: whether to skip the upload, and whether `job_run`'s terminal status is
`'skipped_unchanged'` or `'succeeded'` — a provenance claim about which run actually wrote
the row. Under the race, both are wrong for the loser: it would report `'succeeded'` for a
snapshot it never wrote, or (pre-fix) never get that far at all, since the bare `INSERT`
crashes first.

Fixed by making `insert_snapshot()` itself the authority: `INSERT ... ON CONFLICT (id) DO
NOTHING`, `inserted = cur.rowcount == 1` read before `conn.commit()` (both functions'
`cur.execute()`/rowcount-read happen inside the same `with conn.cursor()` block, before the
`commit()` line — confirmed by reading the final code, not just intending it). `id` alone is
a sufficient conflict target: `id` and the table's other `UNIQUE (content_hash, source_id)`
constraint are both fully determined by the same `(source_id, digest)` pair in this code, so
a conflict on one always means a conflict on the other for any row this code ever writes —
no second conflict path to handle.

`snapshot_exists()` kept, explicitly commented as an optimization only in both scripts —
removing it would re-run `upload_and_verify()`'s full upload+re-download+re-hash round trip
on every dedupe hit, real cost for no correctness benefit. `run_one_fetch()` in both scripts
now sets `inserted = False` on the `already_had_snapshot` branch (skips calling
`insert_snapshot()` at all, same as before) and reads `inserted` — never
`already_had_snapshot` — to decide `job_run`'s terminal status.

**Upload idempotency, checked, not reasoned about.** `object_key()` is purely
`sha256/<2>/<digest>` — content-addressed, deterministic from content alone, confirmed by
reading both scripts' identical implementation. Checked the real bucket directly: 5
concurrent `put_object` calls to the identical key, identical content —

```
versioning status: Enabled
thread 0: OK  thread 1: OK  thread 2: OK  thread 3: OK  thread 4: OK
final object matches original content: True
```

— and, discovered while trying to clean up the test key afterward, the bucket is **Object
Locked**: `DeleteObject` failed with `InvalidRequest: Object is WORM protected`, and
`get_object_retention` showed `{'Mode': 'COMPLIANCE', 'RetainUntilDate': ...2126...}`.
Concurrent identical-content uploads to the same key are safe by construction here: each
becomes its own permanent, byte-identical version, none can corrupt or overwrite another, and
reads always return correct content regardless of which version is "current." (Honest
side-effect: the 5 test versions under a synthetic test-only key are now permanently retained
in the real bucket — harmless, distinctly-prefixed, and the same permanence every real
snapshot in this bucket already has by design.)

---

### 2. RED-first, no threads

Two sequenced (not threaded) psycopg2 connections against a real scratch database. Both call
`snapshot_exists()` before either inserts — both see `False`. Both then run the SAME
deterministic `id` insert. Postgres's own read-committed semantics make this deterministic
without real concurrency: conn_a's `INSERT` commits, then conn_b's `INSERT` runs and sees the
row conn_a just committed.

**RED**, against the pre-fix SQL shape (bare `INSERT`, no `ON CONFLICT`), run directly:

```
conn_a sees exists (before either insert): False
conn_b sees exists (before either insert): False
conn_a: bare INSERT (pre-fix shape, no ON CONFLICT)...
conn_a: committed successfully (the winner)
conn_b: bare INSERT (pre-fix shape, no ON CONFLICT), SAME sid, content committed by conn_a...
conn_b: RAISED psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "snapshot_pkey"
```

**GREEN**: `scripts/test_snapshot_race_invariant.py`, same two-connection sequencing, against
the real, current (fixed) `insert_snapshot()` in both scripts — 12 assertions, all passing,
run twice to confirm repeatability (fresh digest per run, never collides with prior runs;
`snapshot` has no delete path, same as `fact`/`rule`/`licence`/`licence_channel`, 0021).

**Where this test lives, and why.** Not `db/tests/invariants.sql` — a single `psql`
invocation cannot open two connections. A Python test alongside the existing
`scripts/test_*_invariant.py` files, matching their established shape (real database, real
module under test imported and exercised directly, not reimplemented; `PASS`/`FAIL` per
assertion; exit 0/1).

**Wired into the existing `schema` CI job, not a fourth one.** Checked first, not assumed:
none of the four existing `scripts/test_*_invariant.py` files are referenced anywhere in
`.github/workflows/*.yml`, any Makefile target, or any shell script — they are real,
runnable regression proofs, but none is currently CI-gated at all. This is worth naming
plainly, since it means this new test is not "one more like the others" in CI terms — it is
the *first* of this file shape to be wired into CI. The `schema` job already has a live,
disposable `ledgex_ci` database (the same one `make db-test` just used) and `psycopg2`
already installed (`scripts/requirements.txt`, a dependency every sibling test needs) —
nothing about this test needs a database, object store, or dependency set the job doesn't
already have, so a new job would be pure duplication. Added as a step after `make db-test`,
before `make schema-dump` (order doesn't matter for schema-dump's schema-only diff).

Confirmed this fills a real coverage gap, not a redundant one: `run_p5_acceptance.sh`/
`run_phaseb_acceptance.sh` both bypass `phase_b`/`run_one_fetch` entirely (they load
pre-fetched fixture files directly via `--phase e`/`--phase load`), so before this package,
nothing in CI ever exercised `insert_snapshot()`/`snapshot_exists()` at all.

**The licence-contamination pattern, not reintroduced.** The new test's reference-row
seeding uses the real `LICENCE_ID`/`LICENCE_ID_ZONING` ids with the same honest,
non-fabricated `observed_at`/`cleared_by`/`cleared_at` values `db/seeds/day4_sources.sql`
itself uses (`cleared_by=NULL, cleared_at=NULL, observed_at='2026-07-31'`) — the exact
pattern `test_refresh_failure_invariant.py`/`test_zoning_ambiguity_invariant.py` already
established post-P11, copied deliberately, not reinvented. Never the P11-fixed shape
(`cleared_by='test'`, fabricated `cleared_at`/`observed_at`) that poisoned
`ledgex_schema_check` in the first place.

---

### 3. Both scripts, not unified

`ingest_parcels.py`'s and `ingest_zoning_permits.py`'s `insert_snapshot()` fixed separately,
same shape, different signatures (the latter takes `source_id`/`licence_id` as parameters,
serving multiple sources; the former hardcodes single-source module constants). Reported,
not absorbed: extracting a shared primitive here would be scope creep — `core/store.py` and
`core/exceptions.py` exist precisely because that kind of extraction was done deliberately,
from three-plus already-working call sites, not opportunistically from two functions being
touched for an unrelated fix. `core/__init__.py`'s own docstring already states the
precedent explicitly: module boundaries come after a non-ingest consumer exists to compare
against, not as a byproduct of fixing a bug in two of them.

---

### 4. Close-out

No schema change — confirmed, not assumed: `make schema-dump` against a fresh apply reports
`db/schema.sql is current — no diff.` `qa_check`/`check-boundary`: clean. Full
`run_p5_acceptance.sh` re-run end to end (exercises the normal, non-racing `phase_e`/
`load_zoning`/`load_permits` paths, confirming the control-flow change didn't regress
anything reachable from those suites): all checkpoints pass.

Finding #10 closed. P19 row added.

---

### 5. The horizon — reported, not started

With #10 closed, the open queue:

- **#11** (latent) — both loaders hardcode `JURISDICTION_ID`/`SOURCE_ID` as module
  constants, not parameters; nothing scopes by jurisdiction. Still latent — one jurisdiction
  exists today. No trigger event has occurred.
- **#16's remainder** — `parcel_lineage` split/merge and the matching-key decision still
  await their trigger event (an observed parcel split, an observed source change); the
  `pipelines/` split's precondition is met (#4 closed) but the split itself is a conscious
  decision for whoever picks it up next, not a rediscovery.
- **#23** (blocked on access) — the Supabase database named in `.env`'s stray `DATABASE_URL`
  line could not be checked for the P11 licence-contamination fix from an environment with
  no network path to it. Genuinely unknown, not assumed clean. Unchanged this package —
  still needs an environment with reachability, still needs to ask before any rebuild.
- **#27** (closed, watch item) — `ledgex_schema_check`'s migration ledger has now drifted
  behind schema not once but twice (pre-P6, six migrations; before P16, two). Both times
  fixed the moment someone ran `make migrate`/`migrate-verify`; nothing runs those
  automatically between sessions against a shared local database. Not re-opened here — named
  as a recurring risk shape worth noticing if it happens a third time, same unresolved shape
  as #25's now-closed disposable-database question but for staleness instead of
  contamination.

None of these four is a live correctness bug. The real next body of work is elsewhere.

**`make conformance`, `make test` and `make golden` all `exit 1` by design** — Phase 1's own
spec says so, and each target's own comment states plainly what's missing: `core/`,
`commerce/` and `jurisdictions/` packs don't exist yet to back them. Checked what's actually
there, not assumed:

```
core/          __init__.py, exceptions.py, store.py (333 lines total) -- no model, no
               rights, no connectors, no compose beyond scripts/compose_property_file.py
               (core/__init__.py's own docstring states this list explicitly)
commerce/      __init__.py only
jurisdictions/ does not exist
pipelines/     does not exist (#16's deferred split)
tests/         does not exist
```

`scripts/compose_property_file.py` (281 lines) already exists and is real, working,
deliberately-scoped code — not a placeholder. Its own docstring: proves the REFUSAL path
only, on purpose, because `STANDING-BLOCKER.md`'s own documented state is real and current —
every `licence_channel` row is `allowed=false`, `cleared_by`/`cleared_at`/`evidence_uri`
all `NULL`, pending counsel/owner clearance that has not happened. Every composition refuses
today, correctly, because that is genuinely true, not because the composer is unfinished in
a way more engineering would fix. `STANDING-BLOCKER.md`'s own words: "That gate is a
signature, not a commit."

**This changes what "smallest honest first step" means.** It is not "build the success
path" — building a golden fixture for a successful composition today would mean fabricating
a licence clearance that does not exist, exactly the "do not invent values to fill a
silence" rule this whole project is organized around. Two pieces of real, buildable-today
work do NOT depend on that external blocker:

1. **`core/model.py`** — I2's own required-enforcement column already names two halves,
   "DB CHECK; Pydantic model." The DB CHECK half has existed since `fact`'s own migration;
   the Pydantic half has never been built. A mechanical transcription of the schema's own
   already-decided validation rules (source_id+snapshot_id XOR method_version+lineage, etc.)
   into typed models — no new business logic, no dependency on the licence blocker, moderate
   size (roughly this session's own package scale). Cost: reading I2-I5 plus `fact`/
   `property_file`'s actual constraints closely, one report-first design pass (what fields,
   what validators, how it relates to `core/store.py`'s existing tuple-shaped inserts), then
   the models themselves plus tests.
2. **A golden REFUSED-path fixture**, generated from `compose_property_file.py`'s actual
   current output against a real parcel — the one composition outcome that is honestly true
   right now. Cost: small — the composer already exists and already produces this output;
   the work is capturing and normalizing it as a committed fixture plus the `make golden`
   wiring to check future runs against it.

The SUCCESS/PARTIAL composition path, `jurisdictions/` packs, and therefore `make
conformance`/`make test` in any real sense, stay genuinely blocked on the same external,
non-engineering dependency `STANDING-BLOCKER.md` already names — not a queue item an
engineering package can close.

**Recommended, not started**: `core/model.py` first (no blocker, foundational for
everything downstream), the golden refused-path fixture second (small, proves `make golden`'s
own wiring against something real). Both left for a future package to pick up.
