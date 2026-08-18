## P25 — Geometry-disabled Base Core: the L7 refusal path and a fourth golden fixture

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). First real product code in the
repo — report before writing.

Read in full: §1, §5 (runtime workflow), §6.6, §9's refusal table, §14 (as read in P24).

---

### 1. Refusal ordering — the design, settled from the spec, not invented

GEOMETRY_TIER_DISABLED is L7; the I6 rights gate is L8. `compose_property_file.py` had
only L8 and stopped. Does a `property_file` accumulate refusals across stages, or
short-circuit at the first one?

**Settled: accumulate, not short-circuit.** Two pieces of existing text, read together,
answer it — no spec amendment needed, because this is a correct reading of what's
already there, not new content:

- **§5's compose loop is an unconditional straight-line sequence**: "L0 → read
  current_fact → L5 rules as-of → L7 calculate → L6 exception pass → L8 rights gate over
  every touched fact → decide composed/partial/refused → persist property_file →
  return." Every arrow is a stage of work, not a conditional branch — there is no
  "if refused, stop" anywhere in this sentence, and "decide" is its own explicit step,
  positioned *after* every upstream stage including L8, not interleaved with them.
- **§6.6**: "Refusals are asserted as positively as values — a golden file that lost a
  refusal is a regression." This presupposes multiple co-occurring refusals as the
  normal shape a golden fixture should demonstrate — a single-refusal-only design would
  make "losing" one impossible to construct as a distinct failure mode from "having
  none."

The counter-reading (short-circuit) has no textual support once actually looked for:
§5's own opening line ("No stage reaches back upward") describes one-directional flow,
not early termination, and L1's own row ("no fetch is attempted, the field is omitted")
already shows a refusal continuing the pipeline at the field level rather than halting
it.

**Consequence, load-bearing and immediate**: L8's rights gate now always runs regardless
of L7's own outcome. Since `jurisdiction.geometry_tier_enabled` defaults `false` for
every jurisdiction (0002_registries.sql) and rights are still fully blocked
(STANDING-BLOCKER.md, reconfirmed below), **every real composition today produces both
refusals simultaneously** — there is no way to touch a real fact without hitting the
universal rights block, so a "geometry-disabled-only" file is not constructible without
fabricating rights clearance. This directly reshaped step 4's golden fixtures, including
the *already-committed* refused.json — see that section.

---

### 2. `core/calc.py` — refuse-only, and why

`core/calc.evaluate_geometry_dependent_conclusion(conclusion, geometry_tier_enabled)`
takes the flag as a **parameter**, never looks up a jurisdiction (I1: this file contains
no SQL, no jurisdiction id, no database connection at all). Returns `Result[None]` (I8):
refuses with `GEOMETRY_TIER_DISABLED` (already in §9 at L7, already in
`core/model.REFUSAL_CODES` — not invented here) when the tier is disabled, naming *which*
conclusion in `detail` — I10's "refuse BY NAME" requirement, proven by
`tests/core/test_calc.py`'s own positive assertion on `detail["conclusion"]`, not just
that *something* refused.

**Does not compute or persist a derived fact — deliberately, and why this is load-bearing,
not a shortcut.** The first derived fact this codebase ever writes would exercise three
untested surfaces at once: I5/0029's licence-intersection trigger, I2's derived branch
(`source_id` NULL, `snapshot_id` NULL, `method_version` NOT NULL —
`fact_provenance_complete`, 0006), and `fact_input` lineage. Building that safely, with
its own RED-first proof against each surface, is its own package. `geometry_tier_enabled
=True` raises `NotImplementedError` rather than fabricate an answer — confirmed this
branch is unreachable by any real composition today (every jurisdiction defaults the
flag false), and confirmed directly what happens if it's ever hit: a loud, immediate,
informative failure (`scripts/compose_property_file.py --parcel-apn ... ` against a
flipped-column test jurisdiction, shown in this package's own working log), not a silent
wrong answer — exactly what I13 requires. The design did not force derived facts to make
the refusal meaningful; reported and avoided, not absorbed.

`build/check_jurisdiction_names.py` re-run against the real tree: `5 file(s) under core/
scanned, no blocklisted token found.`

---

### 3. `geometry_tier_used` — the hidden bug, fixed and RED-proven

`compose_property_file.py:240` hardcoded `geometry_tier_used=false` into the INSERT
instead of reading `jurisdiction.geometry_tier_enabled` — invisible because both are
`false` for every real jurisdiction today, the identical "coincidence masks the bug
until one side moves" shape README finding #22 (P11, `permits.active`) already named
once.

**RED, reproduced first**: seeded a scratch-database jurisdiction with
`geometry_tier_enabled=true`, ran the pre-fix composer against a parcel there — the
written row showed `geometry_tier_used=false` despite the column being `true`. Fixed:
`geometry_tier_used` now binds to the real, live-read `geometry_tier_enabled` value.

**The GREEN proof needed its own construction, not a coincidence.** The `false` case
alone can never distinguish "correctly read" from "still hardcoded" — both produce
`false` by observation. The `true` case can't be exercised through the real, unstubbed
composer either, since `core/calc` deliberately raises `NotImplementedError` for it
(§2 above). Resolved with a dedicated, permanent regression test
(`scripts/test_compose_geometry_tier_used.py`, wired into CI) that stubs
`evaluate_geometry_dependent_conclusion` for this test only — isolating "does
`compose()` correctly pass `geometry_tier_enabled` through" from "does `core/calc`
correctly handle `True`", which is `tests/core/test_calc.py`'s own, separately-covered
concern. Both a `True`- and `False`-flipped jurisdiction proven to write correctly in
the same run.

---

### 4. The fourth golden fixture — actually the fourth *and* a rewrite of the first

`scripts/check_golden.py` covered 1 of §6.6's 4 classes; this makes it 2 — kept P20's
coverage-honesty discipline exactly: `MISSING_CLASSES` now names only `composed` and
`partial`, on every run, pass or fail, never folded into a blanket pass.

**Both fixtures carry two refusals each, not one — a direct, unavoidable consequence of
§1's accumulate decision**, not a design choice made separately for the new class. This
meant re-blessing the *already-committed* `refused.json`, not just adding
`geometry_disabled.json` — its own real, honest output changed the moment L7 started
running unconditionally, since its jurisdiction (`ca_san_jose`) also defaults
`geometry_tier_enabled=false`. Reported here, not slipped in quietly: `refused.json`'s
own refusal count went from 1 to 2, its `payload_hash` changed, and
`ruleset_version`'s hardcoded string was reworded (`"unevaluated -- refused before L5
Rules"` → `"unevaluated -- L5 Rules not yet built"`, since L7 now genuinely runs even
though L5 still doesn't exist — the old wording was no longer accurate).

Both `GEOMETRY_TIER_DISABLED` and `RIGHTS_BLOCKED` asserted **positively**, by code,
stage, and (for geometry) the named conclusion — not just via the full-object compare,
matching §6.6's own requirement and P20's own precedent that a comparison-logic bug
should never be able to hide a missing refusal.

**Verified, not assumed**: ran against three independent fresh databases (one `--bless`,
two comparison-mode) — all pass identically. Confirmed the mismatch detector still
works: corrupted the committed `geometry_disabled.json`, confirmed a real exit-1
`FAIL`, restored, confirmed exit-0 green again — before ever touching the composer
itself for the real break-then-revert proof below.

**Wired into CI, broken for real on the runner, reverted in the immediately following
commit** — per this repo's own deliberate-break discipline (P12), heeding its own
recorded lesson ("the revert was never written"):

- `f936232` — drifted `GEOMETRY_TIER_DISABLED`'s own message text ("3DEP gate not
  cleared" → "3DEP gate not satisfied"), the same targeted-break shape P20 used.
  Confirmed locally first: both fixtures' full-object compares fail; every positive
  presence/code/stage/conclusion-name assertion still passes.
- Pushed. `db.yml` run `32106785392` — `schema` job (`95617736082`): **failure**,
  isolated exactly to the `make golden` step — every step before it (`make schema`,
  `migrate-verify`, `db-test`, the snapshot-race test) green;
  `scripts/test_compose_geometry_tier_used.py`, `make test`, `make schema-dump` all
  correctly `skipped` since the job failed before reaching them. `p5-acceptance`/
  `phaseb-acceptance` unaffected (neither invokes the composer).
- `8869f8d` — `git revert f936232`, restoring the message text verbatim. Confirmed
  locally first (exit 0, `GOLDEN SUMMARY: PASSED`), then pushed. `db.yml` run
  `32106924248` — `schema`, `p5-acceptance`, `phaseb-acceptance` all green; `docs`/`qa`
  run `32106924357` green too.

Main never carried the break unrecoverable — revert commit exists, landed, confirmed
green on the real runner before this package closed.

---

### 5. Close-out

No migration — this package touches `core/calc.py` (new), `compose_property_file.py`,
`scripts/check_golden.py`, `scripts/test_compose_geometry_tier_used.py`,
`tests/core/test_calc.py`, and the two golden fixtures; nothing under `db/`. `make
migrate-verify` against `ledgex_schema_check` (51 migrations, `MATCH`) then a clean
`make schema-dump`, confirmed before any code changes and reconfirmed after. Both
acceptance suites, three times each, each against its own fresh database per
`CONVENTIONS.md:54` as corrected in P23 — all green, and unaffected (neither suite
invokes the composer). `make test` (167 tests) and `make golden` (2/4 classes) both
green via `make`, not just the underlying scripts directly.

Spec bumped 1.38 → 1.39, real §12 row. §1.2's `make golden` row and the Makefile's own
`golden:` comment updated to state the target's real, current guarantee (two checks, not
one; the two remaining classes named explicitly). `text/*.txt` rename trap fired again
during this package (a sixth time — CONVENTIONS.md's evidence rules already counted
five) and was caught the same way: staged blob hash compared against the working tree's
own hash before trusting `git mv` had done the right thing, not just `git status`'s
own rename inference.
