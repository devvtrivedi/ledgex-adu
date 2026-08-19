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

### 3. REPORT ONLY — #35's concrete design

P32 chose the option — election-as-request-parameter, primary, refusal as fallback. Not
reopened here. What follows is the design that decision never had. Nothing built, no
migration, no schema change, no code — per instruction.

#### The parameter itself

**Name**: `election`. **Values**: exactly two literal strings, `"city"` or `"state"` —
matching the two regimes Bulletin #210 page 3 names and the `.city_standards`/
`.state_standards` suffix shape finding #35's own `rule_key` already established. **Where
it enters**: `scripts/compose_property_file.py`'s `compose(conn, parcel_id, channel,
election=None, as_of=None)` — a new optional keyword parameter, the same shape `channel`
and `as_of` already use, for the same reason: request-scoped, never a `Fact`, never
persisted to the fact ledger. **Absence, named explicitly, not defaulted**: `election=None`
is a real, distinct case — a composition that touches a conclusion whose rule depends on an
election, with no election supplied, refuses by name (see refusal code, below). It never
silently resolves to `"city"` — a silent default here would be exactly the kind of
invented-to-fill-a-silence answer this project's own hard rules forbid, and would make the
file wrong for any applicant who actually meant State standards.

#### I13 — quoted verbatim, not asserted

§7's own field vocabulary, read directly, not from memory:
```
assumption.construction_cost_psf    user_assumption    number   usd   —   Request-scoped; never fact ledger.
assumption.monthly_rent             user_assumption    number   usd   —   Request-scoped; never fact ledger.
condition.roof_hvac_foundation      user_assumption    object   —     —   Separate non-fact input.
derived.economics                   derived_conclusion object   —     —   May use explicitly accepted, labelled assumptions.
```
**P32's read of this precedent was accurate — confirmed, not merely repeated.** These four
rows establish, in the spec's own words, a real category: a customer-supplied value about
*their own project*, explicitly labelled, request-scoped, "never fact ledger" — and
`derived.economics`'s own note confirms a *conclusion* is allowed to consume such a value
directly ("may use explicitly accepted, labelled assumptions"). An election between two
named regulatory pathways is the same shape exactly: not a claim about the external world
(a zoning designation, a parcel boundary) that would need retrieval, provenance, or
verification — a design choice belonging to the applicant, supplied once, at request time.
I13 forbids human *observation* from becoming a **fact** — a claim standing in for verified
world-state. An election is not a claim about the world at all. **I13 does not strain.**

#### I14 — made concrete, not merely asserted "stays clean if synchronous"

*"No stage may block on, queue for, assign to, route to or be supplemented by a person."*
**What would make this asynchronous, concretely**: accepting a request with `election`
omitted, persisting it in a `pending`/`incomplete` state, and waiting — for a follow-up
API call, a form submission, a human touching the record later — before finishing
composition. That is a queue by construction: a stage (composition) blocked on a person
supplying something after the request already started. **What the design must forbid to
stay clean**: no intermediate persisted state between "request received" and "response
returned." `election` is read *only* from the same synchronous call that already supplies
`channel`/`parcel_id`/`as_of` — if absent at that exact moment, the system does not wait;
it composes a **refused** file immediately, in the same request, and returns. Nothing is
held open. The applicant may issue an entirely new request later with the election
supplied — a new request, not a resumed one. This is the one real constraint the
implementation must honor, stated so it cannot be silently violated by a later change: a
follow-up mechanism of any kind (webhook, polling, a "check back" status) would reintroduce
exactly the queue I14 forbids.

#### Does `property_file` need a column for which election produced it?

**Yes — checked against §6.6's own normalization, not assumed.** `check_golden.py`'s
`normalize()` (read directly, P31's own reading confirmed again here) has no special
handling for any column outside `STRIPPED_FIELDS`/`TS_FIELDS`/`as_of` — everything else
falls through `normalized[key] = value`, compared literally. A new `property_file.election`
column would therefore be picked up and compared **automatically**, with zero code change
to `normalize()` itself — but §6.6's own documentation table (§6.6, the field-treatment
list) needs its own new row naming it `Retained`, the same category `ruleset_version`
already carries, for the same reason: *a different election is a different answer, not a
normalized-away detail.* Without the column, a stored `property_file` whose answer depended
on an election would be **unreproducible** — nothing in the row says which regime produced
it, so re-deriving or auditing it later would be guessing. This is the same class of gap
I11 already exists to prevent for rules generally, applied to the one input that decides
*which* rule applied.

#### The exact spec change, named concretely

Not one section — four, plus the version machinery:
- **§3 (database schema)**: new column, `property_file.election` (nullable `text`, or a new
  enum type mirroring the two literal values) — a real migration, forward-only, its own
  number.
- **§5 (runtime workflow) / compose loop description**: `compose()`'s signature gains
  `election`, documented alongside `channel`/`as_of`.
- **§6.6 (golden-file normalisation)**: one new row, `election` — `Retained`, same
  reasoning as `ruleset_version`.
- **§9 (refusal and error codes)**: a new code (see below), plus `core/model.
  REFUSAL_CODES` and `db/migrations/0048`'s own `REFUSALS_CODES_BEGIN/END` CHECK list — all
  three kept in sync by `build/qa_check.py`'s `check_refusal_codes_match_spec()`
  (`core/model.py`'s own comment names this explicitly) — a second real migration widening
  that CHECK constraint.
- **`build/ledgex_source.py`**: `SPEC_VERSION` bump (this session's own established
  1.41 → 1.42 shape); if the refusal code list changes, that constant lives in `core/
  model.py` directly, not here — `ledgex_source.py` only owns `INVARIANTS`/`MAKE_TARGETS`.
- **`text/LedgeX_Engineering_Reference_Spec_v1_41.txt` → `v1_42.txt`**: the rename itself,
  via `git mv`, **then immediately verified** by comparing the staged blob hash
  (`git ls-files -s <path>`) against the working-tree hash (`git hash-object <path>`) —
  this exact rename has staged stale content silently six times this session (P23, P25,
  P26, and by name in this instruction) whenever content was edited in the same pass as
  the move; the fix each time was `git reset <path>` then a fresh `git add <path>`, and
  that must be repeated here as a named step, not assumed safe this time.
- **`docs/LEDGEX_SPEC.md`/`docs/SPEC_INDEX.md`**: regenerated via `make docs`, never
  hand-edited — confirmed clean via `make qa` afterward.
- **`website/index.html`**: its own hardcoded `<h3>Engineering Reference Spec v1.4X</h3>`
  string, the one line `make qa`'s own "no stale version strings" check would catch if
  missed.
- **A real §12 change-record row**, dated, naming this package.

#### Refusal code — new, not reused

`RULE_UNAVAILABLE`'s own real meaning (proven by P31) is temporal: no rule effective at
this `as_of`. "No election was supplied, so which rule_key to even look up is unknown" is a
different failure a customer needs to act on differently (supply an election vs. wait for a
rule to take effect) — conflating the two into one code would make the refusal `message`
carry information the `code` itself should. **Recommend a new code**, `ELECTION_REQUIRED`,
stage `L5` (it fires before rule selection can even begin, the same stage `RULE_UNAVAILABLE`
already occupies for a related but distinct reason) — added to `core/model.REFUSAL_CODES`
and `0048`'s own CHECK list together, per that constraint's own kept-in-sync requirement.

#### Recommended build order — not started

1. Two migrations: `property_file.election` column; `ELECTION_REQUIRED` added to the
   refusal-code CHECK. Spec bump (§3, §9, §12, `SPEC_VERSION`, the `.txt` rename verified
   by hash), `make docs`/`make qa` clean.
2. `core/model.py`: `ELECTION_REQUIRED` added to `REFUSAL_CODES`.
3. `scripts/compose_property_file.py`: `compose()` gains `election=None`;
   `CONCLUSION_RULE_KEYS` generalizes from `{conclusion: rule_key}` to
   `{(conclusion, election): rule_key}` (still Shape 1 — hardcoded, one jurisdiction, now
   more entries, not a general mechanism); `election=None` on a conclusion that needs it
   refuses `ELECTION_REQUIRED`, not `RULE_UNAVAILABLE`; `property_file.election` stamped
   from the real value used (or left `NULL` when nothing election-dependent was touched).
4. `check_golden.py`'s own `run_composition` calls pass an explicit `election="city"` (the
   one real rule that exists) — predict `make golden` goes red first (the fixtures don't
   carry the new column yet), same P31-established RED-then-rebless discipline, then
   re-bless deliberately with the diff shown.
5. `§6.6`'s new row, landed in the same spec-bump pass as step 1, not deferred.
6. **A second real rule (State standards) is explicitly NOT required to prove this
   mechanism** — the refusal path (`election="state"` with no state rule seeded, or
   `election=None`) proves both new branches for real without it. Seeding it — Bulletin
   #210's own footer names a real, citable second source (*"To read about state laws on
   ADUs, see the HCD Accessory Dwelling Unit Handbook, January 2025"*), not fetched or read
   here — is its own later, separate step, the same pacing P31 already used for the first
   rule.

Every step above needs its own report-before-writing pass when it is actually built — this
section is that report for the shape as a whole, not a substitute for the schema-change
report CONVENTIONS requires at the moment a migration is actually written.

---
