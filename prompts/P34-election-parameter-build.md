## P34 — Build #35: the election parameter, refuse-first

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). P33's own six-step build order
(section 3 of [P33-correct-36-close-37-design-35.md](P33-correct-36-close-37-design-35.md))
is this package's plan. Report before writing at each schema change, as CONVENTIONS itself
requires.

---

### 0. Two decisions, reported before writing

**(a) A third refusal code, not a collapse.** `CONCLUSION_RULE_KEYS` generalized to
`{(conclusion, election): rule_key}` creates two genuinely different "no rule_key" causes:

- `election` absent entirely -> the composer never got told which regime at all.
  **`ELECTION_REQUIRED`** (P33's own recommendation, unchanged).
- `election` supplied but `(conclusion, election)` has no dict entry -> the composer *was*
  told, but has never been taught a `rule_key` for that pairing, independent of any `as_of`.
  **A third code: `ELECTION_NOT_SUPPORTED`**, stage L5.

Collapsing case 2 into `RULE_UNAVAILABLE` would be the exact "subtler lie" shape
[P31-l5-refuse-first-one-real-rule.md](P31-l5-refuse-first-one-real-rule.md) was warned off:
`RULE_UNAVAILABLE` asserts a `rule_key` *was* looked up against `rule` and no row matched the
effective window -- a temporal claim, backed by a real query. `ELECTION_NOT_SUPPORTED`'s case
never reaches that query at all -- a static composer-capability gap, closest in shape to
`SOURCE_DEFERRED`'s "real and known but out of Phase 1 scope," applied to L5 instead of L1.
Step 6 needs this distinction for real: `election="state"` with no state rule seeded must read
as "this composer doesn't support state yet," not "no rule was effective today," which would
be false and would silently self-correct the moment any state rule is ever seeded for an
unrelated reason.

**A correction to P33's own design report, found while implementing it.** P33 named the
refusal-code sync target as "`db/migrations/0048`'s own `REFUSAL_CODES_BEGIN/END` list."
Checked directly before writing anything, not assumed: `build/qa_check.py`'s
`check_refusal_codes_match_spec()` hardcodes
`REFUSAL_CODE_MIGRATION = MIGRATIONS_DIR / "0038_refusals_code_check.sql"` and has *never*
pointed at 0048 -- confirmed by grep (`REFUSAL_CODES_BEGIN`/`END` exists only in 0038) and by
0048's own header, which says so explicitly ("build/qa_check.py's check_refusal_codes_match_spec
reads ITS markers from 0038's own file text specifically ... never re-reading any later
migration"). 0048 widened the NULL/shape validation but deliberately kept the vocabulary
byte-identical *specifically so this pointer would never have to move*. This is the first
migration to genuinely widen the vocabulary since 0038 existed -- the pointer has to move now,
onto the migration that actually carries the new codes, since 0038 itself is forward-only and
can never be edited to describe a vocabulary it predates. Fixed in the same commit as the
migration that needed it (0053), not deferred.

**(b) One new golden fixture, not two.** `election=None` (-> `ELECTION_REQUIRED`) is the
operationally important path: every existing caller of `compose()` hits it the moment this
parameter exists, since it is optional and currently unpassed everywhere except the golden
script itself. It also produces a genuinely new *shape* -- three co-occurring refusals
(`ELECTION_REQUIRED` L5 + `GEOMETRY_TIER_DISABLED` L7 + `RIGHTS_BLOCKED` L8) in one file, the
same "richer accumulated refusal" precedent P25 set when geometry-disabled was added. Worth
locking down end-to-end: a third fixture, `election_required`.

`election="state"` (-> `ELECTION_NOT_SUPPORTED`) is mechanically the *identical* branch (skip
the `rule` lookup entirely, append a refusal) with a different code substituted -- a
pytest/script-level proof against `compose()` directly is genuinely sufficient; a fourth
fixture would be near-byte-identical to the third except for one code string, testing the same
mechanism twice. `scripts/test_compose_election.py` (real database, wired into `db.yml`) proves
it instead, alongside `election="city"` reaching a *real* `rule` query (`RULE_UNAVAILABLE`,
against a synthetic jurisdiction with no rule seeded) and an invalid election value raising
immediately -- three distinct code paths, proven distinct, not one path with three labels.

`election_required` is deliberately **not** counted as a fifth member of SPEC.md sec 1.2's own
composed/partial/refused/geometry-disabled taxonomy (`MISSING_CLASSES` stays
`["composed", "partial"]`, unchanged) -- it is a real, additional fixture the taxonomy
predates. Coverage is reported as both counts, not folded into one, everywhere this package
touches: `scripts/check_golden.py`'s own `main()` output, its module docstring, sec 6.6's own
P34 implementation note, and `build/ledgex_source.py`'s `MAKE_TARGETS` "make golden" row.

---

### 1. Two migrations

**`db/migrations/0052_property_file_election.sql`** -- `property_file.election` (nullable
`text`, `CHECK (election IS NULL OR election IN ('city', 'state'))`). NULL is a real, handled
case (CONVENTIONS' "NULL inside a constraint silently disables it" rule, findings #8/#19
precedent) -- it means no conclusion in this file depended on an election at all, never
"unknown," never a silent default to city; a composition that *does* need an election with none
supplied refuses `ELECTION_REQUIRED` before this row is ever written, so NULL here can never
mean "the applicant should have picked one and didn't." Full argument, including why a column
(not just a request parameter) is needed -- checked against `check_golden.py`'s own
`normalize()`, not assumed, per P33's own instruction -- in the migration's own header.

**`db/migrations/0053_refusal_codes_election.sql`** -- widens `refusals_codes_valid()` by two
codes (`ELECTION_REQUIRED`, `ELECTION_NOT_SUPPORTED`), DROP+ADD on
`property_file_refusal_codes_known_election` (0048's own re-validation reasoning), and moves
`build/qa_check.py`'s `REFUSAL_CODE_MIGRATION` pointer here -- see section 0's own correction
above for why. `core/model.py`'s `REFUSAL_CODES` tuple updated to match (now 21 codes, not 19);
`tests/core/test_model.py::test_all_19_spec_codes_individually_accepted` renamed to
`test_all_spec_codes_individually_accepted` (it already iterated the real tuple, not a
hardcoded count -- only its own name was stale).

Applied to a fresh, freshly-migrated scratch database (`ledgex_p34_scratch`, PostGIS 3.4,
Postgres 16, matching `db.yml`'s own `postgis/postgis:16-3.4` image) and to
`ledgex_schema_check` (`make migrate-verify` run first both times -- clean, 51 -> 53 migrations,
`MATCH`). `refusals_codes_valid()` confirmed directly to accept both new codes and still reject
an invented one:

```
SELECT refusals_codes_valid('[{"code":"ELECTION_REQUIRED"}]'::jsonb) AS ok1,
       refusals_codes_valid('[{"code":"ELECTION_NOT_SUPPORTED"}]'::jsonb) AS ok2,
       refusals_codes_valid('[{"code":"BOGUS_CODE"}]'::jsonb) AS bad;
 ok1 | ok2 | bad
-----+-----+-----
 t   | t   | f
```

`build/qa_check.py`'s own sync check confirmed catching the drift *before* the spec text was
updated (proving the pointer move actually works, not merely that the migration compiled):

```
0053_refusal_codes_election.sql: has refusal code(s) §9 does not name: ELECTION_NOT_SUPPORTED, ELECTION_REQUIRED
model.py: has refusal code(s) §9 does not name: ELECTION_NOT_SUPPORTED, ELECTION_REQUIRED
```

and clean after (section 5, below).

---

### 2-3. `scripts/compose_property_file.py`

`CONCLUSION_RULE_KEYS` generalized from `{"placement": "adu.detached.max_height.city_standards"}`
to `{("placement", "city"): "adu.detached.max_height.city_standards"}` -- still Shape 1
(hardcoded, one jurisdiction, now also one election-vocabulary; not a general mechanism).
`("placement", "state")` is deliberately absent, not stubbed -- `.get()`'s own `None` return on
a missing key is exactly what `ELECTION_NOT_SUPPORTED` refuses on.

`compose(conn, parcel_id, channel, election=None, as_of=None)` -- `election` is request-scoped,
read once, never persisted to the fact ledger (I13). `KNOWN_ELECTIONS = ("city", "state")`
validated at the Python boundary; an out-of-vocabulary value raises `ValueError` immediately
(a caller/programmer error today -- `compose()` is called directly, never from an untrusted
request body -- not a customer input this function refuses gracefully), rather than reaching
`property_file_election_known`'s DB CHECK.

Three distinct L5 outcomes, each reached by its own code path, none falling through to another:

```
election is None              -> ELECTION_REQUIRED,     no `rule` query attempted at all
election given, no dict entry -> ELECTION_NOT_SUPPORTED, no `rule` query attempted at all
election given, entry found   -> select_effective_rule() runs for real, may itself
                                  refuse RULE_UNAVAILABLE (a different, temporal claim)
```

`ruleset_version` and `property_file.election` both reflect exactly which of the three
happened, honestly, in every case -- `election` is a direct echo of the raw parameter
(`None`/`"city"`/`"state"`), satisfying "NULL when nothing election-dependent was touched" and
"the real value used" in one simple rule, with no separate "was it used" judgment needed.

**I13 -- confirmed, not merely repeated.** §7's own field vocabulary, read directly:

```
assumption.construction_cost_psf    user_assumption    number   usd   —   Request-scoped; never fact ledger.
assumption.monthly_rent             user_assumption    number   usd   —   Request-scoped; never fact ledger.
condition.roof_hvac_foundation      user_assumption    object   —     —   Separate non-fact input.
derived.economics                   derived_conclusion object   —     —   May use explicitly accepted, labelled assumptions.
```
P32's read of this precedent (quoted in full in P33 section 3) holds: an election is the
applicant's own design choice about their project, request-scoped, never a claim about the
world needing retrieval or provenance. I13 forbids human *observation* becoming a **fact**; an
election is not a claim about the world at all.

**I14 -- stays clean because nothing is held open.** `election` is read only from the same
synchronous call that already supplies `channel`/`parcel_id`/`as_of`. Absent at that exact
moment, the system does not wait -- it composes a refused file immediately, in the same
request, and returns. A follow-up is always a brand-new request, never a resumed one. No
intermediate persisted "pending" state exists anywhere in this change.

---

### 4. `scripts/check_golden.py` -- RED, then rebless

Predicted before running, per CONVENTIONS' "predict before running": adding `property_file.election`
would make `refused`/`geometry_disabled`'s committed fixtures fail their full-object compare
(new key, not yet in the committed JSON), and `election_required.json` would fail on "fixture
file exists" (it doesn't yet). Confirmed exactly that, on a fresh scratch database
(`ledgex_p34_scratch`, all 53 migrations applied, nothing else):

```
GOLDEN SUMMARY: FAILED (3 failure(s)).
```
(one full-object mismatch each for `refused`/`geometry-disabled`; `election-required`'s own
"golden fixture file exists" check failing outright).

Re-blessed deliberately, diff shown in full, nothing else touched:

```diff
--- a/tests/golden/ca_san_jose/geometry_disabled.json
+++ b/tests/golden/ca_san_jose/geometry_disabled.json
@@ -7,6 +7,7 @@
     "composed_at": "<TS>",
     "composer_version": "<COMPOSER_VERSION:shape-checked-only>",
     "delivered_at": null,
+    "election": "city",
     "geometry_tier_used": false,
--- a/tests/golden/ca_san_jose/refused.json
+++ b/tests/golden/ca_san_jose/refused.json
@@ -7,6 +7,7 @@
     "composed_at": "<TS>",
     "composer_version": "<COMPOSER_VERSION:shape-checked-only>",
     "delivered_at": null,
+    "election": "city",
     "geometry_tier_used": false,
```
plus the new `tests/golden/ca_san_jose/election_required.json`. Re-run, GREEN:

```
GOLDEN SUMMARY: PASSED (0 failure(s)). Coverage this run: 2/4 sec 1.2 fixture classes
(refused, geometry-disabled) plus 1 additional fixture beyond that taxonomy (election_required).
NOT covered within sec 1.2's taxonomy: composed, partial.
```
Confirmed again via `make golden` itself (not the script directly) against a second, independent
fresh migrations-only database (`ledgex_p34_scratch2`), `GOLDEN_ALLOW_RULE_SEED=1` (finding #37's
own gate, unaffected by this package -- still fires correctly by default when the rule row is
genuinely absent, confirmed the first time this section's own scratch database was used, before
the flag was set).

`refused`/`geometry-disabled` now pass `election="city"` explicitly, so their own shape and
refusal count are unchanged by this package -- only `election_required` is new. Section 6.6's
own P34 implementation note (spec text, section 5 below) states this explicitly.

---

### 5. Spec bump -- v1.41 -> v1.42

- `build/ledgex_source.py`: `SPEC_VERSION = "1.42"`; `MAKE_TARGETS`'s "make golden" row updated
  to name the third fixture and the corrected 2/4-plus-1 coverage claim.
- `text/LedgeX_Engineering_Reference_Spec_v1_41.txt` -> `..._v1_42.txt`: renamed via `git mv`,
  verified by hash before committing (not by sight -- this exact rename has staged stale content
  six times this session): `git ls-files -s` and `git hash-object` on the renamed path both
  returned `b69505d0c0f42cfd770604e817f225314df0654c` -- MATCH.
- §3.12: two new paragraphs describing 0052/0053 (mirroring each migration's own header,
  condensed).
- §5: the L5 table row's own In/Refuses-when columns updated to name election and both new
  codes; the compose-loop prose gained a P34 implementation note (parallel to P20's own `as_of`
  note already there).
- §6.6: new field-treatment row (`election` -- Retained, same reasoning as `ruleset_version`)
  plus a P34 implementation note explaining the third fixture and why `ELECTION_NOT_SUPPORTED`
  deliberately has no fourth.
- §9: two new rows (`ELECTION_REQUIRED`, `ELECTION_NOT_SUPPORTED`, both L5) inserted directly
  after `RULE_UNAVAILABLE`.
- §12: a new 1.42 change-record row, dated, naming this package and the corrected 0038->0053
  pointer move.
- Four literal `Engineering Reference Spec v1.41` / `This Spec v1.41` page-header artifacts
  (baked into the raw pdftotext extraction, not generated) updated alongside the title.
- `website/index.html`'s own hand-authored `<h3>Engineering Reference Spec v1.41</h3>` bumped
  (this file is NOT covered by `build/build_website.py`'s own regeneration -- `make qa`'s stale-
  version-string check is what would have caught a miss here).

`make docs && make site` regenerated `docs/LEDGEX_SPEC.md`, `docs/LEDGEX_RULES.md`,
`docs/SPEC_INDEX.md`, `website/spec.html`, `website/rules.html`. `make qa` (standalone, matching
CI's own order -- qa before any local `make docs` re-run) clean:

```
DOCUMENT QA PASSED — 20 invariants and 7 make targets verbatim in both artifacts; no copied
tables; markdown current; SPEC_INDEX.md current and every section resolvable; website/*.html
current; no stale version strings anywhere in website/*.html; every migration referenced and
resolvable; every referenced build/ file exists; refusals_codes_valid()'s vocabulary matches §9.
```

---

### 6. No second rule seeded -- confirmed, not just stated

`election="state"` reaches `ELECTION_NOT_SUPPORTED` because `CONCLUSION_RULE_KEYS` has no
`("placement", "state")` entry -- proven directly by `scripts/test_compose_election.py`
(section below), which never touches `db/seeds/day4_sources.sql` or plants a second `rule` row
anywhere. Bulletin #210's own footer (*"To read about state laws on ADUs, see the HCD Accessory
Dwelling Unit Handbook, January 2025"*) remains unfetched and unread -- its own later package,
same pacing P31 used for the first rule.

---

### 7. New finding, recorded only -- `make golden` as a cross-seeder drift detector

`scripts/check_golden.py`'s `seed_reference_rows()` INSERTs the one real `rule` row with
`ON CONFLICT (id) DO UPDATE SET` naming every non-key column (P32, finding #36's fix). On any
database where `db/seeds/day4_sources.sql` has *also* been applied, the two seeders' literals
are compared for real by `0013`'s `rule_no_destructive_update()` -- any disagreement between
them raises `I18 violated` immediately, on the very next `make golden` run against that
database. Nobody has claimed this as a real capability before now; it is one, today, on any
non-CI database carrying both seed paths (`ledgex_schema_check`, a real production database
post-launch).

This gives finding #36's own documented "cross-seeder drift is unreachable in CI" a cheap
remedy: a `db.yml` step applying `db/seeds/` before `make golden` in the `schema` job would make
that drift reachable in CI too, for the first time. **Recorded as a candidate, not built here**
-- it is a change to the CI contract (a job that today runs schema-only, taking on a seed step)
and therefore scope creep for this package, per CONVENTIONS' own "scope creep is reported, not
absorbed" rule.

*For*: closes finding #36's one remaining gap (cross-seeder drift specifically) at negligible
cost -- `db/seeds/day4_sources.sql` is small, idempotent (`ON CONFLICT DO NOTHING`/`DO UPDATE`
throughout), and `ledgex_ci` is already disposable, so nothing about running it there is unsafe
in the way finding #37 identified for the golden-only path.
*Against*: `db.yml`'s `schema` job is documented, repeatedly, as schema-only -- CLAUDE.md's own
words, restated in this repo's CI-precondition rule (CONVENTIONS.md) and in `check_golden.py`'s
own module docstring history. Adding a seed step blurs that boundary for every future reader who
has internalized "CI never runs `db/seeds/`" as a fact about this repository, and the drift this
would catch is a documentation/maintenance risk (two seeders agreeing), not a correctness risk
any customer-facing behavior depends on today.

---

### 8. Close-out

`make migrate-verify` run before every local-database claim above (`ledgex_schema_check`:
51 -> 53 migrations, MATCH, both before and after the two new migrations were applied).
`make schema-dump` clean on a fresh migrations-only database after the two migrations
(reviewed diff: exactly the new column, its two CHECK constraints -- one renamed
`property_file_refusal_codes_known_election` -- and the new column's `COMMENT ON`, nothing
else). `make test` (168 passed, 0 failed), `make golden` (re-blessed, 0 failures across all
three fixtures), `make conformance` (0 failures), `make check-boundary` (5 contracts kept, 0
broken; jurisdiction-name grep clean; `make qa` clean) all green on a fresh migrations-only
database. `make db-test` -- a genuine RED found and fixed, not planted: `db/tests/invariants.sql`'s
T60/T79/T80/T81/T82 hardcoded the pre-0053 constraint name
(`property_file_refusal_codes_known_shape_checked`); updated to the new, correct name
(`property_file_refusal_codes_known_election`, 0053's own DROP+ADD), same rename discipline
0048 itself required over 0038's original name. Re-run after the fix: 108 tests recorded PASS,
1 known gap (I5c, pre-existing, unaffected), 1 skip (S1, `db/seeds/` not applied to this
database, pre-existing, unaffected), exit 0.

Both acceptance suites, twice each, each against its own fresh database (four scratch databases
total, `ledgex_p5_a`/`ledgex_p5_b`/`ledgex_phaseb_a`/`ledgex_phaseb_b`, never the same database
twice): `run_p5_acceptance.sh` -- ALL CHECKPOINTS PASSED, both runs. `run_phaseb_acceptance.sh`
-- ALL ASSERTIONS PASSED, both runs. Neither suite touches `property_file`/`election` at all, so
this is a non-regression confirmation, not new coverage of this package's own change.

`scripts/test_compose_election.py` -- new, real-database, wired into `db.yml` right after
`scripts/test_compose_geometry_tier_used.py`. Proves all three L5 outcomes are reached by three
distinct code paths (not one path with three labels) plus the invalid-election-value guard, all
four assertions passing against a fresh scratch database.

All four `db.yml`/`docs.yml` jobs to be confirmed green on the real runner, on the close-out
commit -- recorded in a follow-up commit once confirmed, per this repo's own established
pattern.
