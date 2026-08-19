## P32 — Close the dual-seeder before it drifts, then scope finding #35

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Step 3 reports only — nothing
is built for it.

---

### 1. Finding #36 — the rule row had two independent `DO NOTHING` seeders

Confirmed directly, not assumed from the prompt's own citation: `db/seeds/
day4_sources.sql`'s rule `INSERT` and `scripts/check_golden.py`'s own copy both ended in
`ON CONFLICT (id) DO NOTHING` — finding #32's exact shape (two independent seeders, same
primary key, `DO NOTHING`), reintroduced by P31 one package after #32 was fixed for
`source`. Byte-identical today; nothing enforced that. A citation or `pack_version` edit to
one seeder alone would pass `make golden` silently — `ruleset_version` is only
`rule_key@version`, so the gate that would otherwise catch drift cannot see it.

**Verified the trigger interaction before relying on it, not on faith, per instruction.**
`db/migrations/0013_rule_triggers.sql`'s `rule_no_destructive_update()` has two guards:
guard 1 fires only when `NEW.effective_to IS DISTINCT FROM OLD.effective_to AND
OLD.effective_to IS NOT NULL` — our row's `effective_to` is `NULL` on both sides of a
same-value `DO UPDATE`, so `NULL IS DISTINCT FROM NULL` is `false`, guard 1 short-circuits.
Guard 2 ORs fourteen `IS DISTINCT FROM` comparisons across every other column — identical
`EXCLUDED` values make every comparison `false`, the OR-chain is `false`, guard 2 doesn't
fire either. Read this way first, then run for real: a full `ON CONFLICT (id) DO UPDATE SET`
covering all fourteen columns, identical `EXCLUDED` values, against the real seeded row on a
scratch database — `INSERT 0 1`, exit code `0`, no exception. Then the other half, for real:
the identical statement with one column drifted (`citation` replaced with a planted string)
raised immediately:
```
ERROR:  I18 violated: rule ca_san_jose.adu_detached_max_height_city_standards.v1 is
immutable. Only effective_to may be set (NULL -> a date, once). A correction is a new
rule row at version + 1, never an UPDATE.
```
`DO UPDATE` does not fire on identical values (confirmed, not the STOP-and-report branch)
— fixed at the source, `scripts/check_golden.py`'s `INSERT INTO rule` now ends `ON CONFLICT
(id) DO UPDATE SET` naming all fourteen non-key columns, the same remedy P26 applied to
`check_conformance.py` for finding #32.

**This is a strictly stronger guarantee than #32's own remedy could get, and the finding
says so rather than "fixed like #32."** `source` (finding #32) has no immutability trigger
— `DO UPDATE` there just makes the second seeder's values win, silently, same as before,
only order-independent now. `rule` has `0013`'s real trigger: `DO UPDATE` here does not
merely resolve ordering, it makes any FUTURE drift between the two seeders **impossible to
land silently** — the moment either copy is edited without the other, the very next
`make golden` run raises `I18 violated` by name, loudly, correctly attributing the row.
Silent drift became a loud, correctly-named exception, not just a fixed race.

**Verified against a fresh database, both orderings, after the fix**: `make schema` → fresh
insert via `check_golden.py`'s own seed → `PASSED`; re-run on the same database (the `DO
UPDATE` path with identical values) → `PASSED`, no exception. Separately: `db/seeds/
day4_sources.sql` applied first, then `check_golden.py`'s seed on top → `PASSED`, no
exception, confirming the two seeders are now safely commutative in either order.

**The drift proof redone against `check_golden.py`'s own real execution path, not just raw
SQL** — `db/seeds/day4_sources.sql` applied first (the realistic scenario: a database that
already carries the real row), then `check_golden.py`'s own `citation` literal drifted by
one string, `make golden` run for real against it. Predicted and confirmed: the script
crashes, not merely fails a fixture comparison —
```
psycopg2.errors.RaiseException: I18 violated: rule
ca_san_jose.adu_detached_max_height_city_standards.v1 is immutable. Only effective_to may
be set (NULL -> a date, once). A correction is a new rule row at version + 1, never an
UPDATE.
CONTEXT:  PL/pgSQL function rule_no_destructive_update() line 19 at RAISE
```
Reverted; re-run on the same database, clean (`GOLDEN SUMMARY: PASSED`).

**CORRECTED BY P33 — the paragraph below was wrong, not merely imprecise. Left in place,
struck through in spirit, replaced by the corrected reasoning immediately after it, per
this project's own "correct in place, do not silently rewrite" discipline (P26/P30):**

~~Deliberately not pushed to CI, and why: `db.yml`'s `schema` job never runs `db/seeds/`
and nothing else in that job seeds a `rule` row before `make golden` does — the very first
time `make golden` runs in any fresh CI database, `check_golden.py`'s own `INSERT` hits no
conflict at all, so `ON CONFLICT`'s two branches are structurally unreachable in a single,
fresh CI run.~~ **False** — see [P33-correct-36-close-37-design-35.md](P33-correct-36-close-37-design-35.md)
section 1: `check_golden.py`'s own `main()` calls `seed_reference_rows()` **twice** per
`make golden` run (once per fixture class), so the second call hits `ON CONFLICT` on every
single CI run, confirmed empirically via `pg_stat_user_tables` (`n_tup_upd` 0→1).

**What was actually true, and is the corrected reason this exact break was still not
pushed**: the break I planted drifted `check_golden.py`'s *own single* citation literal —
both of its two calls within one run therefore agree with each other (same hardcoded
string, executed twice), so the second call's `ON CONFLICT DO UPDATE` compares identical
`OLD`/`NEW` values and the trigger correctly does not fire, exactly as it should not for a
self-consistent (if wrong) value. Pushing that specific break to CI would still not have
reproduced a failure — but not because the conflict branch is unreachable; because a
single seeder drifting against *only itself* can never disagree with itself. What CI
genuinely cannot exercise is **cross-seeder** drift — `day4_sources.sql` writing one value
first, `check_golden.py` disagreeing with it second — because CI never runs `db/seeds/` at
all, so there is never a genuinely different first writer for the second call to conflict
against. This class of proof genuinely requires a pre-seeded database, which is a
local/authorial condition, not something this project's own CI structure can exercise
without adding an artificial pre-seed
step solely to manufacture a test scenario nothing else needs — not done, for the same
"anticipated, not forced by need" reason this codebase avoids scope creep elsewhere.

---

### 2. Finding #37 — `make golden` performs an irreversible write

`0013`'s `rule_no_delete` raises unconditionally — no principal, no migration, no
superuser can ever remove a `rule` row once inserted. `make golden` now inserts one
(`check_golden.py`'s own seed, extended by P31). Every database `make golden` is run
against therefore now carries this row **permanently**. Idempotent, one known id, small
blast radius — but this is finding #28's exact class (a routine check performing an
irreversible write), and #28 was found the hard way, on a real WORM bucket, after real
fixture traffic had already accumulated 302 object versions. Found this time by reading
the trigger before it happened somewhere less recoverable, not after.

**Checked per-database, not assumed**: `ledgex_schema_check` — `make migrate-verify` run
first (required before citing it as evidence, per `CONVENTIONS.md`): 51 migrations,
`MATCH`. Then queried directly: `SELECT count(*) FROM rule WHERE id=
'ca_san_jose.adu_detached_max_height_city_standards.v1'` → `0`. **Does not currently carry
the row** — `make golden` has only ever been run against disposable scratch databases and
CI's own ephemeral containers during P31/P32's authoring, never against this one.
`ledgex_test` (`make test`'s own disposable default) does not exist locally at all right
now — nothing to check.

**The real, live risk, not a hypothetical one**: `Makefile`'s own `DATABASE_URL ?=
postgresql://localhost/ledgex_schema_check` is the bare default for every target,
including `golden`. A developer running `make golden` locally with no override — the
ordinary, unthinking way to run it — plants this row into the shared dev database on the
very next invocation, permanently, with no confirmation prompt. CI's own ephemeral
`ledgex_ci`/`ledgex_ci_p5`/`ledgex_ci_phaseb` databases are not a comparable risk: they are
destroyed with the runner at the end of every job regardless of what any trigger blocks,
the same property that already makes every other CI-only side effect in this project safe.

**Whether `make golden` should be doing this at all — the argument, not a decision.**
Every other row `check_golden.py`/`check_conformance.py` self-seed — `licence`,
`jurisdiction`, `source`, `field_definition` — is either free of any immutability trigger
or already idempotency-safe by construction (source, since #32/#36). `rule` is
categorically different since `0013`: irreversible, not merely re-correctable. A target
whose name is `check` permanently marking every database it ever touches is architecturally
surprising for a verification gate, independent of blast radius. Two real shapes, neither
built here:

- **(a) `make golden` refuses to run, loudly, when the rule row is absent** — requiring
  `db/seeds/day4_sources.sql` (the actual seed layer this row belongs to) to have run
  first. Correct in spirit — a check should verify, not create irreversible state as a
  side effect — but reopens the exact "CI never runs `db/seeds/`" gap this project already
  built a specific, working exception around (`check_golden.py`'s/`check_conformance.py`'s
  own self-seeding, for precisely the reference rows this option would now require `db/
  seeds/` to supply instead). Would need its own CI wiring decision, not a drop-in change.
- **(b) Keep `check_golden.py` as the seeder, but stop treating it as routine.** Document
  explicitly, in the target's own name or a loud one-time confirmation, that running `make
  golden` against a database for the first time is a one-way bootstrap action for this one
  row, not merely a check — closer to how `db/seeds/`'s own scripts are already understood
  by anyone who reads `db/README.md` first.

**No change made in this package** — reported for a decision, per instruction; recording
the current, real state (which databases already carry the row, and why the default
`DATABASE_URL` makes this a live risk rather than a theoretical one) is this section's own
job, not picking between (a) and (b).

---

### 3. REPORT ONLY — finding #35, the City/State election

Bulletin #210 page 3, read directly: *"YOU HAVE A CHOICE: Design the ADU following either
City Standards (Municipal Code 20.80.175) or State Standards (Municipal Code 20.80.176).
The standards cannot be mixed."* Detached ADU max height: 25 ft (City, 1st/2nd story
18/25) vs 18 ft (State, +2 ft for a pitched roof). Side/rear setback: 0 ft/4 ft by story
(City) vs a flat 4 ft (State). Materially different, real, from the primary source — not a
hypothetical. Nothing built here; every option below is scoped against this repo's own
invariants and spec text, read directly, not from memory.

#### Option A — two parallel conclusions, one per regime, both rendered

**I9, checked directly**: *"A derived conclusion never renders in the visual or structural
treatment reserved for a retrieved fact."* Two derived conclusions, both clearly marked as
derived (their own confidence, citation, rule provenance), does not on its own violate I9 —
I9 is about a derived value being dressed up as a retrieved fact, not about how many
derived values may coexist. The real strain is elsewhere.

**§5.1/§5.2, checked directly — does "composed" have a shape for this at all**: no. §5.1
names exactly three outcomes (composed, partial, refused); §5.2 names exactly three actions
a pipeline may take on an unretrievable field (omit, downgrade, refuse) — no fourth shape
for "present two mutually exclusive computed answers, unresolved, and let the customer pick."
§6.6's own fixture-normalisation table treats every field as a single value to compare, not
a branch. Building this option means inventing a payload shape nothing in this spec
anticipates, not filling in an existing one.

**§5.1's own refusal criterion, checked directly**: *"refused... so little available that a
file would mislead."* An unresolved, two-headed "answer" for the same conclusion — 25 ft
here, 18 ft there, no indication which applies to this applicant's actual project — is close
kin to exactly the misleading-file shape §5.1 already names as refusal territory, even
though the cause here is unresolved ambiguity rather than missing data. Weakest of the
three options: not outright forbidden, but it requires new spec-level design work (a branch-
shaped outcome, a new fixture class) to build something that arguably reads as *more*
misleading than a plain refusal, for a case the other two options already handle.

#### Option B — a refusal by name until an election input exists

Honest, and the cheapest to build: reuses `RULE_UNAVAILABLE` exactly as L5 already raises
it (or a more specific code naming the missing election, if that precision is wanted later)
— "no rule selected because no election was supplied" is structurally the same shape as
"no rule effective at this as-of," which L5 already proves end to end (P31). Strains
nothing — I9 is not implicated (nothing renders), I13/I14 are not implicated (nothing is
asked of a person at all). The honest question the instruction raises: is this *too*
conservative, refusing something the system genuinely could answer conditionally? On its
own, yes, slightly — the system knows both numbers, it is only the customer's own choice
that's missing, and permanently refusing rather than ever asking for that choice leaves
real, known, computable value on the table forever. Not wrong to build first (it is the
honest, always-safe fallback), but not sufficient as the only mechanism if the goal is ever
to answer this conclusion for real.

#### Option C — an election input on the request itself

**The real question, exactly as posed**: is an applicant's election of City vs. State
standards a human OBSERVATION (I13) or an input PARAMETER? Checked against real precedent
in this repo's own field vocabulary, not decided in the abstract: §7's own vocabulary
already names `assumption.monthly_rent`, `assumption.construction_cost_psf` and
`condition.roof_hvac_foundation` as `claim: user_assumption` fields, each one stated
explicitly as *"Request-scoped; never fact ledger"* / *"Separate non-fact input."* This is
the identical shape an election needs: a customer-supplied parameter about *their own
project*, never a claim about the external world requiring provenance, never persisted as
a `Fact`. I13 forbids human observation from becoming a **fact** — a claim standing in for
verified data about the world (a zoning designation, a parcel boundary). An applicant's own
design choice is not a claim about the world at all; it is a request-scoped instruction,
the same category `channel` (`paid_property_file` vs `free_snapshot`) already is today,
uncontroversially. **I13 does not strain here**, checked against real precedent, not
assumed.

**I14, checked directly**: *"No stage may block on, queue for, assign to, route to or be
supplemented by a person."* This is about the delivery **path** — a ticket, a queue, a wait
for a human to act after the request has already started. An election supplied
*synchronously*, as part of the original request (exactly like `channel` and `as_of`
already are, per `compose_property_file.py`'s own `compose(conn, parcel_id, channel,
as_of=None)` signature), introduces no wait and no second party — the compose loop still
runs "on demand, end to end automated" (§5's own words) the instant the request arrives.
**This is the distinction the instruction names as decisive, confirmed against I14's actual
text**: the same feature built as a synchronous request field is I14-clean; built as "ask
the applicant afterward and hold the file until they answer" would build exactly the queue
I14 forbids. The option is sound only if it stays synchronous — this is a real design
constraint on *how* to build it, not a reason to avoid it.

**What it would take to build, concretely, so the recommendation is not abstract**: an
`election` parameter threaded through `compose()`/`compose_property_file.py`'s CLI (and,
eventually, the real API request schema) — no schema change, no migration.
`CONCLUSION_RULE_KEYS`'s own shape generalizes from `{conclusion: rule_key}` to
`{(conclusion, election): rule_key}` (still Shape 1 — hardcoded, one jurisdiction, now two
entries instead of one, not a general mechanism). A **second real rule**, State standards,
sourced the same way the first one was (Bulletin #210's own footer already names a second
real, citable source for exactly this: *"To read about state laws on ADUs, see the HCD
Accessory Dwelling Unit Handbook, January 2025"* — not fetched or read here, named only as
evidence a real source exists to seed it from later). Election omitted on a request that
needs it → Option B's own refusal, not a new failure mode — the two options compose rather
than compete.

#### Recommendation

**Option C (synchronous, request-scoped election parameter) as the primary mechanism, with
Option B (a named refusal, not a queue) as its own honest fallback when the parameter is
omitted.** Together they need no new schema, no new outcome shape, and no invariant is
strained when built correctly — I13 is clear against the `user_assumption` precedent
already in this spec, I14 is clear as long as the parameter stays synchronous (the one real
constraint worth stating loudly so a future build of this does not quietly grow a queue).
Option A is not recommended: it is not forbidden outright, but it requires inventing a
branch-shaped outcome nothing in §5.1/§5.2/§6.6 anticipates, to deliver something closer to
§5.1's own definition of a misleading file than a resolved answer.

**Not started here.** This is a §7.4 conclusion-model decision — it deserves its own
report-before-writing package once the shape above (or a different one) is actually chosen,
the same discipline this whole session has applied to every other design decision.

---

### 4. Close-out

`make migrate-verify` against `ledgex_schema_check` before citing it — 51 migrations,
`MATCH`. Clean `make schema-dump` — no diff (no schema change in this package). `make test`
(168), `make golden` (2/4 classes, 0 failures), `make conformance` (0 failures, 3 named
gaps), `make check-boundary` (import-linter 5/5 kept, jurisdiction-name grep clean, `make
qa` clean) — all green, full local CI-order simulation, fresh scratch database. Both
acceptance suites run twice each, each against its own fresh database:
`run_p5_acceptance.sh` — `P5 ACCEPTANCE: ALL CHECKPOINTS PASSED`, twice; `run_phaseb_
acceptance.sh` — `ALL ASSERTIONS PASSED`, twice.

Deliberate-break commit discipline (CONVENTIONS' new rule, P31) applied to this package's
own proof: the finding #36 drift proof was evaluated locally, not via a CI push (argued in
section 1 — CI's own job structure cannot exercise the conflict path in a single fresh run),
so no break-then-revert commit pair was pushed for it; the local break-then-revert was
still done as a clean, isolated action (one file, one line, reverted immediately, never
committed since it was never meant to land).
