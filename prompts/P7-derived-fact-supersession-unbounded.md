## P7 — `0044`'s derived-fact exemption is unbounded

Not an engineering task for this repo yet — a confirmed finding, recorded so it is not
re-discovered from scratch. `0044` is deliberately not touched.

### What is actually wrong

`fact_supersession_target_validate()` (0042, extended by 0044) checks, for every fact
`NEW` with `NEW.supersedes_fact_id IS NOT NULL`:

1. same `(parcel_id, field_key)` as the target,
2. the target's `superseded_at` is actually set,
3. **only if `NEW.source_id IS NOT NULL`** — the target's `source_id` matches `NEW`'s.

Check 3 is the whole fix 0044 exists for, and it is skipped entirely whenever
`NEW.source_id IS NULL` — a derived fact. 0044's own header argues this is safe because
"`fact_input`/I5 already governs whether a derivation may legitimately draw on that
target." That is true of what a derivation may **compute from**. Nothing connects it to
what a derivation is **allowed to supersede** — those are two different questions, and no
constraint, trigger or FK ties `fact.supersedes_fact_id` to `fact_input.input_fact_id` at
all.

### Confirmed, not reasoned

Against a database with the trigger correctly installed and verified working (a
same-shape cross-source **retrieved** supersession was rejected first, as a sanity
check), a derived fact was constructed whose *sole* `fact_input` row pointed at an
unrelated `permits.active` fact, and which superseded an unrelated `zoning.district`
fact from a different source entirely. It committed cleanly. No error, no warning,
nothing in the schema noticed. Reproducible: see the P5 session record for the exact
statements (real `ca_san_jose.zoning_districts` / `ca_san_jose.building_permits_active`
facts, rolled back afterward — no lasting change).

### Why not fixed here

Out of scope for P5, which touches zoning and permits reconciliation, not the
supersession invariant itself. A real fix needs its own reasoning about what "derived
from X, may supersede Y" should actually require — likely: `NEW.supersedes_fact_id` must
be reachable from `NEW`'s own `fact_input` rows, directly or transitively — which is a
schema change and its own migration, argued on its own terms, not folded into a package
that was never about this.
