## P22 — Finding #27 reopened, then `core/model.Fact` adopted at the loaders

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)).

---

### 0. Finding #27: a recurring condition, not a one-time incident

Reopened, not re-closed: three occurrences, not two — six migrations behind before P6,
two behind (missing `0048`/`0049`) at the start of P16, one behind (missing `0051`) at
the start of P21 — and all three found incidentally, never by anything looking for the
condition itself. P16 applied the correction and no prevention; CLAUDE.md's own
both-halves rule means that was not a fix.

Argued as an evidence problem, not a tooling gap, before writing anything: `make
migrate-verify` already exists and already worked both times it was run. What was
missing both times is that nothing ran it *before* the database's state was trusted as
evidence. A CI mechanism was considered and rejected: CI always starts from an empty
database and applies every migration fresh, so a shared local database's drift is
invisible to it by construction — exactly why this keeps recurring locally and never in
CI. `CONVENTIONS.md`'s evidence rules gained the requirement instead, alongside the
planted-input rule: run `make migrate-verify` before citing any local database as
evidence, and state the result. Landed as `00fd1e2`, `prompts/`-only, its own commit.

---

### 1. `Fact.value`'s encoding contract — settled before any call site was touched

Found while investigating the adoption, not anticipated: every real call site (all
eleven) already builds `value` as a pre-encoded JSON string (`json.dumps(...)`,
`geojson_geom_param()`) before it reaches the column — the live `fact.value` is `jsonb
NOT NULL`, inserted via `%s::jsonb`. `value: Any` (P21's original typing) left that
contract undefined. Reproduced directly against a scratch database (never
`ledgex_schema_check` — see below) before deciding anything, predicting each case first:

| input | predicted | actual |
|---|---|---|
| pre-encoded JSON string | succeeds | succeeds |
| native `bool` (not `json.dumps`'d) | succeeds "by accident" | **wrong** — Postgres has no `boolean->jsonb` cast at all; `psycopg2.errors.CannotCoerce` |
| native `str`, not pre-encoded (`"hello"`) | fails | fails — `InvalidTextRepresentation`, not valid JSON text |
| native `dict`, not pre-encoded | fails | fails — `psycopg2.ProgrammingError`, can't adapt a raw dict |
| `None` | fails at NOT NULL | fails — `NotNullViolation` |

Every case already failed loudly — none was the silent "stores wrong data forever"
hazard `confidence_rule_id`/`pack_version` had. But every failure named a raw
driver/Postgres error, at INSERT time, naming no field — exactly the class of failure
this whole package's adoption is supposed to move away from.

Three shapes considered, reported before writing:

- **(1) `value` holds a native Python value; `insert_facts()` does the `json.dumps()`.**
  One encoding rule, in one place — the model describes the domain, not the wire format.
  **Blocked, not chosen**: geometry values are parsed by `ijson` as `decimal.Decimal` and
  need `infra.values.decimal_default` to serialize at all. Giving `insert_facts()` that
  responsibility means `core/store.py` imports `infra/`, and `docs/LEDGEX_SPEC.md` §2
  contradicts itself on whether `core/` may do that — one bullet forbids it, another two
  bullets later allows it, and `.importlinter` enforces neither direction. A real spec
  defect, reported as **README finding #29** regardless of which option won — not
  resolved here (that needs a spec amendment and a §12 row, not a judgement call in a
  commit message).
- **(3) a validator that normalises native values on construction** hits the identical
  Decimal/infra blocker the moment a caller's geometry dict reaches it.
- **(2) CHOSEN**: `value` stays a pre-encoded JSON string — typed `str`, not `Any` (`Any`
  on the one column that is `jsonb NOT NULL` is how `None` reached the database above) —
  with an added validator that the string actually IS valid JSON. Honest about
  describing the wire format on this one field, and costs nothing: no caller's
  serialization logic changes at all, `core/` never needs `infra/`. Re-verified against
  the same five cases with `value: str`: `True`/dict/`None` are now rejected by
  Pydantic's own `str`-type check at `Fact()` construction, naming the field; `"hello"`
  is caught by the new is-valid-JSON validator. All five are now
  `Fact()`-construction-time `ValidationError`s naming `value`, not INSERT-time driver
  errors naming nothing.

Full argument in `core/model.py`'s own module docstring, design decision (c).

---

### 2. `insert_facts()` rewritten, and what it actually enforces

`core/store.insert_facts` now takes `list[core.model.Fact]`, building the same 17-tuple
internally from named fields — one place knows `FACT_COLUMNS`' order. It imports `Fact`
(§2 permits `core/` importing `core/model`) and **refuses anything that is not actually a
`Fact`** — a bare tuple, the exact shape every append site used to hand-build, now raises
`TypeError` naming the function, not a confusing `AttributeError` deep inside the
tuple-building loop (confirmed both ways: with the isinstance check removed, the same
bad input produces `'tuple' object has no attribute 'unit'` instead).

**The twelve extras, settled explicitly, not left implicit.** `Fact` models 29 fields;
`insert_facts()` writes 17. `id`/`recorded_at` are DB-defaulted, `superseded_at` is
post-insertion lifecycle state — legitimately never written by an INSERT. The other
nine (`unit`, `layer_item_id`, `source_published_at`, `source_cadence_stated`,
`effective_to`, `conflict`, `method_version`, `ruleset_version`,
`source_asserted_as_of`) are a real choice: no append site computes a value for any of
them, and widening the INSERT to write all nine would be new scope, not this package's
fix. Left **unwritten, not silently dropped** — `_check_no_unwritten_fields()` refuses
any `Fact` carrying a non-default value in one of the nine, naming the field, before any
tuple is built. The failure mode this specifically prevents was named explicitly before
writing: a caller populates `Fact.method_version`, the model accepts it, and
`insert_facts()` silently drops it — a worse bug than the transposition this package
fixes, because the model would be actively lying about what it persists.

**What "wrong order is now unrepresentable" means, precisely, and what it does not.**
Adopting `Fact` removes the positional-tuple shape itself — there is no longer a 17-slot
tuple in caller source for a human to hand-count and mistranscribe two same-typed values
into the wrong slot, because every value is bound to an explicit keyword in the same
line it's written. That is the specific, narrow hazard this package closes, and
`insert_facts()`'s isinstance check enforces the mechanical half of it directly. It does
**not**, and cannot, catch a caller who swaps which *variable* is passed to which
keyword — `Fact(confidence_rule_id=FACT_PACK_VERSION,
pack_version=FACT_CONFIDENCE_RULE_ID)` is exactly as valid to Pydantic as the correct
call, since both are ordinary non-empty strings and nothing in either field's type
distinguishes what the string *means*. No type system without semantic tagging can catch
that, and claiming otherwise would misstate the fix.

---

### 3. Proof, not assertion — `tests/core/test_fact_adoption_hazard.py`

Against a scratch database (`p22_scratch`), never `ledgex_schema_check` — the RED half
writes a permanent, deliberately-wrong `fact` row on purpose (0017 forbids deleting it,
which is the whole point of proving the historical hazard was real):

1. **`test_historical_hazard_reproduced_on_a_bare_tuple`** — a hand-built positional
   17-tuple with `confidence_rule_id` (position 12) and `pack_version` (position 14)
   swapped, inserted via the raw SQL `insert_facts()` used to accept directly (0006:
   both `text NOT NULL`, no CHECK — verified, not assumed). Inserts cleanly, stores the
   swap permanently. This is the bug, reproduced fresh, not cited from memory.
2. **`test_insert_facts_refuses_a_bare_tuple`** — the identical tuple, through the
   adopted `insert_facts()`: `TypeError`, not a silent pass-through.
3. **`test_insert_facts_accepts_a_correctly_named_fact`** — the ordinary case, end to
   end.
4. **`test_a_swapped_value_between_two_named_fields_is_not_caught`** — states plainly,
   and proves, what adoption does NOT prevent: `Fact` constructed with the two values
   swapped between the two correctly-named kwargs is accepted and persisted, wrong data
   and all. Not a residual gap — no type system can catch this, and this test exists so
   no future reader mistakes "wrong order is unrepresentable" for "wrong values are
   impossible."
5. **`test_insert_facts_refuses_a_fact_with_an_unwritten_field_set`** — the
   `_check_no_unwritten_fields()` guard, RED-proven by temporarily disabling it
   (`DID NOT RAISE`) and restoring.

Both new `core/store.py` guards (isinstance check, unwritten-field check) RED-proven
individually by temporarily disabling each and confirming the corresponding test fails,
then restoring — full `tests/core/` suite (152 tests) green throughout.

Adopting `Fact.value`'s new encoding contract broke 16 pre-existing tests that had been
constructing `Fact(value="v", ...)` — a plain string, not valid JSON text. Fixed at the
source (`value='"v"'`) in both `tests/core/test_model.py` and
`tests/core/test_fact_provenance_equivalence.py`, not worked around; a new
`TestFactValueEncoding` class formalizes the five-case reproduction as real, committed
tests rather than leaving it only in `core/model.py`'s own docstring.

---

### 4. Adopted at all eleven sites; `ParcelException` deliberately deferred

Six sites in `scripts/ingest_parcels.py`, five in `scripts/ingest_zoning_permits.py` —
every `fact_rows.append((...))` positional tuple rewritten to `fact_rows.append(Fact(...))`
with named kwargs. `build/check_jurisdiction_names.py` re-run against the real tree after
writing: `4 file(s) under core/ scanned, no blocklisted token found` — unaffected, since
the source-property-to-`field_key` mapping stays in `scripts/*.py`, unmoved (I1);
`core/store.py` still knows nothing about what any field means for any real place.

**`insert_exceptions` (`core/exceptions.py`) deliberately NOT adopted in this package** —
a real, analogous hazard (`0010_exceptions.sql`: `detector_key`/`detector_version` both
`text NOT NULL`, no CHECK), but a different scope call, made explicitly rather than left
unmentioned: `insert_exceptions()` has 4 call sites across 3 files (`phase_e`,
`load_zoning`, and both detectors in `scripts/flag_invalid_geometry.py` — a script this
package never otherwise touches), against `Fact`'s 11 sites in the 2 files already being
rewritten; and unlike `fact`, `parcel_exception` carries no whole-row immutability
trigger (0017/0040 are `fact`-specific) — a transposed `detector_key`/`detector_version`
is theoretically correctable later by a migration `UPDATE`, where a transposed fact
column is not. Real hazard, smaller stakes, separate package — recorded in
`core/exceptions.py`'s own docstring, not left implicit.

---

### 5. Two findings discovered along the way, reported not fixed

- **README finding #29** — `docs/LEDGEX_SPEC.md` §2's self-contradiction on whether
  `core/` may import `infra/` (§1 above). Independent of which encoding option won;
  flagged so it isn't rediscovered from scratch.
- **README finding #30** — `scripts/run_p5_acceptance.sh` is not actually safe to rerun
  twice against the same already-populated database:
  `scripts/check_p5_acceptance.py:220-224` hardcodes a first-run assumption (parcel
  `23712112`'s `permits.active` fact is asserted to be a brand-NEW fact after phase B,
  true only the first time). Found while verifying this package's own adoption, isolated
  as pre-existing and NOT caused by it: reverted to pre-P22 code via `git diff > patch` +
  `git checkout --` (confirmed via `grep` that the isinstance guard this package adds was
  genuinely absent), reran the identical two-invocations-same-database sequence against
  a fresh scratch database — the identical failure occurred on unmodified code. This
  package's own suite verification used three independent fresh migrations-only
  databases instead (one run each), satisfying CONVENTIONS.md's "run every suite twice
  [...] plus once migrations-only" without tripping the unrelated bug.

---

### 6. Close-out

`make migrate-verify` run first, per the rule this package's own step 0 committed:
`ledgex_schema_check` — `MATCH`, 51 migrations verified. `make schema-dump` against it
afterward: `db/schema.sql is current — no diff` — this package is application-layer only,
as expected. `core/store.py`'s stale claim ("fails at INSERT time with a type-mismatch
error naming a position" — true only for differently-typed positions) corrected in its
own rewrite; `core/exceptions.py:16` and `scripts/ingest_zoning_permits.py:24`'s
now-inaccurate "same tuple-not-type shape" descriptions corrected to state the real,
current, and deliberately different shapes of the two functions.

Both acceptance suites run three times each, independent fresh migrations-only
databases (not twice against one, per finding #30 above) — all green.
`tests/core/` (152 tests) green via `make test`. `make check-boundary` (import-linter,
jurisdiction-name grep, `qa_check.py`) green throughout.

Findings: #27 reopened as recurring (§0). #29 and #30 opened, reported not fixed (§5).
No new finding closed by the adoption itself — the transposition hazard `README` never
had its own numbered row; it was named directly in this package's own instructions,
proven, and fixed.
