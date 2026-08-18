## P20 — Record the WORM hazard, then make `make golden` real for the refused path

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)).

---

### 1. The Object Lock finding P19 half-recorded — closed as finding #28

P19 recorded that `ledgex-snapshots-locked` is Object-Locked, `COMPLIANCE` mode, ~100yr
retention, and that this makes concurrent PUTs safe. Unrecorded: `scripts/
run_p5_acceptance.sh`/`run_phaseb_acceptance.sh` both default `OBJECT_STORE_BUCKET` to that
same bucket, as does `.env` — a local acceptance run with `.env` sourced and no override
writes fixture objects into it permanently, and `COMPLIANCE` mode means nobody, not even the
account root, can remove them.

**Listed directly, not estimated.** `list_objects_v2` alone shows 19 objects (it only
returns each key's *current* version — versioning is enabled). `list_object_versions` shows
the real total: **302 object versions across 20 distinct keys, ~2.16 GB**. Classified by
exact byte-size match against `db/fixtures/p5/`/`db/fixtures/phaseb/`'s real file sizes:

- **8 keys match the current fixture files exactly** (`p5_permits_A/B.csv`,
  `p5_zoning_A/B.geojson`, `phaseb_permits.csv`, `phaseb_zoning.geojson`,
  `phaseb_A/B.geojson`) — 239 versions across them.
- **7 more small keys** (22496–23740 bytes, plus one 365-byte and one 0-byte key) match no
  *current* fixture size — almost certainly earlier revisions of `phaseb_A.geojson`/
  `phaseb_B.geojson` from before they were extended — 40 more versions.
- P19's own idempotency-test key adds 5 versions (34 bytes each, already disclosed there).
- The remaining **~2.15 GB — the overwhelming majority of total bytes — is 4 keys of real,
  production-scale content** (a ~210 MB pair, one ~86 MB, one ~5.7 MB) predating P13, not
  fixture-shaped, not attributed to the acceptance suites.

Retention confirmed on both an old key (uploaded 2026-08-08) and a new one
(2026-08-17): `Mode: COMPLIANCE`, `RetainUntilDate` ~100 years from each version's own
upload time. Not attempted to delete — P19 already hit the WORM rejection once.

**Fixed at the source.** Both runners now read their own `ACCEPTANCE_OBJECT_STORE_BUCKET`
(default `ledgex-acceptance-scratch`, auto-created if missing, same idempotent
create-if-missing shape `db.yml`'s own bucket-creation step already uses) and set
`OBJECT_STORE_BUCKET` — the variable every function under test actually reads — FROM it.
A same-named fallback (`${OBJECT_STORE_BUCKET:-safe-default}`) would not have worked:
`.env` unconditionally exports the real `OBJECT_STORE_BUCKET` before either script runs, the
same shape the `DATABASE_URL` problem P18 fixed for `db-test` had. Confirmed live: both
suites run end-to-end with `.env` sourced and no override, writing only into
`ledgex-acceptance-scratch` — the locked bucket's object count unchanged (still 19) after
both runs.

Findings row #28 added and closed. Landed as `f8e23a7`.

---

### 2. The coverage trap — settled, not defaulted

`make golden` printed a message and exited 1, unconditionally, because no fixtures exist.
§6.6 names four classes: composed, partial, refused, geometry-disabled Base Core. Only
refused is reachable today — `STANDING-BLOCKER.md`: every `licence_channel` row is
`allowed=false`, `cleared_by`/`cleared_at`/`evidence_uri` all `NULL`, pending counsel/owner
clearance that has not happened. `compose_property_file.py`'s I6 rights gate therefore
blocks every touched fact, on every channel, for every parcel — correctly, because that is
genuinely the rights state today. Building a composed/partial fixture would mean
fabricating a licence clearance that does not exist.

**The trap:** making `golden` exit 0 once the refused check passes would be indistinguishable
from a target that checked all four classes — the exact silently-passing-gate shape this
repo already fixed in `qa_check`, `conformance`, `test` and `db-test`. But `conformance`/
`test`'s own current stance — exit 1, unconditionally, "not implemented" — is wrong here for
a *different* reason: those two targets check *nothing*, so any other exit code would be
false. `golden`, after this package, checks something *real*. Exiting 1 regardless of
whether that real check passes would make the exit code carry zero information — a broken
refused-path check and a correctly-passing one would look identical — which would make step
4's own break-then-revert proof meaningless, since red and green would be indistinguishable
either way.

**Decided:** the exit code tracks *only* the refused-path check's own correctness — 0 when it
passes, 1 when it fails. The three absent classes are named explicitly, unconditionally, on
every single run — pass or fail, never folded into a bare "PASSED" that could be misread as
full coverage. Same shape `db/tests/invariants.sql`'s `known_gaps`/`test_skipped` sections
(P9/P14) already use in this exact repo: real coverage counted honestly, absence stated
loudly, neither silently inflated nor silently hidden.

---

### 3. The fixture, from real output

`scripts/check_golden.py` seeds a real, honest reference set (real `LICENCE_ID`/
`JURISDICTION_ID`/`SOURCE_ID` from `ingest_parcels.py`, non-fabricated `observed_at`/
`cleared_by`/`cleared_at` matching `db/seeds/day4_sources.sql` exactly — same pattern P11
step 4 established, not the contamination shape it fixed), a fresh parcel + one fact
(`parcel.apn`, fixed value, so the refusal content — and therefore `payload_hash` — is
stable across runs), and composes it through the real, unmodified `compose_property_file.py`.

Normalized per §6.6: uuids → positional tokens, `composed_at`/`delivered_at`/`retrieved_at`/
`fetched_at` → `<TS>`, `compose_ms`/`source_calls`/`compute_cost_micros`/
`storage_cost_micros` stripped, `pack_version`/`ruleset_version` retained exactly,
`unmet_fields`/`refusals`/`attribution`/`omitted_for_rights` sorted lexically. `snapshot_id`
— retained exactly, joined from the linked fact's own `snapshot_id` since `property_file`
itself has no such column (§6.6's phrasing assumes the reader knows where it lives; confirmed
by reading 0012's actual `CREATE TABLE property_file`, not assumed). Refusals asserted
**positively**, not just via full-object equality — exact code/stage/`licence_id`/
`field_keys` assertions run independently, so a bug in the comparison logic itself could
never hide a lost refusal (§6.6's own words: "a golden file that lost a refusal is a
regression").

**Two deviations from §6.6's literal table, reported, not picked silently:**

- **`composer_version`.** Git-SHA-derived (`compose@<sha>[-dirty]`, `get_composer_version()`'s
  own docstring explains why — provenance, not signal-free version drift). It changes on
  *every* commit to this repo, including ones that never touch the composer — this
  package's own remaining commits, for instance. Literal exact-match retention would make
  `golden` red on the very next unrelated commit, permanently — not what "a version bump"
  means in §6.6 (a deliberate, meaningful change to composition logic). Resolved
  pragmatically: retained in the sense that it is present in the fixture, but its *shape* is
  asserted (`compose@[0-9a-f]{40}(-dirty)?` or `compose@no-git:...`) rather than pinned to
  one frozen SHA — still catches a genuinely broken `get_composer_version()`, a narrower
  guarantee than literal retention. **Left open:** whether `composer_version` needs a
  separate, coarser "composition logic version" distinct from its own git-SHA provenance
  value, or whether golden fixtures should simply be re-blessed as routine practice on every
  commit, is a real design question this package does not decide.
- **`as_of`.** §6.6 lists it separately from the `<TS>` group — "Pinned by the fixture, not
  by `now()`" — read as a distinct mechanism, not merely a distinct label for the same
  normalization. `compose()` gained an optional `as_of=` parameter (defaulting to its
  original `SELECT clock_timestamp()` behavior for the real CLI path, unchanged) so
  `check_golden.py` can pass a fixed value — `2099-01-01T00:00:00+00:00`, far enough in the
  future that any real fact insert's live `now()` will always satisfy
  `current_fact_at`'s `recorded_at <= ts`/`effective_from <= ts` requirements without also
  needing to override the fact's own insert timestamps.

Verified reproducible across genuinely fresh databases (not self-comparison bias) — ran
`--bless` once, then ran the comparison mode against two separate fresh scratch databases,
both passing identically. Verified the mismatch detector actually works: temporarily
corrupted the committed fixture's own text, confirmed a real `[FAIL]`, exit 1, restored,
confirmed green again — before ever touching the composer itself for the real break-then-
revert proof in step 4.

Landed as `7d4d3bf`, alongside the §1.2/§6.6/Makefile updates and the spec bump (1.35 →
1.36, real §12 row, verified via `git show` before trusting the rename landed).

---

### 4. Wired, and proven to fail for real

Added as a step in `db.yml`'s existing `schema` job, right after the P19 snapshot-race test
— no fourth job, same reasoning already established there (a real database check, that job
already has one live and disposable; no object-store dependency needed at all —
`compose_property_file.py` never imports `boto3`).

**Broken for real, on the real runner**, per this repo's own deliberate-break discipline
(P12) — and P12's own warning heeded explicitly ("the revert was never written"):

- `390d603` — edited `RIGHTS_BLOCKED`'s refusal message text ("forbids channel" → "does not
  permit channel") in `compose_property_file.py`. Confirmed locally first (predicted, then
  observed): `check_golden.py` exits 1, the full-object equality check fails, the six
  positive refusal assertions still pass (they don't check message text).
- Pushed. `db.yml` run `32086790046` — its first attempt **stalled twice** on the unrelated
  `Install postgresql-client-16` step (~10+ minutes each time, normally ~8 seconds; a
  transient GitHub Actions runner/apt-mirror issue, unrelated to this repo — every step
  before and after it is identical to every other run in this whole session's history).
  Cancelled and re-ran; the second attempt completed normally. `schema` job
  (`95561748039`) result: **failure**, specifically and only at `make golden` —

  ```
  [FAIL] normalized property_file matches the committed golden fixture --
  GOLDEN SUMMARY: refused-path check FAILED (1 failure(s)). ...
  make: *** [Makefile:342: golden] Error 1
  ```

  Every earlier step (`make schema`, `make migrate-verify`, `make db-test`, the
  snapshot-race test) still green — confirming the failure is isolated to `golden`'s own
  regression, not a side effect of the break.
- `7d12df8` — reverted the message text back to `forbids channel`. Confirmed locally first
  (exit 0, all 7 checks pass), then pushed. `db.yml` run `32087239123` (also stalled once
  on the same unrelated apt-get step before completing) — `schema`, `p5-acceptance` and
  `phaseb-acceptance` all green, `make golden` passing again.

Main never carried the break unrecoverable — the revert commit exists, landed, and was
itself confirmed green before this package closed.

---

### 5. Close-out

§1.2's golden row and the Makefile's own `golden:` comment updated to state what the target
actually guarantees now (one class, real; three named, not silently claimed). Spec bumped,
§12 row added, §6.6 gained a short implementation note recording the two deviations. No
schema change — confirmed via a clean `make schema-dump` against a fresh apply, not assumed.

Findings: #28 closed. No new numbered finding for the golden-coverage decision itself — it's
a design decision fully recorded here and in the code, not an open gap.

All four CI jobs confirmed green on the revert commit (`7d12df8`): `schema`,
`p5-acceptance`, `phaseb-acceptance` (run `32087239123`), `docs`/`qa` (unaffected by any of
this package's changes, confirmed passing on the earlier commits in this same push sequence).

**What composed/partial/geometry-disabled would each still need — a list, not a
re-derivation, for whoever picks this up next:**

- **composed.** Two dependencies, one external, one internal. External: at least one
  `licence_channel` row genuinely flipped to `allowed=true` with real `cleared_by`/
  `cleared_at`/`evidence_uri` — a business/legal event, not an engineering one.
  Internal, and not small: `compose()` today stops the instant the rights gate passes
  ("composing a real file (rendering, payload assembly, a success/partial path) is out of
  scope for this minimal composer" — its own words). Actually reaching `status='composed'`
  needs real rendering (assembling payload fields from touched facts), and `ruleset_version`'s
  own current literal value — `"unevaluated -- refused before L5 Rules"` — names an L5 Rules
  engine that does not exist yet either. `core/__init__.py`'s own docstring already lists
  this gap: "no core/rights, no core/compose beyond what already lives in
  scripts/compose_property_file.py."
- **partial.** Same rendering/rules dependency as composed, plus a real product decision this
  package does not make: what distinguishes `status='partial'` from `status='refused'` when
  *some* touched facts are blocked and others are not, or when a required field was simply
  never observed (a different condition from being licence-blocked) — `unmet_fields`
  populated honestly requires that boundary to be defined first, not inferred from code.
- **geometry-disabled.** A genuinely different invariant (I10), largely orthogonal to the
  licence blocker — worth flagging as possibly reachable *sooner* than composed/partial, not
  necessarily behind them in sequence. Needs: an actual "geometry module disabled" mode in
  the composer (does not exist), a real answer for which fields/conclusions count as
  geometry-dependent (`property_file.geometry_tier_used` already exists structurally, but
  nothing computes or checks it today), and by-name refusals for exactly those conclusions
  when geometry is off, distinguishable from a plain rights refusal — I10's own text: "every
  geometry-dependent conclusion refuses by name; no fallback geometry is inferred." Whether
  this can be built as a REFUSED-shaped fixture (like this package's own refused fixture,
  not requiring the licence blocker to resolve at all) is worth checking directly before
  assuming it's blocked the same way composed/partial are.
