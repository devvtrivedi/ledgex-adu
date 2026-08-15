## P9 — closing a `parcel_exception` when its condition clears

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)).

### Why this package exists

[P8-exception-resolution-undefined.md](P8-exception-resolution-undefined.md) reported the
finding and three open questions, deliberately not built. Report-before-writing already
happened there. This package is the follow-through — with three corrections to P8's own
draft recommendations, made before drafting, and one design question P8 didn't reach that
has to be settled before the migration is written, not after.

### Corrections to P8's recommendations

**a) The new `exception_outcome` value is `condition_cleared`, not `superseded`.**
`superseded` is this codebase's word for a *fact* replaced by a successor that
`supersedes_fact_id` points at — the row is gone but its replacement is findable. A closed
exception has no successor. The condition didn't get replaced by a newer observation of the
same kind; it just stopped being true. Reusing `superseded` would hand the next reader a
`supersedes_fact_id`-shaped expectation — "follow the pointer to what replaced this" — that
`parcel_exception` cannot satisfy, because there is nothing to point at. `condition_cleared`
says exactly what happened and invites no such expectation.

**b) No `resolved_by` convention.** `parcel_exception_outcome_resolution_biconditional`
(0010/0015, `db/schema.sql:976`) already requires `resolved_by IS NOT NULL` for any
non-`open` outcome — that constraint is untouched by this package, so `resolved_by` still
has to carry something. The question P8 raised was whether that something needs a
*documented convention* to signal "a machine did this, not a person." It doesn't: once
`condition_cleared` exists, the outcome column alone answers that question unambiguously —
only a detector will ever write it. `resolved_by` gets the writing detector's `detector_key`
because that is the true, correct answer to "who resolved this," not because a convention
says to encode machine-vs-human there. Nothing new is being documented; the existing column
is just being filled in honestly.

**c) The limit of inline closure, stated up front, not discovered later.** "The detector
closes its own exceptions" only works for a detector that recomputes a full, current
classification every run and can therefore tell "still true" from "no longer true." That is
not all four:

| `detector_key` | Writer | Full recompute every run? | Gets closure in this package |
|---|---|---|---|
| `zoning_spatial_join_unresolvable` | `load_zoning` (`scripts/ingest_zoning_permits.py`) | Yes — classifies the whole parcel set every run | **Yes** |
| `parcel_apn_unresolvable` | `ingest_parcels.py` | No — the resolvability-flip case is a documented, unhandled gap (`scripts/ingest_parcels.py:1094-1107`) | No — see Scope/OUT below |
| `parcel_geometry_invalid` | `flag_invalid_geometry.py`'s `flag_parcel_geometry` | Yes | No — see Scope/IN below (dedup only, not closure) |
| `zoning_source_geometry_invalid` | `flag_invalid_geometry.py`'s `flag_zoning_source_geometry` | Yes | No — see Scope/IN below (dedup only, not closure) |

Also correcting an earlier draft of this scope: `load_permits` (same file) **writes no
`parcel_exception` rows at all** — grep confirms it, and its own comment
(`scripts/ingest_zoning_permits.py:800-804`) says the unmatched-APN breakdown goes to
`job_run.schema_drift` instead, specifically because there is no parcel to attach an
exception to. There is nothing in `load_permits` to wire a close helper into. This package
touches `load_zoning`, not `load_permits`.

Do not build or describe this package as though it closes all four detectors' exceptions.
It closes one (`load_zoning`), and stops a crash in two more (`flag_invalid_geometry.py`),
without closing anything for those two or for the fourth.

### The open question P8 didn't reach: reopening

A condition clears (exception closes, `condition_cleared`), and later the *same* condition
recurs — same `parcel_id`, `detector_key`, `detector_version`, `reason`. `0045`'s partial
unique index only constrains `WHERE outcome = 'open'`, so the new row is unconstrained by
it and inserts cleanly. Nothing links it to the row it followed. Over enough cycles, one
parcel's history with one detector is a set of unlinked rows that happen to share a key,
and nothing says which closed row a given reopening followed — cheap to decide now, while
zero rows exist under any outcome but `open`/`unresolved`/`confirmed`/`false_positive`;
expensive to reconstruct later by timestamp-guessing once real rows with real gaps exist.

**Decision: add `parcel_exception.reopened_from_id uuid REFERENCES parcel_exception(id)`,
nullable, one hop back** — same shape as `fact.supersedes_fact_id`, which links a fact to
its immediate predecessor, not the whole chain. Set exactly when a fresh `open` row is
about to be written for a `(parcel_id, detector_key, detector_version, reason)` that
matches an existing, non-`open` row — pointing at the most recently `resolved_at` one.
Scoped to an *exact* key match, deliberately: `0045`'s own header already argues a
`detector_version` bump opens a fresh finding rather than fighting an old one for the same
slot, and cross-version reopening linkage (which of possibly several old versions' closed
rows a new version's finding "follows") is a harder, separate question — not decided here,
not needed for `load_zoning`'s current single live `detector_version` (`2.0`).

This is a schema change: new enum value, new nullable FK column, explicit `CONSTRAINT` name
(`parcel_exception_reopened_from_fk`, matching `0043`'s `<table>_<column>_fk` style). No
change to the existing biconditional or detected/resolved-ordering CHECK constraints —
both are already generic over any non-`open` outcome and any resolution timestamp, and
`condition_cleared`/`reopened_from_id` don't need either constraint to know about them
specifically.

### The prompt

```
P9: exception resolution. Report-before-writing already ran (P8, then this file) -- build
from here, don't re-litigate the three corrections above or the reopening decision. If you
find a reason one of them is wrong, stop and say so before writing code; don't quietly
work around it.

--- 1. Migration ---
One migration, next number after whatever's current. Two statements that don't conflict
with the ALTER-TYPE-ADD-VALUE-can't-be-used-same-transaction rule (0031's precedent),
because neither the new enum value nor the new column's own definition references
'condition_cleared' in a DEFAULT or CHECK within this migration -- confirm that reasoning
holds before combining them, don't assume it from this paragraph:

  ALTER TYPE exception_outcome ADD VALUE 'condition_cleared';

  ALTER TABLE parcel_exception ADD COLUMN reopened_from_id uuid;
  ALTER TABLE parcel_exception ADD CONSTRAINT parcel_exception_reopened_from_fk
      FOREIGN KEY (reopened_from_id) REFERENCES parcel_exception (id);

IRREVERSIBLE the same way 0031 is (no DROP VALUE) -- carry its §12/§3.13 change-record note
forward the same way, don't skip it because 0031 already set the precedent once.

--- 2. Shared close-and-relink helper ---
core/exceptions.py already owns insert_exceptions, called by every detector. Add the
closure side there, not duplicated per caller. Given (detector_key, detector_version, and
the set of (parcel_id, reason) pairs the CURRENT run found still true -- the same shape
existing_open already computes in load_zoning), it should, in one set-based UPDATE (not a
per-row loop):

  - close every currently-open row for that (detector_key, detector_version) whose
    (parcel_id, detail->>'reason') is NOT in the still-true set: outcome =
    'condition_cleared', resolved_at = clock_timestamp(), resolved_by = detector_key.

And on the insert side (still batched, not per-row): before writing a fresh open row for a
(parcel_id, detector_key, detector_version, reason), check for the most recently resolved
non-open row at that exact key and set reopened_from_id to its id if one exists.

--- 3. Wire into load_zoning only ---
load_zoning already computes existing_open (scripts/ingest_zoning_permits.py:635-680) and
the full current classification (zero_match, ambiguous, matched-with-anomaly) every run --
that IS the still-true set the closure helper needs, already sitting in memory. Call the
helper in the same transaction as the existing exception writes, after computing it, before
commit.

Do NOT wire it into load_permits -- it writes no parcel_exception rows, confirmed by grep,
nothing to close. If you find one, that contradicts this package's own investigation --
stop and report rather than building around it.

--- 4. flag_invalid_geometry.py: dedup guard only, not closure ---
flag_parcel_geometry and flag_zoning_source_geometry build exception_rows unconditionally
every run with no existing_open check -- confirmed: a second run against an unchanged
population hits 0045's unique index and raises UniqueViolation, crashing the job_run
instead of no-op'ing. Give both the same existing_open pre-check load_zoning already has
(query open rows for that detector_key/detector_version, skip parcels already in it). Do
NOT add closure to these two sites in this package -- table above already states why
(scope decision, not a technical blocker). A rerun should no-op cleanly on an unchanged
population; a parcel whose geometry becomes valid keeps its stale open exception until a
later package gives these two closure too.

--- 5. Evidence, RED-first on all of it ---
  a) Reproduce the flag_invalid_geometry.py crash BEFORE fixing it. Run either detector
     function twice in a row against a database already carrying its own prior output.
     Predict UniqueViolation, then show it. Fix, then show the second run no-op cleanly
     with a printed count (0 new rows).
  b) Reconstruct the P5 acceptance run's own empirical case -- a parcel zero-match under
     one zoning snapshot, ambiguous under the next -- against PRE-P9 code first. Show
     both exceptions sitting open simultaneously, confirming the staleness P8 described is
     still real right up to the point this package changes it.
  c) Same case against POST-P9 code: the zero-match exception must close
     (condition_cleared, resolved_by = 'load_zoning' or whatever detector_key literal
     load_zoning actually uses -- check it, don't assume the string) when the parcel
     becomes ambiguous instead. The ambiguous exception opens fresh, not linked (different
     reason -- reopened_from_id must be NULL here, this is not a recurrence, it's a new
     problem under the same detector).
  d) The reopening case: take a closed (condition_cleared) exception, drive the SAME
     parcel back into the SAME reason on a later run, confirm the fresh open row's
     reopened_from_id points at the closed row's id.
  e) No spurious closure. Predict before running, same discipline as P5's changed=0: a
     same-snapshot rerun of load_zoning must close zero exceptions. Run it, show the
     count.
  f) Run every suite twice, and once against a fresh migrations-only database, per
     CONVENTIONS.md. New tests in db/tests/invariants.sql (T75 onward), RED against pre-P9
     code, GREEN after. Raise the pass floor (currently 91, db/tests/invariants.sql:4173)
     by exactly the number of new tests added -- don't guess the count before you know how
     many you wrote.

--- 6. After it lands ---
Add the APN-resolvability-flip gap (scripts/ingest_parcels.py:1094-1107, out of scope here
per this package's own corrections) as its own row in prompts/README.md's open-findings
table if it isn't already tracked there as this package's spinoff -- it's a reconciliation
gap in ingest_parcels, not an exception-resolution gap, and needs its own package.

--- Hard rules ---
prompts/CONVENTIONS.md applies in full, including the CI-green precondition on whatever
commit this starts from. No further schema changes beyond the one migration in section 1 --
report before writing if the design turns out to need more. Do not touch
parcel_apn_unresolvable, ingest_parcels.py's reconciliation logic, or give
flag_invalid_geometry.py closure -- all explicitly out of scope, all next packages.
```

### In plain terms

**Why `condition_cleared` and not `superseded`.** This codebase already has a word,
`supersedes_fact_id`, for "here's what replaced it, go look." An exception that closes
because the problem went away has nothing to hand you — there's no replacement to follow.
Calling it `superseded` would be answering a question ("replaced by what?") that a closed
exception can't answer, using the one word in this codebase already trained to expect an
answer.

**Why closure only reaches one detector.** A detector can only tell you a problem is gone
if it looks at the *whole* current picture every time, not just the new arrivals. Three of
the four do that; the fourth (`parcel_apn_unresolvable`) only ever looks at what's new, so
it has no way to notice something old got fixed — that's a different, harder problem
(giving it the whole-picture view), not this package's problem (deciding what to do once
you have one).

**The reopening link.** Think of it like a return visit to a doctor for the same
complaint. If nothing connects today's visit to the one three months ago that resolved,
the record just shows two unrelated appointments, and nobody reading it later can tell
"resolved, recurred" from "two coincidentally similar problems." One line — "follow-up
to visit #—" — is cheap to write at the time and answers a question that's expensive to
answer by guessing afterward.
