## P4 — Source-scoped reconciliation

Blocked on the P3 review findings being accepted. Standard hard rules apply
([CONVENTIONS.md](CONVENTIONS.md)).

### What this package is for

P3 built reconciliation into `ingest_parcels.phase_e` and, in the disappearance branch,
reached across into `permits.active` and `zoning.district` — facts owned by other sources —
using the parcels snapshot, endpoint and licence as their provenance (P3 finding F1). P4
undoes that reach, establishes the rule that prevents it recurring, and gives zoning and
permits the reconciliation they still do not have (F3).

Order matters: F1 first, because it is currently unpushed and every day it stays in the
working copy is a day it might get pushed by accident.

### The prompt

```
P4: source-scoped reconciliation. Phase B (62cf90f) is still local -- do NOT push it
until step 1 lands on top of it.

--- 1. Retract the cross-source writes ---
ingest_parcels.phase_e's DISAPPEARED branch writes a permits.active=false fact and
supersedes a zoning.district fact. Both carry SOURCE_ID = ca_san_jose.parcels, the
parcels snapshot_id, ENDPOINT_URL and LICENCE_ID -- provenance from a source that did
not observe them.

A parcel absent from the parcels snapshot means the parcels source no longer confirms
that parcel. It is not evidence about permit status and not evidence about zoning.
Your own comment on the geometry/apn/source_parcel_id facts eleven lines above states
this correctly; apply it to permits and zoning too.

Remove both cascades. What a parcel disappearing SHOULD produce: the identity
retirement you already write, and one exception recording that a parcel with live
facts from other sources is no longer confirmed by its own source. That is an honest
observation. Choose its type and reason code and say why.

Also fix, in the same pass: the literal "parcel_absent_from_bulk_parcels_snapshot"
currently sits in the confidence_rule_id position. That column means "which rule
assigned this confidence level." Put the reason where reasons go.

--- 2. Close the invariant gap, before touching zoning or permits ---
Nothing in the schema stopped step 1's bug. fact_one_current_per_source is partial-
unique PER SOURCE, so a cross-source successor does not collide; 0042 validates parcel
and field match on supersession but not source.

Report first: should a supersession ever be allowed to cross source_id? Argue it
either way -- a genuine multi-source conflict resolution might legitimately need to,
and if so the constraint is wrong and an exception mechanism is right. I want the
argument, not the answer I am hinting at.

Then implement whichever you argued for, as a migration with an explicitly named
CONSTRAINT, and a test that goes RED against 62cf90f's code and GREEN after step 1.
That test is the point of this step: it must fail on the bug that already happened.

--- 3. Rewrite the acceptance test to be falsifiable ---
check_phaseb_acceptance.py asserts the cascade behaviour from step 1, including
"permits.active STILL false (not auto-restored by reappearing)". It was written after
the implementation and cannot fail on the thing that is wrong.

Rewrite the disappearance assertions against what SHOULD be true. Then prove the new
test can fail: run it against 62cf90f unchanged and show it red.

--- 4. Establish what zoning and permits actually do today ---
load_zoning and load_permits only insert. Predict, then run, then report: what happens
when each is re-run against a CHANGED snapshot on a database that already has facts
from an earlier one. Exit code and error text.

Do not fix it in this step. I want the failure documented before it is designed away --
if it turns out they silently produce two live facts for one parcel-field-source rather
than raising, that is a much worse finding than a constraint violation and it changes
what P5 has to do.

--- 5. Report before building anything further ---
Given steps 1-4, what does zoning reconciliation actually require? Zoning is a
classification job over the parcel set, not a per-feature load -- rows_in/rows_out are
already parcels, not zoning features. So "disappeared" for zoning means a parcel that
previously classified and now does not, which is a different shape from a source
feature vanishing.

Report the expected transaction size for a realistic zoning republish -- thousands of
facts in one transaction was the original question and it is still unanswered.

Do NOT implement zoning or permits reconciliation in this package. P5.

--- Also record ---
The §5 supersession_reason survey (LASTUPDATE constant for 205,380 of 225,039; PLANMOD
blank on 214,775; NOTES blank on 207,700; APNU_* the only real signal) belongs in the
spec with a version bump and a change-record row, not only in a session summary. It is
the evidence for why supersession_reason stays 'unknown', and the next person to ask
will otherwise re-derive it from scratch.
```

### In plain terms

**Step 1.** The parcels register and the permits register are kept by two different clerks.
A lot dropping off the parcels register tells you the parcels clerk stopped listing it. It
tells you nothing about whether the permits clerk still has an open permit — those are
different books, and the permits clerk never said anything. P3 had the parcels clerk write
"permit closed" into the permits book, sign it with the parcels stamp, and date it with the
day the parcels register was printed. Everything about that entry is wrong except the
intent, which was to keep the books consistent. Consistency isn't the clerk's to assert.

**Step 2.** The reason nobody caught it: the rule says "one live entry per lot per field
*per book*." Writing into someone else's book doesn't break that rule, because it's a
different book. So the guard was real and simply pointed the wrong way. Worth deciding
deliberately whether cross-book entries are ever legitimate before banning them — there are
cases where one register genuinely corrects another, and a flat ban would block those too.

**Step 3.** The exam was written after the answers. It asks "did the parcels clerk write
into the permits book?" and marks *yes* as correct. Rewriting it against what should be true,
then running it against the old code to watch it fail, is the only way to know it's an exam
at all.

**Step 4.** Two other loaders have never been asked what they do when the data changes
underneath them. Ask before fixing. If the answer is "they refuse loudly," that's a small
problem. If the answer is "they quietly write a second live entry," the register has been
lying and that changes everything downstream.
