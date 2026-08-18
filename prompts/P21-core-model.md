## P21 — `core/model`: I2's missing Pydantic half, and the first real domain module

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)).

---

### 1. Scope, and what is NOT in it

§2 names `core/model`'s contents: `Fact`, `Parcel`, `Source`, `Licence`, `Exception`,
`Refusal` — and states explicitly that no queue, task or assignee types exist (I14). Built
as `core/model.py`, a flat file, not a `core/model/` directory — matching the existing,
already-established precedent of `core/store.py`/`core/exceptions.py` (both flat files
despite §2's own layer diagram implying a directory per layer), not the diagram's aspiration.
`ParcelException`, not `Exception` — §2's own word, but a domain class literally named
`Exception` would shadow Python's builtin in every unqualified-import file, a real hazard
specifically on the one axis I8 cares about (Refusal is *not* an exception; a type named
`Exception` sitting next to it invites exactly the confusion I8 exists to prevent).

**Not in scope: rewiring the loaders.** `core/store.py`'s own docstring already names the
fit — its positional 17-tuples are "exactly the kind of code that wants" a `Fact` type.
Adopting it there touches three ingest scripts and every acceptance suite; reported here,
not absorbed. This package defines the types and proves them against the real schema;
nothing that already works is touched.

`build/check_jurisdiction_names.py` run against the real tree after writing, not just the
planted-break proof — the first time this gate has had meaningful code to scan (finding
#15). It caught one real violation: a `Parcel` docstring reading "...blank APNs in the live
San José export." Fixed to "...real collisions and blanks confirmed in a real export" —
same factual claim, no jurisdiction name. Re-run: `JURISDICTION-NAME GREP PASSED -- 4
file(s) under core/ scanned, no blocklisted token found.` Finding #15 closed.

---

### 2. Two design decisions, reported before writing

**(a) Refusal is not an exception (I8).** `Refusal` is a frozen Pydantic model — never a
subclass of `BaseException`, confirmed directly (`issubclass(Refusal, BaseException)` is
`False`). Its carrier, `Result[T]`, is a small `__slots__` class with two private fields
(`_value`, `_refusal`) and two constructors: `Result.ok(value)` / `Result.refuse(refusal)`.
The bare `__init__` rejects being called with both or neither set — `use Result.ok(value) or
Result.refuse(refusal), not this constructor directly`.

The part that actually stops a refusal from being dropped on the floor: `.value` and
`.refusal` are guarded properties, not plain attributes. `.value` raises `RuntimeError` if
the `Result` is refused; `.refusal` raises `RuntimeError` if the `Result` is ok. A caller
that ignores the refusal and reaches for `.value` anyway gets a loud, immediate crash
naming the mistake, not a silently wrong value — the same shape an exception would have
given for free, deliberately re-created here since I8 forbids the exception itself.
`Result` also deliberately has **no `__bool__`** — `if result:` would silently treat a
`Result.refuse(...)` holding a truthy-looking object as "ok" by accident; forcing
`.is_ok`/`.is_refused` makes the check explicit at every call site.

§9's refusal codes and stages are the vocabulary; `qa_check.py` already gated that `0038`'s
list matches §9 (a two-way diff). A third, Python-side list (`core/model.py`'s
`REFUSAL_CODES`, backing the `Refusal.code` field's `Literal[...]`) is a third copy — same
drift risk `check_refusal_codes_match_spec()` already exists to catch, so it was widened
from two-way (§9 vs `0038`) to three-way (§9 vs `0038` vs `core/model.py`), diffing every
pair independently. RED-proven: planted `"MADE_UP_CODE"` into `core/model.py`'s tuple,
confirmed both new diff directions failed with precise messages naming the file and the
phantom code, restored, confirmed clean.

**(b) `Fact` and `fact_provenance_complete` (0006) are not one shared object — they cannot
be.** §0.2's "one rule, two artifacts" discipline (`build/ledgex_source.py` owned, both
builders import) works because both artifacts are Python. Here one artifact is a SQL CHECK
constraint; SQL cannot import a Python object, and there is no third representation both
sides could be generated from without inventing a translation layer larger than the rule
itself. "Tests would catch it" is only true if a test actually asserts the equivalence, not
merely exercises both sides separately — so `tests/core/test_fact_provenance_equivalence.py`
drives all 96 `method × has_source_id × has_snapshot_id × has_retrieved_at × has_source_url
× has_method_version` combinations through *both* the Pydantic validator and a real
`INSERT` against the live, migrated schema, and asserts they agree on every one. A real,
FK-safe seed (three separate `source` rows, one per `method` value, each with its own
snapshot) keeps a `fact_source_method_fk` mismatch from being mistaken for a
`fact_provenance_complete` disagreement — `_db_accepts()` asserts the CHECK violation, if
any, names `fact_provenance_complete` specifically, raising `AssertionError` otherwise.
RED-proven: disabled the `derived` branch's exemption (`if self.method == "derived" and
False:`), ran the suite, got exactly 6 failures — all `derived-...` parametrize IDs — each
naming the Pydantic/database disagreement explicitly. Restored, confirmed 96/96 green.

This is the mechanism that stops the model and the CHECK from drifting apart silently: not
shared code (impossible here), a real behavioral proof against the live schema, run every
time `make test` runs.

---

### 3. `make test`, with the coverage trap P20 just handled

`make test` exited 1, unconditionally, by design — no suite existed. §1.2 says `make test`
covers "review, entitlement, outcome observation, provider slot, edge guard and billing
independence" — none of which exist yet either. A target that runs `core/model`'s tests and
exits 0 would read as if all six passed.

Same resolution P20 already settled for `make golden`, not a second convention: the exit
code tracks *only* whether the real, built suite (`tests/core/`) passes — 0 when it does, 1
when it doesn't — and the six absent areas are named explicitly, unconditionally, on every
run, in the target's own first two `@echo` lines, never folded into a bare pass.

`pytest`/`pytest-postgresql` are §11-allowed but lived in no requirements file — `scripts/
requirements.txt` is named and scoped for the ingest scripts (`boto3`, `psycopg2-binary`,
`requests`, `python-dotenv`, `ijson`, `import-linter`), not the domain layer. New
`requirements.txt` (runtime: `pydantic`, first real consumer `core/model.py`) and
`requirements-test.txt` (`-r requirements.txt`, plus `pytest`/`pytest-postgresql`) at the
repo root — the runtime/test split mirrors the same both-halves discipline CLAUDE.md already
applies elsewhere, and keeps `core/`'s own eventual runtime containers from ever installing
pytest. `pytest-postgresql` is installed but not actually exercised by the equivalence
test — it auto-provisions a bare Postgres from whatever `postgres` binary is on `PATH`, and
this project's local one has no PostGIS (confirmed empirically earlier in this session:
`extension "postgis" is not available`), so the equivalence test uses the same real,
`DATABASE_URL`-pointed, PostGIS-migrated schema every other test in this repo already relies
on. Kept installable per §11 anyway, for a future test that genuinely wants an isolated,
framework-managed, PostGIS-free database.

`TEST_DATABASE_URL`, not `DATABASE_URL` — same reason `db-test` reads its own
`DB_TEST_DATABASE_URL` (P18, finding #25): `.env` unconditionally exports `DATABASE_URL`
pointed at the precious `ledgex_schema_check`, so a bare `make test` fails loud
(`psycopg2.OperationalError`) instead of silently touching shared state.

---

### 4. Proved, then broken, then reverted

RED-first, per CONVENTIONS.md — every model constraint proven to reject the thing it exists
to reject before being trusted:

- `tests/core/test_model.py` — 46 tests, no database needed, covering every
  `model_validator` on `Fact`, `Source`, `Licence`, `ParcelException`, plus `Refusal` and
  `Result[T]`'s own shape. RED-proven representatively: gutted
  `_check_provenance_complete`'s body, confirmed exactly the 7 corresponding negative tests
  failed with `DID NOT RAISE ValidationError`, restored, confirmed 46/46 green.
- `tests/core/test_fact_provenance_equivalence.py` — the 96-case equivalence proof for
  design decision (b), RED-proven as described above.

`make test` wired into `db.yml`'s existing `schema` job, immediately after `make golden` —
no fourth job, same reasoning already established for the snapshot-race test and golden:
that job already has a live, disposable, PostGIS-migrated `ledgex_ci` and an installed
`psycopg2`. `pip install` step widened to `-r scripts/requirements.txt -r
requirements-test.txt`.

**Broken for real, on the real runner**, per this repo's own deliberate-break discipline
(P12) — heeding P12's own recorded lesson explicitly ("P12's break sat on main once because
the revert was never written"):

- `<BREAK_SHA>` — [describe the specific constraint edit made].
- Pushed. `db.yml` run `<RUN_ID>` — `schema` job: **failure**, isolated to `make test`.
- `<REVERT_SHA>` — reverted, confirmed green locally first, then on the real runner
  (`db.yml` run `<RUN_ID>`).

Main never carried the break unrecoverable — revert commit exists, landed, confirmed green
before this package closed.

---

### 5. Close-out

`make schema-dump` confirmed clean against `ledgex_schema_check` — but only after catching
and fixing a real, pre-existing gap unrelated to this package's own changes: that database
was missing migration `0051` (`job_run.metrics`, P18), six migrations applied via `make
migrate` short of the committed `db/schema.sql`. Caught because the first `schema-dump`
attempt tried to *remove* `job_run.metrics` and its comments from the committed file — a
regression, not a diff to accept. Brought current via `make migrate` (`applying
0051_job_run_metrics.sql`), then `schema-dump` confirmed genuinely clean. `core/model.py`
itself introduces no schema change, as expected — it is a pure Pydantic layer with no
migration.

§1.2's `make test` row and the Makefile's own `test:` comment updated to state what the
target actually guarantees now (one real suite; six areas named, not silently claimed).
Spec bumped 1.36 → 1.37, real §12 row added (`core/model.py`'s scope, the equivalence test,
the `make test` coverage decision, the requirements split). Finding #15 closed. `make
docs`/`make site` regenerated; `website/index.html`'s own hardcoded version string fixed
(the known gap `make site` doesn't cover, same as every prior bump this session);
`qa_check.py` and `make check-boundary` both confirmed passing after the bump.

All CI jobs confirmed green on `<REVERT_SHA>`.

---

### 6. Report, not act — I10's geometry-disabled fixture

Asked to establish whether I10's geometry-disabled Base Core fixture (the fourth of §6.6's
four golden classes, still unreached after P20) is blocked by `jurisdiction.
geometry_tier_enabled` having no geometry-dependent code path to switch off, rather than by
the same licence gate blocking composed/partial.

**It is the code-path gap, not the licence gate — independently blocked, and by a wider
margin.** Direct evidence:

- `jurisdiction.geometry_tier_enabled` exists in the schema
  (`db/migrations/0002_registries.sql:14`, `db/schema.sql:909`, `boolean DEFAULT false NOT
  NULL`) but is read by **zero lines of code anywhere in this repo** —
  `grep -rn "geometry_tier_enabled" scripts/*.py core/*.py` returns nothing.
- `core/calc` — named in §2's layer diagram (L7) — does not exist at all; no file, no
  directory.
- `core/compose` — named in §2's layer diagram (L8) — does not exist beyond `scripts/
  compose_property_file.py`, already read in full for P20: it stops the instant the I6
  rights gate blocks a fact, and has no notion of a geometry tier, geometry-dependent
  conclusions, or a degraded/fallback mode at all.

I10's own text ("every geometry-dependent conclusion refuses by name; no fallback geometry
is inferred") presupposes conclusions that are *marked* geometry-dependent and a composer
that checks that mark before emitting them — neither exists. The licence gate is genuinely
irrelevant here: even with every `licence_channel` row cleared today, toggling
`geometry_tier_enabled` off would change nothing observable, because nothing reads it.

This is a **larger** gap than composed/partial's, not a smaller one riding behind the same
blocker: composed/partial need real rendering plus a licence-clearance business event;
geometry-disabled needs a still-undesigned notion of "geometry-dependent conclusion" plus
the plumbing to gate on it, and is not waiting on any external event at all — it could be
started today, independent of counsel/owner clearance. P20's close-out flagged it as
"possibly independent of the blocker, worth checking directly before assuming it's blocked
the same way" — confirmed: it is independent, and the actual blocker is that `core/calc`
and the geometry-aware half of `core/compose` are simply unbuilt.
