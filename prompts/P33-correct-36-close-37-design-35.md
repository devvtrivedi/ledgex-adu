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
