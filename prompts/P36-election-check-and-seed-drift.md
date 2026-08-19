## P36 — Build finding #39's CHECK, decide #38, record the I8 boundary

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Section 3 reports, does not build.

---

### 1. Build #39's CHECK

**Is this premature? Decided explicitly, not inherited from P35's own recommendation.**
Finding #11 (loaders not jurisdiction-scoped) is this repo's own precedent for a latent,
single-consumer gap staying open, "forced by need, not anticipated" — the same question
genuinely applies here, since finding #39 itself says the contradiction is unreachable through
`property_file.election`'s only writer today. The two cases are not the same shape on
inspection:

- **#11's fix requires real, un-testable-today design work**: a second jurisdiction that does
  not exist, deciding how loaders should be parameterized, with no way to prove the
  parameterization correct against real data until that jurisdiction is real. Building it now
  would be speculative in the way CONVENTIONS warns against.
- **#39's fix is a mechanical generalization** of a pattern this schema already has three
  working instances of (0038/0048/0053's own `refusals_codes_valid`), fully testable *right now*
  against the one real writer that exists, with both the violating and the legitimate shapes
  constructible today. There is nothing to anticipate — the CHECK enforces a fact that is
  already, provably, always true of every row `compose()` can produce.
- **This repo has already lived through the counter-scenario for this exact shape**:
  `job_run.schema_drift` (README finding #12) had one documented meaning and, in practice, one
  real writer for a long time — by the time 0051 investigated, two real writers were stretching
  it to carry something it was never meant to, undetected until someone went looking.
  `property_file.election` is in the identical position today. That precedent, not #11's, is
  the one that transfers.

**Decided: build, now.**

`db/migrations/0054_property_file_election_refusal_consistent.sql` adds
`property_file_election_refusal_consistent(election text, refusals jsonb)` — `LANGUAGE sql
IMMUTABLE`, the identical single-row shape `refusals_codes_valid()` already is — backing a
`CHECK`, not a trigger (nothing here needs `OLD`/`NEW`; both exclusions read only the current
row). Enforces exactly the two narrow, structurally-robust one-way exclusions P35 designed, and
explicitly **not** the full biconditional, which P35 showed holds only by the coincidence that
"placement" is currently the sole always-election-dependent conclusion — the finding #22 shape.
The migration's own header states this in full, including the explicit instruction not to widen
it later just because it happens to keep passing.

**Existing rows re-queried, not assumed clean from P35's own count.** `make migrate-verify`
first: `ledgex_schema_check`, 53 migrations, `MATCH`. Still 7 `property_file` rows, 2 with
non-NULL `election`, 0 violating either exclusion — unchanged since P35 (nothing between P35 and
this migration wrote to that database; every intermediate check in both packages ran against
disposable scratch databases). The ~30 other databases reachable on this host (`p22_*`–`p26_*`,
leftover scratch state from packages predating 0052/0053 entirely) were checked for the
`election` column's mere existence, not assumed absent — none have it, so none can violate a
constraint on a column they don't have.

**RED-first, both directions, plus the legitimate combinations proven too** (T98's own lesson):
on a fresh scratch database (`ledgex_p36_scratch`, all 54 migrations applied), four plants:

```
election='city'  + ELECTION_REQUIRED     -> ERROR: new row ... violates check constraint "property_file_election_refusal_consistent"
election IS NULL + ELECTION_NOT_SUPPORTED -> ERROR: new row ... violates check constraint "property_file_election_refusal_consistent"
election IS NULL + ELECTION_REQUIRED      -> INSERT 0 1   (legitimate, still accepted)
election='state' + ELECTION_NOT_SUPPORTED -> INSERT 0 1   (legitimate, still accepted)
```

**Four new invariants, T99–T102, floor raised 115 → 119**, mirroring the four plants above
exactly (T99/T100 negative, exact constraint name asserted; T101/T102 positive controls). Suite
re-run clean at 119/119 (see section 4).

**Spec bump — corrected in place, not silently.** First concluded "no spec bump needed," reasoning
that §3 narrates `property_file`'s DDL history in prose per migration without enumerating every
constraint name individually. That reasoning missed a real, mechanical requirement:
`build/qa_check.py`'s `check_spec_references_migrations()` requires every file in
`db/migrations/` to be named at least once in the generated spec text, independent of how much
prose accompanies it. Running `make check-boundary` caught this directly —
`LEDGEX_SPEC.md: migration(s) on disk but never referenced in the spec:
0054_property_file_election_refusal_consistent.sql` — before this package closed out, not after.
Fixed: `SPEC_VERSION` 1.42 → 1.43, `text/LedgeX_Engineering_Reference_Spec_v1_43.txt` (renamed,
verified by hash before committing), a new §3.12 paragraph for 0054 mirroring 0052/0053's own
style, a new §12 row, `website/index.html`'s own hand-authored version string bumped, `make docs`
+ `make site` regenerated, `make qa` clean. `make schema-dump` regenerated and clean either way
(section 4).

---

### 2. Finding #38 — built

Built, per instruction, no longer scope creep. `.github/workflows/db.yml`'s `schema` job gains a
new step, `db/seeds/day4_sources.sql`, positioned strictly after `make db-test` and
`scripts/test_snapshot_race_invariant.py` (both remain genuinely migrations-only) and strictly
before `make golden`.

**What changes for steps after the seed step, checked, not assumed.** The exact CI order was
rehearsed locally end-to-end on one fresh database (`ledgex_p36_ci_sim`, 54 migrations, then
`make db-test` + the snapshot-race check unseeded, then `db/seeds/day4_sources.sql` applied,
then every remaining step in its real CI order):

- `make golden` — **unchanged**, 0 failures, all three fixtures, identical normalized output.
  Verified by re-running the exact comparison, not merely re-running the target and reading
  `PASSED`. Reasoned through and then confirmed empirically why: `compose()` never reads the
  `source` table at all; the columns it does read (`licence_channel.allowed`,
  `jurisdiction.geometry_tier_enabled`, `rule`) either agree between the two seeders by
  construction (both jurisdiction inserts omit `geometry_tier_enabled`, defaulting `false`;
  `rule`'s own `ON CONFLICT DO UPDATE`, finding #36's fix, makes either seed order converge on
  identical values) or produce the identical refusal either way (day4's `licence_channel` rows
  are all explicit `allowed=false`, matching the *absence*-is-also-`false` default-deny
  `check_golden.py` alone already relied on — same code, same stage, same message either way).
- `scripts/test_compose_geometry_tier_used.py`, `scripts/test_compose_election.py` —
  **unchanged**: both use their own synthetic `test_p25_geom_*`/`test_p34_election_*`
  jurisdictions, never touched by `day4_sources.sql`.
- `make test` — **unchanged**, 168 passed (pure Pydantic/synthetic-jurisdiction tests, no
  dependency on the real `ca_san_jose` seed).
- `make conformance` — **unchanged**, 0 failures. Already immune to seed ordering by
  construction: `check_conformance.py`'s own `source` seed uses `ON CONFLICT DO UPDATE` (README
  finding #32's fix) specifically so its own values always win regardless of what ran first.
- `make schema-dump` — **unaffected**, confirmed clean before and after (schema-only diff, never
  sees row data).
- The `p5-acceptance`/`phaseb-acceptance` jobs use their own, separate databases entirely and
  are untouched by this change.

**The actual point, proven, not merely "harmless."** With `day4_sources.sql` applied, a
deliberately drifted `rule.citation` — the exact `INSERT ... ON CONFLICT DO UPDATE` shape
`check_golden.py`'s own seed uses — now raises for real:

```
ERROR:  I18 violated: rule ca_san_jose.adu_detached_max_height_city_standards.v1 is immutable.
Only effective_to may be set (NULL -> a date, once). A correction is a new rule row at
version + 1, never an UPDATE.
```

This is finding #36's own cross-seeder-drift gap, genuinely reachable in CI for the first time.

**`db/tests/invariants.sql`'s own "CI (always migrations-only, no seed)" language — quoted, then
corrected, not invalidated.** Two occurrences, both about `test_skipped`/S1 specifically:

> "meaning CI (always migrations-only, no seed) ran S1 zero times yet recorded it passing"

> "it only RUNS when db/seeds/day4_sources.sql has been applied, and CI never applies seeds
> (this suite's own standard path is migrations-only)"

Neither describes `make db-test`'s own floor or its 115/119-test coverage — both are about S1's
own conditional skip. Checked directly whether the seed step breaks either claim: **no**, because
`make db-test` runs strictly *before* the new seed step in `db.yml`'s own step order — every CI
invocation of `make db-test` itself still sees a migrations-only database, S1 still does not run
there, and the floor is unaffected (confirmed empirically, section 4: unseeded run — 119 pass,
S1 skipped; a separate, seeded-first run — 120 pass, S1 runs for real, still `>= 119`). What *was*
true and is no longer true is the broader, job-level reading of "CI never applies seeds, full
stop" — corrected in place, not silently rewritten, in both comments: the claim is now scoped to
`make db-test`'s own invocation specifically, with an explicit note that `db.yml`'s `schema` job
as a whole now does apply `db/seeds/day4_sources.sql`, just after `db-test` has already run.

**Finding #36 no longer describes cross-seeder drift as CI-unreachable** — its README row is
updated to record that #38 closed the remaining gap.

---

### 3. RECORD ONLY — the I8 boundary, and whether it's a class

`compose_property_file.py:225–231` raises `ValueError` for an `election` outside
`KNOWN_ELECTIONS`. I8 (§1): "Refusal is a typed return value, not an exception." Today this is
correct, and the code's own comment argues why: a programmer error, no `api/` exists, `compose()`
is called only from the CLI and `check_golden.py`. But §11's stack names FastAPI + Pydantic and
§2's import rules already reserve `api/` — the moment `compose()` is reachable from a request
body, an invalid `election` becomes customer input, and this `raise` sits exactly at the boundary
I8 governs. The code's own error message ("a caller/programmer error today... not a customer
input this function refuses gracefully") concedes the assumption is time-bound, not permanent.

**Checked whether this is a class, not one line** — every `raise` in `compose_property_file.py`
and `core/`:

**Same class — validates what would be request-derived input, once `api/` exists, inside or
adjacent to `compose()` itself:**
- `compose_property_file.py:225` (this one) — `election` outside `KNOWN_ELECTIONS`.
- `compose_property_file.py:261` — `raise SystemExit(f"no parcel with id={parcel_id!r}")`,
  *inside* `compose()` itself. The most significant of the four found: §9 already names
  `PARCEL_NOT_FOUND` as a real refusal code for exactly this situation — this is not even a
  missing-vocabulary problem, only a missing-refusal-instead-of-exception problem.
- `compose_property_file.py:333` — `raise SystemExit(...has no current facts...)`, also inside
  `compose()` itself.
- `compose_property_file.py:187`/`190` — `resolve_parcel_id_by_apn`'s own "no parcel with apn"
  and "ambiguous apn, N candidates" `SystemExit`s. CLI-only today (never called by `compose()`
  itself, only by `__main__`), one step further from the boundary than the other three, but the
  same shape: validates what would be request-shaped input (an APN) and raises instead of
  refusing.

**Checked and excluded — a different class, not customer-facing even once `api/` exists:**
- `core/store.py:107,133` (`insert_facts`'s own `ValueError`/`TypeError` shape guards) and
  `core/exceptions.py:101,123` (`insert_exceptions`'s own, identical shape) — both are internal
  ingest-pipeline caller contracts. Neither function is ever called with customer-supplied data:
  I13 forbids a `Fact`/`ParcelException` from ever being constructed from human/request input in
  the first place (§6.7's own annex: "A support request is not a back door for human facts").
  These guard against a *bug in this repo's own ingest code*, not a malformed customer request.
- `core/calc.py:59` (`conclusion not in GEOMETRY_DEPENDENT_CONCLUSIONS`) — `conclusion` is always
  a hardcoded literal (`"placement"`) supplied by `compose_property_file.py` itself, never
  customer-selected; even under a future `api/`, a request supplies `parcel_id`/`channel`/
  `election`, not "which conclusion to evaluate" by name. An internal contract guard between two
  trusted modules, not an I8 boundary.
- `core/calc.py:74` (`NotImplementedError` for `geometry_tier_enabled=True`) — an explicitly
  documented, deliberate "not built yet" stub (P25's own extensive docstring), a different
  concern entirely from input validation.
- `core/model.py`'s many `ValueError`s inside `@model_validator`s (`Fact`/`Source`/
  `ParcelException` internal consistency invariants) — Pydantic's own validation mechanism is
  inherently exception-based by design, and every one of these validates a domain object only
  ever constructed by trusted ingest/rule/detector code, never directly from a customer request
  body, for the same I13 reason as `core/store.py` above.

**This is a class, four members, not one line** — all four confined to
`scripts/compose_property_file.py`, all four sharing the identical shape: a value that is a
programmer/CLI-caller responsibility today, reachable from customer input the moment `compose()`
is called from a request handler instead of the CLI or `check_golden.py`. Recorded with the same
latent-but-named treatment finding #11 gets — **not fixed**: there is no `api/` to fix it
against, and building one now, or restructuring `compose()`'s own error handling in anticipation
of one, would be exactly the anticipation CONVENTIONS warns against. This becomes real work the
day `api/` starts taking a request body, not before.

---

### 4. Close-out

`make migrate-verify` before every local-database claim above (`ledgex_schema_check`, 53
migrations, `MATCH`, unchanged since P35). Clean `make schema-dump` on a fresh migrations-only
database after 0054 (diff reviewed: exactly the new function, its `COMMENT`, and the new
`CHECK` constraint on `property_file` — nothing else). `make test` (168 passed), `make golden`
(0 failures, all three fixtures), `make conformance` (0 failures), `make check-boundary` (5
contracts kept, `make qa` clean) all green on one fresh migrations-only database. `make db-test`:
**119/119**, 1 known gap (I5c, pre-existing), 1 skip (S1, pre-existing, unseeded path) — exit 0.
S1's own behavior confirmed both ways, empirically: unseeded (matching CI's own `db-test`-before-
seed order) → 119 pass, S1 skipped; day4-seeded-first (a local, non-CI scenario) → 120 pass, S1
runs for real, still `>= 119`. Both acceptance suites run twice each, each against its own fresh
database (four scratch databases, never the same database twice): `run_p5_acceptance.sh` — ALL
CHECKPOINTS PASSED, both runs; `run_phaseb_acceptance.sh` — ALL ASSERTIONS PASSED, both runs —
neither suite touches `property_file.election`, `refusals`, or `db/seeds/day4_sources.sql`, so
this is a non-regression confirmation.

All four `db.yml`/`docs.yml` jobs to be confirmed green on the real runner, on the close-out
commit — this run is also the first real CI exercise of the new seed step and the new
`property_file_election_refusal_consistent` constraint together.
