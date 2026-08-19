## P35 — The DB-layer half P34 skipped

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Section 3 reports, does not build.

---

### 1. The gap, confirmed from the files, not taken on faith

Three claims, each checked directly:

- **The only P34 change to `db/tests/invariants.sql` was the constraint-name rename.**
  `git show 1826300 -- db/tests/invariants.sql` — five hunks, all `IF v_constraint =
  'property_file_refusal_codes_known_shape_checked'` → `'property_file_refusal_codes_known_election'`
  (T60, T79, T80, T81, T82), plus the T60 header comment updated to record the rename lineage.
  No new `TEST T*` block, no floor change. Confirmed.
- **The highest test is still T91, the floor at `invariants.sql:4803` (pre-P35) is still 108,
  unchanged since 0051.** `grep -oE "TEST T[0-9]+"` across the whole file, sorted: highest is
  91. The floor literal's own git history (`git log -p` on the `IF v_pass_count <` line):
  ...→ 106 → 108, and nothing after. Confirmed.
- **0050 raised 102→106 (T86-T89) and 0051 raised 106→108 (T90-T91); every prior migration
  added tests.** The floor block's own comment history states this explicitly (91→95 by 0047,
  95→102 by 0048/0049, 102→106 by 0050, 106→108 by 0051) and matches the `git log -p` trail
  exactly. 0052 and 0053 are the first two migrations since the ledger began (0046) to add
  neither a test nor a floor bump. Confirmed.

All three hold. The gap is real: P34 built the schema and the application-layer proof
(`scripts/test_compose_election.py`) but never gave `db/tests/invariants.sql` — this repo's own
permanent, rerun-safe regression suite — any coverage of 0052/0053 beyond a rename that predated
both of them functionally (the constraint the rename points at now enforces 21 codes, not 19,
and nothing in the suite ever exercised that).

---

### 2. Seven new tests, T92–T98, RED-first

**T92** — `property_file_election_known` rejects `'bogus'`; exact constraint-violation text
captured via `GET STACKED DIAGNOSTICS ... MESSAGE_TEXT` and printed, not just the constraint
name.
**T93** — accepts `NULL` (not skipped as obvious — findings #8/#19 are both cases where a NULL
branch was assumed to behave as written and did not; 0052's own header invokes that precedent in
prose without ever testing it).
**T94** / **T95** — accepts `'city'` / `'state'`.
**T96** / **T97** — `refusals_codes_valid` accepts `ELECTION_REQUIRED` / `ELECTION_NOT_SUPPORTED`
(full `property_file` INSERT positive controls, same shape as 0048's own T83).
**T98** — `refusals_codes_valid`, POST-WIDENING, still rejects a genuinely unknown code — its
own fresh literal (`STILL_NOT_A_REAL_CODE_T98`), not T60's, because T60 predates 0053 and never
asserts anything about the SIZE of the accepted vocabulary, only that its own one literal is
rejected; a widening that accidentally turned into "accept everything" would leave T60 green
too.

**RED, proven directly, not inferred** — a scratch database (`ledgex_p35_pre`) built from
migrations 0001–0051 only (0052/0053 excluded from the apply loop):

```
INSERT INTO property_file (..., election) VALUES (..., 'city');
ERROR:  column "election" of relation "property_file" does not exist
```
(T92–T95's shared cause). After applying 0052 only (0053 still absent):
```
INSERT INTO property_file (..., refusals, ...) VALUES (..., '[{"code": "ELECTION_REQUIRED", ...}]'::jsonb, ...);
ERROR:  new row for relation "property_file" violates check constraint "property_file_refusal_codes_known_shape_checked"
```
(T96/T97's shared cause, by symmetry — same vocabulary gap). T98's own RED is not a schema-
absence RED (its assertion — reject an unknown code — already held pre-0053, via T60's own
mechanism) but a targeted proof that the *widening itself* didn't break rejection: with 0053
fully applied, `refusals_codes_valid()` temporarily replaced with a body returning `TRUE`
unconditionally (simulating exactly the "widening accidentally accepts everything" failure
mode):
```
CREATE OR REPLACE FUNCTION public.refusals_codes_valid(refusals jsonb) RETURNS boolean AS $$
    SELECT true;
$$ LANGUAGE sql IMMUTABLE;

INSERT INTO property_file (..., refusals, ...) VALUES (..., '[{"code": "STILL_NOT_A_REAL_CODE_T98", ...}]'::jsonb, ...);
INSERT 0 1   -- WRONGLY accepted -- this is the RED T98 exists to catch
```
Reverted (re-ran 0053's real `CREATE OR REPLACE FUNCTION`), same INSERT:
```
ERROR:  new row for relation "property_file" violates check constraint "property_file_refusal_codes_known_election"
```
GREEN, as designed.

**Floor raised 108 → 115**, comment history extended in the same style every prior bump used.

**Suite run four times, per CONVENTIONS' own carve-out for `invariants.sql`** (idempotent
under same-database rerun, unlike the two acceptance suites): three times against one
freshly-migrated database (`ledgex_p35_test`) — 115/115 every time, exit 0 every time, teardown
reclaiming the same class-3 tables each run (`property_file`, `parcel_exception`, `job_run`,
zero-fact `parcel`) while the shared class-2 fixture parcel is untouched — plus once more
against a second, independent fresh migrations-only database (`ledgex_p35_test2`): 115/115,
exit 0.

---

### 3. REPORT ONLY — the election / ELECTION_REQUIRED contradiction

**What `compose_property_file.py` actually writes today, read directly, not reasoned from the
name.** `election` (the column) is stamped from the literal `election` parameter with no
transformation, in every INSERT, every path (`scripts/compose_property_file.py` lines 429/441).
The L5 block sets `election_refusal` to exactly one of three things, mutually exclusively:

```
election is None              -> election_refusal = ELECTION_REQUIRED dict     (column stays None)
election given, no dict entry -> election_refusal = ELECTION_NOT_SUPPORTED dict (column = the given value)
election given, entry found   -> election_refusal = None (or RULE_UNAVAILABLE via a real query)
```

**Is "`ELECTION_REQUIRED` ∈ refusals IFF `election IS NULL`" the correct rule?** Checked in both
directions against the real code, not assumed:

- *`ELECTION_REQUIRED` present ⟹ `election IS NULL`* — **holds, and robustly, not by
  coincidence.** `election_refusal` is only ever set to the `ELECTION_REQUIRED` dict inside the
  `if election is None:` branch, and the column is an unconditional echo of that same Python
  variable, later, in the same function invocation. No code path can produce
  `ELECTION_REQUIRED` while stamping a non-`NULL` column — this is a structural consequence of
  "one parameter, read once, echoed once," not an accident of today's schema shape. It would
  take a rewrite that decouples the refusal decision from the column write (two different
  variables) to break this direction, not merely a new conclusion being added.
- *`election IS NULL` ⟹ `ELECTION_REQUIRED` present* — **holds today, but only by
  coincidence, and it is the exact "coincidence masks the bug until one side moves" shape
  README finding #22 already named once** (and `test_compose_geometry_tier_used.py`'s own
  docstring already invoked by name for a different column). It holds today because "placement"
  is the *only* conclusion this composer evaluates, and it *always* needs an election — so
  every composition today either supplies one or refuses `ELECTION_REQUIRED`; there is no third
  case. The moment a second conclusion exists that does **not** depend on an election, and some
  composition touches only that conclusion, `election` would be `NULL` (correctly, per 0052's
  own documented meaning: "no conclusion in this file depended on an election") with **no**
  `ELECTION_REQUIRED` refusal anywhere in `refusals` — a legitimate row that would violate this
  direction of the biconditional. This direction is not a real domain law; it is an artifact of
  the one-conclusion composer that exists today.

Refusal accumulation (P25: refusals ACCUMULATE across stages, both existing fixtures already
carry two, `election_required.json` carries three) does not threaten either direction above —
`ELECTION_REQUIRED` co-occurring with `GEOMETRY_TIER_DISABLED`/`RIGHTS_BLOCKED` in the same
`refusals` array is expected and already proven (P34's own `election_required` fixture); the
biconditional is about the relationship between one specific code's *presence* and the column's
*value*, not about whether other, unrelated codes are also present.

**Does `ELECTION_NOT_SUPPORTED` have its own relationship to the column?** Yes, and it is
likewise a one-way implication, robust for the same "one parameter, echoed once" reason, not
coincidental:

- *`ELECTION_NOT_SUPPORTED` present ⟹ `election IS NOT NULL`* — holds structurally:
  `election_refusal` is only ever set to the `ELECTION_NOT_SUPPORTED` dict inside the `else`
  branch (`election is not None`), and the column echoes that same non-`None` value.
- *`election IS NOT NULL` ⟹ `ELECTION_NOT_SUPPORTED` present* — **does not hold**, and should
  not: `election IS NOT NULL` is also produced by a row where the dict entry WAS found (success,
  or a `RULE_UNAVAILABLE` refusal from a real query) — neither of those carries
  `ELECTION_NOT_SUPPORTED`. `election IS NOT NULL` is a three-way disjunction
  (`ELECTION_NOT_SUPPORTED` present, OR `RULE_UNAVAILABLE` present, OR no L5 refusal at all), not
  a biconditional partner for any single code.

**Recommendation: two one-way exclusions, not the full biconditional.** The two directions that
are structurally guaranteed (not contingent on today's one-conclusion shape) are exactly the
two worth enforcing:

```
NOT (refusals @> '[{"code":"ELECTION_REQUIRED"}]'      AND election IS NOT NULL)
NOT (refusals @> '[{"code":"ELECTION_NOT_SUPPORTED"}]' AND election IS NULL)
```

The full `election IS NULL ⟺ ELECTION_REQUIRED present` biconditional is deliberately **not**
recommended — it is true today only because of the single-conclusion coincidence identified
above, and baking it into a CHECK would either need loosening the moment a second,
non-election-dependent conclusion exists, or would incorrectly reject a legitimate future row.
The narrower pairwise exclusions have no such expiry: they follow from how `compose()`'s own
variable-to-column-and-refusal mapping works, not from how many conclusions exist.

**Mechanism: a CHECK, generalizing `refusals_codes_valid`'s own shape, not a trigger.** Both
proposed exclusions read only the current row's own `refusals` and `election` columns — no
comparison against `OLD`, no cross-row query — exactly the same single-row, no-subquery-needed
shape `refusals_codes_valid()` already is (a `LANGUAGE sql IMMUTABLE` function wrapping a
`jsonb_array_elements` scan, callable from a `CHECK` even though a bare `CHECK` cannot itself
contain a subquery — 0038's own header established this is legal). A trigger is unnecessary and
would be the wrong tool: `rule_no_destructive_update()` needs a trigger because it compares
`NEW` against `OLD` across an `UPDATE`; this is an `INSERT`-time, same-row property with no
history to consult.

**Existing rows — queried, not assumed.** `make migrate-verify` run first:
`ledgex_schema_check`, 53 migrations, `MATCH`. Then, directly:

```sql
SELECT count(*) FROM property_file;                                  -- 7
SELECT count(*) FROM property_file WHERE election IS NOT NULL;       -- 2
SELECT id, election, refusals FROM property_file
WHERE (refusals @> '[{"code":"ELECTION_REQUIRED"}]'::jsonb AND election IS NOT NULL)
   OR (refusals @> '[{"code":"ELECTION_NOT_SUPPORTED"}]'::jsonb AND election IS NULL);
                                                                        -- 0 rows
```
No existing row would violate either proposed exclusion. A migration adding them today would
apply cleanly with no remediation step.

**Is the contradiction reachable today? No — through the only writer.** Both one-way
exclusions already hold for every row `compose()` can produce, by construction (shown above),
so the contradiction is genuinely unreachable through `scripts/compose_property_file.py` as it
exists. **That is not the same claim as "safe to leave unenforced."** `property_file.election`
has exactly one writer today — the identical shape `job_run.schema_drift` had "zero legitimate
writers" before 0051 found two real ones reaching for it anyway (README findings #12/#16), and
the identical shape this repo's own `qa_check.py`-vs-0038 pointer drift (P35's own sibling
correction, P34 section 0) shows for "the one place that reads this" not being the only place
that could plausibly write to it. Nothing today stops a second writer — a direct `INSERT`, a
future batch backfill tool, a second composer entry point for a different jurisdiction or
channel — from writing `election='city'` alongside a manually-constructed `ELECTION_REQUIRED`
refusal, and nothing would catch it: `property_file_election_known` only constrains the
column's own vocabulary, `refusals_codes_valid` only constrains each element's `code` against
§9, and neither knows the other exists. A CHECK is what would make the exclusion true by
construction, independent of which application code happens to be running — the same reason
`refusals_codes_valid` itself is a CHECK and not merely something `compose()`'s own code is
trusted to get right forever.

**Recommendation, not built here:** a new migration (0054), a new function
(`property_file_election_refusal_consistent(election text, refusals jsonb)` or similar,
mirroring `refusals_codes_valid`'s own signature shape) backing a new `CHECK`, enforcing exactly
the two one-way exclusions above. Its own header should name this report and state explicitly,
per CONVENTIONS' NULL-inside-a-constraint rule, that the full biconditional was considered and
rejected as coincidental, not merely narrower.

---

### 4. Close-out

`make migrate-verify` run before citing `ledgex_schema_check` in section 3 (53 migrations,
`MATCH`). Clean `make schema-dump` on a fresh migrations-only database (no diff — this package
touches no migration, only `db/tests/invariants.sql`, which `schema.sql` does not cover).
`make test` (168 passed), `make golden` (0 failures, all three fixtures), `make conformance`
(0 failures), `make check-boundary` (5 contracts kept, `make qa` clean) all green on one fresh
migrations-only database. `make db-test`: 115/115, 1 known gap (I5c, pre-existing), 1 skip (S1,
pre-existing), exit 0 — run four times total (three same-database, one fresh-migrations-only),
per section 2 above. Both acceptance suites run twice each, each against its own fresh database
(four scratch databases, never the same database twice): `run_p5_acceptance.sh` — ALL
CHECKPOINTS PASSED, both runs; `run_phaseb_acceptance.sh` — ALL ASSERTIONS PASSED, both runs.
Neither suite touches `property_file.election` or the refusal-code vocabulary, so this is a
non-regression confirmation.

All four `db.yml`/`docs.yml` jobs to be confirmed green on the real runner, on the close-out
commit.
