## P17 — Invariant-suite hygiene: findings #26, #24 and #25

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). P14's three-class fixture
taxonomy ([P14-invariants-sql-teardown.md](P14-invariants-sql-teardown.md)) is settled and
not re-derived here.

---

### 1. #26: teardown must run even when the suite aborts

**The risk, settled before writing.** `make db-test` runs in CI (`db.yml`, `schema` job:
`make db-test DATABASE_URL="$DATABASE_URL" PSQL="$PSQL"`). Whatever wrapper this package
builds must never let `make db-test` report success on a failing suite — the same
silently-passing-gate shape already found in `qa_check`, `conformance` and `golden`. Design:
run the suite, capture its own exit code, run teardown unconditionally, exit with the
suite's own captured code — never teardown's.

**Splitting teardown into its own file, `db/tests/teardown.sql`, has a real consequence,
worked out, not discovered live.** A standalone script is a separate `psql` invocation with
no access to the suite's session-local `test_state`/`v_parcel_id` — it must scope by durable
namespace instead (`test.%` job_keys, already established; `apn` prefix for parcels).
Checked directly, not assumed uniform: every one of this file's 7 parcel-creating `INSERT`s
(`grep -n 'INSERT INTO parcel\b'`, all 7) uses a `test-`/`TEST-` prefixed apn — 6 uppercase,
one (T68) lowercase (`'test-t68-' || uuid`), inconsistent with the rest. Matched with
`apn ILIKE 'test-%'`, not the case-sensitive `LIKE 'TEST-%'` P14's own inline teardown never
needed to worry about (T68's `INSERT INTO parcel` didn't exist yet, or wasn't reachable, when
P14 wrote its version).

Broader scope also means teardown now sees rows it did not create — including, for the first
time, `parcel` itself. P14's inline teardown never attempted `parcel`: every `v_parcel_id` it
ever saw already had a fact against it, by construction (that run's own tests wrote one). A
namespace-scoped script can see a genuinely fact-free `test-%` parcel too — traced two real
sources: T56 (two parcels proving a shared-apn duplicate is legal, neither ever gets a fact)
and T68 (a parcel whose only fact-insert attempt is inside a `BEGIN...EXCEPTION` block that
catches the expected failure, rolling that insert back to its savepoint while the earlier,
outside-the-block `INSERT INTO parcel` stays committed). A fact-free `test-%` parcel is not
class 2 — I4/0017 has nothing to say about a parcel no fact has ever cited — but `teardown.sql`
does **not** attempt the delete and let the FK reject a locked one: every `parcel` delete is
filtered by an explicit `NOT EXISTS (SELECT 1 FROM fact WHERE fact.parcel_id = parcel.id)`,
checked before the delete runs. A bulk `DELETE` that hits even one FK-locked row fails
entirely and would abort the script under `ON_ERROR_STOP` — the same silently-masks-the-signal
bug finding #26 is about, just relocated into teardown instead of `db-test`.

**Built:**
- `db/tests/teardown.sql` — namespace-scoped class-3 teardown (unchanged table set:
  `exception_evidence`, `property_file_fact`, `parcel_exception`, `property_file`,
  `source_feature_identity`, `job_run`) plus the new, explicitly-filtered zero-fact `parcel`
  cleanup. `fact` is never a target, on any path.
- `db/tests/invariants.sql`'s own inline teardown block removed — replaced with a short note
  pointing at the new file and explaining why (placement-after-the-pass-floor-check could
  never run on a failing suite, structurally, regardless of anything else). Precondition
  comment at the top updated to match.
- `Makefile`'s `db-test` target rewritten: runs the suite, captures `$$suite_exit`, runs
  `db/tests/teardown.sql` unconditionally, prints a warning (non-fatal) if teardown itself
  errors, exits `$$suite_exit` — never teardown's own exit code.

**Proved RED, for real**, not just asserted: `T88`'s own assertion temporarily corrupted
(`v_retired_count <> 2` → `<> 999`, guaranteed to fail since the real count is 2) on a copy
of the file, run against a fresh scratch database via `make db-test`:

```
### TEST T88: retirement UPDATE targets only the exact stranded version (should succeed)
psql:db/tests/invariants.sql:4658: ERROR:  FAIL T88: expected exactly 2 rows retired, got 2
CONTEXT:  PL/pgSQL function inline_code_block line 27 at RAISE

db-test: suite exited 3 -- running db/tests/teardown.sql unconditionally (P17, finding #26)
psql:db/tests/teardown.sql:132: NOTICE:  teardown: exception_evidence 0 row(s)
...
psql:db/tests/teardown.sql:132: NOTICE:  teardown: parcel (zero-fact only) 3 row(s)
...
make: *** [db-test] Error 3
```

`make db-test`'s own process exit code was 2 (not 3) — checked directly against a trivial
unrelated Makefile (`printf 'foo:\n\texit 3\n'`) and confirmed this is generic GNU Make
behaviour, not specific to this recipe: `make` always exits 2 on ANY failing recipe,
regardless of the recipe's own specific nonzero code, surfacing the real code only in its own
diagnostic line (`Error 3`). What's actually load-bearing — CI (and every caller) treats
"exit 0" vs "exit nonzero" as the pass/fail signal, never the specific number — is preserved
exactly: `make db-test` is reliably nonzero if and only if the suite itself failed, and the
suite's own precise code is never silently discarded, only printed instead of being `make`'s
own process-level exit status (a property of `make` itself, present for every failing target
in this or any Makefile, not introduced by this design).

Confirmed via direct query, not the log alone: `parcel_exception`/`property_file` both 0 in
the scratch database immediately after this failing run — teardown genuinely ran and cleaned
real, accumulated residue despite the abort. File restored, re-verified GREEN three times on
an accumulating scratch database (class-2: 4→8→12 parcels, 47→94→141 facts, linear; class-3:
flat at 0, three zero-fact parcels reclaimed every run) plus once fresh migrations-only, no
seed.

---

### 2. #24: run it once on `ledgex_schema_check` — asked first

Re-queried, not cited. `ledgex_schema_check`'s ledger already at `0050` (P16 fixed it).
Before-state:

```
Class-2 (permanent, fact-bearing test-*/TEST-* parcels):  24 parcels, 324 facts
Zero-fact orphan test-*/TEST-* parcels (never reclaimed before): 19
Class-3 rows scoped to test-*/TEST-* parcels:
  parcel_exception       40   (2 already 'version_retired' -- P16 incidentally touched a
                                test-fixture row sharing the same detector_key/version as
                                the real zoning bump; irrelevant to teardown, which deletes
                                parcel_exception regardless of outcome)
  property_file          20
  property_file_fact      8
  job_run (test.% job_key) 8
```

**P16's 10,150 retired rows confirmed NOT in scope**, directly, not assumed: they sit on real
production parcels (real APNs, e.g. `23712112`), never on `test-%`/`TEST-%`-apn ones —
querying `parcel_exception` scoped to `test-%` parcels returns the same 40 P14 originally
found (P16 moved 2 of those 40 to `version_retired`, moved zero of P14's original class-3
total).

Reported, then explicitly confirmed with the user before running.

```
$ psql ... -f db/tests/teardown.sql
NOTICE:  teardown: exception_evidence 0 row(s)
NOTICE:  teardown: property_file_fact 8 row(s)
NOTICE:  teardown: parcel_exception 40 row(s)
NOTICE:  teardown: property_file 20 row(s)
NOTICE:  teardown: source_feature_identity 0 row(s)
NOTICE:  teardown: job_run 8 row(s)
NOTICE:  teardown: parcel (zero-fact only) 19 row(s)
```

Exactly the predicted 40/20/8/8/19. After-state, verified by direct query (not inferred by
subtraction, per CONVENTIONS' "never infer a category from arithmetic" — the first attempt at
this arithmetic was WRONG: 24 test parcels + 225,010 non-`test-%` parcels ≠ 225,096 total,
short by 62; a direct `WHERE apn IS NULL` query found the missing 62 — real, unresolved-APN
production parcels that `NOT ILIKE`'s three-valued NULL logic silently excludes from both
sides of a `LIKE`/`NOT LIKE` split, never at risk from this teardown either way):

```
class-2 after: 24 parcels, 324 facts        -- unchanged
class-3 after: 0/0/0/0                       -- fully reclaimed
total parcel: 225,096 = 24 (test) + 225,010 (real, non-test apn) + 62 (real, NULL apn)
zoning_spatial_join_unresolvable v1.0 version_retired: 10,148 (was 10,150 -- the 2 test-
  fixture rows on test-% parcels were the only ones this teardown ever touched; the 10,148
  remaining are confirmed all on non-test parcels)
```

---

### 3. #25: report only — left open

`make db-test` with no arguments runs against `DATABASE_URL`'s Makefile default,
`postgresql://localhost/ledgex_schema_check`. P14 deferred a scoped default, reasoning it
"affects every other target." That reasoning does not hold up mechanically: a second
Makefile variable (e.g. `DB_TEST_DATABASE_URL ?= postgresql://localhost/ledgex_test`), read
only by `db-test`'s own recipe, leaves `schema`, `schema-dump`, `migrate` and `migrate-verify`
completely untouched — confirmed by reading how `DATABASE_URL` is referenced in each target;
nothing about isolating `db-test`'s default requires touching the other four.

**(a) A separate default for `db-test` only, matching CI's fresh-database-per-run shape.**
Cheapest to build. Cost to a first-time developer: a *second* database-URL variable to learn
existing alongside `DATABASE_URL` (real discoverability cost — which one governs which
target is now a question the Makefile's own comments have to carry, permanently), and the
new default database (`ledgex_test` or similar) does not exist on a fresh clone — the very
first `make db-test` fails loud (`database "ledgex_test" does not exist`) rather than
succeeding silently against precious data, which is strictly better than today's failure mode
but still requires the developer to `createdb`/`make schema` it themselves before their first
real run. Also: CI's current invocation (`db.yml`, `make db-test DATABASE_URL="$DATABASE_URL"
PSQL="$PSQL"`) explicitly passes `DATABASE_URL` — if `db-test` switched to reading a
differently-named variable, CI's own override would be silently ignored unless `db.yml` were
updated in the same change; not a blocker, but a coupled edit this option's cost has to
include, not a free lunch.

**(b) Refuse to run without an explicit opt-in** (e.g. a `CONFIRM_DISPOSABLE=1` flag).
Cheapest to build, but the weakest actual protection of the three — it adds friction to
*every* invocation, including the common, already-safe case (a developer who already has a
real scratch database and just wants to run the suite), forever. And a flag a developer
learns to always append (muscle memory, copy-pasted from shell history) is exactly the kind
of ritual `db/README.md`'s own `make schema`/`migrate`/`migrate-baseline` three-way decision
procedure already argues against — that procedure exists specifically because guessing
(or ritualizing) database state, rather than checking it, is how a database drifts
unnoticed. An opt-in flag checks nothing about the actual target database; it only checks
that the developer typed the flag.

**(c) Refuse unless the database carries an actual disposability marker.** Strongest
protection — the only option that verifies something *true about the target database*
rather than trusting a name or a flag someone chose — matching this repo's own stated
preference for constraints enforced by data over convention or ritual (0045's own header,
already quoted in P14: "application logic that a constraint could enforce is the weaker half
of this repo's own pattern"). Highest cost: the marker mechanism does not exist yet and has
to be invented (a marker table? a naming-convention regex checked at runtime? something
else?) — P14's own report already named this exact question as needing "its own report-first
pass," not decided there, and it is not decided here either. A first-time developer's cost
under this option is the highest of the three until that mechanism exists: `db-test` would
refuse to run against ANY database, including a freshly-created scratch one, until whatever
marking step gets documented and performed first — a real cost, but one that fails loud and
verifiably rather than silently.

**Recommendation, not implemented:** (a) now — cheap, mechanically clean, directly closes the
exact mechanism that caused both real incidents (a bare `make db-test` landing on
`ledgex_schema_check` by default) — paired with (c) named explicitly as the stronger,
deferred fix, its own future package, same shape P14 already deferred it as. (b) not
recommended at all — real cost, illusory protection.

Not implemented in this package. Reported for a future package to decide and build.

---

### 4. Close-out

No schema change in this package — confirmed, not assumed: no new file in
`db/migrations/`, and `make schema-dump` against a fresh apply reports `db/schema.sql is
current — no diff.` No spec bump.

Findings #26 and #24 closed with evidence above. #25 left open, recommendation recorded.
`db-test`'s CI step output pasted below, since it is the target this package changes.
