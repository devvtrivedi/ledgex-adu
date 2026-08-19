## P33 — Correct #36's false premise, close #37, then design #35 concretely

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Step 3 reports only — no
migration, no schema change, no code.

---

### 1. Correcting #36's record — it was wrong, not "clarified"

P32 recorded that the `ON CONFLICT` path is "structurally unreachable on a single fresh CI
database." **That is false.** Verified directly, not on faith, both by reading the call
chain and by running it.

**The call chain, read directly**: `check_golden.py`'s `main()` calls `check_fixture` twice
— once for `"refused"`, once for `"geometry-disabled"` (`main()`, lines 515–516). Each
`check_fixture` calls `run_composition(apn, digest)`. `run_composition` calls
`seed_reference_rows(conn)` unconditionally, first thing (`run_composition`, line 380).
`seed_reference_rows` holds the `rule INSERT ... ON CONFLICT (id) DO UPDATE`. So it runs
**twice** per `make golden` invocation — once per fixture class — against the same database,
the same row, the identical literal values both times.

**Confirmed empirically, not inferred**: a fresh scratch database, `pg_stat_user_tables`
queried before and after one `make golden` run:
```
before: n_tup_ins = 0, n_tup_upd = 0
after:  n_tup_ins = 1, n_tup_upd = 1
```
The first `seed_reference_rows()` call (via the `"refused"` fixture) does a genuine fresh
`INSERT`. The second call (via `"geometry-disabled"`) genuinely hits the `ON CONFLICT`
branch and issues a real `UPDATE` — PostgreSQL's own statistics counter records it as one,
not zero. This is the second call reaching the conflict branch, shown, not assumed.

**What is actually true, corrected**:
- The `ON CONFLICT` branch **is** reached, on every single `make golden` run, by the second
  fixture class's own seed call — including every CI run, on a completely fresh database.
- `0013`'s `rule_no_destructive_update()` therefore **fires against a real row on every CI
  run**, in the identical-values direction, and passes. This is real, standing evidence
  that this trigger is exercised by CI — nobody asserted that before P33, and it happened
  by accident (two fixture classes sharing one seed function), not by design.
- What is genuinely **not** reachable on CI is **cross-seeder drift** —
  `db/seeds/day4_sources.sql`'s copy disagreeing with `check_golden.py`'s own copy — because
  CI never runs `db/seeds/` at all (`CLAUDE.md`'s own documented rule). That was the real,
  sound reason the P32 break was not pushed to CI, and it still is — P32 misattributed that
  soundness to "the conflict path" being unreachable, when the conflict path is reached
  constantly; only the *cross-file* drift scenario is unreachable there.
- **The live failure mode the old wording hid**: if `check_golden.py`'s own two calls to
  `seed_reference_rows()` — or `check_golden.py`'s copy and `day4_sources.sql`'s copy,
  whenever both run against the same database — ever stop being identical, CI does not stay
  green. It goes red with `I18 violated`, immediately, on the very next `make golden` run.
  The prior record said this was impossible. It is not merely possible; the mechanism that
  would trigger it (the second call's own `ON CONFLICT`) already runs, silently and
  successfully, every time.

Not softened to "clarified" — the prior claim was wrong, and this section says so plainly,
per instruction.

---

### 2. Finding #37 — closed

**Current per-database state, from a fresh query, not from P32's report**: `make
migrate-verify` run first against `ledgex_schema_check` — 51 migrations, `MATCH`. Then
queried directly: `SELECT count(*) FROM rule WHERE id=
'ca_san_jose.adu_detached_max_height_city_standards.v1'` → `0`. Still clean — P32's own
authoring never ran `make golden` or `db/seeds/day4_sources.sql` against it, only disposable
scratch databases, so nothing has changed since P32 checked it. `ledgex_test` still does not
exist locally.

**Chosen: option (b), gate it** — keep `check_golden.py` as the seeder (option (a),
requiring `db/seeds/` to run first, would mean restructuring how CI seeds every reference
row this script self-seeds, not a surgical fix for the one irreversible one), but stop
treating the one irreversible write as routine. Gated by **existence, not call count** —
correct regardless of which of the two per-run `seed_reference_rows()` calls reaches it
first (§1's own correction matters here: since the second call already reaches this code
path on every run, gating on "first call only" would have been wrong).

**The gate**: before the `rule` `INSERT`, `check_golden.py` now checks whether the row
already exists. If it does not, and `GOLDEN_ALLOW_RULE_SEED` is not exactly `"1"`, it stops
before writing anything:
```
make golden is about to INSERT a rule row
('ca_san_jose.adu_detached_max_height_city_standards.v1') that CANNOT ever be removed from
this database again (0013's rule_no_delete raises unconditionally) -- this is a permanent,
one-way action, not a routine check. Refusing by default so a bare `make golden` cannot
silently plant this into a real, shared database (Makefile's own DATABASE_URL default is
ledgex_schema_check). If this database is genuinely disposable and you intend this,
re-run with GOLDEN_ALLOW_RULE_SEED=1. If it is not disposable, run
`db/seeds/day4_sources.sql` against it deliberately instead, as its own considered action,
not as a side effect of a check.
```
`db.yml`'s own `make golden` step sets `GOLDEN_ALLOW_RULE_SEED=1` — `ledgex_ci` is fresh
and disposable, torn down with the runner regardless of what `0013` blocks, so confirming
there is correct and costs nothing.

**Both directions proven, real database, not asserted**: fresh scratch database, `make
golden` with no override — fails loud (`make: *** [golden] Error 1`, the exact message
above), **zero rows written** (`SELECT count(*) FROM rule` → `0`, confirmed the gate blocks
before any write, not merely reports a warning after one). Same database, `GOLDEN_ALLOW_
RULE_SEED=1` — proceeds normally, `GOLDEN SUMMARY: PASSED`, row count → `1`. Same database,
a **third** run with no flag set at all — proceeds normally too (`PASSED`, unchanged): the
gate correctly stops blocking once the row genuinely exists, exactly as designed — this is
not "always require the flag," it is "require it only for the one truly first, irreversible
write."

---
