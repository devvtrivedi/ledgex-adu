## P3 — Phase B: changed / new / disappeared

This is the handoff's §9 prompt, corrected for what the code actually does now. Two things
changed since it was written:

1. **The "changed" detector never compares values.** `phase_e` L921–929: if a feature's
   identity already exists and the snapshot isn't the previous successful one, it increments
   `unsupported_changed` and moves on. It has not looked at a single field. So today's
   refusal count is "features that *might* have changed," not "features that changed" — you
   have no baseline number to check Phase B's output against.
2. **Disappearance detection has nowhere to run.** `existing_feature_ids` is built and never
   read. There is no parcel staging table; the only staging precedent in the repo is the
   session-scoped `TEMP TABLE zoning_staging` in `ingest_zoning_permits.py` L360.

Also note `phase_e` accumulates every parcel, fact and exception row in Python lists before
inserting. Moving set-difference into the database, as §9 requires, is a real change to that
shape, not an addition to it.

### The prompt

```
Phase B: changed / new / disappeared. P1 and P2 verified and pushed first.

--- 1. Report before writing ---
  a) Refresh-failure path -- P1 changed this. Restate what the "previous successful
     job_run" anchor now does with facts from an interrupted run, in terms of the
     fix as landed, not as planned.
  b) Supersede-then-insert ordering. fact_one_current_per_source is a partial
     unique index on WHERE superseded_at IS NULL. The old fact must be retired
     before its successor is inserted. execute_values batches do not give you
     per-row statement boundaries. Confirm your batching respects this and show
     the statement sequence you will actually emit.
  c) There is no changed-value baseline today. phase_e increments
     unsupported_changed on identity presence alone -- it never compares a field.
     Before building supersession, produce the real number: for a given incoming
     snapshot, how many features have at least one field whose value differs from
     the current fact. That number is what the acceptance test in step 4 checks
     against, and it does not exist yet.
  d) Staging. Set difference must run in the database, not in Python. Say where
     the staging table lives, whether it is TEMP like zoning_staging or durable,
     and what happens to it if the run dies halfway.

--- 2. Build the three cases ---
Changed: supersede the current fact, insert the successor with supersedes_fact_id
and supersession_reason='unknown'. 0042's parcel/field-match and target-retirement
checks apply.

New: parcel + source_feature_identity + initial facts. No supersession.

Disappeared:
  - permits.active -> explicit false fact superseding the true one
  - zoning -> supersede the old fact with NO successor (legal, I4b permits it)
    and raise the coverage_gap exception you already build
  - do NOT invent false values for geometry or any non-boolean field
  - source_feature_identity gets retired_snapshot_id / retired_at /
    retirement_reason -- 0043's pairing constraint requires all three or none

--- 3. Transaction shape ---
Staging may commit separately if it holds no durable domain truth; all ledger
writes in one transaction. Report expected transaction size for a realistic zoning
republish, which could change thousands of facts at once. phase_e currently holds
every row in Python memory before inserting -- say whether that survives Phase B
or has to change, and do not quietly change it without saying so.

--- 4. Acceptance test ---
The A->B->A case that currently REFUSES must now succeed:
  - load A, load B, load A again
  - after B: changed facts superseded with successors, counts matching the number
    from 1(c) -- not matching a number you compute the same way twice
  - after the second A: B-era facts superseded, A values current again -- confirm
    this is a NEW fact row with its own id, not a resurrection of the original
  - permits that disappeared in B have explicit false facts
  - a parcel absent from B has its zoning fact superseded and a coverage_gap
    exception raised
  - full suite green, current_fact refreshed, job_run successful
Run the whole thing TWICE. Then run it against a fresh migrations-only database
with no seed. Both, separately, with output.
Construct B synthetically if the real source has not moved -- say so clearly and
show how you built it.

--- 5. After it lands ---
Report what LASTUPDATE, PLANMOD and NOTES contain on the features that genuinely
changed. That is the raw material for a real supersession_reason rule, and it is
the first time it will exist.

--- Hard rules ---
No schema changes beyond what reconciliation genuinely requires -- report any
before writing. Ingest freeze stays partially in force. Never change a constraint
to make a test pass. If something in here turns out to be impossible as specified,
that is a finding: stop and report it rather than engineering around it.
```

### In plain terms

**The set-up.** You keep a permanent ledger of everything you've ever observed about every
lot in San José. You never erase a line. When something turns out to be different, you draw
one neat line through the old entry, write the date you retired it, and add a new line
underneath pointing back at the old one. Right now the ledger can only be *started* — hand
it a second, different delivery of data and it refuses to write anything, because nobody has
taught it how to retire a line.

**Why it refuses so bluntly today.** The clerk currently checks only whether he has seen a
lot's ID before. If he has, and the delivery isn't the exact same one he already filed, he
throws his hands up — without ever opening the folder to see if anything inside actually
changed. So "1,200 changed" really means "1,200 folders I declined to open." That's why
step 1(c) exists: before you can grade Phase B's homework, someone has to actually open the
folders and produce the true number.

**The three cases.**

*Changed* — the lot is in both deliveries but a value moved. Line through the old, new entry
underneath, arrow pointing back.

*New* — a lot appears that was never there. Fresh page, no arrows.

*Disappeared* — this is the subtle one, and it splits in two. A building permit that vanishes
from the "active permits" list has genuinely told you something: it isn't active any more.
You can write that down as a fact — `active = false`. But a lot that vanishes from the
zoning file has told you *nothing about its zoning*. Maybe the city just didn't publish it
this week. So you retire the old entry and write **nothing** in its place, and raise a flag
that says "we have a hole here." The rule the prompt is protecting: never invent a value to
fill a silence. "I don't know" is a legitimate ledger state; a made-up shape is not.

**Why the comparison has to happen in the database.** Two lists of 225,000 items, and you
need to know which appear on the old list but not the new. You could carry both lists to
your desk and tick them off by hand — that's what Python does today, and it means holding a
quarter of a million things in your head at once. Or you can lay both lists side by side on
the table and let the database do the crossing-off. Same answer, and the table doesn't get
tired.

**Why A → B → A is the test.** Load one delivery, load a changed one, then load the original
again. The trap: when the original values come back, a lazy implementation "un-crosses" the
first line — pretends the retirement never happened. That's forgery. The correct answer is a
*third* entry that happens to say the same thing as the first, with its own new ID and its
own timestamp. The test checks the ID specifically, because both versions look identical if
you only check the value.

---


---

## Review findings — added after `62cf90f`, before it was pushed

Verified at `62cf90f`. P1 and P2 confirmed landed and pushed (`3bee5bd`, `40b953d`,
`bd5db19`, `6cebdaf`); the history split is clean and `origin/main` is at `6cebdaf`.
Phase B itself is local-only. **Do not push it as-is.**

What is genuinely good: the supersede-then-insert ordering was verified in both directions
against the real index rather than reasoned about; the changed-count baseline was computed
by SQL diff against `fact` rather than `current_fact` (correct — `current_fact` can be
stale); the staging table is TEMP and in-transaction; the reappeared case was found by
testing rather than by design, and `source_feature_identity`'s primary key really does
force row reuse; the acceptance run covers a seeded scratch DB twice and a fresh
migrations-only DB once, with fixtures committed and hashes computed at run time.

### F1 — The parcels loader writes other sources' facts (blocking)

`scripts/ingest_parcels.py` L1262-1270, in the DISAPPEARED branch:

```
fact_rows.append((
    parcel_id, JURISDICTION_ID, "permits.active", json.dumps(False), "bulk",
    SOURCE_ID, snapshot_id, retrieved_at, ENDPOINT_URL,
    LICENCE_ID, FACT_CONFIDENCE, "parcel_absent_from_bulk_parcels_snapshot",
    ...
```

`SOURCE_ID` is `ca_san_jose.parcels`. So a `permits.active` fact is written carrying the
parcels snapshot, the parcels endpoint URL and the parcels licence, superseding a fact that
came from `ca_san_jose.building_permits_active`. Four separate problems:

1. **Semantic.** A parcel feature vanishing from the parcels file is not evidence about
   whether a permit is active. The prompt's "permits.active -> explicit false" described the
   *permits source reconciling its own snapshot* — a permit dropping out of the active list.
   This asserts a permits fact on parcels evidence, which is the "do not invent values to
   fill a silence" rule broken on a different axis than the one it was written to guard.
2. **Rights.** The false fact inherits `LICENCE_ID` (parcels) for a `permits.*` field.
   Under I3/I6 the licence on a fact governs which channels may render it, and the permits
   source has its own (`LICENCE_ID_PERMITS`).
3. **No invariant catches it.** `fact_one_current_per_source` is partial-unique *per source*,
   so a cross-source successor does not collide. 0042 validates parcel and field match on
   supersession, not source. This is a gap in the invariant suite, not only in this code.
4. **`confidence_rule_id` is carrying a reason string.** The literal
   `"parcel_absent_from_bulk_parcels_snapshot"` sits in the `confidence_rule_id` position
   where every other call site passes `FACT_CONFIDENCE_RULE_ID`. Proxy drift: a column
   meaning "which rule assigned this confidence" now holds a disappearance reason.

The zoning half has problems 1-3 too — it supersedes a `zoning.district` fact owned by the
zoning source — though it correctly writes no successor.

The comment directly above this block states the right principle for
geometry/apn/source_parcel_id ("the source no longer confirms this parcel... nothing in this
pass claims they are now wrong, only that we no longer observe them") and then does the
opposite for permits and zoning eleven lines later. The asymmetry is the tell.

**Note on cause:** the P3 prompt was ambiguous here. Its DISAPPEARED bullets listed permits
and zoning without saying "each source reconciles its own snapshot," and the agent resolved
that ambiguity in the cascade direction. Half a prompt defect.

### F2 — The acceptance test encodes F1

`scripts/check_phaseb_acceptance.py` L76-99 and L168-173 assert exactly the cascade
behaviour above, including "permits.active STILL false (not auto-restored by reappearing)".
The test was written to match the implementation, so it cannot fail on the thing that is
wrong. This is the fourth shape in CONVENTIONS.md.

### F3 — Zoning and permits still cannot reconcile at all

`scripts/ingest_zoning_permits.py` changed by 8 lines in `62cf90f`, all of them padding
fact tuples from 15 to 17 columns. So `load_zoning` and `load_permits` still only insert.
What happens when either is re-run against a changed snapshot is unestablished — most likely
a `fact_one_current_per_source` violation, but that is a prediction, not a finding. Establish
it before P4 designs around it.

### F4 — Unanswered from the P3 prompt

- **Transaction size for a realistic zoning republish** (§3). Not reportable while zoning
  reconciliation does not exist, but it was asked and should be recorded as deferred rather
  than dropped.
- **Fact-level vs feature-level counts.** 1(c) reports 3 changed *features*. Each feature
  carries up to three facts. The acceptance criterion was "counts matching the number of
  genuinely changed values" — give both numbers.
- **Exception duplication on re-run.** A known open finding, and the disappearance path now
  raises `coverage_gap` rows. State whether a second reconcile of the same snapshot produces
  a second open exception for the same parcel.
- **`supersession_reason` is `'unknown'` everywhere.** Correct per the prompt, and the §5
  survey now shows why: LASTUPDATE is a bulk-import timestamp for 205,380 of 225,039 rows,
  PLANMOD is blank on 214,775, NOTES blank on 207,700. The `APNU_*` codes are the only real
  signal and are not enough. Record that conclusion in the spec rather than only in a
  session summary, or it will be re-derived from scratch later.

### F5 — Reappearance erases the disappearance from the identity table

`source_feature_identity`'s PK forces row reuse on reappearance, which is right. But clearing
`retired_at` (required — `source_feature_identity_retired_after_seen` fails otherwise once
`last_seen_at` advances) means the row no longer records that the feature was ever retired.
0043 describes the table as "append-and-retire operational identity state." An un-retire is
neither. The fact ledger still holds the supersession, so the event is not lost outright —
but identity history is now only reconstructable by joining out to facts. Decide whether that
is acceptable and write the decision down; do not leave it as a side effect of a constraint.
