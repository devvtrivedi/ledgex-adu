## P13 — The APN resolvability flip: findings #17 and #22, one package

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Design already argued across
two independent passes (P11 1(c), P9's own scoping note for #17) and confirmed to be one
unit, not two — not re-litigated here. `db/README.md`'s "An unresolvable `parcel.apn` is
an exception, not a fact" section is the rule this package enforces.

---

### 1. What was wrong (recap — full detail in P11 §1(c) and README findings #17/#22)

`scripts/ingest_parcels.py`'s `phase_e`, CHANGED branch:

- Never called `is_unresolvable_apn` — a resolvable APN degrading to a `'?'`-placeholder
  or blank was written as a live `parcel.apn` fact (the placeholder string, or JSON
  `null`), violating `db/README.md`'s explicit rule. **#22.**
- `changed_rows` INNER-joined a live `parcel.apn` fact, so a parcel with none — every
  currently-unresolvable parcel — could never enter the query: a resolve-again transition
  was undetectable (**#17**), and its geometry changes were silently dropped forever (the
  other half of #22).

---

### 2. What was built

**Step 1 — CI first.** `scripts/run_phaseb_acceptance.sh`/`check_phaseb_acceptance.py`
were referenced in neither `db.yml` nor `docs.yml` — the same gap P12 closed for the P5
suite, and this package touches exactly the path that suite covers. Ran it first,
predicted green (P4's own domain, untouched since), confirmed green (`exit 0`, `ALL
ASSERTIONS PASSED`) before any wiring or code change. New `phaseb-acceptance` job added to
`db.yml`, modeled on `p5-acceptance` (98cbda4). Proved the gate can fail on the real
runner: pushed a deliberate break (`apn_changed = False`, unrelated to this package's real
fix), confirmed `phaseb-acceptance: failure` on GitHub Actions, reverted in the immediately
following commit, confirmed green again. See `prompts/README.md`'s P13 entry for the run
IDs.

**Step 4 (built before 2/3 — RED needs the fixtures to exist first) — RED-first.** Four
synthetic features added to `db/fixtures/phaseb/phaseb_A.geojson`/`phaseb_B.geojson`
(`99999003`–`99999006`), covering every combination: resolvable→placeholder→resolvable,
resolvable→blank→resolvable, never-resolvable-with-a-geometry-change, and
unresolvable→resolvable→unresolvable-again (the only shape that can exercise a real
close-then-reopen cycle within this suite's A→B→A structure, needed to test
`reopened_from_id`). New assertions in `check_phaseb_acceptance.py` for fact
presence/value, the `parcel.apn` cache column, exception open/`condition_cleared` state,
and `reopened_from_id`. RED against current code, real output: `'99999003???'` and JSON
`null` landing directly as live `fact.value`, `99999005`'s geometry silently
unsuperseded, `99999006` never resolved. (The pre-existing "exactly 3 parcels got a
changed-field successor" assertion legitimately became "exactly 4" — worked out and
documented inline why each new parcel does or doesn't contribute, not asserted by
inspection.)

**Steps 2/3 — the fix**, one commit:
- Degrade: supersede with no successor, raise `parcel_apn_unresolvable` (reusing the
  existing `detector_key`/`detector_version`, not a second detector), `parcel.apn` cache
  → `NULL` via the existing cache-update path. Ordering unchanged — inside the existing
  supersede-before-insert sequence.
- `changed_rows`: `fa` (parcel.apn) → LEFT JOIN, `fg` (parcel.geometry) stays INNER
  (always present). The changed-predicate is a `CASE`, not a bare `IS DISTINCT FROM` —
  worked out for all four (fact present/absent × incoming resolvable/unresolvable)
  combinations explicitly; a bare comparison would false-positive on "fact absent,
  incoming still unresolvable." Verified on real data (`ledgex_schema_check`, 225K
  parcels): simulated a same-snapshot self-comparison through both the OLD and NEW query
  shapes, scoped through `source_feature_identity` the way the real query is — **0 rows
  both ways**, zero false positives introduced.
- Resolve: new fact (no supersession — nothing was live), closed via a **new**
  `core/exceptions.close_exceptions_for_parcels()`, not the existing
  `close_resolved_exceptions()`. Checked first, per instruction, whether the existing one
  applies unchanged — it does not: `close_resolved_exceptions` needs a full
  `still_true_pairs` recompute to safely close-by-exclusion, which `load_zoning` has
  (reclassifies every parcel every run) and `phase_e`'s CHANGED branch does not (P9's own
  scoping note for #17 already said so — the reason this was deferred, not an accident).
  Passing an incomplete set would have closed every *other* open
  `parcel_apn_unresolvable` exception in the database. The new function needs no
  inference: the caller already knows, per `parcel_id`, that the condition cleared this
  run. `relink_reopened_exceptions()` reused **unchanged** — general-purpose by
  construction, no recompute needed.

GREEN, three times as required (twice seeded, once fresh migrations-only): all 57
assertions each run, including `99999006`'s `reopened_from_id` pointing at the *original*
A-era exception, not the intermediate resolved state, not `NULL`.

---

### 3. Step 5 — before-state, remediable, not touched without asking

Queried every locally reachable database for the actual damage pattern (a live
`parcel.apn` fact whose value contains `?` or is JSON `null`) before proposing anything:

```sql
SELECT f.id, f.value, jsonb_typeof(f.value) FROM fact f
WHERE f.field_key = 'parcel.apn' AND f.superseded_at IS NULL
  AND (f.value::text LIKE '%?%' OR jsonb_typeof(f.value) = 'null');
```

**Result: 0 rows, on every database checked** — `ledgex_schema_check` (225K real parcels,
the database CLAUDE.md names) and every scratch database on the tier-2 syntax server
(`current_seed_check`, `ingest_scratch`, `ledgex_phase_a_0808`, `seed_after`,
`seed_before`, `old_seed_check`, `old_seed_check26`). None carry the contamination. One
database remains unchecked — the Supabase instance in `.env`'s `DATABASE_URL`, no network
reachability from this environment, already tracked as finding #23 and not duplicated
here.

**Remediation, proposed but not run, per instruction:** unlike the licence contamination
in #23 (immutable table, rebuild-only), this *is* remediable without rebuilding — for any
row matching the query above: supersede it with no successor (the exact mechanism this
fix now uses going forward), raise the same `parcel_apn_unresolvable` exception the fix
would have raised at write time, and set `parcel.apn` cache to `NULL`. A single guarded
`UPDATE`/`INSERT` pair, legal under `0007`/I4 (superseding is the one legal `UPDATE` on
`fact`) — not run here, and not needed on any database currently reachable, since none
show the pattern. If the Supabase database is ever confirmed to carry it, this same
remediation applies there too — ask first.

---

### 4. Findings #17 and #22 — closed

See `prompts/README.md`'s Open findings table and P13 package-table row for the real-runner
evidence (commit SHAs, CI run IDs, `phaseb-acceptance`'s status when first run).
