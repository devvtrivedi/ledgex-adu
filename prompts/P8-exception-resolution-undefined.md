## P8 — nothing resolves a `parcel_exception` when its condition stops being true

Not an engineering task yet — a confirmed finding, recorded so it is not re-discovered
from scratch. Report only; do not fix inside P5 or any other package until this is
actually scheduled and reasoned through on its own terms.

### What is actually wrong

`0045` (P5) added a partial unique index — `(parcel_id, detector_key, detector_version,
detail->>'reason')  WHERE outcome = 'open'` — so the same detector can't write the same
open finding twice for the same parcel. That is a real fix for duplication. It is not a
fix for staleness, and the two are different problems: the index stops a *second* open
exception for an *unchanged* condition; it does nothing when the condition itself changes
and the exception is now describing something that is no longer true.

Confirmed empirically, not reasoned, during P5's own acceptance run: a parcel classified
`zero-match` under one zoning snapshot (open exception, reason `no_containing_district`)
became `ambiguous` under the next (open exception, reason `multiple_containing_districts`,
a *different* reason, so `0045`'s index does not block it). Both exceptions are open
simultaneously. Nothing in the schema or in `load_zoning`'s new reconciliation logic ever
transitions the first one out of `open` — it is not literally true anymore (the parcel is
no longer zero-match; it is ambiguous), but it is not `false_positive` either (it was a
correct reading of the snapshot at the time), and it is not `confirmed` or `unresolved` in
any sense those words carry elsewhere in this codebase. It just stays `open`, forever,
describing a state that no longer holds.

This is not limited to zoning's own detectors. Every `parcel_exception`-writing detector
in this codebase (`zoning_spatial_join_unresolvable`, `zoning_source_geometry_invalid`,
`parcel_geometry_invalid`, `parcel_apn_unresolvable`) has the same shape: a condition is
detected, an exception is opened, and nothing anywhere ever closes it when a later run
finds the condition gone.

### The actual open questions

1. **What does "resolved" mean for a detector-written exception?** `exception_outcome`
   (0010) has four values: `open`, `confirmed`, `false_positive`, `unresolved`. None of
   these was written with "the underlying condition changed on its own, with no human
   involved" in mind — `confirmed`/`false_positive`/`unresolved` all read, from their
   names and existing usage, like outcomes of a human or process *reviewing* an open
   exception, not outcomes of a machine re-observing the same parcel later and finding
   the problem gone. Using one of them for automatic closure would be reusing a value for
   a meaning it wasn't given, the same shape of problem P4 found and fixed for
   `confidence_rule_id` (a column meaning "which rule assigned this confidence" being
   used to carry "why this fact exists"). A new value, or a new column, may be the
   honest answer — not decided here.

2. **Is resolution a write by the detector itself, or a separate pass?** The detector
   (e.g. `load_zoning`) already has, on every run, exactly the information needed to know
   an old exception's condition no longer holds — it just computed the current
   classification. Closing the exception inline, in the same transaction that writes the
   new fact or the new exception, is the cheapest place to do it correctly. The
   alternative — a separate reconciliation pass over all open exceptions, re-deriving
   whether each one's condition still holds — duplicates detection logic in a second
   place and can drift from it. Leans toward "the detector closes its own exceptions,"
   not decided here.

3. **Do `resolved_at`/`resolved_by` (0010, `parcel_exception_outcome_resolution_biconditional`
   from 0015) already carry the right shape for this?** `resolved_by` is `text` — free
   text today, used so far (per the schema) for a human operator's identifier. A
   detector auto-resolving its own exception would need to write *something* there
   (`resolved_by = 'load_zoning'`? a version string?) that is honest about "a machine
   closed this, not a person," and distinguishable from a human's resolution if anyone
   ever wants to ask that question later. Whether the current `text` column is
   sufficient for that, or whether the biconditional and the column's own history
   assume a human on the other end, is not checked here.

### Why not fixed here

P5's own mandate is zoning/permits reconciliation; this problem existed before P5, is not
made worse in kind by it (only newly *visible*, because `0045` stopped exceptions from
silently re-duplicating and made the empirical case above producible), and touches every
detector in the codebase, not just zoning's. A real fix needs its own reasoning about
what "resolved" means, argued on its own terms — not folded into a package that was never
about this.
