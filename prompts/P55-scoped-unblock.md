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
- `snapshot`: `snapshot_no_update`/`snapshot_no_delete` (0021) — once written, a snapshot
  row's own `licence_observed_id` can never be changed either. **A third immutable-adjacent
  constraint this section did not originally name, found during Stage 5's rehearsal, not
  here at design time:** `fact_snapshot_licence_fk` (`db/schema.sql:1776`, `FOREIGN KEY
  (snapshot_id, licence_id) REFERENCES snapshot(id, licence_observed_id)`) ties a fact's own
  `licence_id` to whatever `licence_observed_id` the snapshot row it cites was FIRST written
  with — meaning a fact citing a NEW licence id can only ever attach to a snapshot row
  ALSO carrying that new id, forcing every reused/rebuilt snapshot's own provenance record
  to move with the fact rather than staying historically accurate. Full analysis, and the
  owner decision it requires, in §12.4-§12.6.
- `source`: **no immutability trigger** — confirmed directly (no `source_no_update` exists
  anywhere in `db/migrations/`). `source.licence_id` is an ordinary mutable column. This was
  also 0056's own finding, re-confirmed here independently.
- Ingest constants, read directly: `scripts/ingest_parcels.py:88` `LICENCE_ID = "cc_by_4_0"`;
  `scripts/ingest_zoning_permits.py:134` `LICENCE_ID_ZONING = "cc_by_4_0"`;
  `scripts/ingest_zoning_permits.py:141` `LICENCE_ID_PERMITS = "cc0"`. **These constants —
  not `source.licence_id` — are what a fact's own `licence_id` column is written from at
  fact-write time.** Confirmed by reading the `Fact(...)` construction sites directly
  (`scripts/ingest_parcels.py:1270,1278,1296,1383,1404,1418`, every one passing
  `licence_id=LICENCE_ID`, the constant, literally) and by confirming no fact-write path
  reads `source.licence_id` at all (`grep -n "source\.licence_id" scripts/ingest_parcels.py
  scripts/ingest_zoning_permits.py` — zero matches). See §4.5's own dedicated step for why
  this matters and what `source.licence_id` is for instead.

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

   **Correction (2026-08-23, §12.9): "9 real (non-test) snapshot ids" was itself wrong,
   found while reconciling every count claim in this document against a direct query
   rather than trusting any of them, including this one. See §12.9 for the full,
   mechanically-verified count — it is 8, not 9, and §12.9 also names two real snapshots
   this figure implicitly (and incorrectly) counted as replay-relevant when they never
   fed a load at all.**

   **The "24" itself is also stale as anything but a description of the ORIGINAL
   database, corrected here so it does not survive as an implied post-rebuild target
   (§12.11): the rebuilt database's own snapshot table is predicted to carry exactly 6
   rows — the 6 that actually feed a replay operation — not 24. The other 18 (`db-test`
   fixture rows, plus the 2 orphaned real snapshots §12.9 names) will not exist in a
   clean rebuild by construction, not by omission.**
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
   own `source` INSERT is updated to point at the new ids). **Corrected reasoning — the
   original draft of this step gave the wrong reason and it mattered.** This repoint is
   required, but NOT because ingest scripts read a fact's licence off `source.licence_id` at
   write time — they do not (see step 9 below, and §4.1's own correction). It is required
   because `scripts/check_conformance.py` (`make conformance`) directly compares
   `jurisdictions/ca_san_jose/sources.yaml`'s own declared `licence:` field against the LIVE
   `source.licence_id` row and asserts they match (`check_conformance.py:259-261`:
   `"{sid!r}'s pack licence matches the live source row's own licence_id"`, `s["licence"] ==
   db_licence_id`) — confirmed by reading that assertion directly, not assumed from its
   name. `source.licence_id` is the human-readable ledger of which licence a source is
   *currently* ingested under; conformance is what actually reads it, not the ingest path.
   **A consequence this correction surfaced, not previously stated anywhere in this
   document:** repointing `source.licence_id` to the new ids means
   `jurisdictions/ca_san_jose/sources.yaml`'s own `licence:` line for `ca_san_jose.parcels`/
   `zoning_districts`/`building_permits_active` must ALSO be updated to the new ids in the
   same Phase 2 change, or `make conformance`'s own check above fails on a mismatch it was
   never asserting anything wrong about (`s["licence"]` would still say `'cc_by_4_0'`/`'cc0'`
   against a database that now says `'cc_by_4_0_api_2026_08'`/`'cc0_api_2026_08'`). Not
   scoped further here — a required Phase 2 edit, named so it is not discovered as a
   surprise `make conformance` failure after the rebuild.
9. **Update the three ingest constants** — `scripts/ingest_parcels.py:88` `LICENCE_ID`,
   `scripts/ingest_zoning_permits.py:134` `LICENCE_ID_ZONING`,
   `scripts/ingest_zoning_permits.py:141` `LICENCE_ID_PERMITS` — to the two new licence ids,
   **before** the re-ingest step below. This is not a note about the seed (an earlier draft
   of this document buried it as one); it is the actual mechanism by which a written fact's
   `licence_id` column gets its value (§4.1's own correction, verified directly against the
   `Fact(...)` construction sites). If step 9 is skipped, step 10's re-ingest reproduces
   every one of the 1,135,140 facts citing the OLD `cc_by_4_0`/`cc0` ids — immutably,
   permanently — and T1 (§7) fails, indistinguishably at first glance from a
   `licence_channel` misconfiguration, on a database that just took a full `--phase e` to
   build. This step exists specifically so that failure is prevented, not diagnosed after
   the fact.
10. Re-ingest, replaying the exact `job_run` sequence found in step 2 above, snapshot by
   snapshot, in the same order: `scripts/ingest_parcels.py --phase e --snapshot-id
   0216d539...` (**a real, ~210MB, full-city ingest — flagged prominently as the single
   largest-blast-radius step in this whole runbook; not run in this design-only pass, and
   Phase 2 should run it with the owner aware it is happening, matching how every prior
   package in this arc has treated `--phase e`**), then the 2026-08-17 delta wave
   (`--phase e --snapshot-id b98138f0...`), then `scripts/ingest_zoning_permits.py --source
   zoning --phase load --snapshot-id eae7823...` and `--snapshot-id 699ec193...`, then
   `--source permits --phase load` for both permit snapshots, in the same relative order.
11. Re-run `scripts/flag_invalid_geometry.py` for parcels and zoning (writes
    `parcel_exception` rows, not facts — needed for full state parity, not for licence
    correctness).
12. `current_fact` refresh — see §4.6 immediately below; do this correctly the first time.
13. Verification queries: `SELECT count(*) FROM fact` (expect 1,135,140, matching the
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

**A collision this recommendation creates, found by reading `scripts/smoke_real.py`
directly, not anticipated when the recommendation above was first written.**
`scripts/smoke_real.py:100` hardcodes `BLOCKED_LICENCE = "cc_by_4_0"` — the OLD id — and its
own module docstring (`scripts/smoke_real.py:31-33`) states plainly: *"Step 15 proves the
gate holds for cc_by_4_0 on channel 'api' on these parcels."* `step_rights_gate`
(`scripts/smoke_real.py:754-817`) filters the smoke parcel's own facts down to
`lic == BLOCKED_LICENCE` before asserting anything. This pass repoints exactly the licence
that constant names, on exactly the channel it names, for exactly the parcels `make
smoke-real` loads (`step_query_sql`, `scripts/smoke_real.py:683-708`, always selects a real
`ca_san_jose`-jurisdiction parcel, ordered by `apn` — the smoke-loaded parcels are the only
candidates). Rebuilding `ledgex_smoke` under this design's own runbook (§4.5 steps 8-10)
means every fact that parcel carries now cites `cc_by_4_0_api_2026_08`, not `cc_by_4_0`.
**The consequence is not what an earlier reading of this collision assumed — see the
analysis immediately below, which corrects it against the actual code before proposing
either resolution.**

**The actual mechanical consequence, read directly from `step_rights_gate`'s own code
(`scripts/smoke_real.py:770-776`), is not "step 15 goes RED."** It is:

```python
blocked_sql = [(fk, lic, val) for fk, lic, _s, _sn, val in ctx["sql_facts"]
               if lic == BLOCKED_LICENCE]
if not blocked_sql:
    return (SKIP, "this parcel carries no %s fact, so there is nothing for the gate "
                  "to block here. Not a pass and not a failure -- ...")
```

If every fact the smoke-loaded parcel carries now cites `cc_by_4_0_api_2026_08` instead of
the literal string `cc_by_4_0`, `blocked_sql` is **empty**, and the function's own existing
"nothing to block here" branch fires — **`SKIP`, not `FAIL`.** Confirmed against the
runner's own summary logic (`scripts/smoke_real.py:886-900`): a `SKIP` does not fail
`make smoke-real` overall (`failed = [... == FAIL]` only; the final line still prints
`RESULT: PASS -- N step(s) passed, M skipped`). **This is a materially different, and in one
real sense worse, failure mode than "RED":** a hard failure would be impossible to miss; a
`SKIP` folds invisibly into a summary line (`make smoke-real`'s own step numbering, distinct
from this runbook's — its step 12, `--phase d`'s non-idempotency skip, already reports one
routine `SKIP` today) that already reads as "fine, expected." The byte-level proof its own
step 15 currently provides would not loudly break — it would silently stop existing, in a
report that still says `PASS`.

**RESOLUTION A — leave `ledgex_smoke` on the old licences; do not rebuild it.** Step 15 keeps
its current facts, keeps citing `cc_by_4_0` literally, keeps `FAIL`ing loudly if the gate
ever actually leaked a value, and keeps proving the same real-data, byte-level property it
proves today. **Cost:** `ledgex_smoke` no longer mirrors `ledgex_schema_check`'s post-rebuild
licence posture, so `make smoke-real` stops being an end-to-end rehearsal of the real
database's actual state, and the cheap-first-rebuild strategy this section otherwise
recommends is lost — the 1.1M-fact database becomes the first real rebuild attempted, not the
second. Stated plainly because it is the significant cost, not a minor one.

**RESOLUTION B — rebuild `ledgex_smoke` and re-scope step 15 to a licence that is still
deliberately blocked.** Checked directly, per the prompt's own requirement, rather than
assumed available: **does anything in `ledgex_smoke` still cite a genuinely-blocked licence
after a rebuild? No — and not for a reason this document anticipated either.**
- The `internal_test.*` P42 fixture (`scripts/seed_internal_test_licences.py`) — even if
  re-seeded after the rebuild — uses `jurisdiction_id = "internal_test.viewer_demo"`, a
  DIFFERENT jurisdiction than `"ca_san_jose"`. `step_query_sql`'s own SQL
  (`WHERE p.jurisdiction_id = %s`, bound to the hardcoded `JURISDICTION_ID = "ca_san_jose"`,
  `scripts/smoke_real.py:95,686`) **structurally cannot select that fixture's parcel**,
  whether or not the fixture exists in the database. Re-seeding it would not help step 15 as
  currently written.
- The `'unknown'` licence (0056) can **never** have a fact under it at all — its own source
  (`ca_san_jose.city_limits`) is `method='manual'`, and I13 forbids a manual source from ever
  producing one. Not a candidate, structurally, not just today.
- The OLD `cc_by_4_0`/`cc0` ids themselves would have **zero** facts in a correctly-rebuilt
  database (§4.5 step 13's own verification query already asserts this as the acceptance
  bar for a correct rebuild).

**So Resolution B, exactly as described, is not available without a real code change** — not
merely "re-point step 15 at a different existing fact," but either widening
`step_query_sql`'s own jurisdiction scope to also consider `internal_test.*` parcels, or
seeding a NEW, permanently-blocked fixture fact inside the `ca_san_jose` jurisdiction
specifically for this purpose. Either is a real `scripts/smoke_real.py` edit, designed
before Phase 2 runs, not improvised during it — exactly the caveat the original framing of
this resolution already anticipated, now with the concrete reason why.

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

**A strengthening of this conclusion, not a caveat against it** — verified directly:
`db/seeds/day4_sources.sql`'s own three-row `INSERT INTO source (...) VALUES (...)` block for
`ca_san_jose.parcels`/`zoning_districts`/`building_permits_active` (`day4_sources.sql:240-
283`) ends `ON CONFLICT (id) DO NOTHING;`. Because of that clause, re-running the MODIFIED
seed (carrying the two new licence rows, their twelve `licence_channel` rows, and this same
`source` block repointed at the new ids) against a database that is **not** being rebuilt
does exactly this: the two new licence rows and their `licence_channel` rows get created
(harmless — zero facts cite them there, since nothing in that database was ever re-ingested
under the new ids), and the `source` block's own `DO NOTHING` means its **existing**
`ca_san_jose.parcels`/`zoning_districts`/`building_permits_active` rows are left completely
untouched — `source.licence_id` does **not** silently move on a database this design isn't
rebuilding. Nothing repoints by accident. This is the mechanical reason seed-only is safe to
apply universally (every database, rebuilt or not) rather than needing per-database
judgment about whether it is safe to run.

### 4.8 Q3.7 — the old rows, orphaned forever

Confirmed acceptable, matching 0033's own explicit design intent ("the old row's channels
stay false forever, an accurate record of what was believed at the time"). After a rebuild,
the old `cc0`/`cc_by_4_0` rows and their twelve `allowed=false` `licence_channel` rows would
have **zero** facts referencing them in the rebuilt database (verification query in §4.5
step 13 checks this explicitly) — they become pure historical record, still seeded (their own
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
ones. Goes RED if the three ingest constants (§4.5 step 9) were not updated before
re-ingest — the actual, corrected root cause a missed edit here would produce (§4.1, §4.5
step 8's own correction) — or if the rebuild didn't happen, if `source.licence_id` wasn't
repointed, or if the new `licence_channel` row is missing/`false`.

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

**`scripts/smoke_real.py` — depends entirely on which resolution §4.5's `ledgex_smoke`
collision analysis lands on, so it cannot be pre-sorted into either list without that
decision.** Under Resolution A (don't rebuild `ledgex_smoke`): *expected to pass
unmodified* — step 15 keeps citing the real, unchanged `cc_by_4_0`. Under Resolution B
(rebuild it): *expected to change* — `BLOCKED_LICENCE` and step 15's own scope need a real
edit, or the step silently degrades from `FAIL`-capable to permanent `SKIP` with no error
(§4.5's own corrected finding — not a `FAIL`, which is its own reason this cannot be left
unlisted: a test that quietly stops testing something, while its suite still reports
`PASS`, is exactly the failure T8 exists to catch before Phase 2, not after).

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
2. That the three ingest constants (§4.1, §4.5 step 9) and `source.licence_id` (§4.5 step 8)
   can never drift apart from each other once both exist as separate, independently-editable
   values — this pass confirmed which one governs a fact's own `licence_id` at write time
   (the constants) and which one `make conformance` checks (`source.licence_id`, against
   `sources.yaml`'s own declaration), but **nothing in this codebase checks the constants and
   `source.licence_id` against EACH OTHER.** A future edit to one without the other would
   pass `make conformance` (which never reads the ingest constants) and would only surface
   as a mismatch a human happens to notice between what `source.licence_id` claims and what
   newly-ingested facts actually cite — a real, separate, currently-unguarded gap, not the
   same uncertainty this correction pass closed.
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
9. What a rebuilt `ledgex_smoke` actually looks like, as opposed to what a rebuild's own
   mechanics predict it should look like. §4.5's collision analysis worked out, from reading
   the code, that `step_query_sql`'s jurisdiction scoping and I13's own fact-method
   restriction together mean no genuinely-blocked licence would remain visible to step 15
   after a rebuild — but that is a claim about the CODE's behavior, checked directly; this
   pass did not execute a rebuild to confirm the claim against real, rebuilt data. If Phase
   2's actual rebuilt `ledgex_smoke` disagrees with this reasoning, that disagreement is
   itself the more important finding, and should be reported rather than the rebuild quietly
   proceeding past it.

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
8. **§4.5's `ledgex_smoke`/`scripts/smoke_real.py` collision.** Resolution A (leave
   `ledgex_smoke` on the old licences, keep step 15's current proof, lose the cheap-first-
   rebuild rehearsal) or Resolution B (rebuild it, and accept that step 15 needs its own
   real re-scoping — not a small edit, since neither the existing `internal_test.*` fixture
   nor the `'unknown'` licence can stand in for it as currently written, per §4.5's own
   analysis)? **If Resolution B is chosen, step 15's own re-scoping needs to be designed
   before Phase 2 runs the rebuild, not improvised during it** — the same "design first"
   discipline this whole document exists to apply to the rebuild itself.

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
  build is verified (§4.5 step 13) and kept for some agreed retention window after that.**
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

---

## 11. Step 15 re-scope — design (Phase 2, Stage 0)

Design only, per Phase 2's own Stage 0 gate. No code below is written yet; Stage 4
implements exactly this, or Stage 4 stops and reports why not.

### 11.1 What step 15 must prove after this pass

In one sentence: that `core.rights.evaluate_rights_gate`, exercised end-to-end through a
real HTTP request against the real `ledgex_smoke` database, both (a) permits and renders a
real, currently-ingested fact whose licence is `allowed=true` for channel `'api'`, and (b)
withholds — from both the parsed response and the raw response bytes — a fact whose licence
is genuinely `allowed=false`, on the same parcel, in the same request.

### 11.2 Options, enumerated from the code, not assumed complete

Checked directly against `scripts/smoke_real.py` and the schema, three options were found,
not the two this document's own §4.5 anticipated:

**Option 1 — widen `step_query_sql`'s jurisdiction scope to also consider
`internal_test.*` parcels.** Rejected. Three independent problems, each sufficient alone:
(a) it would make `make smoke-real` depend on `scripts/seed_internal_test_licences.py`
having been run — the module's own docstring states twice, in the "WHAT IT DOES NOT PROVE"
section, that this target deliberately "will not trigger that as a side effect, for the
same reason viewer-test does not"; widening scope to select an `internal_test.*` parcel
would either violate that (auto-seed it) or leave step 13 selecting nothing on a database
where it hasn't been run, reintroducing a SKIP-shaped hole one level up. (b) `ORDER BY
p.apn NULLS LAST LIMIT 1` across two jurisdictions makes the parcel selection depend on
apn string comparison between two different id spaces (`internal_test.viewer_demo`'s
literal apn `INTERNAL_TEST-VIEWER-DEMO-1` vs. real numeric APNs) — fragile, and a bad fit
for a step whose entire point (module docstring, "9-10... a real byte from a real city
endpoint") is proving something about the real fetch. (c) It does not even solve the
problem cleanly: `step_query_viewer` (step 14) and `step_rights_gate` (step 15) would then
be exercising the SYNTHETIC fixture parcel instead of the REAL one on some runs,
undermining step 13-14's own "one parcel read back" real-data claim depending on ordering
luck.

**Option 2 — seed a new, permanently-blocked fixture fact inside the `ca_san_jose`
jurisdiction, attached to the real, `--phase d`-ingested parcel `step_query_sql` already
selects.** Recommended — argued in 11.3 below.

**Option 3 — prove the property on a different axis: a direct, non-HTTP call to
`core.rights.evaluate_rights_gate` (the same function §2.3 of this document already calls
standalone, no database write) instead of a full HTTP round-trip.** Rejected. This would
weaken, not merely change, what step 15 proves: the module docstring's own "WHAT IT PROVES"
list (§ near the top) frames step 15 as byte-level proof through the *viewer's own HTTP
response*, catching exactly the class of bug `scripts/test_viewer_rights_gate.py`'s own
docstring already argues for ("a value absent from a parsed structure but present in the
serialized body has still left the building") — a class of bug a direct function call
cannot see at all, because there is no serialization step to get wrong. §0.1's own
requirement ("real-data, byte-level, end-to-end") rules this out on its face; recorded here
because it was a real candidate before being checked against that requirement, not because
it survives.

**Recommendation: Option 2.**

### 11.3 The two-sided design (0.3), concretely

Schema constraints checked directly, not assumed, before proposing INSERT shapes:
`fact_parcel_jurisdiction_fk` (`db/schema.sql:1760`, `FOREIGN KEY (parcel_id,
jurisdiction_id) REFERENCES parcel(id, jurisdiction_id)`) and `fact_source_jurisdiction_fk`
(`db/schema.sql:1800`, same shape against `source`) together mean a fixture fact's own
`jurisdiction_id` — and its fixture `source`'s own `jurisdiction_id` — must both literally
be `'ca_san_jose'` to attach to a real `ca_san_jose` parcel at all; there is no fixture
jurisdiction to hide behind here, unlike P42's `internal_test.viewer_demo`. `fact_
method_automated` (I13) additionally forbids `method='manual'` on the fixture's `source`
row — confirmed relevant because `ca_san_jose.city_limits` already demonstrates exactly
that shape blocking a fact from ever existing (§2.2); the fixture source must use
`method='bulk'` (or `'direct'`), matching P42's own fixture sources, not `city_limits`'s.

**New, permanent, `ca_san_jose`-scoped fixture, modelled directly on
`scripts/seed_internal_test_licences.py`'s own P42 "blocked fixture fact" pattern (same
idempotency shape, `WHERE NOT EXISTS` for the fact/parcel-shaped rows since P42's own
comment already explains why `ON CONFLICT` cannot be used there; `ON CONFLICT DO NOTHING`
for the rows that do have real PKs) — but namespaced `smoke_fixture.*`, deliberately
distinct from `internal_test.*`, so a reader never mistakes this for part of the P40/P42
viewer-demo fixture set living in a different jurisdiction:**

```
licence:            id='smoke_fixture.always_blocked', restriction='open',
                     commercial_use='allowed', redistribution='allowed',
                     cleared_by='smoke_fixture_seed', cleared_at=now() -- deliberately
                     marked resolved/fake, exactly like internal_test.*'s own two licences,
                     so nobody reads this as a second real pending-diligence item
licence_channel:    all six KNOWN_CHANNELS, allowed=false, rationale states plainly this is
                     scripts/smoke_real.py's own permanent fixture, asserts nothing about
                     any real licence
source:             id='smoke_fixture.blocked_source', jurisdiction_id='ca_san_jose',
                     method='bulk', active=false, licence_id='smoke_fixture.always_blocked'
snapshot:           one row, object_uri/content_hash fabricated the same way P42's own
                     fixture snapshot is (a fixed, greppable non-real URI) -- required by
                     fact_provenance_complete for any non-derived method
field_definition:   field_key='smoke_fixture.blocked_marker'
fact:               one row, parcel_id=ctx["parcel_id"] (the SAME parcel step 13 already
                     selected -- not a second parcel), jurisdiction_id='ca_san_jose',
                     value a greppable sentinel string mirroring P42's own
                     "BLOCKED FIXTURE VALUE - MUST NOT RENDER"
```

**Placement: inside `step_rights_gate` (step 15) itself, at the top, before either of its
two directions is checked — not a new numbered step, and not folded into step 13.**
Argued: `step_rights_gate` is the one place already named "step 15" in the Makefile
comment (`Makefile:437`), this document (repeatedly), and `prompts/P52-rights-vs-
diligence.md`. Inserting a new step ahead of it would silently renumber it to 16 across
every one of those references — the same class of staleness `CLAUDE.md`'s own 2026-08-22
correction exists to prevent, self-inflicted for no benefit. Folding the ensure-fixture
logic into step 13 was considered and rejected for a sharper reason: step 14's HTTP GET
runs *between* step 13 and step 15 today, so a fixture inserted during step 13 would be
captured correctly by step 14's fetch — BUT that makes step 15's byte-level "absent from
the body" check trivially true by insertion-timing coincidence (the fact simply existed
before the one fetch that happened), not because a load-bearing property of the gate was
exercised at the moment it mattered. Keeping the ensure-and-then-fetch-fresh sequence
entirely inside step 15 makes step 15 a self-contained, non-order-dependent proof: it seeds
the one fact whose blocked status is under test, queries `current_fact_at` fresh (not
reusing step 13's own `ctx["sql_facts"]`, captured before the fixture could exist), and
performs its OWN `GET /v1/parcels/{id}/facts` (not reusing step 14's `ctx["viewer_doc"]`/
`ctx["viewer_body"]`, captured before the fixture could exist either) — so both directions
it asserts are checked against one fresh, complete snapshot of real, current state.

**Both directions, from that one fresh fetch:**
- **Blocked side (unchanged mechanism, new source):** `blocked_sql` becomes "current facts
  on this parcel whose `licence_id == SMOKE_FIXTURE_LICENCE_ID`" instead of `==
  BLOCKED_LICENCE`. The existing three checks (not leaked into `facts`, present in
  `omitted_for_rights`, sentinel value byte-absent from the raw body) carry over verbatim,
  generalized to the new constant.
- **Blocked side ALSO used as-is for a fourth thing, decided here rather than left implicit:
  the search for `blocked_sql` covers every current fact on the parcel, not just the
  fixture** — meaning if a rebuild bug ever left a real fact citing an old, still-genuinely-
  blocked id (`cc_by_4_0`/`cc0` pre-rebuild, or some future mis-scoped id) on this SAME
  parcel, it would be swept into the same blocked-side proof for free. Not relied upon as
  the primary mechanism (the fixture is), but not discarded either — the filter is written
  as "licence_id in the set of licences whose `('api', allowed=false)` row this step
  confirms live, per-run" rather than a single hardcoded id, so it stays correct without
  editing if a second permanently-blocked id is ever added later. (Implementation detail
  for Stage 4, not a new design axis — flagged so Stage 4 does not narrow it back to a
  single hardcoded constant without noticing this was intentional.)
- **Allowed side (new):** `allowed_sql` = "current facts on this parcel whose `licence_id`
  is NOT the fixture licence" — on a rebuilt `ledgex_smoke`, this is exactly the real
  `parcel.apn`/`parcel.geometry`/`parcel.source_parcel_id` facts, now citing
  `cc_by_4_0_api_2026_08`. Asserts: every one of those `field_key`s IS present in
  `doc["facts"]` (mirroring the blocked side's `omitted_keys` check, inverted), and — the
  byte-level half, symmetric with the existing sentinel check — each one's own value IS
  present in the raw response body. This is the "new property this pass creates, currently
  proven nowhere at smoke level" the Phase 2 prompt names in its own 0.3.

### 11.4 The SKIP path (0.4)

**Argued explicitly, per 0.4's own instruction, rather than inherited: SKIP is removed
entirely from step 15, on both sides, and this is correct, not merely convenient.** The
existing SKIP branch existed because whether the loaded parcel carried a `cc_by_4_0` fact
was NOT under this step's control — a fact of which real parcels the live snapshot happened
to contain. That precondition no longer holds for the blocked side: this step now *creates*
the fixture fact itself, deterministically, on the one parcel it already knows about. If
`blocked_sql` is empty after `_ensure_blocked_fixture` runs, that is not "nothing to block
here" — it is the seeding step failing silently, which must FAIL loudly, naming that
specifically (not the gate) as the thing to fix, so a future reader is not sent looking for
a rights-gate bug that does not exist. Symmetrically, if `allowed_sql` is empty (the
selected parcel carries no fact besides the fixture), that would mean step 13's own
selection query — `WHERE EXISTS (SELECT 1 FROM fact WHERE f.parcel_id = p.id)` — matched a
parcel with a fact, and yet after the rebuild no non-fixture fact exists for it, which is
itself a real, reportable inconsistency (not a "rerun later" condition) — FAIL, not SKIP,
for the same reason.

### 11.5 What this re-scope does not prove

1. That the specific real ids `cc_by_4_0_api_2026_08` / `cc0_api_2026_08` are the ones
   permitting the allowed-side fact — the check is written against "whatever licence isn't
   the fixture," not those ids by name, so it would pass unchanged if the real ingest
   constants pointed somewhere else entirely. T1 (§7, DB-level, run against the rebuilt
   database directly) is what actually pins the real ids; step 15 only proves the *shape*
   of the two-sided property on whatever `--phase d` currently loads.
2. Anything about a licence that is `allowed=true` on some channel other than `'api'` — `
   VIEWER_CHANNEL` stays fixed (D1), unchanged by this re-scope.
3. Anything about `ledgex_schema_check`'s real, ~1.1M-fact database — `make smoke-real`
   only ever binds to `SMOKE_DATABASE_URL` (module docstring, "WRITES"); this proof is, and
   remains, `--phase d`-scale only.
4. That `smoke_fixture.always_blocked` represents a real city licence or a real diligence
   decision — synthetic by construction, the same caveat `internal_test.*` already carries
   for its own permitted-side fixture, stated here for the blocked side.
5. That the gate behaves correctly for a fact whose licence is *unknown to the response
   entirely* (a licence id with no `licence` row at all) — out of scope; I3's FK already
   makes that state unreachable for any real fact (§4.5 step 8 of this pass reuses that same
   guarantee), so there is nothing real to construct a fixture for.

### GATE — resolved

A step 15 satisfying 0.3 (two-sided) and 0.4 (no silent SKIP) against the code as it
actually exists is designed above, concretely enough to implement without further
invention. Phase 2 proceeds to Stage 1.

---

## 12. Stage 5 rehearsal findings — the smoke delta reconciled, and an owner decision
## on `licence_observed_id`

Written before Stage 6, per the owner's own explicit instruction not to proceed with
either the acceptance-bar question or the mass snapshot registration until both are
answered here, in writing, with evidence.

### 12.1 The 41 → 40 `cc_by_4_0`-lineage delta — fully reconciled, no drift

Queried directly against `ledgex_smoke_pre_p55_20260822` (the renamed-aside original):
all 41 pre-rebuild facts citing `licence_id='cc_by_4_0'`, listed. 40 of them are
`parcel.apn`/`parcel.geometry` on the 20 real `ca_san_jose` parcels, all citing
`snapshot_id='ca_san_jose.parcels:sha256:61b58c56...'` — the real `--phase d` load. The
**41st is `internal_test.viewer_field_blocked_fixture`**, on parcel `9aaa4672-...`
(`jurisdiction_id='internal_test.viewer_demo'`) — `scripts/seed_internal_test_licences.py`'s
own P42 "blocked fixture fact," which by that script's own documented design cites the
literal, real `cc_by_4_0` id on purpose (`seed_internal_test_licences.py`'s own docstring:
*"licence_id is the real, unchanged 'cc_by_4_0'"*). It has nothing to do with `--phase d`
ingest and was never going to be reproduced by Stage 5's own runbook, which only re-ingests
real `ca_san_jose` data.

Confirmed empirically, not assumed: the exact set of 20 APNs loaded from
`61b58c56...` is **byte-identical** pre- and post-rebuild (`diff` of both sorted APN
lists — zero differences). `select_parcels()` is deterministic given identical input
bytes, exactly as content-addressing and the "reproduce from retained snapshots" premise
require.

**Reconciled: 40 real parcels facts pre-rebuild = 40 real parcels facts post-rebuild,**
exactly, byte-for-byte, no drift. The apparent "41 → 40" was never a real discrepancy —
it was comparing 41 (40 real + 1 unrelated fixture residue) against 40 (recorded at a
moment before the fixture had been re-seeded into the fresh database at all). Not a
near-miss; a like-for-like match once the comparison is done correctly.

### 12.2 The 0 → 4 permits delta — a re-derivation bug in Stage 5's own execution, not an
### open design question

**Confirmed, with direct evidence: yes, Stage 5 replayed an ingest operation the original
`ledgex_smoke` never ran.** Every one of the original database's `ingest_permits` `job_run`
rows — both `succeeded` entries and every `skipped_unchanged` one — has **`rows_in`,
`rows_out` and `metrics` all NULL**. `scripts/ingest_zoning_permits.py`'s own matching/
fact-writing logic (`load_permits()`, its own `rows_out = len(matched)` and the metrics
block) only runs under `--phase load`; a `--phase b` call (fetch → hash → upload → snapshot
only, no parcel matching, no fact writes) never touches those columns. Confirmed directly
by grepping `scripts/smoke_real.py` for every `--phase` it ever passes: **`d` for parcels,
`b` for permits — `--phase load` for permits appears nowhere in this file.** The original
`ledgex_smoke`'s zero `cc0`-lineage facts is not a gap or an oddity; it is `make
smoke-real`'s own design working exactly as built — permits are fetched and snapshotted (to
exercise and verify the object-store path) but never matched against parcels or written as
facts, because nothing in this target's own 15-step design ever calls `--phase load`.

**Stage 5, as I ran it, called `ingest_zoning_permits.py --source permits --phase load`
twice — an operation this database's own real history never performed.** That produced 4
new, real, immutable facts (2 matched parcels × 2 fields) with no analog in the original
database at all. This is exactly the re-derivation the owner's question named: not a
reproduction of `ledgex_smoke`'s own prior state, an expansion of it, done in good faith
(misreading this document's own §4.5 "2 real snapshots" phrasing — written about
`ledgex_schema_check`'s multi-source rebuild, not `ledgex_smoke`'s narrower, parcels-only
one) but wrong.

**Consequence, and the fix.** `fact`/`snapshot` immutability (0007/0017/0040, 0021) means
these 4 facts and their 2 registered snapshot rows cannot be corrected in place — the
database that carries them has to be set aside and rebuilt again, correctly this time
(`--phase d` only; permits stays at the `--phase b` `make smoke-real` already performs on
its own, matching the original design exactly). **Not done yet** — held pending this
report, per the owner's own "hold Stage 6" instruction, since the identical mistake at
schema_check's scale (a real ingest operation beyond what that database's own job_run
history actually shows) is precisely the class of error this whole rehearsal exists to
catch before it is expensive. Proposed fix, to run once acknowledged: rename this
`ledgex_smoke` aside too (e.g. `ledgex_smoke_p55_attempt1_permits_overreach_<date>` —
evidence of the mistake kept, not dropped, matching this pass's own rename-don't-drop
discipline throughout), fresh `createdb`, replay `--phase d` only.

### 12.3 What Stage 6's acceptance bar should actually be

**The exact-count bar (1,135,140) is still the right bar — but only under a discipline
this rehearsal shows is easy to violate by accident.** Nothing about content-addressed,
SHA-256-verified snapshots or deterministic parcel/fact-write logic makes a rebuild
inherently lossy or re-derivative — §12.1 already proves byte-for-byte reproduction holds
when the SAME operations run against the SAME verified bytes. The single, sufficient cause
of drift found here is procedural, not structural: **running an ingest operation the
target database's own real `job_run` history does not show**, whether from misreading a
prose summary (as happened here) or from assuming a phase "should" run rather than
confirming it did.

**Stage 6's own acceptance bar should therefore be:** exactly 1,135,140 facts, achieved by
replaying **precisely** the operation sequence a mechanical query against `job_run`
produces — not a document's own prose summary of it, including this one's.

**Correction, caught live while building that mechanical query (`scripts/
_p55_stage6_prep.py`), not left standing:** §4.5's own "two `ingest_parcels_full` calls,
two `ingest_zoning --phase load` calls, two `ingest_permits --phase load` calls" — six
operations — **is itself wrong.** Filtering `job_run` for `job_key IN
('ingest_parcels','ingest_parcels_full','ingest_zoning','ingest_permits')` with
`rows_in IS NOT NULL` (the discriminator this rehearsal's own permits bug established)
returns **eight** real loads, not six: `ingest_zoning` ran the `699ec193...` delta snapshot
**twice** on 2026-08-17 (`rows_out=522` then `rows_out=443`), and `ingest_permits` ran the
`70bf19c1...` delta snapshot **twice** the same day (`rows_out=0` both times). §4.5's own
prose collapsed each pair into one mention. This is the exact failure mode item 5 warned
about, caught by building the mechanical query rather than trusting the document that
asked for one — including this document's own earlier count. The verified, complete list:

```
2026-08-07 20:23:04  ingest_parcels_full  225,039 -> 225,039  ...0216d539...
2026-08-07 21:17:24  ingest_zoning        225,042 -> 214,892  ...eae7823a...
2026-08-07 21:22:59  ingest_permits        17,499 ->   8,322  ...8f3328b5...
2026-08-17 00:28:25  ingest_parcels_full       25 ->      25  ...b98138f0...
2026-08-17 00:28:40  ingest_zoning        225,088 ->     522  ...699ec193... (1st)
2026-08-17 00:29:18  ingest_permits             2 ->       0  ...70bf19c1... (1st)
2026-08-17 00:29:22  ingest_zoning        225,088 ->     443  ...699ec193... (2nd)
2026-08-17 00:29:25  ingest_permits             3 ->       0  ...70bf19c1... (2nd)
```

All 6 distinct snapshot ids independently re-hashed against S3 and confirmed to match
their own id-embedded `content_hash` exactly (`scripts/_p55_stage6_prep.py`'s own dry run,
2026-08-23) — byte integrity is not in question; **operation count and order were.**

Re-verify this list live, immediately before Stage 6 actually runs (per §4.5's own step 1,
"check again, don't assume the earlier catch-up is still current," now applied to the
OPERATION LIST itself, not only the migration ledger, and now proven to matter: this
document's own list was wrong until the mechanical query ran) — **not** a near-miss to be
explained after the fact; a bar to be hit exactly.

### 12.4 `licence_observed_id` — what `fact_snapshot_licence_fk` actually asserts

Quoted verbatim, `db/schema.sql:1776`:
```sql
ALTER TABLE ONLY public.fact
    ADD CONSTRAINT fact_snapshot_licence_fk FOREIGN KEY (snapshot_id, licence_id)
    REFERENCES public.snapshot(id, licence_observed_id);
```
This is a **composite** foreign key: for any fact row, the pair `(snapshot_id, licence_id)`
must exactly match some `snapshot` row's own `(id, licence_observed_id)` pair. Not weaker
than "must match" — Postgres composite FKs require every column to match the same
referenced row simultaneously. Since `snapshot.id` is the table's own primary key (one row
per id) and is itself content-addressed (`snapshot_id_format CHECK (id = source_id ||
':sha256:' || content_hash)` — determined entirely by the source and the bytes, never by
which licence anyone believes applies), **there can only ever be one `licence_observed_id`
value associated with a given `snapshot_id`, permanently, the moment that row is first
written** (`snapshot_no_update`/`snapshot_no_delete`, 0021).

**Is there a shape where the snapshot keeps `cc_by_4_0`/`cc0` (what was actually observed
at fetch time) while the fact cites the new id? No — the constraint forbids it, and not
only administratively: it is structurally impossible, not merely disallowed.** A second
snapshot row for the identical bytes cannot exist (same `source_id`+`content_hash` ⇒ same
`id`, the primary key, so a second `INSERT` for "the same content, a different
`licence_observed_id`" is a primary-key collision, not a legal second row). Considered and
rejected: writing the fact as `method='derived'` instead, to route around the FK entirely
(`fact_provenance_complete` only requires `source_id`/`snapshot_id` for non-derived
methods) — rejected because the fact is not actually derived (no real `fact_input`
relationship, no genuine computation from another fact); that would trade one false
provenance claim for a different one. Considered and rejected: a schema change adding a
second, mutable column separate from `licence_observed_id` to hold the "current scoping"
value independently — real design work, a migration, out of scope for this seed-only pass
(§4.7's own established conclusion), not something to improvise here.

**So the repoint is forced, given this pass's own mechanism (reuse the exact retained
bytes, no re-fetch) and this schema's own constraints as they exist today.** The real cost,
named plainly rather than left implicit: **for any snapshot whose bytes are reused under a
rebuild, `snapshot.licence_observed_id` will read a licence id that did not exist at the
real, historical `fetched_at` timestamp the same row carries.** For `ledgex_schema_check`'s
own real snapshots (`fetched_at` 2026-08-07/2026-08-17), a rebuilt row would assert
`cc_by_4_0_api_2026_08` — an id created 2026-08-22 — was the licence *observed* fifteen
days before it existed. That is a false provenance claim, stated as such, not as
"a minor detail."

### 12.5 Consistency with P45's own intent

Checked directly, not assumed: `prompts/P45-ingest-provenance.md` and
`scripts/audit_snapshot_provenance.py` — grepped for `licence_observed_id` — **zero
mentions in either.** P45's own scope, read from its own text, is byte-identity provenance
(binding a fact to the *verified, correct bytes*, `--snapshot-id` required, no "newest"
guess) — a different axis from *which licence applied*. This tension is not something P45
already resolved or even considered; it is **consistent with P45's own underlying
principle** (provenance metadata should tell the truth about what was actually observed,
when) **while being a genuinely new gap P45's own hardening never closed**, because
`licence_observed_id` sits outside what P45 touched.

### 12.6 Owner decision required before Stage 6 proceeds on this point

Per the owner's own instruction: **not proceeding** with `licence_observed_id` repoints for
`ledgex_schema_check`'s own nine real snapshots until this is decided. The honest answer to
"is there a shape that avoids this" is no — the options are: (a) accept the repoint as a
deliberate, recorded, named consequence of this pass (the snapshot table's own
`licence_observed_id` column, for any rebuilt/reused snapshot, records the scoping decision
under which the data is CURRENTLY used, not the licence genuinely believed to apply at the
historical moment of fetch — a real, permanent narrowing of that column's own meaning for
every future reader), or (b) decline the rebuild-with-reused-snapshot mechanism for this
reason and find a different path (not designed here; would need real work, likely a schema
change, and is a larger decision than this pass's own seed-only scope anticipated). This
document does not pick between them — that is the owner's call, named here so it is
recorded as a decision rather than defaulted into.

**RESOLVED, 2026-08-23 — owner decision: option (a).** Accepted, by the owner, in this
session, with three conditions attached and landed before Stage 6 writes a single snapshot
row:

1. **Mitigated in the data, not only in this document.** Both new licence rows' own `notes`
   column now states the succession explicitly, in every seeder that writes them
   (`db/seeds/day4_sources.sql`, `scripts/check_golden.py`'s `seed_reference_rows()`,
   `scripts/check_conformance.py`'s own fallback, `scripts/_p5_setup.py`,
   `scripts/_phaseb_setup.py` — verified byte-identical across the three that share a real
   convergence risk, per this document's own established discipline): this id did not
   exist before 2026-08-22, was minted then as a scoping decision under terms observed
   2026-07-31, and any snapshot row citing it under an earlier `fetched_at` records "these
   bytes were fetched under the terms this id represents," never that this id existed at
   fetch time. A query against `licence.notes` now carries this reading with it; a reader
   is not dependent on having also read this prompt file.

2. **The cost, stated plainly, not as a footnote.** `snapshot.licence_observed_id`, for
   every snapshot row this pass rebuilds or reuses, will permanently record the scoping
   decision under which the data is currently used rather than the licence identification
   genuinely believed to apply at the real, historical moment of fetch. This is a real,
   deliberate narrowing of what that column means for any reader of a rebuilt row, going
   forward, for as long as those rows exist. **This belongs in §10 ("what this pass does
   not do") at close-out, explicitly, not only here** — flagged so it is not dropped
   between this section and that one.

3. **The honest future fix, named as a scheduled gap, not a someday.** Separating "the
   licence identification believed to apply when these bytes were fetched" from "the
   licence id under which this data is currently, lawfully used" needs its own column (or
   an equivalent structural separation) and its own migration — real design work, out of
   this seed-only pass's scope (§4.7's own established conclusion). §12.5 already
   establishes that P45's own ingest-provenance hardening never covered this axis (byte
   identity, not licence identity over time) — this is that axis's own first real
   collision with an immutable schema, and the fix belongs to a future package, named here
   so the next reader who hits this finds a scheduled gap rather than rediscovering the
   same defect from scratch. **Named successor: a future pass separating
   `snapshot.licence_observed_id` (historical, at-fetch belief) from a licence's own
   current-use scoping — not P55, not designed here, owed to whoever picks up
   `fact_snapshot_licence_fk`'s own consequences next.**

With all three landed, Stage 6 may proceed to register `ledgex_schema_check`'s own real
snapshots under the new licence ids.

### 12.7 Flagged for this pass's own close-out — recorded now so neither is lost

**A correction to P52's own close-out claim, not merely a P55-internal fix.**
`prompts/P52-rights-vs-diligence.md:419-424` lists `make smoke-real`'s step 15 among
"every existing gate run against real data, none edited," citing "step 15's byte-level
cc_by_4_0 absence proof" as part of the evidence P52's own changes broke nothing. That
characterization overstated what the proof actually covered: `_sentinel_text`'s own
`json.dumps(sort_keys=True)` re-serialization could never byte-match a dict/list value's
real wire encoding (§4.5's own finding above, commit `7b4e45e`) -- a failed match there was
indistinguishable from a genuinely absent value, for every run before this one, on any
blocked fact whose value was non-scalar. Whether P52's own real run actually exercised a
non-scalar blocked value is not re-derived here; the claim itself -- "byte-level absence
proof" as an unqualified guarantee -- was not accurate as stated, and this pass's own fix
narrows it explicitly to scalars. Recorded here for this pass's own close-out (§9-to-be) to
carry into `prompts/P52-rights-vs-diligence.md`'s own Review findings section, per this
repo's standing convention for correcting a landed package (`prompts/README.md`'s own
"Adding a package" rule: findings against a landed package go in *its* Review findings
section, not a silent rewrite) -- not done in this commit, flagged so it is not forgotten.

**`fact_snapshot_licence_fk` as a documented constraint, not just a fixed bug.** Already
folded into §4.1's own list above (this section cross-references it, not duplicates it) --
recorded here too only as a close-out reminder that §4.1 itself was the design document's
own constraint inventory, written before Stage 5 ever ran, and it was incomplete; the
close-out should say so plainly rather than let the corrected §4.1 read as though it always
listed three constraints.

### 12.8 Stage 6 housekeeping, completed

**`scripts/_p55_stage6_prep.py`** -- a one-off utility (not wired into any make target),
built and dry-run 2026-08-23. Generates §12.3's replay list mechanically from `job_run`
(never typed), and independently re-downloads and re-hashes each of the 6 distinct
snapshot ids against S3/MinIO before registering anything, refusing on any mismatch
against the id's own embedded hash -- `content_hash`/`byte_size` are read from the
retained object, never transcribed by hand. `--register` mode (not yet run) inserts the
verified rows, `licence_observed_id` already repointed per the ingest constants Stage 2
set, into whatever `DATABASE_URL` points at -- intended for the fresh, post-rename,
post-migrate, post-seed `ledgex_schema_check`.

**`ledgex_schema_check`'s own current baseline, recorded before Stage 6 touches it:**

```
fact count:      1,135,143   (1,135,140 real + 3 golden-fixture facts, this session's own
                              Stage 2 isolated-convergence testing -- see §2's own commit)
parcel count:      225,391   (225,388 real + 3 golden-fixture parcels, same cause)
snapshot count:         27   (24 real + 3 golden-fixture snapshots, same cause)
licence_id breakdown (fact table):
  cc_by_4_0    1,106,855     (1,106,852 real + 3 golden-fixture facts -- P52's own
                              recorded figure, 1,106,852, confirmed still exactly right
                              for the real data)
  cc0             27,936     (unchanged -- golden fixtures never touch permits.* fields)
  test.*                352  (pre-existing db-test invariant-suite residue across 17
                              distinct test.* ids, fact-bearing and therefore permanent
                              by teardown.sql's own design -- unrelated to P55, not
                              reconciled further here)
```

The 3 golden-fixture rows (`GOLDEN-REFUSED-FIXTURE`, `GOLDEN-GEOMETRY-DISABLED-FIXTURE`,
`GOLDEN-ELECTION-REQUIRED-FIXTURE` apns) are this session's own residue, confirmed by
`apn LIKE 'GOLDEN-%'` matching exactly 3 parcels/3 facts. Stage 6.7's own acceptance bar
(exactly 1,135,140) is unaffected -- the rebuilt database starts from an empty `createdb`
and will not carry these -- but the PRE-rebuild count a future reader might compare against
is 1,135,143, not 1,135,140, and should be read with this note rather than as an
unexplained discrepancy.

### 12.9 Every snapshot/operation count reconciled to one authoritative set

Five different numbers were in circulation across this document and the owner's own
prompts before this section: "24 snapshots" (§1), "24 real snapshot rows" / "9 real
(non-test) snapshot ids" (§4.5), "6 distinct snapshots" / "eight operations" (§12.3). Not
all of these describe the same thing, and one of them (the "9") was simply wrong. Queried
directly, 2026-08-23, against `ledgex_schema_check` as it currently stands (before Stage 6
touches it):

```
Total snapshot rows, this database, right now:                    27
  = 24 (§1's own original Phase 1 figure, before this session)
  +  3 (this session's own Stage 2 golden-fixture contamination, §12.8)

Of the 24 "original" rows, by source:
  ca_san_jose.parcels                    2   (0216d539..., b98138f0...)
  ca_san_jose.zoning_districts           3   (eae7823a..., ea709a04..., 699ec193...)
  ca_san_jose.building_permits_active    3   (8f3328b5..., 15b57694..., 70bf19c1...)
  ca_san_jose.test_source                7   ] fixture rows, db-test's own invariant
  ca_san_jose.test_source_b              1   ] suite (P5/P34 election tests etc.) --
  test_other_jurisdiction.test_source    1   ] not San José production data, not
  test.p21_source_{bulk,derived,direct}  3   ] relevant to this pass or Stage 6 in
  test.p34_election_source_* (x4)        4   ] any way
                                        ----
                                         24
```

**§4.5's own "9 real (non-test) snapshot ids" was wrong — it is 8** (2 + 3 + 3 above), not
9. No 9th real `ca_san_jose` production snapshot exists anywhere in this database; queried
directly, not inferred.

**Of those 8, only 6 distinct ids ever fed a real load** (the discriminator §12.2/§12.3
already established: a `job_run` row with `rows_in` populated). The other two --
`ca_san_jose.zoning_districts:sha256:ea709a04...` (817 bytes) and
`ca_san_jose.building_permits_active:sha256:15b57694...` (153 bytes), both `fetched_at`
2026-08-17 00:28:25, the identical timestamp their own sibling loaded snapshots
(`699ec193...`/`70bf19c1...`) carry -- **have zero `job_run` rows referencing them at
all**, confirmed by checking every one of the 6 distinct `job_key` values that exist
anywhere in this database (`ingest_parcels`, `ingest_parcels_full`, `ingest_zoning`,
`ingest_permits`, `flag_invalid_geometry_parcels`, `flag_invalid_geometry_zoning` -- no
missed job_key this time). Real, historical, and legitimately part of what `--phase b`
fetched on 2026-08-17 -- apparently a second, differently-hashed fetch attempt in the same
wave that was never subsequently matched/loaded. **Contribute zero facts. Out of Stage 6's
own reproduction scope** -- the acceptance bar is fact count, and no operation ever
attaches a fact to either of these two ids. Named here so the rebuilt database's own
(smaller, by exactly these two rows) snapshot table is a stated, understood gap rather than
a silently incomplete mirror of the original.

**The reconciled, authoritative set, going forward:**

```
Real ca_san_jose production snapshots (parcels+zoning+permits):     8, not 9
  -- of which fed a real load (distinct ids):                        6
  -- of which never fed a load ("orphaned", real, not replayed):     2
Real load OPERATIONS (job_run rows, replayed by Stage 6):            8, not 6
  -- because 2 of the 6 loaded ids were each replayed TWICE
     (zoning 699ec193..., permits 70bf19c1...)
Target fact count, unchanged throughout this whole reconciliation:    1,135,140
```

Nothing above changes Stage 6's own plan: the 8-operation replay list in §12.3 was already
correct and already accounts for the asymmetric double-replay of `699ec193...`/`70bf19c1...`.
This section exists so no other number in this document contradicts it.

### 12.10 The operation-2 deviation, closed: code evolution, not contamination alone, and
### not a regression

§12.9's own bounded experiment (fresh scratch database, real 225,039 parcels from
`0216d539...` plus the 4 reconstructed stray parcels identified via `parcel.first_seen_at`)
did **not** reproduce history: `rows_in` 225,040 (predicted 225,042), `rows_out` 214,903
(predicted 214,892, identical to the unmodified rebuild's own figure) — the stray parcels
moved `rows_in` by exactly 1 (only one of the four had real geometry) and moved `rows_out`
by **zero**. The owner's own instruction on a non-reproducing bounded experiment was to
stop and check whether the ingest script's own matching logic had changed since the
historical run, rather than keep guessing. It had.

**OLDREF, found mechanically:** `git log --before='2026-08-07 21:17:24' -1` →
`24849dfee40c608684b356ba78a54bebe4757ec5` (2026-08-07 19:47:48 -0700, "Extract the fact
and parcel_exception insert primitives into core/store, core/exceptions") — the commit
checked out at the exact historical moment `ingest_zoning`'s job_run for `eae7823a...`
started.

**The zoning matching logic changed, and the commit that changed it names the exact delta
by itself, independently, a week before this pass existed.** `git log --oneline
OLDREF..HEAD -- scripts/ingest_zoning_permits.py` shows 17 commits; the load-bearing one is
`40b953d` (2026-08-14 11:21:16 -0700, **eight days after OLDREF, eight days before P55's
first commit**), *"Fix zoning ambiguity: count distinct real classifications, not candidate
rows."* Read directly, not summarized: the old code counted intersecting *candidate
polygon rows* to decide ambiguity; a parcel touching two candidate rows that happened to
agree on the real zoning classification (or where one candidate carried a null/blank
classification field) was wrongly recorded ambiguous even though exactly one real answer
existed. The fix replaced that with counting *distinct real classification values* --
`classify_zoning_candidates()`'s own three-way split (`matched` / `matched with a
polygon-overlap anomaly, non-blocking` / genuinely `ambiguous`) did not exist in the
OLDREF-era code at all (confirmed: `grep` for `anomaly`/`classify_zoning_candidates`
against the OLDREF-era file returns nothing; the old file's own "ambiguous" concept is a
flat "ambiguous (multiple districts)" bucket with no overlap-resolution path). **The
commit's own message states, verified against this exact real snapshot, before P55 ever
touched this repo: "matched 214,892 -> 214,903, ambiguous 12 -> 1, zero-match unchanged at
10,138."** `214,892 -> 214,903` is not a similar number to this rehearsal's own delta -- it
is the identical delta, to the digit, independently recorded eight days before this pass
began.

**Permits matching logic also changed, the same day, a different bug.** `bd5db19` (also
2026-08-14, one minute after `40b953d`), *"Fix APN mismatch between permits and parcels:
shared canonicaliser"* -- a permit CSV row's leading-apostrophe APN artifact (an Excel
"force text" export shape) never string-equalled `parcel.apn` before this fix; a shared
`canonicalize_identifier()` now strips it on both sides of the join. The commit's own
message: 1 of 17,499 real permit rows carried this artifact. A real, if small, change to
which permit rows can match a parcel -- confirmed present, not assumed, by reading the
commit directly.

**Did any P55 commit touch this logic? Checked explicitly and separately, per the owner's
own instruction -- no.** `git show 6bcb97d -- scripts/ingest_zoning_permits.py`, every
added/removed line: exactly two constant reassignments (`LICENCE_ID_ZONING`,
`LICENCE_ID_PERMITS`) plus their own comments. No P55 commit anywhere in this branch's
history touches `load_zoning`, `load_permits`, `classify_zoning_candidates`, or
`canonicalize_identifier`. **This is not a P55 regression.** It is two genuine correctness
fixes (P-something, 2026-08-14, a full arc before this one) landing, correctly, on the same
real production data this rebuild replays -- an improvement arriving late to a database
that was never rebuilt since, not a defect this pass introduced.

**Consequence, stated exactly as the owner's own instruction requires: the exact-count
acceptance bar is retired completely, not narrowed to zoning.** Operation 1 (parcels)
matched only because `--phase e` is a straight per-feature write with no cross-row
matching logic to evolve -- `rows_in`/`rows_out` there are just "how many features are in
the file," unaffected by either the ambiguity fix or the APN canonicaliser. Zoning and
permits both have real matching/resolution logic that has demonstrably evolved since the
historical run, independent of anything this pass did. **1,135,140 is unreachable for TWO
independent, now-confirmed reasons, both recorded:**

1. **A contaminated parcel set** (§12.9) -- historical `job_run` metrics for zoning/permits
   reflect incidental `db-test` invariant-suite parcels sharing the real `ca_san_jose`
   jurisdiction at ingest time, not reproducible by a clean rebuild and not something a
   clean rebuild should try to reproduce.
2. **Evolved matching code** (this section) -- the ingest scripts a rebuild runs today are
   not the ingest scripts that produced the historical figures; two real bug fixes (
   `40b953d`, `bd5db19`, both 2026-08-14) changed how many zoning/permits facts a real
   parcel resolves to, correctly, in ways that will never reproduce the original,
   less-correct counts and should not be made to.

No historical `job_run` metric -- for zoning or permits, on any snapshot, replayed once or
twice -- can serve as a per-operation acceptance bar for this or any future replay. §12.11
proposes the bar this retirement requires.

### 12.11 The replacement bar

Proposed, not yet run against -- `ledgex_schema_check` stays exactly as §12.10 left it
(operations 1-2 committed, 3-8 not run) until this is settled.

**Operation 1 (parcels) keeps the exact-count bar.** `--phase e` reads only the verified
snapshot bytes and writes one parcel/fact set per feature -- no cross-row matching, no
join, nothing for a later bug fix to have changed. It already matched exactly
(225,039/225,039) and §12.10 gives the structural reason it always will: there is no logic
between the bytes and the count for a `git log` to ever show evolving.

**Zoning and permits are accepted on structural correctness, not a count match --
partition invariants that can actually fail, not a re-derivation that calls
`classify_zoning_candidates()` again and risks proving the matcher equals itself.**
Considered a genuinely independent PostGIS re-derivation (a second, hand-written spatial
join bypassing `classify_zoning_candidates()` entirely) and did not build one: it would
substantially duplicate the real join/classification logic, risking a second, independent
place to get the same bug wrong, for a check this partition approach already covers.
Chose partition invariants over persisted, independently-queryable outcome data instead
(facts + `parcel_exception`, never a second call into the matcher):

For each zoning operation:
- **`matched + ambiguous + zero_match == the real-source parcel count, exactly`** --
  `matched` = distinct `parcel_id` with a current `zoning.district` fact;
  `zero_match` = open `parcel_exception` rows, `detector_key='zoning_spatial_join_
  unresolvable'`, `detail->>'reason'='no_containing_district'`;
  `ambiguous` = same detector_key, `detail->>'reason'='multiple_containing_districts'`
  (both reason strings read directly from `scripts/ingest_zoning_permits.py`'s own
  `REASON_NO_CONTAINING_DISTRICT`/`REASON_MULTIPLE_CONTAINING_DISTRICTS` constants, not
  guessed); `real-source parcel count` = `count(*) FROM parcel WHERE jurisdiction_id=
  'ca_san_jose' AND centroid IS NOT NULL` (the same denominator `load_zoning()` itself
  uses). **NEW check** -- nothing in `db-test`'s own invariant suite asserts this
  partition; it is specific to this rebuild's own concern (did every parcel land
  somewhere, with nothing silently falling through all three buckets).
- **No parcel carries two conflicting current `zoning.district` facts.** **NOT a new
  check** -- already an unconditional schema guarantee (`current_fact_pk UNIQUE
  (parcel_id, field_key)` on the `current_fact` materialized view, itself built via
  `DISTINCT ON (parcel_id, field_key)`). Verifying it here would only confirm the
  materialized view refreshed without error, which the ingest scripts' own successful
  exit already establishes.
- **Every zoning/permits fact's parcel resolves through the real parcels snapshot.**
  Simplified from "trace each fact's own parcel" to the stronger, sufficient claim this
  clean rebuild actually needs: `count(*) FROM parcel WHERE jurisdiction_id='ca_san_jose'
  AND id NOT IN (SELECT parcel_id FROM fact WHERE source_id='ca_san_jose.parcels')` is
  **exactly 0** -- i.e., there is no non-real-source `ca_san_jose` parcel in this database
  at all (§12.9's own contamination could not exist even in principle). **NEW check.**
  Named risk, not hypothetical: `check_golden.py`'s own `make_fixture_parcel_and_fact()`
  creates exactly this kind of contamination (§2's own commit already found and fixed
  once) -- `make golden` must not run against this rebuilt database before this check
  runs, or it reintroduces the exact defect being guarded against.
- **Zero facts under the old licence ids** (`cc_by_4_0`/`cc0`) -- already the acceptance
  criterion §4.5 step 13 specifies. **Not new.**
- The delta from the historical `job_run` figure is **stated and explained**, not required
  to be zero -- §12.10's own two named causes (contaminated historical parcel set, evolved
  matching code) are the explanation for every one of the six zoning/permits operations,
  recorded per-operation rather than asserted away.

**The final fact count is recorded with its delta from 1,135,140 and the reason -- and the
direction of that delta is now a BINDING stop condition, not a range.** The predicted
shape, stated before running: strictly more than 1,135,140, because `40b953d`'s own fix
resolves parcels the historical run left as `zero-match`/`ambiguous` (net positive to
`matched`, hence to fact count) and `bd5db19`'s own fix recovers at least the one permit
row it names -- both are strictly additive, never subtractive, to the real fact count. **A
final count at or below 1,135,140 does not merely deviate from a prediction -- it
contradicts both named mechanisms directly, and is a HALT, to be diagnosed before this
document records any final number, not a delta folded into the close-out as if it were
just another explained gap.** No attempt is made here to predict the exact new total --
doing so from the two commits' own before/after deltas (zoning: `+11` per operation, times
however many of the eight operations that logic path affects; permits: `+1` known, more
possible) would be exactly the prose-arithmetic this whole rehearsal exists to distrust.
The real total is measured after the replay runs, not predicted and then defended -- only
its *direction* is predicted and bound.

**Predicted post-rebuild snapshot count: exactly 6, stated before running.** Only the 6
real, verified snapshots this rebuild explicitly registers (`0216d539...`, `b98138f0...`
for parcels; `eae7823a...`, `699ec193...` for zoning; `8f3328b5...`, `70bf19c1...` for
permits, per §12.9/§12.3). Not 24 -- that count (§1, §4.5 step 2) describes the *original*
database's full snapshot table, including `db-test`'s own `test_source`/`p21`/`p34`
fixture rows and the 2 orphaned real snapshots that never fed a load (§12.9) -- none of
which this clean rebuild will ever create, because `db-test` will not have been run
against it and the 2 orphans are explicitly out of replay scope. **§4.5 step 2's own "24
real snapshot rows" is corrected here to state plainly what it actually describes: the
pre-rebuild integrity-check scope on the ORIGINAL database, not a post-rebuild target --
already narrowed to "8, not 9" real `ca_san_jose` production snapshots by §12.9; this
paragraph adds the missing other half, what the REBUILT database's own snapshot table
should contain, which §4.5 never stated at all.**

**A stronger bar is not available, argued rather than assumed:** the only inputs that are
genuinely fixed and reproducible are the retained snapshot bytes (SHA-256 verified, §12.9)
and the current, live matching code -- both already exact-match constraints in the
structural bar above (real-source-only facts, zero old-licence facts). Historical
`job_run` counts are not a third fixed input; they are the output of a *different* version
of that code, which is precisely what this section demonstrates. Asking for exact
reproduction of a value produced by code that no longer exists is not a stronger bar, it is
an unsatisfiable one -- already proven unsatisfiable twice, mechanically, in this rehearsal
alone.

Once acknowledged: rename the current, partial `ledgex_schema_check` aside (per the
owner's own item 3 -- kept, not dropped, alongside the two P55-attempt renamed-aside
copies already retained), rebuild from scratch, and replay all eight operations against
this new bar.
