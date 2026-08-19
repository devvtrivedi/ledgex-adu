## P38 — Fix compose()'s undefended return contract, then report the program state

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Section 2 reports only, no
building.

---

### 1. Finding #41, recorded, then decided

**The gap.** `compose()` returns three heterogeneous shapes: `Result.refuse(...)` (line 307,
`PARCEL_REFERENCE_UNKNOWN`), `None` (line 498, rights gate passed), `str` (line 539, a row
written). `check_golden.py:454-455` binds the return to `property_file_id` and checks only
`is None` — a `Result` arriving there is truthy, flows on as if it were a uuid, and fails
downstream. Confirmed directly, not inferred: fed a real `Result` (a fabricated nonexistent
`parcel_id`, run against a real database):
```
psycopg2.ProgrammingError: can't adapt type 'Result'
```
A genuinely misleading failure — nothing in it names `parcel_id`, `PARCEL_REFERENCE_UNKNOWN`,
or `compose()` at all. Unreachable through `run_composition()`'s own current usage, since it
always creates its own fixture parcel moments before calling `compose()` — the identical
"unreachable through the only caller today" shape P35 weighed for finding #39 and P36
explicitly rejected as a safety argument, citing `job_run.schema_drift`'s one writer becoming
three (README finding #12) before anyone checked. Recorded as finding #41 first (README), not
skipped to a fix.

**Decided: (a), uniform `Result[T]`.** Checked `docs/LEDGEX_SPEC.md:74` verbatim before
relying on it: I8's own enforcement column reads `Result[T]; refusal tests`. Read against the
whole column's own style across every row (I2: `DB CHECK; Pydantic model` — two named
mechanisms, not an exhaustive list; I4: one named trigger) — this names *an* enforcement
artifact this project uses for I8, not a textually-absolute mandate that forbids any other
return shape anywhere. So option (b) is not spec-illegal on the letter of I8's own enforcement
column.

(a) wins anyway, on a sharper, structural argument: `core.model.Result`'s own guarded
`.value`/`.refusal` accessors already raise `RuntimeError` immediately, by name, if a caller
reads the wrong one without checking `is_ok`/`is_refused` first (`core/model.py`'s own class
docstring: "reading the wrong one raises RuntimeError immediately, naming which check the
caller skipped"). Under (b), that safety net does not exist automatically — every call site
must remember its own `isinstance` assertion, which is *exactly* the discipline gap that
produced finding #41 in the first place (`check_golden.py` forgot). Under (a), a future sixth
call site that forgets to check gets an immediate, informative crash instead of a silent
wrong-type flow. `Result.ok(None)` is itself invalid (`Result.__init__`'s own guard: exactly
one of value/refusal, never neither) — the "rights gate passed, nothing written" state needed
a small local sentinel, `NOTHING_COMPOSED` (`compose_property_file.py`, Shape-1-scoped, not
`core/`), not a `core/model.py` change. Cost bounded: every call site changes, but
`core/rules.py` already returns `Result` — the pattern is not new to this codebase, only
extended to a function that had deviated from it.

**Every call site audited, not just `check_golden.py`:**

| Site | Before | After |
|---|---|---|
| `compose_property_file.py`'s own `__main__` | Already checked `isinstance(result, Result)` (P37's own partial fix) — str/None cases fell through unhandled | Checks `.is_refused` / `.value is NOTHING_COMPOSED` explicitly; every branch named |
| `check_golden.py`'s `run_composition()` | `if property_file_id is None:` only — the flagged bug | `.is_refused` checked first (raises `SystemExit` naming the real refusal), then `.value is NOTHING_COMPOSED`, then unwraps `.value` |
| `test_compose_election.py` (3 sites) | Bound `pf_id = cpf.compose(...)` directly, passed straight into a raw SQL query | New `_compose_ok()` helper asserts `is_ok` and `value is not NOTHING_COMPOSED` loudly before returning `.value` |
| `test_compose_geometry_tier_used.py` (2 sites) | Same direct-bind pattern | `assert` on `.is_ok`/`.value is not NOTHING_COMPOSED` before unwrapping, loud not soft (a `check()`-style soft failure here would let a bad value flow into the SQL query right after) |
| `test_compose_parcel_refusals.py` (2 sites) | Already `isinstance(result, Result)`-based (P37 wrote this file correctly the first time) | Adapted: `isinstance` check removed (always true now, no longer the interesting assertion) — `.is_refused`/`.is_ok` checked instead |

**RED-first, against the real code, not inferred**: shown above (`can't adapt type 'Result'`).
**GREEN, same scenario, after the fix**:
```
compose() refused before writing a property_file row: PARCEL_REFERENCE_UNKNOWN: No parcel
exists with id='075ee32e-...'. This is a direct-by-id lookup, not an APN resolution --
distinct from PARCEL_NOT_FOUND (§9: 'APN not present in any parcel layer'). -- this fixture's
own parcel was just created above, so this should be unreachable; see this script's own
module docstring.
```
Correctly attributed, names the real code, names why it should be unreachable. All five real
scripts re-run against a real database after the fix: all green (section 3).

No schema, migration or spec change — a pure Python return-contract fix, confirmed by
`make schema-dump` staying clean throughout (section 3).

---

### 2. REPORT ONLY — where this program actually is

No building in this section.

#### Findings #31–#41: origin, counted, not estimated

| # | Finding | Origin |
|---|---|---|
| 31 | No `timeout-minutes` on any CI job | Repo's own (infra omission, found by a real hung run) |
| 32 | `check_golden.py`/`check_conformance.py` seeder collision | Repo's own (P20/P26's own seed code) |
| 33 | `make conformance` never proven red | Repo's own (P26's own close-out never finished; a CONVENTIONS discipline gap) |
| 34 | Seeded rule cites a bulletin, not the ordinance text | **Product** — a real external-evidence completeness gap, found from the primary source itself |
| 35 | City vs. State election, undesigned | **Product** — found from Bulletin #210's own page 3, a real regulatory-structure gap |
| 36 | Dual-seeder `ON CONFLICT DO NOTHING` drift | Repo's own — P31 reintroduced finding #32's exact shape one package after #32 was fixed elsewhere |
| 37 | `make golden`'s irreversible write | Repo's own — a consequence of P31's own migration (0013's immutability trigger) |
| 38 | Cross-seeder drift CI-unreachable | Repo's own — a direct corollary of #36, entirely CI-infrastructure |
| 39 | `election`/`ELECTION_REQUIRED` contradiction | Repo's own — a gap in P34's own schema design (0052/0053) |
| 40 | I8 exception boundary in `compose_property_file.py` | Repo's own — an audit of P31/P34's own code |
| 41 | `compose()`'s undefended return contract | Repo's own — a direct consequence of **P37's own fix**, one package prior |

**9 of 11 (findings #31, #32, #33, #36, #37, #38, #39, #40, #41) originate from this repo's
own prior packages or process gaps — corrections of work this repo itself wrote, not external
product requirements. 2 of 11 (#34, #35) originate from the product's real requirements —
both found by reading Bulletin #210 itself, not by auditing this repo's own code.** Finding
#41 is the sharpest instance: it is a correction of P37, which is itself a correction of P36,
which is itself a correction of P35, which is itself the DB-layer half of P34. Four packages
in a direct corrective chain off one feature package, the fourth correcting the third's own
fix.

Cross-checked against the package table itself, not just the findings: `git log --oneline`
from P26 onward shows exactly two packages that added product-facing capability — P31 (L5,
one real rule) and P34 (the election parameter). Every package since P34 (P35, P36, P37, P38)
has been correction or hardening of those two. P32/P33 were the identical shape one cycle
earlier, off P31.

#### Honest inventory, current

**Make targets** (`build/ledgex_source.py`'s own `MAKE_TARGETS`, the file of record):
`check-boundary` — real (I1/I15/I17/I19). `schema`/`schema-dump` — real (apply + diff).
`conformance` — real for one pack (`ca_san_jose`); mappings, rights-broadening-vs-Appendix-K,
and dependency cascades are named, not built. `test` — real for `core/model`'s own suite;
review, entitlement, outcome observation, provider slot, edge guard, billing independence
don't exist because `core/`/`commerce/` don't have that scope yet. `golden` — real for 2 of
`§1.2`'s own 4 fixture classes (`refused`, `geometry-disabled`), plus one fixture beyond that
taxonomy (`election_required`, P34); `composed`/`partial` remain unreachable —
`STANDING-BLOCKER.md`. `liveness` — real for the pack's three active sources (P28), scheduled
only, not push-gated.

**Fixture classes**: 3 real (`refused.json`, `geometry_disabled.json`,
`election_required.json`), 2 named-but-unreachable (`composed`, `partial` — both require a
real `licence_channel` clearance that does not exist).

**`STANDING-BLOCKER.md`, read directly, unchanged since it was written**: every
`licence_channel` row is `allowed = false`, `cleared_by`/`cleared_at`/`evidence_uri` all
`NULL`; `ca_san_jose.city_limits` carries `licence: unknown`, annotated "LD-1 — BLOCKS
EVERYTHING." Its own words: *"P1, P2 and P3 all make the machine correct. None of them make it
able to emit a Property File. That gate is a signature, not a commit."*

**Genuinely unbuilt, confirmed by inspection, not assumed:**
- `api/` does not exist as a directory. §11 names FastAPI + Pydantic; nothing has been built
  yet.
- `jurisdictions/ca_san_jose/conclusions.yaml` (§7.4's own conclusion model) does not exist.
  `CONCLUSION_RULE_KEYS` remains Shape 1 — one hardcoded conclusion (`"placement"`), one
  hardcoded jurisdiction — "not a general mechanism," per P31's own founder-ratified decision,
  restated at every subsequent extension (P34, P37).
- `commerce/` is an empty scaffold (`commerce/__init__.py`, six lines, no schema, no code).
  §13's own DDL (`commerce.customer`, `commerce.plan_version`, `commerce.subscription`,
  `commerce.billing_event`, `commerce.access_entitlement`) has never been migrated. Confirmed
  directly: no `commerce.` schema exists anywhere in `db/migrations/` or the live database.

#### Is there anything left that is (i) not blocked, (ii) not a correction, (iii) moves the product?

**Yes — checked both named axes, not assumed "no" the way P28 was wrong to.**

**The rule-pack axis — finding #34's own named next source.** Bulletin #210's own footer
names *"the HCD Accessory Dwelling Unit Handbook, January 2025"* as the real citable source
for State standards — not fetched or read by any package to date (P31 through P37 all
deliberately declined to seed a second rule, each one naming this exact source as the reason
to wait, not the reason to skip). Building it now would be a narrow, mechanical extension of
an already-proven pattern (P31's own precedent: one rule row, one `CONCLUSION_RULE_KEYS`
entry) — not anticipatory, since the mechanism it feeds (`election="state"`) is already built
and already fully tested against its own absence (`ELECTION_NOT_SUPPORTED`, P34–P37). Not
blocked by `STANDING-BLOCKER.md`: L5 rule selection is independently observable through the
refusal path regardless of L8's permanent rights block, the identical shape P31 already
proved for the City rule. Real, unverified risk before starting: whether the HCD Handbook's
text is actually fetchable — finding #34 already hit exactly this class of failure once for
the City ordinance text (four real, documented dead ends) before the founder supplied the
Bulletin #210 PDF directly. Worth checking before committing to this as the next package, not
assumed reachable.

**The commerce axis — checked, not skipped, per instruction.** P29 already investigated this
precisely (section (a) of that package's own fork report) and found: `STANDING-BLOCKER.md`
blocks a *real* customer, subscription, or payment integration — it does **not** block a
minimal `commerce/` slice tested against synthetic `test-*` fixtures, the identical legitimate
pattern `db/tests/invariants.sql` already uses for I18's synthetic `rule` rows. §13.1–13.3
already carry complete, ready-to-transcribe DDL (P29's own words: "the same 'spec already
drafted it, transcribe don't design' shape P26 used for `sources.yaml`/`licences.yaml`"). I15
(`commerce` may reference `public`; never the reverse) and I16 (billing independence from
Property File outcome) are, right now, enforced only by `import-linter` and prose — neither
has ever been backed by a real schema or a real test, because no `commerce.` table has ever
existed to test against. P29 named this candidate and explicitly left it unscoped ("whether
that minimal slice is worth building on its own... is a real, unscoped design question this
package does not answer"). **No package since P29 has touched it — nine packages have passed
(P30–P38) with `commerce/` unchanged.** Not blocked, not a correction, moves the product: it
would give I15/I16 their first real enforcement and stand up the billing/entitlement plumbing
this business needs before it can take a paying customer at all — plumbing that arguably
should exist *before* the signature clears, not after, so it is ready the moment it does.

**§7.4's conclusion model — real, but not ready, named and set aside deliberately, not by
omission.** A genuine unbuilt piece of the product, but building it now would mean
generalizing `CONCLUSION_RULE_KEYS` beyond Shape 1 before a second jurisdiction or a second
conclusion actually forces the shape — the exact "forced by need, not anticipated" test this
repo has applied consistently since P31 (and cited again in 0055's own migration header,
P37). Not recommended as the next move; named for completeness.

**The honest answer is not "no."** Two real, concretely-startable, non-corrective candidates
exist: the State-standards rule (small, mechanical, one known external-access risk) and a
minimal synthetic-fixture `commerce/` slice (larger, already-drafted DDL, no external
dependency, closes a longer-standing gap — P29's own candidate, untouched for nine packages).

#### Recommendation

**This specific hardening loop (election/refusal-code plumbing, P34→P38) has reached
diminishing returns and should stop as a loop.** Five consecutive packages (P35–P38) have
each found the previous one's own remaining gap; #41 closing on top of #37 closing on top of
#36 is the concrete evidence, not an impression. Continuing to audit this same surface for a
sixth time would be exactly `STANDING-BLOCKER.md`'s named risk (P29's own section (c)):
*"work that... becomes its own kind of activity that feels like progress without being the
thing actually gated."*

That does not mean "stop building." Two real candidates exist, checked, not assumed away —
**recommend the minimal `commerce/` slice over the State rule as the next package**, if the
founder wants another engineering package at all right now: it does not carry the rule's own
external-access risk (P34's own four dead ends before a human had to intervene), it closes a
gap that has sat unscoped for nine packages rather than one, and it gives two invariants (I15,
I16) their first real enforcement instead of leaving them as prose the way `STANDING-BLOCKER`
itself has sat as prose. The State rule remains real and worth doing — smaller, more
mechanical, and a good choice if the founder specifically wants rule-pack coverage finished
before anything else.

But this is, explicitly, the founder's call, not this report's: whether founder time is better
spent on either engineering candidate or on pursuing `STANDING-BLOCKER.md`'s own signature is
a resourcing question this repository's evidence cannot answer (P29 said the same, correctly,
and it still holds). This report exists to make that choice informed, not to make it.

---

### 3. Close-out

`make migrate-verify`, clean `make schema-dump` (no diff — this package changes no schema),
`make test`, `make golden`, `make conformance`, `make check-boundary` (`make qa` included), all
green on one fresh migrations-only database, real CI order rehearsed (`day4_sources.sql`
seeded before `make golden`). `make db-test`: at its existing floor (122/122; this package adds
no new invariants — a pure code-contract fix, no schema). Both acceptance suites twice each,
each against its own fresh database. All four `db.yml`/`docs.yml` jobs to be confirmed green on
the real runner, on the close-out commit.
