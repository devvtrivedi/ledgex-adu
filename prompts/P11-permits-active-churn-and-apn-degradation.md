## P11 — Two fabricated-fact bugs the acceptance suites cannot see

Numbered P11, not P10: P10 is already reserved by README finding #19 (`0045`'s index vs.
`zoning_source_geometry_invalid`). Standard hard rules apply
([CONVENTIONS.md](CONVENTIONS.md)).

Found by a full-repo read at `de61f53` (working tree clean, nothing unpushed). Every
finding below was checked against the committed code and, where stated, against the
committed fixtures — not carried over from any earlier document. Marked
**verified** / **unverified** / **assumed** individually.

---

### 1. What is actually wrong

#### 1(a) — `load_permits` fabricates a supersession on every single run (HIGH)

`scripts/ingest_zoning_permits.py:902-961`.

```python
fresh_active = True if fresh is not None else None      # :904
...
if fresh_value == live_value:                            # :927
    counts["same"] += 1
    continue
fact_ids_to_supersede.append(live_fact_id)
...
elif retire_with_false_successor:                        # :940
    # writes json.dumps(False), supersession_reason='world_change'
```

For a parcel with **no active permits this run** and a live `permits.active = false`
fact from a previous run:

- `fresh` is `None`, so `fresh_active` is `None`.
- `live_value` is `False` (psycopg2 decodes jsonb `false` to Python `False`).
- `None == False` is `False` in Python, so the `same` branch is never taken.
- The run supersedes the existing `false` fact and writes **another** `false` fact
  with `supersedes_fact_id` set and `supersession_reason = 'world_change'`.

**Verified** (logic reproduced in isolation, no database needed):

```
parcel has NO active permits this run, live permits.active =
   live=True   fresh=None  ->  SUPERSEDE + write successor value=False reason='world_change'
   live=False  fresh=None  ->  SUPERSEDE + write successor value=False reason='world_change'

None == False evaluates to: False
```

The second line is the bug. Every re-run of `load_permits` against unchanged data adds
one more `permits.active = false` fact row per zero-permit parcel, forever, each one
asserting `world_change` for a world that did not change. This is CONVENTIONS.md's
"do not invent values to fill a silence" and the fabricated-supersession failure class
P1/P5 exist to prevent — arriving by a third route.

`permits.series_earliest` is **not** affected: its `retire_with_false_successor` is
`False`, so it retires with no successor, `live_entry` is `None` on the next run, and
it is genuinely idempotent. Only `permits.active` churns. **Verified** by reading both
branches.

`load_zoning`'s equivalent diff (`:591-625`) is also unaffected — it compares
`live_value == fresh_value` where both sides are `None`-or-string, never `None`-vs-`False`.
**Verified**.

#### 1(b) — the P5 acceptance suite structurally cannot catch 1(a) (HIGH)

`scripts/check_p5_acceptance.py:166-172`, `scripts/run_p5_acceptance.sh:72-76`.

`run_p5_acceptance.sh`'s final step is a **same-snapshot re-run** of permits followed by
`check_p5_acceptance.py after-a2`. At that point parcel `23712112` carries exactly the
state 1(a) triggers on: live `permits.active = false`, and fixture `p5_permits_A.csv`
contains no row for it. **Verified** against the committed fixtures — `p5_permits_A.csv`
lists only `23717099` and `58705049`.

The assertion that should catch it is:

```python
check("after A2: 23712112 permits.active = false again (true -> false, superseded, world_change)",
      d_active is not None and d_active[1] is False and d_active[2] is not None and d_active[3] == "world_change",
```

It asserts the live **value** is `False` and that `supersedes_fact_id` is non-null. After
the churn the live value is still `False` and `supersedes_fact_id` is still non-null — it
just points at the previous `false` instead of the previous `true`. The assertion passes
and the script prints `P5 ACCEPTANCE: ALL CHECKPOINTS PASSED`.

This is the repo's own named shape: **the test that encodes the bug**. `prompts/README.md`
currently claims "Core safety property (`different=0`, `retired-no-successor=0` on a
same-snapshot re-run) proven in the acceptance suite itself" — that claim is false for
`permits.active`, because nothing in the suite ever reads `diff_counts` or counts fact
rows. **Verified** by reading `check_p5_acceptance.py` end to end; the string
`diff_counts` does not appear in it.

#### 1(c) — `phase_e` writes a placeholder or JSON-null as a `parcel.apn` fact (HIGH)

`scripts/ingest_parcels.py:1176-1215`.

`is_unresolvable_apn` (`:852-861`) is called **only** on the NEW branch (`:1130`). The
CHANGED branch never calls it and writes `json.dumps(canon_apn)` unconditionally at `:1208`.

For a feature whose APN degrades between snapshots from a real value to `'27704???'`:
the `changed_rows` query (`:1108-1120`) matches (`fa.value IS DISTINCT FROM
to_jsonb(s.apn_canonical)` is true), `apn_changed` is true, and the successor fact is
written with value `"27704???"`.

For a degradation to blank: `s.apn_canonical` is SQL `NULL`, `apn_incoming` is Python
`None`, `json.dumps(None)` is `'null'` — and `fact.value` is `jsonb NOT NULL` (`0006`),
which a jsonb `null` satisfies. A fact whose value is JSON `null` lands in the ledger,
and `parcel_apn_cache_updates` sets `parcel.apn = NULL` alongside it. **Verified** by
reading `0006_fact.sql` and the `to_jsonb`/`IS DISTINCT FROM` semantics; **unverified**
against a live database (no PostgreSQL available in the audit environment).

This directly contradicts `db/README.md`'s own rule — "Ingest code must **not** write a
`parcel.apn` fact for either case" — and contradicts the loader's own comment at
`:1102-1107`, which claims a resolvability flip is "flagged here as a known gap, not
silently absorbed into 'changed' or 'unchanged'." It **is** absorbed into "changed", and
a non-value is stored as if it were a value. `0017` forbids deleting it afterward.

Related to README finding #17 but **not the same finding**. #17 describes the
*undetected* direction (unresolvable → resolvable). This is the *actively wrong*
direction (resolvable → unresolvable), and it writes a bad row rather than missing one.

The same query has a second consequence worth naming separately: `fa` and `fg` are
**INNER** joins, so a parcel with no live `parcel.apn` fact — every one of the 54
unresolvable-APN parcels — can never enter `changed_rows` at all. Its **geometry**
changes are therefore silently dropped forever, and a retired identity for it can never
be un-retired. **Verified** by reading the query; **unverified** against real data.

#### 1(d) — five setup scripts write real licence ids with fabricated clearance (MEDIUM)

`scripts/_p5_setup.py:51`, `scripts/_phaseb_setup.py:53`,
`scripts/test_refresh_failure_invariant.py:60`,
`scripts/test_apn_canonicalization_invariant.py:45`,
`scripts/test_zoning_ambiguity_invariant.py:46`.

All five insert the **real** licence ids `cc0` / `cc_by_4_0` with
`observed_at = now()`, `cleared_by = 'test'`, `cleared_at = now()`.

This is precisely the contamination CLAUDE.md documents as having permanently poisoned
`ledgex_schema_check` — "`cc0`/`cc_by_4_0` licence rows with `cleared_by='test'` and a
fabricated `observed_at`, created by an old, unnamespaced version of
`db/tests/invariants.sql`". `db/tests/invariants.sql` was fixed to use `test.*` ids
(**verified**: `:41-48` inserts `test.cc0` / `test.cc_by_4_0`). These five scripts were
never fixed at the source.

Three things make this worse than a stale test fixture:

- `ON CONFLICT (id) DO NOTHING` means it only fires on a database that does **not**
  already have the real licences — i.e. exactly the "fresh migrations-only database with
  no seed" CONVENTIONS.md requires every suite to be run against once.
- `0027` makes `licence` immutable. Per CLAUDE.md, once contaminated there is no
  guarded-migration route left; the only remedy is drop, re-migrate, reseed.
- `cleared_by` / `cleared_at` non-null asserts counsel clearance that
  `STANDING-BLOCKER.md` and `db/seeds/day4_sources.sql` both state does not exist. The
  seed deliberately leaves them NULL and explains why at length; these scripts overwrite
  that position with a fabrication on any database they reach first.

None of the five insert `licence_channel` rows (**verified** by grep), so the I6 gate
still blocks by absence and no composition is wrongly permitted. The falsehood is in the
`licence` row itself, not in the rights outcome.

#### 1(e) — reconciliation reads are not source-scoped (MEDIUM, latent)

`scripts/ingest_zoning_permits.py:564-571` and `:884-891` build `live` as
`{(parcel_id, field_key): (fact_id, value)}` from `SELECT ... FROM fact WHERE field_key
IN (...) AND superseded_at IS NULL` — **no `source_id` filter**.
`scripts/ingest_parcels.py:1108-1120` joins `fact fa` / `fact fg` with no `source_id`
filter either.

`fact_one_current_per_source` (`0006`) is unique **per source**, so two sources may each
hold a live fact for the same `(parcel, field)`. When that happens:

- the dict silently keeps whichever row arrived last (the repo's own **arbitrary pick**
  shape), and this source's own live fact may be compared against a different source's
  value — potentially taking the `same` branch and skipping a write it owed;
- in `phase_e`'s join it multiplies rows and queues duplicate supersessions.

`0044` (`fact_supersession_source_match`) would raise on the cross-source supersession,
so the loud path is covered. The silent path — comparing against the wrong source and
concluding "same" — is not. Latent today (one source per field, **verified** by reading
all three loaders' `field_key` sets), and exactly the class P4 was written to close.

#### 1(f) — low-severity, no behaviour change needed to argue about

| Where | What |
|---|---|
| `scripts/ingest_parcels.py:94`, `ingest_zoning_permits.py:139`, `flag_invalid_geometry.py:99` | `SCRATCHPAD` is a hardcoded absolute path containing a machine- and session-specific UUID. Non-portable; `run_p5_acceptance.sh:30` already greps it back out of the source as a workaround. |
| `core/store.py:30,39` | Docstring still says "Callers still build the **14-tuple** list" / "Positional **14-tuples**" after the widening to 17 that the same docstring describes at `:9-28`. |
| `.importlinter:16` | References `build/check_boundary_grep.py`. The file is `build/check_jurisdiction_names.py`. |
| `scripts/ingest_parcels.py:1004` | Comment is corrupted mid-word: "verifying identity presence is sufinvariant to prove that". |
| `scripts/ingest_parcels.py:998` | `have_prior_identities` assigned, never read. |
| `scripts/migrate_baseline.py:127`, `migrate_verify.py:77` | `env("DATABASE_URL").rsplit("/", 1)[0] + f"/{ref}"` builds the reference URL by string surgery; a `DATABASE_URL` carrying a query string (`?sslmode=require`) produces a malformed URL. Both already parse the URL properly via `parsed_url()` a few lines away. |

#### 1(g) — checked and found clean, so nobody re-checks

**Verified**, so the next package does not spend context re-deriving these:

- `build/qa_check.py` exits 1 correctly on failure; all nine non-website gates pass
  against the committed tree.
- `db/schema.sql` is current through `0047` (`condition_cleared`, `reopened_from_id`,
  `schema_migrations`, `baselined` all present) — `make schema-dump` should not be red.
- No new migration carries an unnamed `CHECK`. Every unnamed one is in `0002`-`0012`,
  which CLAUDE.md grandfathers.
- The only two `INSERT`s in migrations are `0032` (guarded `INSERT ... SELECT`) and
  `0035` (`field_definition`, a table with no outbound FK, `ON CONFLICT DO NOTHING`) —
  both safe against CI's migrations-only database.
- `0035`'s guarded `UPDATE` has its paired seed fix (`db/seeds/day4_sources.sql:256`).
- `build/check_jurisdiction_names.py` passes against the real tree, 3 files scanned.
- Working tree clean, nothing unpushed.

**Unverified**: `qa_check.py`'s `check_website_current` reported `website/spec.html` and
`website/rules.html` as differing, but the audit environment has pandoc 2.9.2.1 and
`docs.yml` pins 3.10.1 — `build/build_website.py`'s own docstring names this exact
false-positive. Do not treat it as a finding without a 3.10.1 run.

---

### 2. The prompt

```
P11: two fabricated-fact bugs, plus the acceptance test that hides one of them.
Read prompts/CONVENTIONS.md and prompts/P11-permits-active-churn-and-apn-degradation.md
section 1 before doing anything. Standard hard rules apply. Read
docs/LEDGEX_SPEC.md §1 in full and db/README.md in full — both are load-bearing here.

Work the steps in order. Steps 1 and 2 are one unit: do not fix the code before the
test that proves the bug exists.

--- 1. Make the P5 acceptance suite able to fail on this ---
scripts/check_p5_acceptance.py cannot detect a same-snapshot re-run that supersedes a
fact and writes an identical successor. It asserts the live VALUE and that
supersedes_fact_id is non-null; both stay true through unbounded churn.

Add an assertion that would fail. Do not guess at the shape — decide between (at least)
counting total fact rows per (parcel_id, field_key) across a same-snapshot re-run, and
asserting the live fact's id is UNCHANGED across that re-run. Say which you chose and
why the other is weaker. The suite's existing final step is already a same-snapshot
re-run; you should not need to add one.

Run the new assertion against the CURRENT code and show it RED, with output. Per
CONVENTIONS.md this is not optional and a planted-input proof does not substitute: it
must go red on the real bug, in the real suite, before you touch
scripts/ingest_zoning_permits.py.

--- 2. Fix load_permits' permits.active comparison ---
scripts/ingest_zoning_permits.py:902-961. `fresh_active = True if fresh is not None
else None` is compared against a live jsonb value that decodes to Python False, and
`None == False` is False, so a parcel with no active permits and a live
permits.active=false is superseded and rewritten as false on every run, with
supersession_reason='world_change'.

The fix must preserve the distinction db/README.md draws and CONVENTIONS.md restates:
"we no longer observe this" and "this is now false" are different claims. Today the
code gets that right for a parcel that has NEVER had a permits.active fact (live_entry
is None and fresh is None -> no-op, no false written) and wrong for one that already
has a false. Whatever you write must keep the first behaviour exactly.

Report the shape before writing it. Do not change the comparison in a way that also
changes permits.series_earliest, which is currently correct and idempotent — check
that, do not assume it.

Then show the step 1 assertion GREEN, and re-run the whole P5 acceptance suite twice,
once against a fresh migrations-only database with no seed.

--- 3. Report, do not build: phase_e's APN degradation ---
scripts/ingest_parcels.py:1176-1215. The CHANGED branch never calls
is_unresolvable_apn. A feature whose APN degrades to a '?'-placeholder writes that
placeholder as a parcel.apn fact value; one that degrades to blank writes JSON null
(fact.value is jsonb NOT NULL, which jsonb null satisfies). db/README.md forbids both
explicitly, and 0017 makes either permanent.

The same query's INNER JOIN on a live parcel.apn fact also means the ~54 parcels with
no parcel.apn fact can never appear in changed_rows at all, so their GEOMETRY changes
are dropped too.

Do not fix this in this package. Report:
  (a) Confirm both cases against a real database — construct the degradation, run
      phase_e, show what actually lands in fact.value. Predict the outcome first.
  (b) What SHOULD happen when a resolvable APN degrades? Supersede with no successor
      plus a parcel_apn_unresolvable exception is the obvious candidate — argue it
      against at least one alternative, including what the parcel.apn cache column
      should become and what happens to the still-open exception if it later resolves
      again. README finding #17 is the other half of this; say whether they are one
      package or two.
  (c) Whether the INNER JOIN half is separable from (b) or has to move with it.

This carries a design decision and touches a shared reconciliation path, so it is
report-first without exception.

--- 4. Fix the test-fixture licence contamination ---
scripts/_p5_setup.py:51, scripts/_phaseb_setup.py:53,
scripts/test_refresh_failure_invariant.py:60,
scripts/test_apn_canonicalization_invariant.py:45,
scripts/test_zoning_ambiguity_invariant.py:46 all insert the REAL licence ids
cc0/cc_by_4_0 with cleared_by='test', cleared_at=now(), observed_at=now(). CLAUDE.md
documents this exact contamination as what permanently poisoned ledgex_schema_check;
db/tests/invariants.sql was fixed to use test.* ids and these five were not.

Fix at the source. Note the real obstacle before you start: unlike invariants.sql,
these scripts seed licences for the REAL ingest scripts, which read
LICENCE_ID/LICENCE_ID_ZONING/LICENCE_ID_PERMITS as module-level constants. You cannot
just rename the ids without deciding how the loader learns which licence to cite.
Report that decision before writing it — a jurisdiction-free parameter on the loader is
a shared-primitive change and CONVENTIONS.md says scope creep is reported, not absorbed.

Second half, per CLAUDE.md's "both halves" rule: a fix at the source does not clean a
database that already has the bad rows, and 0027 makes licence immutable so no
migration can. Say explicitly which databases are affected, query the actual
observed_at/cleared_by/cleared_at columns on them to put the before-state on record,
and state that rebuild is the only remedy. Do not rebuild anything without asking.

--- 5. Report, do not build: source-scoping ---
scripts/ingest_zoning_permits.py:564-571 and :884-891 build their `live` map with no
source_id filter; scripts/ingest_parcels.py:1108-1120 joins fact with no source_id
filter. fact_one_current_per_source is unique PER SOURCE, so a second source holding a
live fact for the same (parcel, field) makes the dict an arbitrary pick and can make
this source skip a write it owed. 0044 catches the cross-source SUPERSESSION but not
the silent wrong-comparison.

Latent today — one source per field. Report whether adding `AND source_id = %s` to all
three is a safe, behaviour-preserving change on the current data (prove it: the counts
must be identical before and after), or whether it belongs with P4's own scoping work.

--- 6. Low-severity sweep, batch into one commit, no design decisions ---
  - SCRATCHPAD hardcoded machine-specific absolute path in ingest_parcels.py:94,
    ingest_zoning_permits.py:139, flag_invalid_geometry.py:99. run_p5_acceptance.sh:30
    and run_phaseb_acceptance.sh:31 grep it out of the source — whatever you do must
    keep those two working or fix them in the same commit.
  - core/store.py:30,39 still say "14-tuple" after the widening to 17 the same
    docstring describes. core/ is blocklist-scanned by
    build/check_jurisdiction_names.py — re-run it against the real tree after editing,
    per CONVENTIONS.md's planted-input rule.
  - .importlinter:16 names build/check_boundary_grep.py; the file is
    build/check_jurisdiction_names.py.
  - scripts/ingest_parcels.py:1004 comment corrupted: "is sufinvariant to prove that".
  - scripts/ingest_parcels.py:998 `have_prior_identities` assigned, never read.
  - scripts/migrate_baseline.py:127 and migrate_verify.py:77 build the reference URL
    with rsplit("/", 1); both already have parsed_url() available.

--- Before you start ---
Check the actual GitHub Actions run for de61f53 — both db.yml and docs.yml — not a
local re-run. prompts/README.md's "both CI gates green" claim is pinned to 4c66d2d,
which is five commits behind and predates 0047, core/exceptions.py's new helpers and
flag_invalid_geometry.py's changes. Do not start on an assumed-green tree.

--- When you are done ---
prompts/README.md's P5 line claims the same-snapshot safety property is "proven in the
acceptance suite itself". Correct that line: it was not, for permits.active. Add the
P11 row to the package table, and add rows to the Open findings table for whatever
steps 3 and 5 leave unfixed.
```

---

### 3. In plain terms

**1(a)** is a filing clerk who, every morning, finds no new permits for a property,
pulls yesterday's card that already says "no active permit", stamps it *superseded —
the world changed*, and files a fresh card that says "no active permit". The cabinet
grows forever and every card in it claims something happened. Nothing happened.

**1(b)** is the auditor who checks that the top card in the drawer says "no active
permit". It does. The auditor signs off, every time, and never looks at how many cards
are underneath.

**1(c)** is the same clerk being handed a form where the parcel number reads `27704???`
— the county's own marker for *we haven't worked this one out yet* — and copying it
into the ledger as though `27704???` were the parcel's number. The house rules
(`db/README.md`) say in as many words: when the number is a placeholder, file a query,
not a number. The margin note next to the code even says it isn't doing that. It is.

**1(d)** is a test rig that, on a clean machine, stamps the real licence file
"cleared by: test" — on the one document the entire project is currently blocked
waiting for a lawyer to actually sign. It only does it on a machine where nobody has
signed yet, which is every machine. And the file is written in ink.

**1(e)** is filing by property and field but not by *who told you* — fine while there
is exactly one informant, and quietly wrong the first day there are two.
