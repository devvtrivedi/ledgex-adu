# P52 — separate licence permission from diligence/sign-off status (Phase 1: audit + plan)

Scope, per the P52 prompt's own D1/D2/D3: **reporting semantics only. The I6 gate does not
change in this pass.** This document is Phase 1's deliverable. No code changes accompany it.

## 0. Environment note (not a codebase finding)

Verifying section 4/5's claims required a live database. This machine's actual project
Postgres runs in Docker (`docker ps`: containers `ledgex` on host port 5432 — matches the
Makefile's `DATABASE_URL` default `postgresql://localhost/ledgex_schema_check` — and
`ledgex_minio` for the snapshot object store). All real-data numbers below come from that
container, queried read-only (`SELECT` only, no writes, no deletes). A same-named
Homebrew-managed Postgres@16 was started and stopped in the course of this audit for an
independent from-scratch schema+seed build (used to confirm section 4's claims two ways,
since PostGIS is only available on this machine's Postgres 17 build); it was empty, is
unrelated to the project's real data, and has been fully torn down — stopped, scratch
database dropped, no trace left running. Nothing in the real `ledgex`/`ledgex_minio`
containers was modified.

## 1. Audit findings — conflation sites

### 1.1 The schema is NOT the conflation site

Confirmed directly against `db/schema.sql:952-979` and a live query of `licence`/
`licence_channel` on `ledgex_schema_check` (225,388 parcels, 1,135,140 facts, 24 snapshots —
the one substantial local database with real San José data):

```
id=cc_by_4_0  restriction=attribution  commercial_use=allowed  redistribution=allowed
              attribution_text='Data © City of San José'  terms_url=<CC BY 4.0 URL>
              evidence_uri=NULL  cleared_by=NULL  cleared_at=NULL
licence_channel: all 6 channels, allowed=false, rationale='...counsel/owner sign-off Pending...'
```

`licence.commercial_use`/`.redistribution`/`.restriction`/`.attribution_text` (what the
licence permits), `licence.cleared_by`/`.cleared_at`/`.evidence_uri` (diligence/evidence),
and `licence_channel.allowed` (the actual I6 runtime decision) are three already-separate
columns/tables. 0030's own migration header says this explicitly: *"Licence IDENTIFICATION
is not the same thing as CLEARANCE."* The hypothesis the P52 prompt asked to test — no new
column or migration needed — holds. **The conflation is entirely in what gets queried and
rendered, not in what's stored.**

### 1.2 Where the conflation actually lives

| Site | file:line | What's wrong |
|---|---|---|
| `get_rights()` | `api/main.py:167-182` | `SELECT` omits `attribution_text`, `terms_url`, `evidence_uri`, `observed_at`, `notes`. The viewer literally cannot show "CC BY 4.0, attribution required" today — the data exists in `licence` but this query never fetches it. |
| `loadRights()` | `api/static/viewer.html:147-158` | Renders one `ALLOWED`/`BLOCKED` pill straight off `licence_channel.allowed`. `cc0` (no restriction) and `cc_by_4_0` (attribution required) render identically; the only text distinguishing them is the free-form `rationale` string, not a structured field. No column shows what the licence *permits* versus why the channel is closed. |
| `get_parcel_facts()` reason string | `api/main.py:417-423` | Every `omitted_for_rights` entry gets the same templated sentence: *"Licence X forbids channel Y (§7.3, I6) — default-deny applies whether the licence explicitly denies this channel or simply has no allowed=true row for it."* This sentence is honest about the gate's mechanics but erases the distinction the prompt wants surfaced: "licence permits, sign-off pending" vs "licence unknown/prohibited." |
| `loadFacts()` | `api/static/viewer.html:245-253` | Every blocked fact renders an identical `RIGHTS-BLOCKED` pill; the richer distinction is only reachable via a hover tooltip on the same undifferentiated reason string above. |
| `jurisdictions/ca_san_jose/licences.yaml` | whole file | Descriptive-intent doc (its own header says so explicitly, and §7.3 backs that up), but its `channels: { free_snapshot: true, ... }` keys for `cc0`/`cc_by_4_0` are the licence's own textual grant, not the runtime decision — someone skimming this file without reading its header could walk away thinking channels are open. Named as a readability risk, not a defect: this file is not read by any code path (`git grep` confirms only `_schema`'s JSON Schema and doc prose reference it), so it cannot itself leak a wrong decision. Not in this pass's scope to edit (§7.3 already treats it as documentation, not authority), but worth the owner's awareness. |

### 1.3 Confirmed NOT conflated — leave alone

- **`core/rights.py`'s `evaluate_rights_gate()`** — reads only `licence_channel`, returns only
  `(allowed_by_licence, blocked_by_licence)`. No diligence concept enters this function at
  all. Exactly one job, done cleanly.
- **`scripts/compose_property_file.py`'s `_compose()`** — builds each `RIGHTS_BLOCKED`
  refusal from `blocked_by_licence` alone: `detail: {licence_id, channel, field_keys}`,
  `message: "Licence {id} forbids channel {channel} for touched field(s): {keys}."` No
  diligence language here either.
- **`db/tests/invariants.sql`** — its licence/licence_channel tests use an isolated
  `test.*` namespace (0029's per-dimension fixtures), never `cc0`/`cc_by_4_0`. Unaffected by
  anything this pass could do.
- **`scripts/check_conformance.py`'s `test_licences_not_broader_than_appendix_k`** — does not
  exist as real code. It is explicitly listed in `NOT_YET_CHECKED`
  (`scripts/check_conformance.py:79-83`) alongside the reason ("no machine-readable Appendix
  K to diff against"). Nothing to touch or break here.

### 1.4 Fixture/test inventory — none require modification for a reporting-only design

Checked each named in the prompt directly:

| Test/fixture | What it actually asserts | Touched by a reporting-only change? |
|---|---|---|
| `db/tests/invariants.sql` | `test.*`-namespaced licence dimension fixtures, `fact.licence_id NOT NULL`, etc. | No — different namespace entirely. |
| `tests/golden/ca_san_jose/*.json` | **Byte-exact** `payload_hash` (SHA-256 of the full composed JSON) over the property_file payload, including the `RIGHTS_BLOCKED` refusal's exact `detail: {channel, field_keys, licence_id}` and `message` string, verified directly in `refused.json` and `election_required.json`. | **Only if the composer's refusal construction is touched.** This is the load-bearing constraint on the whole design (§4 below). |
| `scripts/test_viewer_rights_gate.py` | `facts[]` non-empty, `omitted_for_rights[]` non-empty, correct `licence_id` partition, and the blocked sentinel value byte-absent from the serialized response. No assertion on `reason` string content or on `OmittedForRights`'s exact field set. | No — new optional fields and new reason wording pass through untouched. |
| `scripts/smoke_real.py` step 15 (`step_rights_gate`) | Same shape: no leak under `facts`, every blocked `field_key` present in `omitted_for_rights` by `licence_id`, byte-absence of blocked values from the raw response. No string-content assertion. | No. |
| `scripts/check_conformance.py` | `test_licences_not_broader_than_appendix_k` doesn't exist yet (real code, see 1.3). | No. |

This is the single most important scoping fact for Phase 2: **the composer's own
`RIGHTS_BLOCKED` refusal (`scripts/compose_property_file.py`, `core/rights.py`) is
golden-locked byte-for-byte and must not be touched.** Every viewer-visible test that
*could* be touched checks structure and leakage, never exact wording — which is exactly the
surface a reporting-only change needs to be safe.

## 2. I6 before vs. after

Per D1, every cell must be identical. It is — because Phase 2 (as recommended in §4) never
writes to or re-derives from `licence_channel`; it only widens what else gets queried
alongside it.

| Licence | Channel | `evaluate_rights_gate` today | After Phase 2 |
|---|---|---|---|
| `cc0` | any of the 6 | `allowed_by_licence['cc0'] = False` (all 6 real rows `allowed=false`) → blocked | **identical** |
| `cc_by_4_0` | any of the 6 | `allowed_by_licence['cc_by_4_0'] = False` (all 6 real rows `allowed=false`) → blocked | **identical** |
| `unknown` | any of the 6 | no `licence_channel` row exists for id `'unknown'` → default-deny → blocked | **identical** |

No cell differs. Confirmed live: `SELECT licence_id, channel, allowed FROM licence_channel
WHERE licence_id IN ('cc0','cc_by_4_0')` returns exactly 12 rows, all `allowed=f`, on the
real database.

## 3. What the caller sees change (concrete response-shape diff)

**`GET /v1/rights`** — widen the join to include `attribution_text`, `terms_url`,
`evidence_uri`, `observed_at`, `notes` (all already on `licence`, just not selected today),
plus two *computed, not stored* fields per row:

```
rights_position:  "allowed"  if commercial_use='allowed' and redistribution='allowed'
                   "restricted" if either is 'prohibited'
                   "unknown"  if either is 'unknown'
                   (a pure read of already-existing columns; never written anywhere)

diligence:         "written_confirmation_pending" if cleared_by IS NULL
                    "cleared" if cleared_by IS NOT NULL
                    (same — pure read of cleared_by/cleared_at)
```

**`GET /v1/parcels/{id}/facts`** — `OmittedForRights` gains two optional fields
(`rights_position`, `diligence`), computed the same way via a join on the `licence_id`
already in hand inside the existing blocked-fact loop. `reason` becomes two-branch instead
of one-size-fits-all:

```
if rights_position == "allowed":
    f"Licence {licence_id!r} permits channel {channel!r}; not yet cleared for output "
    f"(diligence: {diligence})."
else:
    f"Licence {licence_id!r} forbids or has not confirmed channel {channel!r} (§7.3, I6)."
```

Both routes' underlying `facts` vs `omitted_for_rights` partition, and every `licence_channel`
read, stay byte-identical — this is additive columns/fields only, verified against §2's table.

## 4. Recommended design

**No migration.** Every field needed already exists on `licence`
(`commercial_use`/`redistribution`/`restriction`/`attribution_text`/`terms_url`/
`evidence_uri`/`observed_at`/`cleared_by`/`cleared_at`). `rights_position` and `diligence`
are computed at query time (SQL `CASE` or a small Python helper in `api/main.py`), never
persisted, never read by `evaluate_rights_gate`. This satisfies §7.3's own instruction
("nothing else grants a channel") by construction — a computed reporting label cannot become
a fourth channel-eligibility authority because nothing ever reads it back into a decision.

Alternatives considered and rejected:

- **New `licence.diligence_status` column.** Rejected — `cleared_by IS NULL` already carries
  this information exactly (0030's header: *"licence.cleared_by, cleared_at and evidence_uri
  were all NULL... the audit's own diligence register lists ... Pending"*). A new column
  would duplicate an existing NULL-ness check as redundant state that could drift from it.
- **New `RefusalCode` (e.g. `RIGHTS_PENDING_CLEARANCE`).** Rejected for this pass — would
  require a spec version bump and a §12 row per the prompt's own instruction, and more
  importantly the composer's refusal is golden-locked (§1.4); inventing a code implies
  changing what the composer emits, which this pass must not do. If Phase 3 ever wants a
  distinct refusal code, that is a live option then, argued fresh against real success-path
  behavior — not absorbed here.
- **Touching `evaluate_rights_gate`'s return shape.** Rejected — it has exactly one job
  (§1.3) and both call sites already have everything else (the touched fact's `licence_id`)
  needed to do the enrichment join themselves. Adding a second concern to this function
  because a third one (reporting) also wants `licence_id` is the wrong direction.

## 5. L0 / LD-1 analysis and the PASS 1 specification

**Confirmed independently, twice** — once against the real `ledgex_schema_check` database
(Docker, 1,135,140 real facts) and once against a from-scratch schema+seed build in an
isolated scratch database:

```
SELECT count(*) FROM source WHERE id = 'ca_san_jose.city_limits';        -- 0
SELECT count(*) FROM field_definition WHERE field_key = 'jurisdiction.incorporated'; -- 0
SELECT count(*) FROM fact WHERE field_key = 'jurisdiction.incorporated'; -- 0
```

`db/seeds/day4_sources.sql` seeds exactly three sources: `ca_san_jose.parcels`,
`ca_san_jose.zoning_districts`, `ca_san_jose.building_permits_active`. No `city_limits` row,
ever, in this repo's seed data.

**`scripts/compose_property_file.py` itself says so.** Its own header, verbatim
(`scripts/compose_property_file.py:44-48`): *"'gate' (per 0012's own comment) names facts
that resolve JURISDICTION and never appear in a payload (e.g. a city_limits-shaped fact) --
**nothing ingested so far plays that role.**"*

Tracing `_compose()` directly: `jurisdiction_id` is read straight off the `parcel` row
(`SELECT id, jurisdiction_id, apn FROM parcel WHERE id = %s`, line 448) — a plain FK assigned
at ingest time, never resolved via a spatial join or lookup against any city-limits-shaped
fact. The `touched` set is `current_fact_at(ts) WHERE parcel_id = %s` (line 526-530) — every
fact this parcel actually has, which today can only be `parcel.*`/`zoning.*`/`permits.*`
fields, because that's all any ingest script has ever written. **There is no code path,
anywhere in this composer, that ever queries, requires, or gates on a
`jurisdiction.incorporated` fact.**

**Answer to the prompt's question 3, directly:** yes. If `cc0`/`cc_by_4_0`'s channels were
cleared today (hypothetically — not being done), a composition for a real San José parcel
would proceed straight through L0 to a non-rights-refused outcome, and the L0/LD-1 gate
would never be evaluated at any point, because nothing in the schema, the seeds, or the
composer represents it. `prompts/STANDING-BLOCKER.md`'s claim that `city_limits`'s
`licence: unknown` (**"LD-1 — BLOCKS EVERYTHING"**) is one of two things currently holding
composition closed is **not accurate as a description of enforced behavior** — it accurately
describes `sources.yaml`'s stated intent, but that intent has no runtime representation. The
only thing actually blocking every composition today is `licence_channel.allowed=false` on
`cc0`/`cc_by_4_0` (0030). This is exactly D3's concern, now confirmed rather than assumed —
worth a correction note on `STANDING-BLOCKER.md` itself, flagged as an open question (§9)
since a documentation fix arguably falls inside "reporting," but the owner should decide.

**PASS 1 specification** (not implemented here — named per the prompt's requirement to cost
it now):

1. A real `source` row, `id='ca_san_jose.city_limits'`, `licence_id='unknown'`,
   `phase_status='blocked_rights'` — same posture `sources.yaml` already declares, now given
   a runtime row. Still blocks; this is not a clearing of any kind (D3's own constraint).
2. A `field_definition` row for `jurisdiction.incorporated`.
3. An actual mechanism by which `_compose()` (or an earlier resolution step) touches a
   `jurisdiction.incorporated` fact for every parcel — today no such fact can exist because
   no ingest script writes one. This needs real design (a boolean per jurisdiction? a spatial
   join against a real city-limits geometry?) — out of scope to design here; PASS 1's own
   plan document should do that, not be defaulted to a placeholder in passing.
4. A positive test: a composition for a real San José parcel refuses with `LICENCE_UNKNOWN`
   (or `RIGHTS_BLOCKED`, depending on how PASS 1 wires it — §9's table lists `LICENCE_UNKNOWN`
   specifically for "a gate source is unconfirmed" at L0) citing the `city_limits` fact,
   independent of `cc0`/`cc_by_4_0`'s own posture.
5. A negative control, this repo's own established style (`db/migrations/0036`'s test pair is
   a good local precedent): a test that would go RED if the L0 touch were silently removed —
   e.g., construct a fixture where `cc0`/`cc_by_4_0` are (test-fixture-locally) cleared but
   the `city_limits` fact is still `unknown`, and assert the composition *still* refuses.
   Without this, a PASS 1 that adds the row/field but never actually wires the composer to
   touch it would pass every other test while remaining exactly as unenforced as it is today.

**Confirmed: nothing in this (reporting-only) pass touches any of the above.** Phase 2's
design (§4) reads only `licence`/`licence_channel` for `cc0`/`cc_by_4_0`/`unknown` as already
seeded; it adds no source row, no field_definition row, and no composer logic.

## 6. PASS 3 costing — U1 vs U2

**Immutability confirmed absolute, both tables, no carve-out:**
`db/migrations/0027_licence_immutability.sql` — `licence_no_update`/`licence_no_delete`,
unconditional `RAISE EXCEPTION` on any `UPDATE`/`DELETE`, no exception clause.
`db/migrations/0033_licence_channel_immutability.sql` — same shape, same table-wide, same
unconditional raise. `cleared_by`/`cleared_at`/`evidence_uri` live on `licence`, so they can
never be set on the existing `cc0`/`cc_by_4_0` rows by any means short of a new licence row
(0030's own migration comment says exactly this, in its final paragraph, about
`commercial_use`/`redistribution`).

**U1 (rebuild) — recommended, and confirmed cheap, not merely assumed:**

Real local databases enumerated directly (Docker container `ledgex`, the actual project
database, not the empty Homebrew-managed database of the same name that this audit's own
scratch tooling briefly and confusingly also created — see §0):

| Database | facts | parcels | snapshots | property_file | Disposition |
|---|---|---|---|---|---|
| `ledgex_schema_check` | 1,135,140 (27,936 `cc0` + 1,106,852 `cc_by_4_0` + ~187k across many `test.*` fixture namespaces) | 225,388 | 24 | 7 (all `status='refused'`) | The one substantial real database. Rebuildable — see below. |
| `ledgex_smoke` | 40 | 21 | — | 0 | Trivial; `make smoke-real` regenerates it from a fresh `--phase d` ingest against a real fetch. |
| `ledgex_viewer` | 3 | 1 | — | 0 | P40/P42's demo fixture (`scripts/seed_internal_test_licences.py`); regenerated by re-running that script. |
| ~50 `p2x_*`/`ledgex_p3x_*`/`ledgex_p4x_*` scratch databases | — | — | — | — | Disposable per-prompt scratch/test databases (P22–P43 naming). Zero production content, not costed further. |

**Content-addressing verified, not assumed.** `ledgex_schema_check`'s 24 snapshot rows for
the three real sources point at keys like
`s3://ledgex-snapshots-locked/sha256/02/0216d539a3995ccc.../`,
`.../sha256/ea/eae7823a.../`, `.../sha256/8f/8f3328b5.../` — I confirmed these objects
physically exist in the running `ledgex_minio` container (`ls` inside the container showed
each key's directory with a populated `xl.meta`, i.e. present and intact at the object-store
level). A snapshot id is `source_id || ':sha256:' || content_hash` (§3.5) — re-ingesting from
the *same retained snapshot id* reproduces byte-identical source bytes by construction; this
was checked for existence, not re-hashed end-to-end in this pass, so full byte-integrity
re-verification is still worth a real run before actually executing PASS 3, not merely
assumed from existence.

**Recommendation: U1.** Drop the target database(s), reapply every migration, reseed with
the corrected licence posture, re-ingest from the retained snapshots. No trigger touched;
0027/0033 stay exactly as strict as they are today. This matches this repo's own established
precedent for exactly this shape of problem, verbatim from `CLAUDE.md`: *"once a table is
immutable ... the only remaining answer is to rebuild: drop the database, reapply every
migration, reseed."*

**U2 (drop and re-add the immutability triggers) — not recommended.** Directly against
0027/0033's stated intent (*"every fact that already cites this licence depends on its rights
position staying exactly as recorded"*), and U1 is viable and cheap here, so there is no
justification for weakening the guarantee to avoid a rebuild that costs little. Not proposed
further.

**What becomes viewable, and what doesn't:** every local database above becomes viewable
under real clearance after a U1 rebuild — all three are rebuildable from retained,
content-addressed, verified-present snapshot bytes or from trivial script reruns. **The one
database this does not touch is the hosted one named in `prompts/README.md` row #23** (a
Supabase instance) — its status is recorded there as unverified, and per this pass's own hard
constraints it was not queried, connected to, or touched in the course of this audit. Whether
it holds anything real, and whether U1 applies to it the same way, is answered by finally
running the audit finding #23 has flagged as outstanding since at least P39 — not by this
pass.

## 7. Spec impact

None required for this pass. `RIGHTS_BLOCKED` and `LICENCE_UNKNOWN` already exist as
distinct §9 codes and already distinguish "forbidden in this channel" from "gate source
unconfirmed at L0" at the vocabulary level — Phase 2 invents no new code, changes no
existing code's meaning, and touches no refusal the composer emits (§1.4, §4). `core.model.
Refusal.detail` is already an open `dict[str, Any]` if a composer-side enrichment were ever
wanted later, but nothing in this pass exercises that, since the golden fixtures lock the
composer's current `RIGHTS_BLOCKED` detail byte-for-byte.

One documentation-only item flagged, not a spec change: `prompts/STANDING-BLOCKER.md`'s
description of `city_limits`/LD-1 as actively blocking composition is inaccurate per §5 above
(it has zero runtime representation). Whether correcting that prose counts as in-scope
"reporting" for this pass, or should wait for PASS 1 to actually give it teeth, is listed as
an open question below rather than decided unilaterally here.

## 8. What this would not prove

- That Phase 2's exact copy/wording ("written_confirmation_pending", etc.) is the right
  language for a real viewer or a real customer-facing surface — needs a human read, not
  just a passing test.
- That `attribution_text = 'Data © City of San José'` is legally sufficient CC BY 4.0
  attribution. Also worth flagging directly: this text differs slightly from
  `docs/LEDGEX_SPEC.md` §7.2's own transcription of `licences.yaml`
  ("Contains data from the City of San José."). The live database's seeded value is the one
  that would actually render if Phase 2 ships — confirmed by reading `db/seeds/
  day4_sources.sql:40` directly, not by trusting the spec's prose copy of it. This drift
  predates P52 and is not this pass's to fix, but it means whoever reviews attribution
  wording should read the seed file, not the spec section, as source of truth.
- That `evidence_uri` will ever be populated, or by what process — only that it is currently,
  honestly, `NULL`, and this pass does not fabricate a value for it.
- That PASS 1's L0/`city_limits` runtime representation is fully designed — §5 specifies its
  acceptance criteria, not its implementation (in particular, exactly how a
  `jurisdiction.incorporated` fact gets produced is real, undesigned work).
- That the retained snapshot objects in MinIO are byte-identical to their recorded
  `content_hash` — existence was confirmed directly; a full re-hash was not performed in this
  pass.
- Anything about the Supabase-hosted database (finding #23) — untouched, per the prompt's own
  hard constraint.

## 9. Open questions for the owner

1. Bless (or redirect) the exact `rights_position`/`diligence` vocabulary in §4 —
   `"allowed"/"restricted"/"unknown"` and `"written_confirmation_pending"/"cleared"` are this
   audit's proposal, not a decision.
2. Is correcting `prompts/STANDING-BLOCKER.md`'s inaccurate description of the L0 gate
   in-scope for this reporting pass, or should it wait until PASS 1 actually implements the
   gate it currently describes as already real?
3. Should PASS 1 (giving the L0/LD-1 gate a real runtime representation) be scheduled next,
   now that §5 confirms it is a genuine, currently-unenforced gap rather than a documentation
   nicety?
4. Does `attribution_text`'s current wording need a legal look before Phase 2 surfaces it
   anywhere a viewer might read it, even internally?
5. Should the Supabase-hosted database (finding #23) finally be audited, now that U1's
   mechanics (§6) are worked out for the local databases and could plausibly extend to it —
   explicitly not decided or attempted here, per the prompt's own constraint.

---

## 10. Phase 2 amendment 4 — attribution_text factual assessment (not legal)

Not a blocker for Phase 2, done now because of a sequencing constraint: `licence` is
immutable (0027), so `attribution_text` can never be corrected in place — only a new
licence row or a full rebuild (§6's U1) can change it. PASS 3's rebuild is the only cheap
moment to fix it; reviewing it after PASS 3 means paying for a second rebuild. Recorded
here, not fixed: neither this audit nor the owner is a lawyer, and no legal conclusion is
embedded below or anywhere in code/comments from this pass.

**Current value, read live from `ledgex_schema_check` (not transcribed from the spec, which
carries a slightly different string — see the gap this itself represents, below):**

```
licence_id:        cc_by_4_0
attribution_text:  'Data © City of San José'
terms_url:         'https://creativecommons.org/licenses/by/4.0/'
```

CC BY 4.0 attribution conventionally wants five elements. Assessed against the current
value:

| Element | Present? | Detail |
|---|---|---|
| Title (of the specific work) | **No** | `attribution_text` names no dataset ("Parcels", "Zoning Districts") — a consumer citing this string alone cannot say which of the city's datasets it attributes. |
| Creator / rightsholder | Partial | "City of San José" is named via the © mark. No named individual or department, which is likely fine for a municipal open-data publisher but is an assumption, not a confirmed convention for this specific steward. |
| Source (link to the original) | **No** | Neither `attribution_text` nor `terms_url` links to the dataset's own source page (the GIS Open Data portal or data.sanjoseca.gov listing) — `terms_url` links to the CC BY 4.0 legal deed, a different thing. |
| Licence name + link | Partial | `terms_url` is a correct, live link to the CC BY 4.0 deed, but it is a SEPARATE column from `attribution_text` — nothing in the current schema or seed composes them into one attribution string a consumer would actually display together. Whether a real rendering joins them is a Phase 3+/customer-delivery question, not decided here. |
| Indication of changes made | **No, and arguably doesn't belong here** | Whether a given output modifies the source data is a property of THAT COMPOSITION/DELIVERY, not of the licence identification itself — the same touched fact could be delivered verbatim in one channel and transformed (e.g. reprojected, joined, summarized) in another. Recording it on `licence` would conflate a per-licence fact with a per-use one, the same shape of error this whole pass exists to fix one level up. This audit's opinion: this belongs at compose/delivery time (perhaps `property_file.attribution`, already a real jsonb column — P52 does not design that mechanism), not on `licence`. Not decided or implemented here.

**What this finding does NOT do:** it does not conclude the current `attribution_text` is
legally insufficient, and it does not propose replacement text — inventing either would be
exactly the kind of legal conclusion embedded in a migration comment section 12 of the P52
prompt explicitly warned against. It records a factual gap against a named external
convention so the owner can decide whether counsel review happens before PASS 3, as
`prompts/P52-rights-vs-diligence.md`'s own §8 already flagged as an open question. See §9
question 4, unchanged by this section — recorded, not answered.

## 11. Phase 2 close-out

Implemented exactly what §4 designed, no more:

- `api/main.py`: `derive_rights_position()`/`derive_diligence()`, one implementation each,
  called by both `GET /v1/rights` (widened `SELECT`, two new computed fields per row) and
  `GET /v1/parcels/{id}/facts` (`OmittedForRights` gained optional `rights_position`/
  `diligence` fields; two-branch `reason` wording). Amendment 1's vocabulary
  (`permits_use`/`permits_with_conditions`/`prohibits_use`/`unknown`, never `"allowed"` or
  `"restricted"`) and Amendment 2's three-state diligence (`cleared`/`cleared_unevidenced`/
  `written_confirmation_pending`) shipped exactly as specified.
- `api/static/viewer.html`: Rights tab gained Rights position/Diligence columns (plus an
  inline attribution note when `restriction='attribution'`) alongside the untouched,
  still-verbatim per-channel Allowed/Rationale columns. Facts tab's blocked rows now show a
  two-line detail (`PENDING CLEARANCE` + licence posture, vs. `RIGHTS-BLOCKED` + default-deny
  note) instead of a single uniform pill — visible text, not tooltip-only.
- `scripts/test_rights_reporting.py`: new, all passing — the full 45-row
  `derive_rights_position` truth table, the 4-row `derive_diligence` table, a fake-cursor
  proof that `core.rights.evaluate_rights_gate`'s default-deny behavior is unchanged, and two
  database-backed tests against real seeded data (model_training's rationale stays distinct
  from the other five channels; neither response ever reports `diligence='cleared'` while
  `evidence_uri IS NULL`).
- `prompts/STANDING-BLOCKER.md`: corrected per Amendment 3 — the LD-1/`city_limits` sentence
  now carries a dated correction citing this document's own §5 finding, rather than standing
  as an uncorrected claim that gate is live. Confirmed `build/qa_check.py` validates only
  `docs/*.md`, never `prompts/*.md` (`make state` reads `prompts/README.md`'s package table
  only, for a status line, never as a pass/fail gate) — this edit has no build-gate
  consequence, checked directly rather than assumed.
- This document: §10 above (Amendment 4's factual, non-legal attribution assessment).

**Confirmed unchanged, every existing gate run against real data, none edited:**
`make db-test` (122/122), `make golden` (both real fixtures + the election_required one, all
byte-exact `payload_hash` matches), `make conformance` (0 failures), `scripts/
test_viewer_rights_gate.py` (5/5), `make smoke-real` (14 passed, 1 skip for the
documented idempotency reason — step 15's byte-level cc_by_4_0 absence proof included),
`.claude/hooks/test_guard_destructive.py` (38/38).

**What did not ship, and why:**
- No migration, no new column — confirmed unnecessary, exactly as §4 predicted.
- `core/rights.py` and `scripts/compose_property_file.py` — untouched, per the hard boundary;
  their golden-locked payloads are byte-identical to before this pass.
- No new refusal code, no spec version bump — §7's reasoning held throughout implementation;
  nothing arose that needed one.
- `attribution_text` itself — not rewritten (§10); not this pass's decision to make.
- The Supabase database (finding #23) — untouched, per explicit out-of-scope instruction.

**Where reality corrected the plan, not the other way round:** none found. Every mechanism
Phase 1 predicted (existing columns sufficient, golden fixtures byte-locking the composer,
`OmittedForRights`/`get_rights` as the two extension points, `evaluate_rights_gate` reachable
via a fake cursor without a real database) held exactly as designed once implemented against
a real database. The one genuine surprise was not a plan defect: the `internal_test.*` P42
fixture already had `cleared_by='internal_test_seed'` with `evidence_uri IS NULL` in real
seeded data, which meant `cleared_unevidenced` rendered correctly on real, organic data
(`ledgex_smoke`'s own Rights tab) without needing the synthetic demo fixture built for it —
confirmation the state was worth building, not a correction to anything Phase 1 claimed.
