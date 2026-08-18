## P28 — make liveness: the last named gate that does not exist

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Report before writing.

Read: `docs/LEDGEX_SPEC.md` §1, §6.4, §7 in full, §5's C7 fetch policy (recorded in §12's
change record at the migration-0028 entry; implemented in `run_one_fetch`/`fetch_and_hash`).

---

### 1. Is a liveness probe a "fetch" under C7? No — argued, not assumed.

C7's actual text (§12, migration 0028 entry): *"the ingest script now writes a snapshot
row for EVERY fetch, including a zero-result response or an HTTP error, with http_status
recorded... a failed fetch is part of the provenance record."* `fetch_and_hash`'s own
docstring: *"C7 policy is to snapshot every fetch... a failed fetch is part of the
provenance record, not something that skips writing a snapshot row."*

What makes something a fetch in this sense is not "an HTTP request happened" — it's that
the **complete** response was captured, content-addressed, and durably stored as the thing
a future Fact could point back to (I2: a retrieved fact needs `source_id` + `snapshot_id`).
`snapshot.content_hash` is a real, verifiable claim: this exact hash is the sha256 of the
entire artifact object-stored at this URI. That claim is only true when the whole response
was hashed.

A liveness probe, by §6.4's own "responds with expected fields" and step 3's own "not a
225k-feature download" constraint, must read a **bounded prefix**, not the complete
artifact. Writing a `snapshot` row for a prefix read has exactly two possible shapes, both
wrong: (a) hash only the prefix and store it as `content_hash` — a false claim, since
nothing durably stored is actually addressed by that hash (the object never gets uploaded;
this would be recording a digest of bytes nobody kept, which is worse than recording
nothing — "do not invent values to fill a silence"); or (b) do a full fetch just to get a
correct hash — which is exactly the disallowed full ingest.

**Conclusion: liveness sits outside the ingest path entirely. It writes no `snapshot` row,
ever, and is not a `job_run` in the L1/L2 ingest-loop sense (§5's "job_run opens → L1
fetch → L2 content-address...").**

§6.4 still wants it to be monitoring: *"a city breaking is a failing test, not a support
ticket."* A check whose failures leave no trace is not that. `job_run.schema_drift`
already has a declared meaning that fits exactly, and it has never had a real writer:
0051's own committed comment (`db/schema.sql`, `COMMENT ON COLUMN job_run.schema_drift`)
states its meaning is *"fields expected but missing — a source dropping an expected
column"* and names this precise gap: *"ingest_parcels.py's phase_c builds a dict that DOES
match this column's declared shape but has never persisted it... a real, separate, still-
open gap, not fixed by this migration."* This is that gap's forced need, not a convenience
reach — the column's declared meaning was written before this package existed and matches
what liveness produces without stretching it.

Design: liveness writes its own `job_run` row per source, per run — `job_key='liveness'`,
`source_id=<the source>`, `snapshot_id=NULL` (never set, per the argument above),
`status` succeeded/failed, `schema_drift={"missing_fields": [...]}` when a declared field's
raw key is absent from the prefix, `error` set on an HTTP/connection failure, `metrics`
left null (this is exactly the shape `schema_drift` already means, not a generic
per-job breakdown). No new column, no migration.

**On durability**: this job_run row lives in the same disposable, migrations-only database
every scheduled run creates fresh (see §2) — it does not persist across runs the way a row
in the real dev/production database would. That is a real, named limitation, not hidden:
the actual cross-run monitoring trail this project already relies on for every other CI
signal is GitHub's own workflow-run history (`gh run list`/`gh run view`, the same
mechanism P27 used throughout), which is genuinely durable and already how a red run gets
noticed. Writing job_run within the run is still worth doing — it exercises
`schema_drift`'s real declared meaning for the first time, and gives each run structured,
queryable-within-that-run diagnostic detail (which field, on which source) beyond a bare
exit code — but it is not being oversold as a persistent database of liveness history.
Using the real Supabase database instead was considered and rejected: it would require
storing live production credentials as a GitHub secret, a real new trust decision this
package should not make unilaterally, and finding #23 already flags that database as the
one this project is deliberately most cautious about touching from an automated context.

---

### 2. Schedule, not push-gated — argued against P12's precedent, not despite it

§6.4 lists `make liveness` among the CI gates, but with its own blank-line separation from
the other five and its own explanatory sentence — the spec's own formatting already treats
it differently before this package touches anything.

**The naive reading** ("§6.4 says CI gate, so gate every push on it") fails for a reason
P27 just paid to learn concretely: gating a job on a third party's uptime means an
unrelated commit — a comment fix, a spec typo — fails because San José's ArcGIS portal is
having a bad day, for a reason nobody who pushed that commit can fix. `CONVENTIONS.md`'s
own hard rule, *"every CI workflow must be green before a package starts, verified on the
real runner"*, would then block every future package on an external outage this project
has zero control over — not a rare edge case for a government open-data portal, a routine
one.

**P12 already rejected "scheduled, non-blocking" once** — but for a materially different
failure, and the difference is the argument, not a footnote. P12's actual finding was that
`run_p5_acceptance.sh` was *"never run by any CI gate"* at all — not scheduled and ignored,
literally not wired into anything. P12's own text, considering the weaker alternative,
named the real risk precisely: *"a scheduled, non-blocking check can go red and stay red
through several packages before anyone reads its output, because reading it was never a
precondition for starting work the way the two real gates are."* That risk is specific to
an **internal correctness regression** — caused by a commit in this repo, silently
persisting because nothing about starting new work required looking at it.

Liveness fails for the opposite reason: **almost never because of a commit in this repo.**
A commit changing `core/model.py` cannot make San José's server stop returning `APN`. Two
consequences follow, and they cut against each other:
- Because the cause is external, gating every push on it (as §6.4's naive reading argues
  for) actively erodes the "must be green" precondition's own integrity — it starts
  reporting failures no committer can act on, training exactly the ignore-red-because-it's-
  probably-not-us reflex CI gates exist to prevent.
- Because the cause is external, the P12 risk (silently stale through several packages)
  is less severe here than it was for internal regressions: this project does not "start
  new work" against a jurisdiction pack the way it starts work against `core/` on every
  single package, so the cost of a scheduled check not being re-checked before every
  unrelated package is genuinely lower — nothing about, say, fixing a CI timeout (P27)
  depended on San José's endpoints being observed fresh that day.

**Decided: scheduled (`schedule:` cron, daily) plus `workflow_dispatch` for a manual run,
not `push`/`pull_request`.** Unlike P12's rejected case, this is not "scheduled and
forgotten" — a failing scheduled run still shows up red in the Actions tab exactly like
any push-triggered failure (the same discovery mechanism P27 used throughout), and it
still fails loudly (nonzero exit, no soft-pass path) satisfying "a failing test, not a
support ticket" without extending "must be green to start a package" to a promise this
project cannot keep. `CONVENTIONS.md`'s own "two workflows" line is corrected in this
package (§5) to name three and to scope "must be green before a package starts" to the
push/PR-gated two — liveness's own health is a check to make when the work at hand
actually touches ingest or a jurisdiction pack, not an unconditional precondition for
starting unrelated work.

**What a developer does when it goes red for a reason they can't fix**: nothing blocks —
they keep working. The red run is evidence a source may need attention (open a finding,
check `phase_status`), not a wall between them and every other package. That is the whole
point of not gating this on push.

Per P27: `timeout-minutes` on the job, plus a tighter step-level timeout on the actual
probing step, since an external endpoint hanging (not just erroring) is exactly the
failure mode P27 found once already, one layer down (apt, not a city government server —
but the shape is identical: an external dependency with no SLA to this project).

---

### 3. "Responds with expected fields" — cheap, and what it actually catches

A 200 status proves reachability, not liveness in §6.4's sense — the check must confirm
the endpoint still serves the fields the pack declares. Full ingest is explicitly
disallowed (a 225k-feature download is not a probe). The design: a **bounded-prefix GET**
(`requests.get(..., stream=True)`, read at most 256 KiB, then stop and close the
connection regardless of what the server had left to send) — cheap, bounded, and, for
every real response this pack's three active sources produce, comfortably past the first
feature's full `properties` object (GeoJSON exports from this portal write every feature
with the complete property set, so the first feature already carries every key the whole
file will ever carry).

**What "contains the field" means, checked without ingesting**: for the GeoJSON sources
(parcels, zoning_districts), a raw substring check for the quoted property key
(`"APN"`, `"PARCELID"`, `"ZONING"`, `"ZONINGABBREV"`) inside the prefix bytes — cheap,
no JSON parsing required, and a false negative only if the key legitimately isn't in the
first N features, which 256 KiB rules out in practice for this pack (verified in §4).
`parcel.geometry` has no named key — it's the GeoJSON `"geometry"` member itself, checked
structurally (`"geometry"` and `"type"` both present) rather than by name. For the CSV
source (`building_permits_active`), the header row alone (first line of the prefix) is
parsed and checked for `ASSESSORS_PARCEL_NUMBER`/`ISSUEDATE` — the two raw columns
`permits.active`/`permits.series_earliest` are actually derived from (see
`ingest_zoning_permits.py:load_permits` — `permits.active` isn't a literal column, it's
inferred from row presence in this pre-filtered export; `permits.series_earliest` comes
from `ISSUEDATE`).

**This crosswalk (field_key → raw key) is not `field_map.yaml`.** P26 explicitly deferred
designing that pack file's format, for good reason (no real caller yet). This package does
not build it either — `scripts/check_liveness.py` declares its own small, explicit,
commented `LIVENESS_FIELD_CHECKS` table, cross-referenced against the exact line in each
ingest script where that raw key is actually read (`ingest_parcels.py`'s
`props.get("APN")`/`props.get("PARCELID")`, `ingest_zoning_permits.py`'s
`props.get("ZONING")`/`props.get("ZONINGABBREV")`/`row.get("ASSESSORS_PARCEL_NUMBER")`/
`row["ISSUEDATE"]"`) rather than reused from a live export — `ingest_parcels.py`'s own
`PROPERTY_TO_FIELD_KEY` dict is declared but has exactly one entry and is never actually
read anywhere in that file (confirmed by grep — a real, separate, minor dead-code finding,
not fixed here, out of scope). Endpoint URLs come the same way: imported directly
(`ip.ENDPOINT_URL`, `izp.ENDPOINT_URL_ZONING`, `izp.ENDPOINT_URL_PERMITS`) rather than read
from the live `source.endpoint_url` column, deliberately avoiding a repeat of P26's own
found seeding-order bug (two independent seed functions racing to populate the same row) —
the ingest scripts' own constants are the single owner here, not a database row a second
process might seed differently.

**Scope, same precedent `make conformance` already set**: only sources whose `id` starts
with `ca_san_jose.` AND whose pack `phase_status` is `active` are probed (the pack's three
owned, active sources: parcels, zoning_districts, building_permits_active). The two active
federal sources (`us_fema.nfhl`, `us_nrcs.soil_survey`) get a `NOTE`, not a probe — no
ingest script exists for either yet, so there is no known-good raw-key crosswalk or
endpoint constant to check against; this is real, separate, unbuilt schema/pack design
(same conclusion P26 reached for the identical scoping question), not something this
package can silently paper over as covered.

**What this catches that a status-code check would miss**: a source whose endpoint still
returns 200 but has quietly dropped a column — the exact failure §6.4 exists to catch, and
the one a bare liveness-as-uptime check would sail past. Proven in §4.

---

### 4. Proof — two distinct real failures, both wired to fail red, both reverted

**Baseline, real network calls to the real San José endpoints, confirmed first** — a fresh
migrations-only scratch database, all three owned/active sources: `[PASS]` for all three,
exit 0, before either plant existed. This is the check's own real-input pass, not merely
its planted-input fail, per CONVENTIONS' "proving a check can fail on planted input does
not establish it passes on real input."

**Failure 1 — deliberately wrong endpoint.** Predicted: non-200 status, `error` set,
`schema_drift` NULL, other two sources unaffected. `ip.ENDPOINT_URL` for `parcels`
temporarily replaced with a syntactically-valid but nonexistent item id under the real
`gisdata-csj.opendata.arcgis.com` host. Confirmed exactly as predicted: `HTTP 400`
recorded, `zoning_districts`/`building_permits_active` both still `[PASS]`. Restored,
re-confirmed clean.

**Failure 2 — the one that matters: responds 200, missing a declared field.** Predicted:
`parcels` fails specifically on the fabricated field, `schema_drift =
{"missing_fields": ["parcel.NONEXISTENT_FIELD_P28_RED_PROOF"]}`, other two sources
unaffected. A field key checked against a raw property name provably absent from the real
response (`TOTALLY_MADE_UP_PROPERTY_NAME`) added to `LIVENESS_FIELD_CHECKS['ca_san_jose.
parcels']`. Confirmed exactly as predicted, against the real, live endpoint (not a local
stand-in) — verified via direct query afterward:
`SELECT job_key, source_id, status, error, schema_drift FROM job_run WHERE job_key=
'liveness' AND status='failed'` returned exactly one row, `schema_drift =
{"missing_fields": ["parcel.NONEXISTENT_FIELD_P28_RED_PROOF"]}`. Restored, re-confirmed
clean.

Both proven locally first (real network calls, no CI risk while iterating). Then on the
real runner, since `liveness.yml` is not push-triggered: baseline dispatch confirmed green
first (run [32180367376](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32180367376),
before any plant existed) — the same "real input passes" check CONVENTIONS asks for, done
on the runner, not only locally. `9e702cd` planted the same `parcel.NONEXISTENT_FIELD_P28_
RED_PROOF` break, pushed (no auto-trigger — `liveness.yml` is schedule/`workflow_dispatch`
only), then manually dispatched: run
[32180505074](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32180505074) —
`conclusion: failure`, the job's own log line matches the local proof exactly: `[FAIL]
ca_san_jose.parcels: responded 200 but missing declared field(s):
['parcel.NONEXISTENT_FIELD_P28_RED_PROOF']`, `zoning_districts`/`building_permits_active`
both still `[PASS]`. Reverted in the immediately following commit (`c321b2f`), dispatched
again: run [32180636098](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32180636098)
— `conclusion: success`.

---

### 5. Close-out

`Makefile`: new `liveness:` target, `.PHONY` updated. `CONVENTIONS.md`: "this repo has
two" corrected to three, "must be green before a package starts" scoped to the push/PR-
gated two. `docs/LEDGEX_SPEC.md`: §6.4's liveness line updated to state it is schedule-
triggered, not push-gated, and why; §1.2's table gains a seventh row ("Six make targets" →
"Seven"), naming the real scope and the named gaps (federal sources, non-active sources,
prefix-only field presence not full-content validation). `scripts/check_conformance.py`'s
own `NOT_YET_CHECKED` list updated too — "endpoint liveness ... a separate unbuilt target"
was itself now a stale claim the moment this package landed; conformance's own coverage
count dropped from four named gaps to three, confirmed by re-running it after the fix
(`CONFORMANCE SUMMARY: ... NOT covered: rights broadening ...; dependency cascades ...;
mappings ...` — three, not four). Spec bumped 1.40 → 1.41, real §12 row (verified rendered,
not just written to the `.txt` source — `make docs && make qa` confirmed "20 invariants
and 7 make targets verbatim in both artifacts" and a clean website regen).

No schema change — `make migrate-verify` (51 migrations, MATCH) and a clean `make
schema-dump`, both against `ledgex_schema_check`, confirm this before and after.

Full CI-order local simulation (fresh scratch database, every `schema`-job step in real
order including the new `make liveness`) green throughout: `make test` 167 tests, `make
golden` 2/4 fixture classes, `make conformance` now 3 named gaps. The two acceptance
suites (`p5-acceptance`, `phaseb-acceptance`) were not re-run locally — nothing in this
package touches `ingest_parcels.py`/`ingest_zoning_permits.py`'s own functions, only reads
their already-existing, unmodified constants — and both came back green on the real
runner regardless (below), so the local skip cost nothing.

**Real runner, all four jobs, main build (`21a0095`)**: `db.yml` run
[32180241295](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32180241295) —
`schema`/`p5-acceptance`/`phaseb-acceptance` all `success`, ~55s each (baseline, unaffected
by this package). `docs.yml` run
[32180241294](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32180241294) —
`success`. `liveness.yml`'s own three-run break-then-revert cycle is in §4 above.

Final commits: `21a0095` (main build), `9e702cd`/`c321b2f` (deliberate break/revert,
evidence not work). P28 row added to `prompts/README.md`.

### 6. Report: what's left after this, and is anything else honestly buildable

**Verified directly against `ledgex_schema_check`, not assumed from an older report**:
`commerce/` is still exactly `commerce/__init__.py` — an empty scaffold, unchanged since
day one. `licence_channel` still has every channel `allowed = false` for both real
licences (`cc0`, `cc_by_4_0`) — 12/12 rows, `false` — and `licence.cleared_by`/
`cleared_at` are both still NULL for both. `prompts/STANDING-BLOCKER.md`'s own claim
(*"That gate is a signature, not a commit"*) is not stale — it is exactly the live state
today, checked fresh for this report.

With `make liveness` real, every one of `docs/LEDGEX_SPEC.md` §1.2's seven make targets is
now backed by a genuine, scoped, honestly-named check — `make test`'s own six areas
(review, entitlement, outcome observation, provider slot, edge guard, billing
independence) are the only claim left in this codebase that CI names without a real
check behind it anywhere. All six are, as the package prompt already states plainly,
commerce/ and §13/§15 territory that does not exist — this report confirms that framing
rather than re-deriving it, since P24's own build-direction report already reached the
identical conclusion for the identical reason and nothing material has changed since.

**Plainly: nothing in this repo can honestly move next on any of those six.** Building any
one of them means writing `commerce/` schema and code against zero real rows, zero real
review evidence, and zero real entitlement state — which means either inventing the state
that would make it testable (the one thing this entire session has refused to do,
consistently, since finding #3) or building untestable scaffolding whose own tests would
have to assert against fabricated fixtures standing in for a clearance that has not
happened. Both are the same failure this session's own hard rules exist to prevent.

This is not a new blocker P28 discovered — it is the same one, confirmed still standing,
now that the two gates that WERE buildable without it (`make conformance`, `make
liveness`) are both done. The honest state of this project, as of this package: **every
make target that could be built without STANDING-BLOCKER.md's signature has been built.**
What remains is not a queue of small packages to pick off one at a time — it is one
package, `commerce/` plus §13/§15's outcome-observation and provider-slot schemas plus
`core/compose`'s real composed/partial paths, all gated on and worth planning together
only once that signature exists. Until then, the correct next action for a future session
opening this repo is to check whether `STANDING-BLOCKER.md` has changed, not to look for
another six-area gap to chip away at — there isn't one.
