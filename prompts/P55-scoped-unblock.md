# P55 — scoped unblock: open specific channels under I6 without faking diligence (Phase 1: design)

Scope: **design only.** No migration, no seed change, no composer change, no ingest change,
no licence row, no database drop, in this commit. The only file this pass creates is this
one. All findings below are dated 2026-08-22, database `ledgex_schema_check` unless stated
otherwise, queried via the Docker `ledgex` Postgres container that backs it.

## 0. The owner's ask, quoted back

> Implement the separately scoped unblocking pass. Preserve `written_confirmation_pending`
> as an independent diligence/evidence status, while making the specifically approved output
> channels eligible under I6. Existing facts must become viewable. Do not represent written
> confirmation, evidence, counsel approval, `cleared_by`, or `cleared_at` as completed.
> Preserve CC BY 4.0 attribution requirements and default-deny for all other
> sources/channels. First verify/fix the L0 city-limits runtime prerequisite identified in
> P52, then propose the minimum immutable-data-safe mechanism for changing channel
> eligibility. Prefer rebuild/reseed/re-ingest from retained snapshots over weakening
> immutability triggers. Show the plan and tests before implementation.

Six hard constraints (C1–C6) follow directly and are treated as red lines throughout: C1
diligence independence, C2 owner-named channels only, C3 existing facts viewable, C4
attribution preserved, C5 immutability untouched, C6 plan-before-implementation (this
document).

## 1. Audit — every claim in the prompt re-verified against the live database

**Housekeeping first, per `CONVENTIONS.md`'s evidence rule ("run `make migrate-verify`
before citing any local database as evidence").** `ledgex_schema_check` was found **one
migration behind** — 55 of 56 applied, missing `0056_l0_gate_boundary_source.sql` (the
entire P53 L0 gate). This is exactly the recurring drift class `CONVENTIONS.md` already
names three prior instances of. Brought forward with `scripts/migrate.py` (`applied 1
migration(s)`), then re-verified: `MATCH — ledgex_schema_check's live schema is exactly what
its ledger claims. 56 migration(s) verified.` Every claim below is against the
now-caught-up database, not the stale one.

**Real counts, live:**
```
facts=1,135,140  parcels=225,388  snapshots=24
cc_by_4_0-licensed facts=1,106,852   cc0-licensed facts=27,936
```
Unchanged from P52's own figures — confirms no drift in the data itself, only in the
migration ledger.

**`make check-boundary`**, run after the catch-up: import-linter 5/5 kept, jurisdiction-name
grep passed, `qa_check.py` passed (`docs/LEDGEX_SPEC.md` v1.45, 0056 named). Green, as the
prompt predicted.

## 2. The L0 prerequisite

### 2.1 Is claim (d) true? — verified empirically, not reasoned to

Composed a real `ca_san_jose` parcel (id `7c7f853f-ae36-436e-b12b-520c8efd70e4`, apn
`47731014`) against the now-caught-up `ledgex_schema_check`:

```
$ python3 scripts/compose_property_file.py --parcel-id 7c7f853f-ae36-436e-b12b-520c8efd70e4 --election city
parcel 7c7f853f-ae36-436e-b12b-520c8efd70e4 (apn='47731014'): 3 touched facts
  parcel.apn                   licence=cc_by_4_0    value="47731014"
  parcel.geometry              licence=cc_by_4_0    value={...}
  parcel.source_parcel_id      licence=cc_by_4_0    value="67114"

property_file d4be3217-cf1c-4bbc-93d4-31d382c577ec -> refused (4 refusal(s), 3 touched facts linked)
  LICENCE_UNKNOWN: Jurisdiction 'ca_san_jose' declares boundary_source_id='ca_san_jose.city_limits'
    as the source that resolves its boundary, but no current jurisdiction.incorporated fact
    exists for this parcel -- default deny (§1.1, §9).
  GEOMETRY_TIER_DISABLED: ...
  RULE_UNAVAILABLE: ...
  RIGHTS_BLOCKED: Licence cc_by_4_0 forbids channel paid_property_file for touched field(s):
    parcel.apn, parcel.geometry, parcel.source_parcel_id.
```

**Claim (d) is TRUE, verified, not assumed.** `LICENCE_UNKNOWN` fires on a real parcel,
independent of the other three refusals. Since `ca_san_jose.city_limits` can structurally
never produce a fact (§2.2 below), this refusal fires for *every* `ca_san_jose` parcel,
*every* channel, *forever*, regardless of what any `licence_channel` row says. Opening
channels changes nothing on the composer path (Surface B) while this holds.

### 2.2 The minimum honest fix (Q2.2)

The only path that satisfies the gate rather than removing it is D-A
(`prompts/P53-l0-gate.md` §3): a real, verified city-limits endpoint → a `source` row with
`method='direct'`/`'bulk'` → a real ingest writing `jurisdiction.incorporated` facts.

**No such endpoint was found or verified in this pass.** This pass did not attempt network
discovery of one — that is real, separate work (P53 §11 already scoped it as a
pre-paid-output precondition, not a P55 task) and finding one is not achievable inside a
design-only pass regardless. **This is the finding, stated plainly: D-A is not deliverable
here, and P55 cannot open Surface B (the composer) as a consequence — see §3.**

### 2.3 The chain nobody had written down — verified, not merely asserted

Even if a real `jurisdiction.incorporated` fact existed, would it clear L0 for real? Tested
directly against `core.rights.evaluate_rights_gate` — no database write, a pure read of the
live `licence_channel` table:

```python
touched = [('fake-fact-id', 'jurisdiction.incorporated', 'unknown', True)]
for channel in KNOWN_CHANNELS:
    print(channel, evaluate_rights_gate(cur, touched, channel))
```
```
free_snapshot       -> allowed: {'unknown': False} | blocked: {'unknown': ['jurisdiction.incorporated']}
paid_property_file  -> allowed: {'unknown': False} | blocked: {'unknown': ['jurisdiction.incorporated']}
api                 -> allowed: {'unknown': False} | blocked: {'unknown': ['jurisdiction.incorporated']}
bulk_export         -> allowed: {'unknown': False} | blocked: {'unknown': ['jurisdiction.incorporated']}
analytics           -> allowed: {'unknown': False} | blocked: {'unknown': ['jurisdiction.incorporated']}
model_training       -> allowed: {'unknown': False} | blocked: {'unknown': ['jurisdiction.incorporated']}
```

**Confirmed exactly as the prompt's Q2.3 predicted.** A `jurisdiction.incorporated` fact,
even if real, is *itself a touched fact* under I6 (I1.1: the gate covers every touched fact,
not only rendered ones) — and it would cite licence `'unknown'` (0056's own source row), all
six `licence_channel` rows for which are `allowed=false` (0056's own seed). So satisfying L0
with a real fact does not open the composer path; it swaps `LICENCE_UNKNOWN` for
`RIGHTS_BLOCKED` at the identical stage the fact resolves. **The chain, refusal code at every
link:**

```
no jurisdiction.incorporated fact exists       -> LICENCE_UNKNOWN  (L0, today)
      |  (D-A: real endpoint + real ingest, not attempted here)
      v
jurisdiction.incorporated fact exists,
citing licence 'unknown'                        -> RIGHTS_BLOCKED   (L8, would replace L0's refusal)
      |  (a SEPARATE decision: identify city_limits' real licence,
      |   open a channel for it, exactly the same shape this pass
      |   is proposing for parcels/zoning/permits)
      v
jurisdiction.incorporated fact exists, citing
an identified, channel-eligible licence         -> composer proceeds past L0/L8 for this fact
```

The composer stays closed on Surface B regardless of anything this pass does. This is not a
gap in this pass's design — it is a structural fact about the repo today, and it directly
shapes §3's scope.

### 2.4 The forbidden shortcut, named and refused

`jurisdiction` carries **no immutability trigger** (confirmed directly: no
`jurisdiction_no_update`/`jurisdiction_no_delete` exists anywhere in `db/migrations/`, the
same grep P53 already ran). `boundary_source_id` is an ordinary mutable column. **`UPDATE
jurisdiction SET boundary_source_id = NULL WHERE id = 'ca_san_jose'` would silently switch
the L0 gate off in one statement and "unblock" the composer.** This is explicitly rejected.
Weakening a guardrail to make a downstream task easier is exactly what `CONVENTIONS.md`'s
first hard rule forbids ("never change a constraint, test or threshold to make something
pass"), and P53 built this gate *specifically* so that clearing `cc0`/`cc_by_4_0` could never
silently reopen output on its own — reversing it here to reopen output a different way is the
same violation with different paperwork. **Not proposed, not implemented, not left as an
implicit option anywhere below.**

## 3. The two-surface asymmetry

Verified directly, both surfaces:

**Surface A — the viewer.** `api/main.py`'s `get_parcel_facts()`: `grep -n
"boundary_source_id\|jurisdiction.incorporated\|LICENCE_UNKNOWN" api/main.py` returns
**zero matches**. This route calls `evaluate_rights_gate` only — I6, and nothing else. No L0
check exists on this path, confirmed by absence, not inferred from design intent.

**Surface B — the composer.** `_compose()`'s own success path, quoted verbatim
(`scripts/compose_property_file.py:679-687`):

```python
if not refusals:
    print(f"\nRIGHTS GATE PASSED for channel={channel!r}: every touched fact's licence "
          f"permits this channel, and no geometry-dependent conclusion was refused. "
          f"No property_file written -- composing a real file (rendering, payload "
          f"assembly, a success/partial path) is out of scope for this minimal "
          f"composer. ...")
    return Result.ok(NOTHING_COMPOSED)
```

**No property_file row is ever written when the gate passes.** Confirmed, not assumed.

### 3.1–3.2 Consequences, stated plainly

Opening channels cannot produce a composed property file in this pass — not because L0
blocks it (though it also does, §2), but because **the success path does not exist at all**.
Building one is separate, larger work; not smuggled into P55. Therefore **C3 ("existing
facts must become viewable") is achievable in this pass ONLY on Surface A** — the viewer.
This needs the owner's explicit confirmation that Surface A is what "viewable" was meant to
cover, rather than an assumption carried forward silently.

### 3.3 An owner question, not a decision made here

If `'api'` opens while L0 stays unsatisfiable (§2.2's own finding — it will, for the
foreseeable term), the viewer will render facts for a parcel the composer would refuse at L0.
**Two output surfaces then disagree about the same jurisdiction's own boundary-resolution
status.** Two readings, presented without a pick:

- **Acceptable.** The L0 gate is about boundary-resolution *correctness* for output that
  claims to be a finished product (a Property File); the viewer is an internal,
  localhost-only tool with no auth and no customer, already labeled
  `INTERNAL TESTING ONLY` in its own header. Showing facts there was never a claim that the
  parcel's jurisdiction is confirmed — it is a raw-data read, gated only by rights, same as
  it already behaves for every other channel today.
- **Not acceptable.** A future reader of the viewer (an internal team member, sales, support)
  could reasonably read "facts visible" as "this parcel is composable," which is false. If
  the two surfaces are meant to agree about jurisdiction correctness, the viewer would need
  its own L0-shaped check — a real code change, not attempted here, and its own design
  question if the owner wants it (does the viewer refuse-and-render-nothing for an
  L0-unsatisfied parcel, or render facts with a banner naming the gap?).

**Left for the owner (§9).**

## 4. The mechanism

### 4.1 Immutability constraints, re-confirmed by reading the trigger bodies directly

- `licence`: `licence_no_update`/`licence_no_delete` (0027) — unconditional `RAISE`, no
  carve-out (read the function bodies directly, not the comment describing them).
- `licence_channel`: `licence_channel_no_update`/`licence_channel_no_delete` (0033) — same
  shape. `INSERT` stays legal. PK is `(licence_id, channel)` — an `INSERT` for
  `('cc_by_4_0', 'api')` with `allowed=true` collides on that PK; the existing
  `allowed=false` row can be neither updated nor deleted to make room.
- `fact`: `fact_no_update`/`fact_no_delete` (0007/0017/0040) — a fact's `licence_id` can
  never be repointed once written.
- `source`: **no immutability trigger** — confirmed directly (no `source_no_update` exists
  anywhere in `db/migrations/`). `source.licence_id` is an ordinary mutable column. This was
  also 0056's own finding, re-confirmed here independently.
- Ingest constants, read directly: `scripts/ingest_parcels.py:88` `LICENCE_ID = "cc_by_4_0"`;
  `scripts/ingest_zoning_permits.py:134` `LICENCE_ID_ZONING = "cc_by_4_0"`;
  `scripts/ingest_zoning_permits.py:141` `LICENCE_ID_PERMITS = "cc0"`.

Put together: a new `licence_channel` row for the *existing* `cc_by_4_0`/`cc0` ids is not a
path (PK collision, immutable). Repointing an *existing* fact's `licence_id` is not a path
(fact immutable). The only legal path is a **new licence id**, fresh `licence_channel` rows
under it, `source.licence_id` repointed (source is mutable), the ingest constants updated —
and then, because **C3 requires existing facts to become viewable and no existing fact can
ever be repointed**, a **rebuild**: drop, reapply every migration, reseed, re-ingest from
retained snapshots. This is CLAUDE.md's own documented conclusion for this exact shape
("once a table is immutable ... the only remaining answer is to rebuild"), reached
independently here rather than only cited.

### 4.2 Q3.1 — the new licence ids

Two new rows needed, mirroring the two real licences that source real, currently-blocked
facts: one for the CC BY 4.0 material (parcels, zoning), one for the CC0 material (permits).

**Recommended: `cc_by_4_0_api_2026_08` and `cc0_api_2026_08`.**

Argument: `cc0`/`cc_by_4_0`/`unknown`/`sj_portal_terms` etc. are all short, undated ids —
but none of them has ever needed a *second* row for the *same underlying licence text*.
0027 makes every future re-scoping (a different channel, a later date, a reversed decision)
its own new row, forever — so an id that does not encode *which* scoping decision it is
would become ambiguous the moment a second one exists. Encoding the channel and the
year-month of the decision (not a package number — "P55" means nothing to a reader in 2028;
a date is a durable fact) keeps every future row self-describing without relying on `notes`
alone. This is a naming convention proposal, not a technical requirement — flagged as an
open question (§9) in case the owner prefers different style.

### 4.3 Q3.2 — every column, field by field (both rows have identical shape; `cc0` differs
only in `restriction`/`attribution_text`/`terms_url`)

```sql
-- cc_by_4_0_api_2026_08
id:                'cc_by_4_0_api_2026_08'
display_name:      'CC BY 4.0 (api channel, scoped 2026-08)'
restriction:        'attribution'                 -- unchanged; same licence text
commercial_use:      'allowed'                      -- unchanged; matches the real CC BY 4.0 terms
redistribution:      'allowed'                      -- unchanged
attribution_text:    'Data © City of San José'      -- carried forward AS-IS from cc_by_4_0's own
                                                     -- row; see §6.5 for whether the owner wants
                                                     -- it corrected AT rebuild time (the cheap
                                                     -- moment) -- not corrected by default, not
                                                     -- fabricated here
terms_url:           'https://creativecommons.org/licenses/by/4.0/'   -- unchanged
evidence_uri:        NULL                            -- C1: nothing retained, unchanged
observed_at:          '2026-07-31'::timestamptz       -- SAME date as the original cc_by_4_0 row,
                                                     -- not today's date -- the LICENCE TEXT was
                                                     -- observed then and has not changed; this row
                                                     -- is a new SCOPE decision under those same
                                                     -- already-observed terms, not a new reading of
                                                     -- the licence. Fabricating today's date here
                                                     -- would falsely claim a fresh observation of
                                                     -- terms that were not re-read.
cleared_by:           NULL                            -- C1, non-negotiable
cleared_at:           NULL                            -- C1, non-negotiable
notes:                'Owner decision <rebuild date>: licence terms (CC BY 4.0) are identified
                       and permit this use (commercial use and redistribution both allowed per
                       the licence text itself). Opened for the api channel only -- viewer-only
                       display of already-ingested facts. Written confirmation, evidence and
                       counsel review remain outstanding (cleared_by/cleared_at/evidence_uri
                       NULL, deliberately) -- this row does NOT assert diligence is complete.
                       See prompts/P55-scoped-unblock.md and licence_channel.rationale (per
                       channel) for the authoritative per-channel decision text.'

-- cc0_api_2026_08 -- same shape, these three columns differ:
restriction:          'open'
attribution_text:     NULL
terms_url:            'https://creativecommons.org/publicdomain/zero/1.0/'
observed_at:          '2026-07-31'::timestamptz       -- same reasoning
```

`licence_attribution_present` (`restriction <> 'attribution' OR attribution_text IS NOT
NULL`) is satisfied for `cc_by_4_0_api_2026_08` (`attribution_text` is not null) and vacuous
for `cc0_api_2026_08` (`restriction = 'open'`).

### 4.4 Q3.3 — every `licence_channel` row, both new licences (identical shape)

```
api                 allowed=true
  rationale: 'Owner decision <date>: licence terms are identified and permit this use.
             Opened for viewer-only display (api channel) of already-ingested facts.
             Written confirmation / evidence / counsel review remain outstanding --
             this is NOT a diligence-complete signal. See prompts/P55-scoped-unblock.md.'

free_snapshot       allowed=false
paid_property_file  allowed=false
bulk_export         allowed=false
analytics           allowed=false
  rationale (all four, same text): 'Licence identification confirmed; counsel/owner
             sign-off Pending. No channel is cleared for output beyond the api-channel
             decision recorded above until sign-off completes.' -- deliberately echoing
             0030's own wording shape for the channels this decision did NOT touch, so a
             reader sees continuity with the pre-P55 posture on everything except api.
             paid_property_file additionally depends on the L0 gate (§2, still closed)
             and the boundary cross-check + counsel review P52 §10 / P53 §11 already
             named as its own preconditions -- unaffected by this pass either way.

model_training      allowed=false
  rationale: 'Denied pending review: no one has yet read [cc_by_4_0/cc0]'s terms as
             applied specifically to model-training use, separately from the api-channel
             decision above. Requires its own rationale before this can flip.' --
             UNCHANGED from 0032's own wording pattern, own independent reason, never
             inferred from the api decision (standing decision, restated per §9 below).
```

### 4.5 Q3.4 — the rebuild runbook

**Scope, per-database, named separately as required:**

| Database | Real data? | Rebuilt in this design? |
|---|---|---|
| `ledgex_schema_check` | Yes — 1,135,140 facts, 225,388 parcels, the actual San José dataset | **Yes — primary target** |
| `ledgex_smoke` | Yes, but small (40 facts, 21 parcels, from `make smoke-real` runs) | Recommended, same procedure, much cheaper |
| `ledgex_viewer` | No — P40/P42's synthetic demo fixture (`internal_test.*`), 3 facts | **No** — not real San José data, C3 does not apply |
| ~50 `p2x_*`/`p4x_*` scratch databases | No — disposable per-package test/scratch databases | **No** — irrelevant to C3 |

**A finding the runbook must account for, found by reading `job_run` directly rather than
assuming a single `--phase e` reproduces the current state:** `ledgex_schema_check`'s
1,135,140 facts came from **multiple ingest waves across two separate days**, not one clean
load. `job_run`, ordered by `started_at`:

```
2026-08-07 20:22  ingest_parcels_full  --phase e  snapshot 0216d539...  225,039 rows -> 225,039
2026-08-07 21:17  ingest_zoning                    snapshot eae7823...  225,042 rows -> 214,892
2026-08-07 21:22  ingest_permits                    snapshot 8f3328b5...  17,499 rows -> 8,322
2026-08-07 22:06  flag_invalid_geometry_parcels     (parcel_exception writes, not facts)
2026-08-07 22:06  flag_invalid_geometry_zoning      (parcel_exception writes, not facts)
2026-08-16 18:30–18:35  flag_invalid_geometry_*     (re-run, same shape)
2026-08-17 00:28  ingest_parcels_full  --phase e   snapshot b98138f0...  25 rows -> 25
2026-08-17 00:28  ingest_zoning                     snapshot 699ec193...  225,088 rows -> 522/443 (two runs)
2026-08-17 00:29  ingest_permits                    snapshot 70bf19c1...  2/3 rows -> 0
```
Confirmed by direct query (`SELECT snapshot_id, count(*) FROM fact WHERE field_key='parcel.apn'
GROUP BY snapshot_id`): two distinct `parcels` snapshots actually contributed facts
(224,985 + 25), similarly for zoning and permits. **A rebuild that runs only the single
largest `--phase e` call would reproduce most, but not all, of the real state.** The
honest, fully-reproducible runbook replays the `job_run` sequence in order, snapshot by
snapshot, not a single call.

**Runbook, `ledgex_schema_check` (primary):**

1. `make migrate-verify` against the live database — confirm still `MATCH` immediately
   before touching anything (this pass already found one instance of undetected drift; check
   again, don't assume the earlier catch-up is still current).
2. Snapshot-integrity pre-check (this rebuild performs, as a side effect, the byte-integrity
   re-verification P52 §8 listed as *not performed* in that pass — worth stating as a
   positive, not just a mechanical step): for each of the 24 real snapshot rows,
   `verified_snapshot_file()` (already built, `scripts/ingest_parcels.py`) re-downloads from
   `snapshot.object_uri`, re-hashes, and **raises** on any `content_hash`/`byte_size`
   mismatch. Run this for all 9 real (non-test) snapshot ids named above *before* dropping
   anything — confirms the rebuild's raw material is intact while the pre-rebuild database
   (and its ability to cross-check) still exists.
3. Take the current database offline from any consumer (`make local-down` if the viewer is
   bound to it — it is not; the viewer binds to `ledgex_smoke`, confirmed by `LOCAL_SMOKE.md`
   §2 — so this step is a no-op for `ledgex_schema_check` specifically, worth confirming
   rather than assuming, since a different rebuild target might not be so lucky).
4. Rename the live database aside rather than dropping outright, as the first, reversible
   step (`ALTER DATABASE ledgex_schema_check RENAME TO ledgex_schema_check_pre_p55_<date>`)
   — see §10 for why this, not `DROP`, is step one.
5. `createdb ledgex_schema_check`; `make schema DATABASE_URL=postgresql://.../ledgex_schema_check`
   — fresh migrations replay, 56 files, including 0056.
6. `make migrate-verify` — confirm `MATCH`, 56/56, before seeding.
7. Apply the **updated** `db/seeds/day4_sources.sql` (carrying the two new licence rows +
   twelve `licence_channel` rows, and the existing L0-gate content from P53) — one file,
   `ON CONFLICT DO NOTHING` throughout, matching the established pattern.
8. Confirm `source.licence_id` for `ca_san_jose.parcels`/`zoning_districts` now reads
   `cc_by_4_0_api_2026_08` and `building_permits_active` reads `cc0_api_2026_08` (the seed's
   own `source` INSERT is updated to point at the new ids — this is the "ingest constants
   updated" half of Q3.1/4.1, landing in the seed alongside the licence rows since `source`
   is what ingest scripts actually read `LICENCE_ID` from at write time, not the Python
   constant directly — **confirm this precisely in Phase 2**, it is stated as design intent
   here, not verified against ingest code's exact read path in this pass).
9. Re-ingest, replaying the exact `job_run` sequence found in step 2 above, snapshot by
   snapshot, in the same order: `scripts/ingest_parcels.py --phase e --snapshot-id
   0216d539...` (**a real, ~210MB, full-city ingest — flagged prominently as the single
   largest-blast-radius step in this whole runbook; not run in this design-only pass, and
   Phase 2 should run it with the owner aware it is happening, matching how every prior
   package in this arc has treated `--phase e`**), then the 2026-08-17 delta wave
   (`--phase e --snapshot-id b98138f0...`), then `scripts/ingest_zoning_permits.py --source
   zoning --phase load --snapshot-id eae7823...` and `--snapshot-id 699ec193...`, then
   `--source permits --phase load` for both permit snapshots, in the same relative order.
10. Re-run `scripts/flag_invalid_geometry.py` for parcels and zoning (writes
    `parcel_exception` rows, not facts — needed for full state parity, not for licence
    correctness).
11. `current_fact` refresh — see §4.6 immediately below; do this correctly the first time.
12. Verification queries: `SELECT count(*) FROM fact` (expect 1,135,140, matching the
    pre-rebuild count exactly — content-addressed snapshots reproduce byte-identical source
    data, so an identical fact count is the correct acceptance bar, not merely a
    sanity-check); `SELECT count(*) FROM fact WHERE licence_id IN ('cc_by_4_0_api_2026_08',
    'cc0_api_2026_08')` (expect 1,134,788, i.e. the original `cc_by_4_0`+`cc0` total);
    `SELECT count(*) FROM fact WHERE licence_id IN ('cc_by_4_0','cc0')` (expect **0** — the
    old ids should have zero facts in the rebuilt database, confirming nothing accidentally
    re-cited them); a live `GET /v1/parcels/{a real id}/facts?channel...` — actually the
    viewer's channel is fixed to `'api'` (D1) — confirming `facts[]` is now non-empty for a
    parcel that was `omitted_for_rights[]` before the rebuild.

**`ledgex_smoke`:** same procedure, far cheaper (21 parcels, 2 real snapshots at
`--phase d` scale, not `--phase e`) — recommended as the FIRST rebuild attempted in Phase 2,
specifically because its small size makes a failed or wrong rebuild cheap to diagnose and
redo before touching the 1.1M-fact database.

### 4.6 Q3.5 — `current_fact` refresh, confirmed safe, and already built correctly

`db/README.md`, read in full per this pass's own required reading: the *first* refresh after
a `make schema` bootstrap (migrations replayed in order, not a `pg_dump` restore) is safe
with `CONCURRENTLY` directly, because `CREATE MATERIALIZED VIEW` with no `WITH NO DATA`
populates the view immediately even at zero rows. **Checked whether the ingest scripts
already handle this correctly, rather than assuming the runbook needs to add logic for it:**
`scripts/ingest_parcels.py:795-804` already checks `pg_matviews.ispopulated` and falls back
to a plain refresh before `CONCURRENTLY` — this is already built, confirmed by reading the
code directly, and the rebuild runbook needs no special handling beyond running the existing
ingest scripts as designed.

### 4.7 Q3.6 — migration vs. seed, worked through, and the answer differs from P53's

P53's `boundary_source_id` needed **both** halves (a guarded migration for already-existing
databases, plus a seed fix for future installs) because `boundary_source_id` sits on a
**mutable** column — a guarded `UPDATE` could genuinely fix an already-seeded database in
place. **This pass's mechanism cannot use that path at all**, for the specific reason C3
exists: the new licence rows are new INTRODUCTIONS (seed's job, not a migration's — matching
P53 §6's own precedent argument, and cc0/cc_by_4_0/ca_san_jose themselves were never
introduced via migration either), but even if a migration inserted the new rows into an
**already-existing, non-rebuilt** database, that database's own 1.1M existing facts would
still cite the OLD `cc_by_4_0`/`cc0` ids — permanently, immutably — so C3 ("*existing* facts
become viewable") would remain unmet for that database regardless of whether the new rows
exist. **A migration only ever helps a database that is ALSO being rebuilt — and a rebuilt
database gets a fresh seed anyway, in the correct order, making a companion migration
redundant for this specific mechanism.** Conclusion: **seed-only, no migration** — a
structurally different answer than P53's, reached by working through the same "both halves"
question honestly rather than pattern-matching P53's own conclusion onto a mechanism that
doesn't share its shape.

(If a migration were added anyway — not recommended — every `CHECK` constraint would need an
explicit `CONSTRAINT <name>` per `CLAUDE.md`, and any `INSERT` naming a specific id would need
an existence guard per the same 0032 pattern P53 already used. Named for completeness, not
because this design calls for it.)

### 4.8 Q3.7 — the old rows, orphaned forever

Confirmed acceptable, matching 0033's own explicit design intent ("the old row's channels
stay false forever, an accurate record of what was believed at the time"). After a rebuild,
the old `cc0`/`cc_by_4_0` rows and their twelve `allowed=false` `licence_channel` rows would
have **zero** facts referencing them in the rebuilt database (verification query in §4.5
step 12 checks this explicitly) — they become pure historical record, still seeded (their own
`INSERT ... ON CONFLICT DO NOTHING` statements are not removed from `day4_sources.sql`, so a
brand-new install still gets the full lineage: both the original, fully-blocked rows and the
new, api-scoped ones). Nothing in `check_conformance.py` or elsewhere enumerates *all*
licence rows expecting them to be referenced — its own checks are scoped to *active sources'*
`licence_id`, which will point at the new ids post-rebuild. No breakage found; none expected.

## 5. Diligence and wording — C1 in mechanical detail

### 5.1–5.2 The wording trap, checked against the actual code, not assumed

`api/main.py`'s `derive_diligence()` is untouched by this design — reused exactly as built
in P52, and it already does the right thing: `cleared_by IS NULL` (true for both new rows,
by construction, C1) always yields `"written_confirmation_pending"`, regardless of
`licence_channel.allowed`. **Checked directly: does either of `get_parcel_facts()`'s two
reason-string branches (P52 Phase 2, `api/main.py:563-575`) render something false for a now-
`allowed=true` fact?** No — because that code only runs inside the `else` branch of `if
allowed_by_licence.get(licence_id, False):` (`api/main.py:545`). **Once a fact's licence is
`allowed=true` for the `'api'` channel, it goes straight into `permitted.append(row)` and
never reaches the reason-string logic at all.** The wording trap the prompt worried about
does not exist in the omitted-fact branch, because opened facts never reach that branch.

### 5.3 The gap that actually exists — found by checking, not assumed away

**A different, real gap, in the *permitted*-fact rendering, not the omitted one.** A
`permitted` row (`api/main.py:529-544`) carries `fact_id`, `field_key`, `value`, `licence_id`,
`source_id`, `snapshot_id`, `method`, `is_derived` — **no `rights_position`, no
`diligence`** at all; those are computed only for `omitted_for_rights` entries
(`api/main.py:549-552`, inside the same `else` branch). `viewer.html`'s own rendering,
confirmed by reading the template directly (`api/static/viewer.html:296-303`):

```js
facts.forEach(f => rows.push(`
    <tr class="fact-row allowed${f.is_derived ? ' derived' : ''}">
      ...
      <td><span class="pill pill-allowed">VISIBLE</span>${f.is_derived ? ' ... ' : ''}</td>
    </tr>`));
```

**A permitted fact renders a bare green "VISIBLE" pill and nothing else.** Once `'api'`
opens, a viewer looking at the Facts tab sees cc_by_4_0/cc0-licensed facts as plain
"VISIBLE" — with **no diligence indication anywhere on that row**, not hover-accessible, not
scroll-accessible. The only place diligence renders at all is the Rights tab (a different
tab, keyed by licence, not by fact) — a viewer would have to separately navigate there and
cross-reference `licence_id` to learn that written confirmation is pending. **This is a real
finding, per §5.3's own instruction: report it, propose wording/UI only if the finding
demands it.** It does. Not built in this pass (no code changes in Phase 1) — recorded as a
required Phase 2 UI change: the `permitted` row shape (`api/main.py:529-544`) needs
`rights_position`/`diligence` added the same way `omitted_for_rights` already carries them,
and `viewer.html`'s Facts tab needs a small pending-diligence badge next to "VISIBLE" for any
row whose diligence isn't `"cleared"`.

### 5.4 The escalation — reported, not absorbed

`licence_channel.allowed=true` while `cleared_by IS NULL` is exactly the shape §7.3 (via
0030's own header) currently frames as the thing default-deny exists to prevent — 0030's own
words: *"An open licence_channel row for a licence with no counsel/owner sign-off is exactly
the class of silent rights-broadening [immutability] exists to close."* This pass's whole
design is a **deliberate, owner-directed exception to that framing** — a real decision to
open a channel while sign-off is genuinely still pending, made explicitly rather than by
accident (the failure mode 0030 fixed). **Whether §7.3's own prose needs to change to
describe this new, intentional state is a real question this pass does not answer.** If the
owner concludes it does, that is a version bump and a §12 row (I17) — `CONVENTIONS.md`
reserves that for the owner explicitly. **Left red, reported here, not bumped, not quietly
satisfied.** (There is nothing to "leave red" mechanically — no CI check currently asserts
§7.3's prose matches runtime behavior — but the *spec's own claim* would be stale the moment
this pass ships, and that staleness is the thing being reported, the same shape
`CLAUDE.md`'s own recently-corrected claim was.)

## 6. Attribution — factual only

### 6.1–6.2 Verified live, and the drift is real and unrelated to this pass

`cc_by_4_0.attribution_text = 'Data © City of San José'` (live query, `day4_sources.sql:40`).
`docs/LEDGEX_SPEC.md` (four locations: lines 878, 905, 985, 1718) carries a **different**
string, `"Contains data from the City of San José."` — this drift predates P55, was already
found and recorded in P52 §10, and is unaffected by anything here; re-confirmed still present
after the P53 spec regeneration.

**A third string, found in this pass, not previously recorded:** `docs/LEDGEX_SPEC.md` lines
905 and 985 show `"attribution": ["Contains data from the City of San José."]` as an
**illustrative example payload** inside §4's own API documentation — a THIRD value, distinct
from both the seed's real string and the spec's own §7.2 prose, describing an
`attribution` array shape that `_compose()` never actually populates (§6.4). Recorded as a
new facet of the existing drift finding, not a new finding of its own.

### 6.3 Constraint, re-confirmed

`licence_attribution_present: restriction <> 'attribution' OR attribution_text IS NOT NULL`
— satisfied by `cc_by_4_0_api_2026_08`'s own row (§4.3).

### 6.4 The gap that matters most — verified directly, both places it could live

**Composer side, confirmed by reading the literal INSERT, not the surrounding prose:**
```python
"geometry_tier_used, refusals, omitted_for_rights, attribution,
 payload, payload_hash, delivered_at, compose_ms
) VALUES (
    %s, %s::jsonb, '[]'::jsonb, '{}',
    %s::jsonb, %s, NULL, %s
)
```
`'{}'` — a **literal empty array**, not a parameter, not derived from `payload["attribution"]`
(itself also hardcoded `[]` two lines earlier). Nothing anywhere composes a real attribution
string. This is moot for Surface B regardless, since §2/§3 already established the composer
never reaches a written row for `ca_san_jose` at all — but it means the gap would need
closing independently the moment a success path is ever built, whether or not this pass
happens.

**Viewer side (Surface A — the one that matters for this pass):** attribution renders in
**exactly one place**, confirmed by grep: `api/static/viewer.html:205`, the Rights tab's
`restriction === 'attribution'` note. **The Facts tab — where the actual now-visible facts
live — carries no attribution text anywhere near them.** The moment `cc_by_4_0_api_2026_08`-
licensed facts render as "VISIBLE" on the Facts tab (§5.3's own finding), the licence's
attribution *condition* is being met, at best, by a note on a different tab a viewer would
have to separately visit and cross-reference by `licence_id`.

### 6.5 Sequencing, and the question that is not this document's to answer

Because `licence` is immutable, correcting `attribution_text` for the NEW row is only free
*before* the rebuild lands (after, it costs a second rebuild — the identical sequencing
argument P52 §10 already made for the original `cc_by_4_0` row). **§4.3 carries the text
forward unchanged (`'Data © City of San José'`) by default** — not because it is judged
sufficient, but because inventing a "corrected" string here would be exactly the fabrication
C1's spirit forbids applied to a different field. **Whether the text is legally sufficient
for CC BY 4.0's own attribution convention is a question for counsel — P52 §10's own
five-element assessment (title absent, source-link absent, creator partial, licence-name-
and-link split across a separate column, indication-of-changes absent-and-arguably-
misplaced) stands unchanged and is not re-litigated here.** Neither this document nor its
author is a lawyer; that assessment is not a legal conclusion and is not presented as one.

### 6.6 The minimum surface that would actually discharge attribution on Surface A

Proposed, not built: a persistent, page-level (not per-row, not hover-only) banner on the
Facts tab, shown whenever any rendered fact's `licence_id` carries `restriction ===
'attribution'`, reading the same `attribution_text` the Rights tab already fetches — e.g. a
line above the facts table: *"Facts from this parcel include City of San José data under CC
BY 4.0 — attribution: [text]."* **Recommendation: precondition of opening `'api'`, not
deferred.** Argument: the whole reason this pass exists is to make previously-invisible
CC-BY-licensed facts visible; shipping that visibility *without* its own licence's stated
condition visible in the same place is a narrower, weaker version of "viewable" than what
was asked for, and the fix is small (a banner reading an already-fetched value) relative to
the rebuild it rides alongside. Not attempted in this pass; named as required Phase 2 scope
alongside §5.3's diligence-badge finding.

## 7. Test list — specified, not written

Each test: file, assertion, and the named RED condition.

**T1 — POSITIVE, C3's acceptance test.** File: a new `scripts/test_scoped_unblock.py` (or
folded into `scripts/test_viewer_rights_gate.py` if the owner prefers one file — proposed as
its own file since it asserts against rebuilt real data, not the P42 synthetic fixture that
file already owns). Assertion: `GET /v1/parcels/{a real, rebuilt ca_san_jose parcel id}/facts`
returns `facts[]` containing `parcel.apn`/`parcel.geometry` (previously in
`omitted_for_rights[]`, pre-rebuild). **Must run against the rebuilt `ledgex_schema_check` (or
`ledgex_smoke`), not a synthetic fixture** — the whole point is *existing* facts, not new
ones. Goes RED if the rebuild didn't happen, if `source.licence_id` wasn't repointed, or if
the new `licence_channel` row is missing/`false`.

**T2 — DILIGENCE INDEPENDENCE, C1's guard, the single most important test.** Same response:
assert `diligence` (surfaced via `GET /v1/rights` for the new licence id) is exactly
`"written_confirmation_pending"`. Goes RED if anything, anywhere, ever writes `cleared_by`
for the new licence rows — including accidentally, e.g. a copy-paste of `seed_
internal_test_licences.py`'s own pattern (which DOES set `cleared_by='internal_test_seed'`)
into the real seed.

**T3 — NEGATIVE CONTROL, CHANNEL SCOPE.** Modeled on P53 §7's three-fixture pattern
(negative / positive companion / untouched control — reused deliberately, it earned its
place). For the new licence: `free_snapshot`/`paid_property_file`/`bulk_export`/
`analytics`/`model_training` all still block a touched fact under it. Goes RED if any
channel besides `'api'` shows `allowed=true`.

**T4 — NEGATIVE CONTROL, SOURCE SCOPE, C2's guard.** A licence/source *outside* the approved
set (e.g. `sj_portal_terms`, or a `test.*` fixture licence) still default-denies on `'api'`.
Goes RED if opening the two named licences somehow widens `evaluate_rights_gate`'s behavior
for any other licence — it structurally cannot (the gate reads `licence_channel` per-id), but
this test exists to prove that rather than assume it.

**T5 — L0 SURVIVES.** `scripts/test_compose_l0_gate.py`'s existing negative control (fully-
cleared test licence, no `jurisdiction.incorporated` fact, composition still refuses
`LICENCE_UNKNOWN`) **must pass unmodified.** If it needs editing, that is scope drift —
report it, do not edit the test.

**T6 — IMMUTABILITY INTACT, C5's guard.** `UPDATE licence SET ... WHERE id = 'cc_by_4_0'` and
`UPDATE licence_channel SET allowed = true WHERE licence_id = 'cc_by_4_0' AND channel =
'api'` (the PK-collision path §4.1 already named as not-a-path) both still raise. Proves the
rebuild route was actually taken, not a trigger quietly loosened.

**T7 — ATTRIBUTION.** Depends on §6.6's outcome. If the banner is built: assert it renders
whenever a `restriction='attribution'` fact is present in `facts[]`. If deferred: a test
that asserts the CURRENT state honestly — e.g. "no attribution string appears anywhere in
the Facts tab's own DOM for a cc_by_4_0_api_2026_08-licensed fact" — so the gap is visible in
CI rather than remembered by someone.

**T8 — SCOPE-DRIFT SIGNAL.** Enumerated before Phase 2 runs, per P52's own honest-acceptance
precedent (every existing rights test passing unmodified was itself the proof nothing moved
that shouldn't have):

*Expected to pass unmodified:* `scripts/test_compose_l0_gate.py` (all four functions),
`scripts/test_compose_election.py`, `scripts/test_compose_geometry_tier_used.py`,
`scripts/test_compose_collision_invariant.py`, `scripts/test_compose_parcel_refusals.py`,
`.claude/hooks/test_guard_destructive.py`, `make db-test` (122/122, no invariant touches
licence/licence_channel content), `make conformance` (scoped to active sources' agreement
with the live DB — will pass once `source.licence_id` and the seed converge, but its *content*
doesn't change shape).

*Expected to change:* `scripts/test_rights_reporting.py`'s model_training-rationale and
no-fabrication tests may need a NEW parametrization for the new licence ids (existing
assertions about `cc0`/`cc_by_4_0` stay true and unmodified; NEW assertions get ADDED, which
is not the same as editing existing ones — call this out explicitly in Phase 2, since P52's
own acceptance bar was "unmodified," and adding parallel coverage for a new id is additive,
not a modification, but should be named rather than silently bundled).
`scripts/check_golden.py`'s own `seed_reference_rows()` uses the real `cc_by_4_0` id — does
NOT need to change (it seeds its own reference data independently of the real ingest-scoped
licence; confirm in Phase 2 rather than assume). `scripts/test_viewer_rights_gate.py`
unaffected (P42's own `internal_test.*` fixture, untouched by real-licence changes).

*Golden fixtures — the important one:* `tests/golden/*.json`'s `payload_hash` is byte-locked
over `_compose()`'s refusal detail. **Does this pass change any composed refusal?** No —
verified by §2/§3's own findings: `ca_san_jose` still refuses `LICENCE_UNKNOWN` at L0
unconditionally (nothing in this design touches `boundary_source_id` or the composer), and
the golden fixtures' own fixture parcels cite `cc_by_4_0` (the OLD id, per
`ingest_parcels.LICENCE_ID` at fixture-seed time — `check_golden.py`'s own
`seed_reference_rows()` is independent of the real seed) — unaffected. **If Phase 2 finds a
golden hash moving, that is unexpected and must be explained in one sentence before
`--bless`ing, per P53 Obstacle 4's own precedent — not assumed safe here, flagged as the
check to run first in Phase 2.**

`db.yml`'s CI job structure, re-confirmed by reading the workflow file directly rather than
trusting a description of it (`CLAUDE.md`'s own 2026-08-22 correction exists precisely
because someone didn't): the `schema` job's main database runs `db/seeds/day4_sources.sql`
between `make db-test` and `make golden`; the separate `ledgex_ci_p5` and `phaseb-
acceptance` databases stay migrations-only for their whole run, per their own step comments.
Unaffected by this design.

## 8. What this would not prove

1. That a rebuild actually reproduces `ledgex_schema_check`'s exact 1,135,140-fact state
   byte-for-byte — the runbook (§4.5) specifies replaying the real `job_run` sequence, but
   this pass did not execute it; the multi-wave history found there could still hide an
   ordering dependency not visible from `job_run` alone (e.g. a manual fixup between waves
   that left no `job_run` row).
2. That `source.licence_id`'s repointing is read correctly by every ingest code path —
   stated as design intent in §4.5 step 8, not verified against `scripts/ingest_parcels.py`'s
   exact source of truth for `LICENCE_ID` at write time (the constant, or the live `source`
   row, or both, and whether they could ever disagree).
3. That the attribution banner proposed in §6.6, if built, is legally sufficient — explicitly
   a question for counsel, never answered here.
4. That §3.3's asymmetry question has an answer at all — presented as a live, unresolved
   owner decision, not something this design silently picked a side on.
5. That every consumer of `licence_channel.allowed=true` elsewhere in this codebase (any
   future surface, not yet written) will correctly treat "allowed" and "diligence complete"
   as independent facts the way `api/main.py`'s current two routes do — only the two routes
   audited here are covered.
6. That the two new licence ids' naming convention (§4.2) is the one the owner wants —
   presented as a recommendation with its argument, not a foregone conclusion.
7. That opening `'api'` alone is sufficient to satisfy whatever the owner actually meant by
   "the specifically approved output channels" — §9 makes one recommendation and argues for
   it, but the channel selection is explicitly the owner's call, not resolved here.
8. That `ledgex_smoke` and `ledgex_viewer`'s own rebuild (or non-rebuild) treatment is
   correct for every purpose those databases serve beyond C3 — scoped narrowly to "does C3
   apply," not audited for every other use `make smoke-real`/P40's fixtures make of them.

## 9. Open questions for the owner

1. **§3.3.** Does the viewer need its own L0-shaped check once `'api'` opens, so the two
   surfaces agree about jurisdiction-resolution status — or is "gated by rights only,
   unchanged from today's behavior for every other channel" acceptable for an internal,
   localhost-only tool? Two readings presented in §3.3; no default assumed.
2. **Channel selection (§10 below).** This document argues for `'api'` alone. Confirm,
   expand, or redirect.
3. **§4.2.** Bless (or redirect) the `cc_by_4_0_api_2026_08` / `cc0_api_2026_08` naming
   convention, or propose different style.
4. **§4.3.** `observed_at = '2026-07-31'` (the original licence-text observation date, carried
   forward) — confirm this reading, or state a preferred convention if this pass's situation
   (a new SCOPE decision under already-observed terms, not a new terms-reading) should be
   dated differently.
5. **§6.5/§6.6.** Correct `attribution_text` at rebuild time (the one cheap moment), or carry
   it forward unchanged as this design defaults to? Build the Facts-tab attribution banner as
   a precondition of opening `'api'` (this document's recommendation), or defer it and ship
   T7 as an honestly-red gap instead?
6. **§5.4.** Does §7.3's own prose need a version bump to describe "allowed while diligence
   pending" as an intentional state, or does the existing text stand (read as describing the
   *default*, not forbidding a deliberate, recorded exception)? Escalated, not decided here.
7. **§4.5.** Confirm the `--phase e` re-ingest (the largest single step in the rebuild) is
   something the owner wants present for when Phase 2 actually runs it, given every prior
   package in this arc has treated `--phase e` as something to run deliberately, never
   casually.

## 10. Rollback

**If the rebuild goes wrong halfway** (a re-ingest fails partway through the multi-wave
sequence, a snapshot fails its integrity re-check, `current_fact` ends up in a bad state):

- **Step 4 of the runbook (§4.5) renames the live database aside rather than dropping it —
  this is the rollback mechanism, not a separate one.** `ledgex_schema_check_pre_p55_<date>`
  still exists, complete, with its own 55-then-56-migration history intact, for as long as
  the operator chooses to keep it. Recovery from *any* failure at *any* later step is: drop
  the half-built `ledgex_schema_check` (nothing valuable was ever written to it if the
  rebuild didn't finish — it was built from empty), rename
  `ledgex_schema_check_pre_p55_<date>` back to `ledgex_schema_check`, and the database is
  exactly where it was before this pass touched anything. **No data is destroyed until the
  operator deliberately drops the renamed-aside copy, which should not happen until the new
  build is verified (§4.5 step 12) and kept for some agreed retention window after that.**
- The retained snapshots that make re-ingest possible are themselves untouched by any of
  this — they live in the object store (`s3://ledgex-snapshots-locked`, confirmed present in
  P52's own audit), not in the Postgres database being rebuilt, so a failed rebuild never
  puts the *source material* for a retry at risk, only the rebuilt database's own
  in-progress state.
- A partial re-ingest (e.g. parcels loaded, zoning failed) is diagnosable directly:
  `job_run` records each step's own outcome, the same way it already does for the original
  build (§4.5's own evidence). Fix forward (re-run the failed step; ingest scripts are
  designed to be safely re-run — `skipped_unchanged` is a real, handled `job_run` status)
  rather than restart from scratch, unless the failure is structural (a bad snapshot,
  requiring the rename-back path above).
- **Not costed here, flagged as a real gap:** how long to retain the renamed-aside copy, and
  who decides when it is safe to actually drop it — an operational policy question, not a
  technical one, left for Phase 2 or the owner to set explicitly rather than defaulted to
  "delete immediately" or "keep forever" by this document.

---

## §10 (of the P55 prompt) — the channel table, and one recommendation

| Channel | Real rendering surface today | What opening it exposes | Depends on (not built) |
|---|---|---|---|
| `free_snapshot` | **None** — zero references outside `KNOWN_CHANNELS` (confirmed by grep across `api/`, `scripts/`, `core/`) | Nothing — no route or script serves this channel at all | A free-snapshot delivery mechanism |
| `paid_property_file` | Surface B only (the composer's own default channel) — and Surface B has no success path (§3) | Nothing today, regardless of licence state | Composer success/payload-assembly path; commerce/entitlement (I15/I16, doesn't exist); real L0 ingest for `ca_san_jose` (D-A, §2.2); counsel review + boundary cross-check (P52 §10, P53 §11) |
| **`api`** | **Surface A — real, working, localhost-only, no auth** (`api/main.py`'s `get_parcel_facts`) | Existing ingested facts (`parcel.apn`, `parcel.geometry`, `permits.active`, `zoning.district`, etc.) become visible in the internal viewer | Nothing further — the one channel satisfiable in this pass (§3.2) |
| `bulk_export` | **None** | Nothing | A bulk-export mechanism |
| `analytics` | **None** | Nothing | An analytics consumption mechanism |
| `model_training` | **None**, and independently denied regardless (0032) | Nothing | Its own separate terms review, never inferred from any other channel's clearance |

**Recommendation: `'api'` alone.** It is the only channel with a real rendering surface
today; the viewer is localhost-only with no auth and no customer (its own header already
says so); it is the only channel that can satisfy C3 at all in this pass (§3.2, verified, not
assumed); and `paid_property_file` specifically reaches the exact surface P52 §10 and P53
§11 both already named as needing counsel review and a real boundary cross-check *first* —
opening it now would be opening a door onto a room this repo has already, twice,
independently flagged as not ready. Argued for, not decided — the owner's call per §9.

**Per-channel rationale stays authoritative** (§4.4): `model_training` keeps its own,
different reason from the other five; nothing in this design collapses that into a
licence-level label.

**Vocabulary discipline maintained:** `rights_position` values stay `permits_use` /
`permits_with_conditions` / `prohibits_use` / `unknown` throughout this document and its
proposed test names — never `"allowed"`, which collides with `licence_channel.allowed`, the
actual gate this whole pass is about.
