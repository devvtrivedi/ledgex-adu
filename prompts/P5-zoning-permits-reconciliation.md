## P5 — Zoning and permits reconciliation

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)).

### Why this package exists

P3 gave `ingest_parcels.phase_e` real reconciliation. P4 retracted its cross-source reach
and made `0044` enforce same-source supersession. `load_zoning` and `load_permits` were never
touched: P4 step 4 established that both raise `UniqueViolation` on
`fact_one_current_per_source` against any changed snapshot, roll back cleanly and mark
`job_run` failed. Safe, but it means two of three sources cannot re-ingest at all.

Both are same-source-on-both-sides, so `0044` is satisfied by construction and the
supersession machinery from P3 is reusable unmodified. The difficulty is elsewhere: the two
sources have completely different disappearance shapes, and neither matches parcels'.

### The three traps

**Zoning recomputes everything, every run.** `load_zoning` classifies the entire parcel set
on each execution — 214,903 currently matched. A naive recompute-and-write supersedes all of
them every run, fabricating ~215,000 supersession events that never happened and permanently
poisoning `supersession_reason` as a signal. The unchanged path must be an explicit, counted
no-op. This is the single largest risk in the package.

**`zoning.district_verbatim` is legitimately absent sometimes.** P2's fix skips rather than
fabricates it when `ZONINGABBREV` conflicts among polygons agreeing on `ZONING`. So a parcel
can hold a live `district` fact and no `verbatim` fact at all. Each field has three states,
not two: absent, present-and-same, present-and-different.

**Permits are matched by canonicalised APN, and APN is not identity** (`0034`, 49 collisions).
A permit's parcel match can move between snapshots without the permit itself changing.
Disappearance has to be computed over the permit source's own identity, if it has one.

### The prompt

```
P5: zoning and permits reconciliation. Push first -- 62cf90f, 46a24c2 and a62b4a7 are
still local and origin/main is at 6cebdaf. Commit prompts/ with them.

--- 1. Three carried items, before any new code ---
  a) The transaction-size argument is not like-for-like. The 675,063-fact precedent was
     INSERT-only; a zoning republish is UPDATE + INSERT per changed fact -- different
     lock footprint, more WAL, and dead tuples a pure insert never creates. Separately,
     REFRESH MATERIALIZED VIEW CONCURRENTLY over ~429,000 changes is a cost outside the
     transaction entirely. Re-ground the "no chunking needed" conclusion on evidence of
     the right shape, or measure it. It may well still hold -- I want it to hold for a
     reason.
  b) P4 changed the parcel-disappearance exception from coverage_gap/info to
     record_to_ground/warning. State that as a decision: why record_to_ground rather
     than coverage_gap, and whether anything gates on severity. If nothing does today,
     say so -- "inert today" is a fine answer, "nobody checked" is not.
  c) 0044 exempts derived facts (source_id IS NULL) from the source-match rule, on the
     argument that fact_input/I5 governs them. T70 shows derived supersession still
     works; it does not show it is BOUNDED. Show me what stops a derived fact
     superseding an arbitrary cross-source retrieved fact, with a test. If nothing
     does, that is a finding -- report it, do not quietly widen 0044.

--- 2. Zoning: report before writing ---
load_zoning classifies the whole parcel set every run. 214,903 parcels currently carry
a live zoning.district fact. If your diff supersedes unchanged classifications you will
fabricate ~215,000 supersession events and destroy supersession_reason as a signal
permanently -- 0017 means you cannot take them back.

Report your unchanged-detection before writing, and the count it produces on a re-run
of the SAME snapshot. Expected: changed 0, superseded 0. Predict it, then run it.

Then handle each field independently. zoning.district_verbatim is skipped, not
fabricated, when ZONINGABBREV conflicts (P2), so a parcel may hold a live district fact
and NO verbatim fact. Three states per field -- absent, same, different -- not two.

And distinguish the transitions, which are not symmetric:
  - matched -> matched, same value      : no-op
  - matched -> matched, different value : supersede + successor
  - matched -> zero-match               : supersede, NO successor, no_containing_district
  - matched -> ambiguous                : supersede, NO successor, and NOT the same
                                          reason as zero-match -- say which
  - zero-match/ambiguous -> matched     : NEW fact, not a supersession. There is nothing
                                          live to supersede. Getting this wrong raises
                                          0042's target-retirement check, so it will
                                          fail loudly -- confirm that it does.

Detector reruns creating duplicate open exceptions is a standing open finding and
zoning re-runs are the whole point of this package. Answer it here: does a second
reconcile of the same snapshot produce a second open exception for the same parcel?

--- 3. Permits: report before writing, separately ---
This is where P3's original "permits.active -> explicit false" bullet actually belongs.
Same source on both sides, so 0044 is satisfied and it is now honest: a permit dropping
out of the active list IS evidence that it is no longer active.

But first: does ca_san_jose.building_permits_active have a stable per-permit identity in
its own bytes? Report it. Permits are currently matched to parcels by canonicalised APN,
and APN is not identity (0034, 49 collisions) -- so a permit's parcel match can move
between snapshots without the permit changing. If disappearance can only be computed
over the parcel join rather than over the source's own identity, that is a finding and I
want it before you build on it, not after.

permits.series_earliest is an aggregate over a parcel's permit rows. Say what it means
for it to change when one row of the series disappears.

--- 4. Acceptance ---
A->B->A for each source, separately, on the same terms as P3: twice against a seeded
scratch DB, once against a fresh migrations-only DB with no seed. Fixtures committed,
hashes computed at run time.

Write the assertions against what SHOULD be true, then run them against pre-P5 code and
show them red. An acceptance test written after the implementation is what F2 was.

Report before/after counts for every category, from output. Do not infer any category
from arithmetic.

--- Hard rules ---
prompts/CONVENTIONS.md applies in full. No schema changes beyond what reconciliation
genuinely requires -- report any before writing. Never change a constraint to make a
test pass. If something is impossible as specified, stop and report it.
```

### In plain terms

**Zoning's trap.** Every run, the zoning job re-classifies all 215,000 lots from scratch —
it doesn't read a list of changes, it recomputes the whole map. If you treat "I computed this
again" as "this changed," you draw a line through every entry in the ledger and rewrite it
identically, every single run. The ledger fills with 215,000 corrections that correct
nothing, and the record of what genuinely changed is gone for good — you can't erase them
afterward. Recomputing a value and observing a new one are different events and the code has
to tell them apart before it writes anything.

**Zoning's asymmetry.** A lot that stops having a clear zone and a lot that starts having one
are not mirror images. Stopping means retiring an entry you already have. Starting means
writing a fresh one — there's nothing to retire, and if the code tries to retire something
anyway it'll be pointing at nothing.

**Permits' trap.** Permits don't have their own house number — they're matched to a lot by
APN, and APNs aren't unique. So a permit can appear to move house without anything having
happened to it. Before you can say "this permit disappeared," you need to know whether the
source gives permits a name of their own. If it doesn't, "disappeared" isn't a question the
data can answer yet, and that's worth finding out before building on the assumption.
