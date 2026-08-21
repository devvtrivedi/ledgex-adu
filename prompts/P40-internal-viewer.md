## P40 — internal viewer over the LedgeX database

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Prompt as issued:
`PROMPT-P40-internal-viewer.txt` (repo root, unmodified). Baseline: `c52a266` + P39's own
uncommitted working tree (`infra/env.py`, `scripts/compose_property_file.py`,
`prompts/README.md` -- see `prompts/P39-compose-transaction-and-db-binding.md`; not
committed either, per that package's own report).

**Not committed.** Working tree only, per CONVENTIONS' "a delegated agent reports; it does
not commit or push to `main` on its own." New: `api/__init__.py`, `api/main.py`,
`api/static/viewer.html`, `scripts/seed_internal_test_licences.py`. Modified:
`.importlinter`, `requirements.txt`, `scripts/compose_property_file.py` (a small extraction,
not a behavior change -- §3).

**Read first, per CLAUDE.md:** `docs/LEDGEX_SPEC.md` §1 in full (all 20 invariants, §1.1),
§2, §4, §7.3, §11 -- all five read in full this session, not selectively.

---

### 0. Section 0 — the four decisions, and one blocker found while checking them

No code was written before this section was reasoned through, per the prompt's own
instruction. Two of the four were founder-ratified already and are not re-litigated: **scope**
is the ops viewer *plus* the real fact/file view; **F1's workaround** is new `internal_test.*`
licence ids, never a change to the real ones.

#### D1 — which channel does the viewer read on? → `api`

Taken as recommended. `api` is already a live member of `output_channel`, confirmed against
the running database, not assumed:

```
output_channel = free_snapshot, paid_property_file, api, bulk_export, analytics, model_training
```

§7.3 is unambiguous that this is the *only* lever that matters: "Channel eligibility for any
fact is determined solely by licences.yaml, seeded into licence + licence_channel and
enforced by the composer (I6). Nothing else grants a channel." Reading on `api` means the
viewer is gated by the exact same vocabulary as everything else, including P39's own
`KNOWN_CHANNELS` check.

**Rejected: a new `internal_ops` enum member.** That is a forward-only migration to a shared
vocabulary and a rights decision on its face ("we grant ourselves a channel") -- a spec bump
and a §12 row, not a judgement call inside a tooling package. Not attempted.

Direct consequence, stated plainly and shown for real in §2 below: every real `cc0` /
`cc_by_4_0` fact is `RIGHTS_BLOCKED` on `api`, because all 12 of their `licence_channel` rows
are `allowed=false`. That is the correct result, and the viewer shows it.

#### D2 — licence id namespace → `internal_test.`

`internal_test.cc0`, `internal_test.cc_by_4_0`. Visibly not a real licence id, greppable,
impossible to mistake for the real thing in a query result or a screenshot.

**Deliberately not `test.`** (the `db/tests/invariants.sql` namespace): `db/tests/
teardown.sql` keys its cleanup off `TEST-%`/`test.%`, and reusing it would imply these rows
are disposable fixtures. They are not -- `licence_no_delete` raises unconditionally, verified
directly against a real database this session (not merely cited from an earlier package):

```
ERROR:  B2/I3 violated: licence test.p40_probe cannot be deleted. Every fact and snapshot
that cites it depends on it for provenance; deleting it would invalidate their rights
history without touching them.
```

(That probe used the `test.` prefix on purpose, to make the point concrete against a
namespace `teardown.sql` is *supposed* to be allowed to touch -- and even there, the delete
still fails, because `licence_no_delete` has no namespace exception. `teardown.sql` itself
deletes from exactly seven tables -- `exception_evidence`, `job_run`, `parcel`,
`parcel_exception`, `property_file`, `property_file_fact`, `source_feature_identity` -- and
by design never touches `licence`, `source` or `jurisdiction`.) `internal_test.` says
"permanent, deliberate" instead of "fixture, disposable."

#### D3 — where does the rights gate live? → extracted within `scripts/`, not yet `core/rights.py`

The gate existed exactly once, inline, in `_compose()` (post-P39 numbering: lines 569-582).
A grep for `licence_channel` across every `.py` file confirmed no second reader existed
before this package: the only other hits were two test suites *inserting* fixture rows, and
comments.

The viewer puts fact values on a screen, which makes it an output channel under I6 (§1.1:
"a fact used to resolve jurisdiction participates in composition even if it is not
rendered" -- the same reasoning extends past the composer to any renderer). Copying the gate
would create two implementations that could silently disagree -- a viewer more permissive
than the composer renders something the composer would refuse, with no error attached
anywhere.

**§2's own layer X (`core/rights/`) is where this belongs eventually.** It is not where it
went this package, because of finding #45, immediately below. **Recommendation taken:**
extract the gate into a standalone function, `evaluate_rights_gate(cur, touched, channel)`,
inside `scripts/compose_property_file.py` itself -- same query, same two-pass shape, provably
identical behavior (§3) -- and have `api/main.py` import and call that ONE function
(`import compose_property_file as cpf; cpf.evaluate_rights_gate(...)`), the same
`sys.path.insert(0, "scripts")` pattern every `scripts/test_compose_*.py` file already uses.
`scripts/` is not a package any `.importlinter` contract governs (it is not even in §2's own
repository-layout diagram -- pre-architecture tooling, not a layer), so this sidesteps finding
#45 entirely rather than building on top of it. **This is reported as scope, done, not
absorbed silently:** it is a small, mechanical, RED-first-equivalence-proven refactor of a
working script five suites depend on, not a new domain module — see §3 for the proof.

#### D4 — what is the UI, mechanically? → FastAPI + one static HTML file

Taken as recommended. `fastapi`/`uvicorn` are §11-allowed ("API FastAPI + Pydantic v2 +
uvicorn") and were absent from the tree; `requirements.txt`'s own comment explained why
("adding a dependency before anything needs it...") -- P40 is the thing that needs them.
Added, with that comment updated to say so, not left to rot as a stale justification (`git
diff requirements.txt`).

One self-contained HTML file, inline CSS/JS, no npm, no build step, no framework -- 1-3
internal users, a toolchain is a liability. Not in `website/`: that directory is generated
from `docs/*.md` by `build/build_website.py`, and `qa_check.py`'s `check_website_current`
fails `docs.yml` the moment it stops matching what that builder produces -- confirmed by
reading that check, not assumed; `make check-boundary`'s own green run in §4 includes it.

**The `.importlinter` half, checked and acted on, not just checked:** before this package,
`api/` was referenced only as a `forbidden_modules` target (I1's "core must not import ...
api ..."); it was not a `root_packages` entry, so its own outbound imports were completely
invisible to `lint-imports` -- confirmed directly (`Analyzed 21 files, 19 dependencies` with
`api/main.py` already written and importing `infra.env`, identical to the count with no
`api/` present at all). `api` added to `root_packages`; the existing `core/commerce/infra`
layers contract extended to `api` (topmost layer, above `core | commerce`, above `infra`) --
`lint-imports` now analyzes 27 files/27 dependencies, all 5 contracts `KEPT`
(§4). RED-first proof that the new layer actually fires: planted `commerce` importing
`api.main` (a gap NO existing contract covered, before this edit) -- caught, named exactly,
reverted, confirmed green again (§4). **Deliberately not given `api/` its own
`commerce`-style "may only import core.compose" allowlist**: that shape is exactly finding
#45's stale-blacklist problem, one paragraph below -- adding a second instance of the same
broken pattern for `api/` would compound the finding this package found, not avoid it.

#### Finding #45 — the I15 contract's own stated precondition expired three packages ago, and the layers contract is stricter than §2

Found while checking D3, verified independently and for real in this session (not merely
inherited from an earlier draft). **Blocks a clean `core/rights.py` extraction; does not
block anything else in this package.**

`.importlinter`'s `i15-commerce-no-core-store` contract carries its own precondition, in its
own comment: *"Forbidding core.store alone is a faithful proxy for that allowlist ONLY
because core/ has nothing else under it yet... The day core/ grows a submodule besides
model/compose/store, this needs revisiting."* That day was P21 (`core/exceptions.py`), P25
(`core/calc.py`), P31 (`core/rules.py`) -- three packages ago. `core/` today holds
`model.py`, `store.py`, `exceptions.py`, `calc.py`, `rules.py`, and the contract still only
names `core.store`.

**Half (a), reproduced this session:** planted `commerce` importing `core.rules` (a real §2
violation -- the allowlist is "core.model and core.compose only"):

```
I15: commerce may import core.model and core.compose only, never core.store   KEPT
```

The blacklist stayed green. It is blind to everything except the one module name it lists.

**Half (b), reproduced this session, the sharper one:** the same probe *did* go red, but via
the separate infra-layers contract, and its message contradicts §2. Then planted the
*opposite* case -- `commerce` importing `core.model`, which §2 explicitly permits:

```
core/commerce may import infra/; infra/ may never import upward (finding #29)   BROKEN
  commerce is not allowed to import core:
  - commerce -> core.model (l.7)
```

`make check-boundary` goes red the moment `commerce/` does the one thing the spec explicitly
allows. Both probes reverted; `lint-imports` confirmed back to 5 kept / 0 broken before
moving on.

**Why this blocks D3 and nothing else:** `core/rights.py` would be a fourth submodule the
stale blacklist doesn't cover, and a module `commerce/` has no business importing (rights
evaluation is not a commerce concern -- I15's whole point) -- extracting into `core/` now
would compound the exact gap this package found, not route around it. It does not block
building the viewer, the seed script, or adding `api/` to the import graph (D4) -- none of
that touches `commerce`'s relationship to `core/`.

**Recommended repair, not done here (report, not absorb):** move `i15-commerce-no-core-store`
to import-linter's `independence` contract type, or an explicit per-submodule allowlist, and
reconcile the layers contract with §2's actual permitted direction (`commerce → core.model` /
`core.compose`) in the same pass -- one small package, its own RED-first proof per submodule,
before `core/rights.py` is ever attempted.

---

### 1. Step A — the internal-test licence seed

`scripts/seed_internal_test_licences.py`. Gated by `SEED_INTERNAL_TEST_LICENCES=1`, modelled
directly on `GOLDEN_ALLOW_RULE_SEED`'s shape and tone. Seeds, under the `internal_test.`
namespace only: one jurisdiction, two licences (`internal_test.cc0`,
`internal_test.cc_by_4_0`) each with an `api`-channel `allowed=true` `licence_channel` row,
two sources, two snapshots, two `field_definition` rows, one parcel, two facts (one per
licence). Every INSERT is `ON CONFLICT DO NOTHING` or an equivalent `WHERE NOT EXISTS` guard
(see below) -- idempotent by construction, and it reports what it skipped, never claims a
write that didn't happen.

**A real bug found and fixed while testing this script, not left in:** `parcel` has no
unique constraint on `(jurisdiction_id, apn)` -- 0034 dropped it deliberately (real APN
collisions). A first draft used `ON CONFLICT DO NOTHING` on the parcel insert; since there is
no unique index for that clause to target, it never actually conflicted, and a second run
inserted a *second* parcel row under the same apn -- confirmed by running it twice and
querying `count(*)`, not caught by reading the code. Fixed with a `WHERE NOT EXISTS` guard
(the same shape the fact insert already needed for the same underlying reason) plus an
`ORDER BY id` on the lookup that follows it -- never a bare `fetchone()` on an unordered
result, the exact "arbitrary pick" shape this codebase has already found and fixed twice
(`resolve_parcel_id_by_apn`'s own precedent). The orphaned duplicate row this bug produced
was deleted from the one throwaway evidence database it landed in before re-testing; no
production or shared database was ever touched by it.

**Predicted, then run, all three shown exactly as predicted:**

```
$ python3 scripts/seed_internal_test_licences.py            # no opt-in -- predicted: exit 1, refuses, names the db
refusing to seed internal_test.* licence rows into 'ledgex_p40_seedtest': this INSERTs
licence and licence_channel rows that CANNOT ever be removed or edited again ... Refusing by
default so this cannot be run against a database by accident. ... re-run with
SEED_INTERNAL_TEST_LICENCES=1. This does not touch, and never implies clearance of, the real
cc0 / cc_by_4_0 licence rows -- LD-1 remains open regardless of this script.
exit code: 1

$ SEED_INTERNAL_TEST_LICENCES=1 python3 scripts/seed_internal_test_licences.py   # predicted: exit 0, every row "wrote"
  wrote   jurisdiction 'internal_test.viewer_demo'
  wrote   licence 'internal_test.cc0'
  wrote   licence_channel ('internal_test.cc0', 'api')
  wrote   licence 'internal_test.cc_by_4_0'
  wrote   licence_channel ('internal_test.cc_by_4_0', 'api')
  wrote   parcel apn='INTERNAL_TEST-VIEWER-DEMO-1'
  wrote   source 'internal_test.viewer_source_cc0'  ... (+ snapshot, field_definition, fact) ...
  wrote   source 'internal_test.viewer_source_cc_by_4_0' ... (+ snapshot, field_definition, fact) ...
exit code: 0

$ SEED_INTERNAL_TEST_LICENCES=1 python3 scripts/seed_internal_test_licences.py   # re-run -- predicted: exit 0, every row "skipped"
  skipped (already exists)   jurisdiction 'internal_test.viewer_demo'
  skipped (already exists)   licence 'internal_test.cc0'
  ... (all 12 rows) ...
exit code: 0
```

Run a third time after that, identical output, stable. Not wired into any `make` target, CI
workflow or test suite -- confirmed by grep, no reference anywhere outside this file and this
report.

---

### 2. Boundary 2, proven, not asserted — the real licence rows never move

Captured `licence`/`licence_channel` state for `cc0`/`cc_by_4_0` on a real, previously-seeded
database (`ledgex_p39v_run2`) *before* running the seed script, ran the seed script for real
against that same database, captured the identical query again, and diffed:

```
$ diff p40_licence_before.txt p40_licence_after.txt
$ echo $?
0
```

Byte-identical: both rows' `display_name`/`restriction`/`commercial_use`/`redistribution`/
`cleared_by`/`cleared_at`, and all 12 `licence_channel` rows'
`channel`/`allowed`/`rationale` verbatim, unchanged. `cleared_by`/`cleared_at` are still
`NULL` on both real licences, on both sides of the diff -- LD-1 untouched by anything in this
package.

---

### 3. `evaluate_rights_gate` extraction — equivalence proven, not assumed

Extracted verbatim (no logic change) from `_compose()`'s inline block into its own function,
called from the one place it used to run inline. Proven equivalent by running the identical
suite twice, on two independent fresh databases, once with the pre-extraction shape and once
with the post-extraction shape (a temporary revert/restore, not a git branch, since this is a
same-session mechanical refactor, not two different code states worth keeping around):

```
BEFORE (ledgex_p40_refactor_before, fresh)     AFTER (ledgex_p40_refactor_after, fresh)
  PASS  make schema                              PASS  make schema
  PASS  make migrate-verify (MATCH, 55)          PASS  make migrate-verify (MATCH, 55)
  PASS  db/seeds/day4_sources.sql                PASS  db/seeds/day4_sources.sql
  PASS  make golden                              PASS  make golden
  PASS  test_compose_geometry_tier_used          PASS  test_compose_geometry_tier_used
  PASS  test_compose_election                    PASS  test_compose_election
  PASS  test_compose_parcel_refusals              PASS  test_compose_parcel_refusals
```

Full stdout from both runs diffed with UUIDs/timestamps/random test-suffixes normalized:
every remaining line is a per-run random fixture suffix or timestamp (each test suite
generates a fresh `uuid.uuid4().hex[:8]` per run, by design, for isolation); every refusal
code, every gate outcome, every structural line is identical. The extraction changed nothing
observable.

`make check-boundary` green with the new function present and with `api/` present (D4):

```
lint-imports: Analyzed 27 files, 27 dependencies. Contracts: 5 kept, 0 broken.
JURISDICTION-NAME GREP PASSED -- 6 file(s) under core/ scanned, no blocklisted token found.
DOCUMENT QA PASSED -- ...
exit: 0
```

RED-first proof that the widened `.importlinter` layers contract actually fires (D4): planted
`commerce` importing `api.main` (a real gap no prior contract covered) --

```
api above core/commerce above infra (finding #29, extended P40 D4)   BROKEN
  commerce is not allowed to import api:
  - commerce -> api.main (l.7)
```

-- reverted, confirmed `git diff --stat` empty on the probed file, confirmed green again.

---

### 4. Step B/C — the API and the viewer, and the one-screen proof

`api/main.py`: FastAPI, every route a `GET`, no `POST`/`PUT`/`PATCH`/`DELETE` anywhere in the
module. Routes: `/v1/rights` (licence × licence_channel, rationale verbatim), `/v1/sources`,
`/v1/job-runs` (filterable by status), `/v1/exceptions` (filterable by outcome/detector,
default `outcome=open`), `/v1/property-files` (refusals expanded + `property_file_fact`
links), `/v1/parcels/{id}/facts` (through the rights gate, `?as_of=` supported, fixed to the
`api` channel -- never a caller-supplied channel, which would recreate exactly the
"second gate that could silently disagree" D3 argues against), `/v1/schema` (ledger vs.
migrations on disk). `/` serves `api/static/viewer.html`. Zero of §4's 16 endpoints are
implemented or claimed to be -- see §6.

**Connection handling, decided and stated, not defaulted into:** each request opens its own
connection via `infra.env.get_db()` and closes it, after an explicit rollback if not already
`IDLE`, in a `finally` -- never pooled, never reused across requests. This is a deliberate
choice for 1-3 internal users hitting a handful of read routes, not an oversight: it
trivially satisfies "every request ends its own transaction" (there is no connection left
open for a later request to inherit anything from), and a real pool is exactly the kind of
complexity this codebase's own `requirements.txt` comment already argues against building
before it's forced by need. If P39's Fix 3 (non-local `DATABASE_URL` guard) is present in the
working tree it landed in, it applies here unmodified -- `get_db()` is not wrapped or
special-cased. **If Fix 3 has not landed in whatever tree this report is read against: running
this viewer from the repo root with no `DATABASE_URL` exported connects to whatever `.env`'s
`DATABASE_URL` names, which may be a live remote database (P39, finding #43) -- export
`DATABASE_URL` explicitly before running `uvicorn api.main:app` either way.**

I9 (a derived conclusion must never render in a retrieved fact's visual treatment): no
derived fact exists anywhere in this database (confirmed: `method='derived'` has zero rows
in every database this session touched), so this is unexercised against real data -- but the
distinction is built in now, free, rather than retrofitted at the first one: the facts route
tags `is_derived` (`method == 'derived'`, the same signal `fact_provenance_complete`'s own
CHECK already ties to that method value), and the viewer renders it with a visually distinct
border, an italic field name and its own `DERIVED` badge, layered on top of (never instead
of) the rights-visibility pill.

**The one-screen proof (evidence item 1):** ran the server for real
(`uvicorn api.main:app --host 127.0.0.1 --port 8420`) against `ledgex_p39v_run2` /
`ledgex_p39v_run1`, seeded via the real seed script, plus one additional evidence-only fact
(`internal_test.evidence_field`, licence `internal_test.cc_by_4_0`) inserted directly onto
the SAME real `ca_san_jose` parcel that already carries a real `cc_by_4_0` fact
(`parcel.apn`) -- so one parcel, one channel, carries both a real blocked fact and an
internal-test permitted fact simultaneously. Queried through a real Chrome session, not just
curl:

```
GET /v1/parcels/43576680-60bb-45d6-a78f-b6847f9b3967/facts
{
  "channel": "api",
  "facts": [ { "field_key": "internal_test.evidence_field", "value": "visible via api
              (internal_test.cc_by_4_0)", "licence_id": "internal_test.cc_by_4_0", ... } ],
  "omitted_for_rights": [ { "field_key": "parcel.apn", "licence_id": "cc_by_4_0",
              "reason": "Licence 'cc_by_4_0' forbids channel 'api' (§7.3, I6) ..." } ]
}
```

Screenshot of the rendered viewer, same parcel, same load: `parcel.apn` (licence
`cc_by_4_0`) shows a red **RIGHTS-BLOCKED** pill with no value; `internal_test.evidence_field`
(licence `internal_test.cc_by_4_0`) shows a green **VISIBLE** pill with its real value. Same
table, same request, same channel. This is the proof the seed did not become a bypass:
the gate the viewer calls is the exact function `_compose()` calls, and it treated the real
licence and the test licence exactly according to their own, unrelated `licence_channel`
rows.

(Screenshots and the Compositions/Rights-position screens captured this session are held in
the delegate session's own scratchpad, not committed to the repo -- available on request; the
JSON transcript above is the load-bearing evidence and is reproducible by any reader with
`DATABASE_URL` pointed at a seeded database.)

---

### 5. Full gate set, twice, each against its own fresh migrations-only database

Per this package's own evidence list (not `db.yml`'s -- `db/seeds/day4_sources.sql` and
`test_snapshot_race_invariant.py` are not part of P40's requested set):

```
=== ledgex_p40_gate1 (fresh) ===                  === ledgex_p40_gate2 (fresh) ===
  PASS  make schema                                 PASS  make schema
  PASS  make schema-dump                            PASS  make schema-dump
  PASS  make db-test                                PASS  make db-test
  PASS  make test                                   PASS  make test
  PASS  make golden (GOLDEN_ALLOW_RULE_SEED=1)       PASS  make golden (GOLDEN_ALLOW_RULE_SEED=1)
  PASS  make conformance                            PASS  make conformance
  PASS  make check-boundary                         PASS  make check-boundary
  PASS  test_compose_geometry_tier_used             PASS  test_compose_geometry_tier_used
  PASS  test_compose_election                       PASS  test_compose_election
  PASS  test_compose_parcel_refusals                PASS  test_compose_parcel_refusals
  PASS  test_compose_collision_invariant            PASS  test_compose_collision_invariant
  --> 11 passed, 0 failed                           --> 11 passed, 0 failed
```

`make migrate-verify`, run and stated before citing either database for anything above:

```
MATCH -- ledgex_p40_gate1's live schema is exactly what its ledger claims. 55 migration(s) verified.
MATCH -- ledgex_p40_gate2's live schema is exactly what its ledger claims. 55 migration(s) verified.
```

Both against the real `docker` `postgis/postgis:16-3.4` container already running on this
machine (Postgres 16.4, PostGIS 3.4.3 -- an exact match for §11's "PostgreSQL 16 + PostGIS
3.4"), the same image `db.yml` itself uses. `db.yml`/`docs.yml` were confirmed green on the
real GitHub Actions runner for baseline `c52a266` in this same session's earlier package
(P39; run `32314117415`/`32314117407`) -- not re-checked here since no commit has landed
since, and this package makes no CI-relevant change of its own (nothing here is wired into
any workflow).

---

### 6. Stated plainly, in this report's own words, per this package's own instruction

- **This viewer is internal-only and must not be exposed beyond localhost until entitlement
  (`commerce/`) exists.** There is no authentication, no session, no role system anywhere in
  `api/main.py` -- deliberately: a half-built auth layer would be worse than an honestly
  absent one. Bind to `127.0.0.1` only; do not put this behind a public port, a tunnel, or a
  reverse proxy, ever, until a real entitlement system exists to gate it.
- **The `internal_test.*` licences are a testing workaround and assert nothing about `cc0`'s
  or `cc_by_4_0`'s real rights position.** Running `scripts/seed_internal_test_licences.py`
  does not constitute, and must never be read as implying, counsel's clearance of either real
  licence. §2 above proves this by direct query, not by policy statement alone.
  `internal_test.cc0` and `internal_test.cc_by_4_0` are separate, permanent, clearly-namespaced
  rows that exist solely so the viewer has real, gate-permitted data to render.
- **LD-1 remains open, and every real fact remains rights-blocked.** `cc0`/`cc_by_4_0`:
  `cleared_by` NULL, `cleared_at` NULL, all 12 `licence_channel` rows `allowed=false`,
  confirmed live in §2. Nothing in this package changes that state or moves LD-1 forward.
- **Which §4 endpoints remain unbuilt: all 16.** `GET /v1/access/plans`, `POST
  /v1/disclosures/{id}/accept`, `POST /v1/subscriptions/checkout`, `POST
  /v1/commerce/provider-events`, `GET /v1/subscriptions/current`, `GET /v1/jurisdictions`,
  `GET /v1/jurisdictions/{id}/sources`, `GET /v1/snapshots/{id}`, `POST
  /v1/admin/ingest/{source_id}`, `GET /v1/admin/job-runs`, `GET /v1/metrics/track-a`, `GET
  /v1/metrics/track-b`, `POST /v1/resolve`, `POST /v1/property-files`, `PATCH
  /v1/exceptions/{id}`, `POST /v1/support-requests`. This package's own routes
  (`/v1/rights`, `/v1/sources`, `/v1/job-runs`, `/v1/exceptions`, `/v1/property-files`,
  `/v1/parcels/{id}/facts`, `/v1/schema`) are new, internal, read-only routes that happen to
  overlap in *name* with a few of the above (`sources`, `job-runs`, `property-files`) --
  none of them implement §4's actual contract (request/response shapes, `Idempotency-Key`,
  `problem+json` errors, `attribution[]`/`omitted_for_rights[]` on every fact response,
  etc.), and none should be mistaken for progress against §4's own launch checklist.

---

### 7. On F1 (deferred, acknowledged, not touched)

The prompt's own closing section names a real, separate problem: once LD-1 clears for real,
`fact.licence_id` is immutable (0007's whole-row `IS DISTINCT FROM` list) and facts can't be
deleted (0017), so every fact already in the ledger stays permanently bound to a licence id
whose every channel is permanently `false` -- clearance would need a brand-new licence id
(licence rows can't be updated either) plus a full re-ingest writing superseding facts against
it. This package does not touch that problem. It is recorded here only to confirm it was read
and understood, not silently absorbed or forgotten: the `internal_test.` namespace exists
specifically so this viewer could be built and exercised without pretending F1 is solved.

---

### Review findings

**P41 Fix 4 — the `api/ → scripts/` dependency is real and is currently invisible to
`.importlinter`.** `api/main.py` does `sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))`
then `import compose_property_file as cpf` to reach `evaluate_rights_gate` (D3, §0/§3 above).
That is a real, load-bearing cross-package dependency this package created, and §0's own D4
claim that the extended `.importlinter` layers contract now makes `api/` "a real, analyzed
layer" is true of `api/`'s dependencies on `core`/`commerce`/`infra` and NOT true of this one:
`scripts/` is not in `root_packages`, so `lint-imports` has no opinion on this edge at all —
it would not fire if `api/` imported anything else out of `scripts/`, or if a future edit
made that import reach into something it shouldn't. It disappears entirely the moment finding
#45 is repaired and `evaluate_rights_gate` moves to `core/rights.py` (§0, D3) — this is a
transitional gap, not a permanent one, but it is real until that repair lands.

**Considered, not done: adding `scripts/` to `root_packages`.** For: it is a real dependency,
and this package's own principle (D4) was "everything else real is tracked." Against, and the
stronger argument: `scripts/` is not a package (no `__init__.py` — every file in it,
including `compose_property_file.py` and all four `scripts/test_compose_*.py` suites, is
imported via `sys.path` manipulation, not real package syntax), and import-linter's actual
handling of a directory like that as a `root_packages` entry (implicit PEP 420 namespace
package vs. something grimp simply can't resolve) is untested here, not merely assumed to be
fine — finding out requires an experiment, and if it works, `scripts/`'s four *other* files
(three ingest scripts plus this one) all become subject to whatever contract governs it,
which may or may not be desired for working, already-shipped scripts nobody asked to
restructure. That combination — an untested mechanism plus a blast radius wider than the one
import this package actually cares about — is scope beyond what this report is for. Not
absorbed either way: recorded here so the gap is tracked, not rediscovered.

**P42 — this package's own headline proof did not ship, and the reproducibility sentence
above overstated it.** §4's mixed-parcel screenshot/JSON transcript was real, but it was
produced by hand-inserting an extra fact onto a *different* real `ca_san_jose` parcel (§4
does disclose this — "plus one additional evidence-only fact ... inserted directly" — so the
claim itself was never false), not by `scripts/seed_internal_test_licences.py` alone. Verified
directly: on a fresh migrations-only database, `db/seeds/day4_sources.sql` applied, then the
seed run with its opt-in set, the seed's OWN parcel returned `"omitted_for_rights": []` — the
proof's own precondition, absent. **The closing sentence above — "reproducible by any reader
with `DATABASE_URL` pointed at a seeded database" — was not true before P42 landed; it is now.**
`scripts/seed_internal_test_licences.py` was extended (P42) to also plant exactly one fact
citing the REAL, unchanged `cc_by_4_0` licence onto the SAME demo parcel it already creates —
source id, snapshot id and field key are all `internal_test.*`; only `licence_id` is the real
`cc_by_4_0`, still `allowed=false` on every channel, still completely untouched (see P42's own
report, §2, for the byte-identical before/after diff). The corrected, now-true way to
reproduce §4's proof, exactly:

```
SEED_INTERNAL_TEST_LICENCES=1 python3 scripts/seed_internal_test_licences.py   # prints the parcel id
GET /v1/parcels/<that parcel id>/facts   # channel "api": N permitted under "facts",
                                          # 1 blocked (licence_id "cc_by_4_0") under
                                          # "omitted_for_rights"
```

or, non-interactively: `python3 scripts/test_viewer_rights_gate.py` (P42's own new script)
runs exactly this check, including the programmatic "the blocked value appears nowhere in the
serialized response" assertion, against whatever database `DATABASE_URL` names. Full argument,
evidence and the RED (empty `omitted_for_rights`) → GREEN transcripts in
[P42-seed-mixed-parcel-evidence.md](P42-seed-mixed-parcel-evidence.md).
