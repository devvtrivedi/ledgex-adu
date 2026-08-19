# prompts/ — the work queue

One package per file. **Read this index plus the one active package. Nothing else.**
Finished packages move to `done/` and are not read again unless something contradicts them.

| # | Package | Status | Landed as |
|---|---|---|---|
| P1 | [Refresh-failure hole](done/P1-refresh-failure.md) | done, pushed | `3bee5bd` |
| P2 | [Three correctness fixes](done/P2-correctness-fixes.md) | done, pushed | `40b953d`, `bd5db19`, `6cebdaf` |
| P3 | [Phase B — changed / new / disappeared](P3-phase-b.md) | done, reviewed, pushed | `62cf90f` |
| P4 | [Source-scoped reconciliation](P4-source-scoped-reconciliation.md) | done, pushed | `46a24c2`, `a62b4a7` |
| P5 | [Zoning + permits reconciliation](P5-zoning-permits-reconciliation.md) | done, reviewed, pushed | `4d0f7ea`, `8a7286e` |
| P6 | [Migration application has no ledger](P6-migration-ledger.md) | done, pushed | `8be8505`, `7b6aceb`, `47d826e`, `c5d681a`, `303e0db`, `4eac993`, `aea2d79`, `e02afe2`, `4c66d2d` |
| P7 | [`0044`'s derived-fact exemption is unbounded](P7-derived-fact-supersession-unbounded.md) | confirmed finding, not fixed | — |
| P8 | [Nothing resolves a `parcel_exception` when its condition changes](P8-exception-resolution-undefined.md) | design reported, folded into P9 | — |
| P9 | [Closing a `parcel_exception` when its condition clears](P9-exception-resolution.md) | done, pushed | `7c88d15` |
| P11 | [Two fabricated-fact bugs the acceptance suites cannot see](P11-permits-active-churn-and-apn-degradation.md) | steps 1/2/4/6 built, pushed; steps 3/5 reported, not built | `66d80a8`, `0317e02`, `7df58db`, `62fee5f` |
| P12 | [The P5 acceptance suite asserts a bug P9 already fixed, and nothing would have caught it](P12-p5-suite-blind-to-p9-and-ci-gap.md) | done, pushed | `0057bd3`, `3af23f6`, `98cbda4`, `c77ba5b` (`065f3e5`/`a9eafac`: deliberate CI-gate break + revert, evidence not work) |
| P13 | [The APN resolvability flip: findings #17 and #22, one package](P13-apn-resolvability-flip.md) | done, pushed | `105e2e7`, `c115888`, `4bda739` (`6c41103`/`c460792`: deliberate CI-gate break + revert, evidence not work) |
| P10 | [The NULL-inside-a-constraint class: findings #8 and #19, one package](P10-null-inside-a-constraint.md) | done, pushed | `576ce9e`, `686ce14` |
| P14 | [Finding #9: `db/tests/invariants.sql` commits fixtures and never cleans up](P14-invariants-sql-teardown.md) | done, pushed | `3817030` |
| P15 | [Bookkeeping, then finding #21: source-scope the three reconciliation reads](P15-source-scope-reconciliation-reads.md) | done, pushed | `721a138`, `90dc9df` |
| P16 | [Finding #18: exceptions stranded by a detector_version bump](P16-detector-version-retirement.md) | done, pushed | `c3fdc81` |
| P17 | [Invariant-suite hygiene: findings #26, #24 and #25](P17-invariant-suite-hygiene.md) | done, pushed | `843294a` |
| P18 | [job_run gets a real metrics column: findings #12 and #16's metrics half](P18-job-run-metrics.md) | done, pushed | `e42a45d`, `7005813` |
| P19 | [Finding #10: snapshot dedup is check-then-insert](P19-snapshot-dedup-race.md) | done, pushed | `f6b3cb0` |
| P20 | [WORM bucket hazard (finding #28), then a real golden gate for the refused path](P20-golden-refused-path.md) | done, pushed | `f8e23a7`, `7d4d3bf`, `390d603`, `7d12df8` |
| P21 | [Finding #15: core/model, I2's missing Pydantic half, and the first real domain module](P21-core-model.md) | done, pushed | `9135f79` (`cc84fe6`/`896ce71`: deliberate CI-gate break + revert, evidence not work) |
| P22 | [Finding #27 reopened, then core/model.Fact adopted at the loaders](P22-fact-adoption.md) | done, pushed | `00fd1e2`, `349ebb2`, `5c79dbf` (CI-only pydantic-install gap, caught on the real runner, not locally) |
| P23 | [Two contradictions in the authority layer: findings #29 and #30](P23-authority-contradictions.md) | done, pushed | `7975063` |
| P24 | [ParcelException adopted, then the build-direction report](P24-parcel-exception-and-build-direction.md) | done, pushed | `4651ea7` |
| P25 | [Geometry-disabled Base Core: the L7 refusal path and a fourth golden fixture](P25-geometry-disabled-base-core.md) | done, pushed | `8a1da6d` (`f936232`/`8869f8d`: deliberate CI-gate break + revert, evidence not work) |
| P26 | [The jurisdictions/ pack format, and one real ca_san_jose pack](P26-jurisdictions-pack-format.md) | done, pushed — close-out was never run; backfilled by P29. `make conformance`'s own real-runner break-then-revert never happened either; open as finding #33 | `3980560` |
| P27 | [Bound the CI jobs, then find what actually hung](P27-ci-timeouts-and-lock-wait.md) | done, pushed | `1da54bd`, `f06324a`, `689c022` (`6465b46`/`0c8145a`: deliberate CI-gate break + revert, evidence not work) |
| P28 | [make liveness: the last named gate that does not exist](P28-liveness.md) | done, pushed | `21a0095` (`9e702cd`/`c321b2f`: deliberate break + revert on `liveness.yml`, via `workflow_dispatch` since it is schedule-only, evidence not work) |
| P29 | [Close P26 properly, correct P28's close-out, then decide the fork](P29-close-p26-correct-p28-scope-fork.md) | done, pushed | `322b314`, `21dd7be`, `fbce774` |
| P30 | [Prove make conformance red on the real runner, then report (b)'s two open decisions](P30-conformance-red-and-fork-report.md) | done, pushed | `b5ea1a3`, `9a45566`, `6e8a5f9` (`9a45566` is NOT evidence-only despite containing the deliberate break — it also carries `prompts/P30-conformance-red-and-fork-report.md`, real work, a bundling mistake caught and hand-amended before push; `2936f25` reverts `9a45566`'s `sources.yaml` change only, cleanly, and is the genuine evidence-not-work commit — see CONVENTIONS.md's new rule, P31) |
| P31 | [The prevention P30 skipped, then L5: refuse-first, one real rule](P31-l5-refuse-first-one-real-rule.md) | done, pushed | `f5e2cf1`, `5c020bb`, `6dca93c`, `e795bbe`, `cfb70e6`, `7bad3b1` |
| P32 | [Close the dual-seeder before it drifts, then scope finding #35](P32-dual-seeder-and-rule-election-scope.md) | done, pushed | `1d94acd`, `b0f5e3b`, `53944ec` |
| P33 | [Correct #36's false premise, close #37, then design #35 concretely](P33-correct-36-close-37-design-35.md) | done, pushed | `2f51a60`, `3a32654`, `30ad99d` |
| P34 | [Build #35: the election parameter, refuse-first](P34-election-parameter-build.md) | done, pushed | `b783b22`, `307eb0d`, `fcee2ad`, `f72ad2a`, `1826300`, `b15b7b8` |
| P35 | [The DB-layer half P34 skipped](P35-election-invariants-and-fk-report.md) | done, pushed | `f992588`, `bd63601` |

**P6 — built.** `db/migrations/0046` adds `schema_migrations` (explicit `CONSTRAINT` names,
a `baselined` column). `scripts/migrate.py` applies only unrecorded migrations, each atomic
with its own ledger row. `scripts/migrate_baseline.py` is the one-time adoption path for a
pre-ledger database (full schema diff against a disposable from-empty reference — refuses on
any mismatch, never guesses) — already run for real against `ledgex_schema_check` itself,
MATCH, 46 rows recorded. `scripts/migrate_verify.py` independently checks a database's live
schema against what its own ledger claims — the one thing `migrate.py`'s own ledger-read
can't see by construction. `make schema` unchanged (CI's clean-apply contract, not made
idempotent — what was argued in the design is what got built). All three failure modes
(applied-unrecorded, recorded-unapplied, file changed after recording) proven RED then GREEN
with a real deliberate break each, not just reasoned. `make schema` loops every migration
with `ON_ERROR_STOP=1` and no `--single-transaction` — checked every migration for anything
that can't run inside a transaction block before finalizing this (one real case, `0031`'s
`ALTER TYPE ... ADD VALUE`, already split from the migration using the new values for
exactly this reason); confirmed directly, not just reasoned, by applying all 45
pre-existing migrations with `--single-transaction` per file against a fresh database.
`ledgex_schema_check` drifted **six** migrations behind by construction before this pass
(0039/41/42/43/44 found and fixed during P5's own investigation; 0040 found and fixed
separately, mid-package, when T64 in the full invariant suite surfaced a stale
`fact_no_destructive_update()` body that an earlier, existence-only check had missed — a
real methodology lesson: checking that a function EXISTS is not checking that it is the
CURRENT version). Full design in `P6-migration-ledger.md`.

**P7.** A derived fact (`source_id IS NULL`) can supersede an arbitrary fact from any source;
nothing ties `supersedes_fact_id` to `fact_input`. Confirmed by construction against a
correctly-installed trigger, not reasoned. `0044` deliberately untouched. Full writeup in
`P7-derived-fact-supersession-unbounded.md`.

**P8.** `0045` stops a detector writing the same open exception twice; it does nothing when
an exception's condition changes instead of repeating. Confirmed empirically during P5's
acceptance run, not hypothesized: a parcel that went `zero-match` → `ambiguous` across two
zoning snapshots now carries both exceptions open simultaneously (different `reason`, so
`0045`'s index doesn't block it) — the first one describes a state that is no longer true,
and nothing ever closes it. Applies to every exception-writing detector, not just zoning's.
Full writeup, including what "resolved" should mean and where the code would need to change,
in `P8-exception-resolution-undefined.md`.

**P9 — written, not built.** Implements P8, with three corrections to P8's own draft
recommendations settled before drafting: the new `exception_outcome` value is
`condition_cleared`, not `superseded` (a closed exception has no successor to point at,
unlike a fact); no documented `resolved_by` convention is needed (the outcome value alone
already distinguishes machine closure from human review, once `condition_cleared` exists;
`resolved_by` still gets `detector_key` because the existing 0015 biconditional requires it
non-null, not because of a new convention); and inline closure only ever reaches
`load_zoning` — `parcel_apn_unresolvable` has no full-recompute reconciliation pass to
close from (the resolvability-flip gap below), and `flag_invalid_geometry.py`'s two
detectors get only the `existing_open` dedup guard that stops their real, reproducible
`UniqueViolation` crash on rerun, not closure. `load_permits` writes no `parcel_exception`
rows at all, confirmed by grep — an earlier draft of this scope wrongly named it alongside
`load_zoning`, corrected before the package was written. One design question P8 didn't
reach, settled in P9: a condition that clears and later recurs currently produces an
unlinked new row (`0045`'s index only constrains `open` rows) — P9 adds
`parcel_exception.reopened_from_id`, one hop back, same shape as `fact.supersedes_fact_id`.
Full design and paste-ready prompt in `P9-exception-resolution.md`. Not started.

**P9 — built.** `db/migrations/0047` adds `condition_cleared` (following 0031's
ALTER-TYPE-ADD-VALUE precedent explicitly, in its own migration comment) and
`parcel_exception.reopened_from_id` in one migration (neither addition
references the new enum value in a DEFAULT/CHECK/DML, confirmed against
0031's reasoning before combining them, not assumed). `core/exceptions.py`
gains `close_resolved_exceptions()`/`relink_reopened_exceptions()` -- each one
set-based `UPDATE`, not a per-row loop -- wired into `load_zoning` only, per
the package's own scope table. One open question P9 left unsettled, decided
before the migration was written: the close helper matches on EXACT
`(detector_key, detector_version)`, same shape `existing_open` already used --
not cross-version. Checked directly, not assumed, before deciding:
`ledgex_schema_check` carries 10,150 real open
`zoning_spatial_join_unresolvable` rows at `detector_version='1.0'` with zero
overlap against `2.0` (v2.0 has never actually run against this dataset) --
cross-version closing would assert `condition_cleared` for a condition the
current run's classifier never evaluated under the OLD rule, fabricating a
claim; exact-version match doesn't touch those 10,150 rows at all, the same
gap `0045`'s own header already named and deferred, not a new one (see finding
#18 below). Found while building, not in the original plan: `0045`'s unique
index never fires for `flag_zoning_source_geometry`
(`scripts/flag_invalid_geometry.py`) -- its `detail` never sets a `reason`
key, so `detail->>'reason'` is SQL `NULL` for every row and Postgres unique
indexes never treat `NULL = NULL`; confirmed directly, a second real run
silently doubled 157 rows to 314 instead of raising `UniqueViolation` the way
`flag_parcel_geometry`'s does. Both detectors' dedup guard is keyed on
`parcel_id` alone (not `(parcel_id, reason)`) for this reason -- correct for
both, since neither ever writes more than one open exception per parcel per
run, and it is the only key that actually works for the NULL-reason
detector. RED-first throughout: the `flag_invalid_geometry.py` crash
reproduced for real against `ledgex_schema_check`'s own prior output before
any fix; P8's own zero-match-then-ambiguous staleness (`23707070` in P5's own
fixtures) reconstructed against pre-P9 code first (both exceptions open
simultaneously, confirmed) and again against post-P9 code (the stale one
closes, `condition_cleared`, `resolved_by='zoning_spatial_join_unresolvable'`;
the new one opens with `reopened_from_id IS NULL`); a third run of the same
parcel back to its original reason confirmed `reopened_from_id` links to the
row closed two runs earlier; a same-snapshot rerun closed exactly the
predicted 0. `db/tests/invariants.sql` gained T75-T78 (floor 91 -> 95),
RED against pre-0047 schema (the whole suite errors loudly, `ON_ERROR_STOP`,
at the first new test referencing the not-yet-existing column) then GREEN.
Every suite run twice, plus once each against a fresh migrations-only
database with no seed -- satisfied directly, since every local run in this
package used a fresh migrations-only scratch database, none seeded.
Full design and reasoning in `P9-exception-resolution.md`.

**P11 — steps 1/2/4/6 built and verified; steps 3/5 reported, not built; working tree,
not committed.** Started from `de61f53` — checked on the real GitHub Actions runs, not a
local re-run (`db.yml` run `31966379316`, `docs.yml` run `31966379242`, both `success`).

Step 1: `scripts/check_p5_acceptance.py` gained a `total_fact_rows()` assertion (counting
every fact row, live or superseded, for `23712112`/`permits.active` across the suite's
existing same-snapshot re-run) rather than an unchanged-live-id check — the id-unchanged
form would need state carried across the two separate CLI invocations that bracket the
re-run, which nothing in the harness provides; a row-count against the fixture-determined
expected total (2) needs no new plumbing. RED against real `de61f53` code, real suite,
real database (`got 3`) before any ingest code changed.

Step 2: `scripts/ingest_zoning_permits.py`'s `load_permits` normalizes the equality
comparison (not what gets written) for `retire_with_false_successor` fields only, so
continued absence compares equal to an already-`false` live value instead of `None`
literally. `permits.series_earliest` (not a `retire_with_false_successor` field) confirmed
untouched and idempotent, not assumed. Step 1's assertion GREEN afterward; full suite run
three times as required (twice seeded, once fresh migrations-only, no seed) — `facts
superseded: 0` on the redundant re-run each time, versus 1 before the fix.

Found while running the suite, not in the original plan: `run_p5_acceptance.sh` cannot
complete end-to-end on any database today, for a reason unrelated to this package — see
finding #20 below.

Step 3 (report-only, not built): both APN-degradation cases confirmed against a real
database, not by inspection — a placeholder degrade (`23712112`-shaped) lands the literal
placeholder string as a live `parcel.apn` fact value and cache column; a blank degrade
lands JSON `null` as the fact value (satisfies `jsonb NOT NULL`) and `NULL` in the cache
column. The INNER JOIN half confirmed separately: a feature unresolvable from its first
appearance (no `parcel.apn` fact ever) had its geometry moved in a later snapshot and
`changed_rows` reported zero changes — the live geometry fact still held the pre-move
centroid. Recommended fix: retire-no-successor + a `parcel_apn_unresolvable` exception
(cache column `NULL`), closed via the same `condition_cleared` mechanism P9 built for
zoning if the APN later resolves again — rejected the alternative of writing a sentinel
fact value as exactly the non-value-as-value violation `db/README.md` already forbids.
Argued this is one package with finding #17 (the reverse direction), not two: the
resolve-again half of the fix cannot see its own trigger condition without the INNER
JOIN also being fixed, so the two do not split cleanly. Not built — carries a design
decision on a shared reconciliation path, report-first per the package's own instruction.

Step 4: fixed at the source in all five scripts (`_p5_setup.py`, `_phaseb_setup.py`,
`test_refresh_failure_invariant.py`, `test_apn_canonicalization_invariant.py`,
`test_zoning_ambiguity_invariant.py`) — decided against a jurisdiction-free loader
parameter (the `test.*`-namespacing route `db/tests/invariants.sql` used, unavailable
here without that shared-primitive change, reported not absorbed) and instead corrected
the fabricated `observed_at`/`cleared_by`/`cleared_at` to match `db/seeds/day4_sources.sql`'s
own honest values exactly, so the real ingest loaders' hardcoded `LICENCE_ID*` constants
keep resolving unchanged. Verified against a fresh migrations-only database: the fix
inserts the honest, unfabricated row and the loader still runs end to end. Second half —
which databases carry the old contamination — checked directly: `ledgex_schema_check`
(the database CLAUDE.md names) and every locally reachable scratch database queried clean
(`cleared_by`/`cleared_at` both `NULL` everywhere checked). One database could not be
checked — the Supabase instance named in `.env`'s `DATABASE_URL` — no network reachability
from this environment; marked unverified, not clean, own row (#23 below) rather than left
only in narrative. No rebuild performed; nothing found warranted one, and the one
unverified database was not touched.

Step 5 (report-only, not built): confirmed "one source per field" directly against
`ledgex_schema_check`'s full real dataset (1.1M facts) for all four fields the three
un-scoped queries touch — exactly one distinct `source_id` each. Proved `AND source_id =
%s` is a behavior-preserving no-op on current data by direct count comparison
(`permits.active`+`permits.series_earliest`: 6,984 both ways; `parcel.apn`+`parcel.geometry`
join: 225,010 both ways; zoning fields: 886 both ways). Recommended against applying it
under P11 anyway: P4 (already done, pushed) was the package scoped to close this class of
bug and did not cover these three specific read-side queries (it fixed the DISAPPEARED-
branch cross-source *write* cascade and added `0044`'s constraint, a different code path)
— this is a new, still-latent gap for a future package to pick up, not scope to fold into
an unrelated fabricated-fact-bugs pass. See finding #21 below.

Step 6: batched into the working tree in one pass — `SCRATCHPAD` in all three loaders is
now a portable `/tmp/ledgex_ingest_scratch` (both acceptance scripts' `grep`
confirmed still resolving it correctly, unmodified); `core/store.py`'s "14-tuple" →
"17-tuple" (`build/check_jurisdiction_names.py` re-run against the real tree afterward,
3 files, clean); `.importlinter`'s stale `check_boundary_grep.py` reference corrected to
`check_jurisdiction_names.py`; the corrupted "sufinvariant" comment and the unused
`have_prior_identities` in `scripts/ingest_parcels.py` fixed/removed; both `rsplit`-built
reference-database URLs in `scripts/migrate_baseline.py`/`migrate_verify.py` replaced with
the already-available `parsed_url()`, verified against a genuine pre-ledger database via
`make migrate-baseline` then `make migrate-verify` (both `MATCH`).

Landed in five commits, in order (RED-first test, then fix, then licence fix, then the
low-severity sweep, then this file): `66d80a8`, `0317e02`, `7df58db`, `62fee5f`, and this
reconciliation commit. Full design and reasoning in
[P11-permits-active-churn-and-apn-degradation.md](P11-permits-active-churn-and-apn-degradation.md).

**Both CI gates confirmed green simultaneously, on the real runner, at `4c66d2d`
(2026-08-15).** `db.yml` (`make schema`, `make migrate-verify`, `make db-test`, `make
schema-dump`) and `docs.yml` (`make qa`, then separately `make check-boundary`) both
passed in full on that commit — the first point in this session either was actually
checked on CI rather than assumed, and the first point both are known green at once.
`docs.yml` had been red since `bd5db19` (`core/store.py`'s docstring named `APN`,
blocklisted since `330a91b`, before this session) — closed by `e02afe2`. Worth being able
to point at directly rather than re-deriving: anything built on top of `4c66d2d` inherits
a verified-clean starting point for both gates; anything built on an earlier commit does
not, regardless of what any individual package's own local `make qa`/`make check-boundary`
run reported at the time.

**P5 — landed, pushed.** `db/migrations/0045` adds a partial unique index closing the
exception-duplication gap (RED-first, T73/T74 in `invariants.sql`, floor 90 → 92).
`scripts/ingest_zoning_permits.py`'s `load_zoning`/`load_permits` are real diff-based
reconciliation now, not blind insert — no same-snapshot short-circuit (zoning/permits
classification is a function of the snapshot AND the current parcel set, not the snapshot
alone; proven directly, not assumed, by an 11-parcel drift the first same-snapshot probe
didn't predict). Core safety property (`different=0`, `retired-no-successor=0` on a
same-snapshot re-run) proven in the acceptance suite itself, not just a prototype:
`scripts/run_p5_acceptance.sh` (A→B→A per source, plus a same-snapshot re-run at the end),
`scripts/check_p5_acceptance.py` (115 assertions), fixtures in `db/fixtures/p5/`. Run RED
against the pre-P5 code (real `UniqueViolation` crash, exactly P4's documented finding) and
GREEN against the current code, three times: twice against an independent
migrations+`db/seeds/day4_sources.sql` database, once against a fresh migrations-only one.
One assertion needed correcting mid-run, not the code: a parcel found genuinely ambiguous
under a live-data drift retained a stale, still-open exception from an earlier zero-match
classification that nothing auto-resolves — direct, empirical confirmation of the
stale-exception gap already flagged in P5's own investigation, not a new bug.

**Correction (P11, 2026-08-16): that "proven in the acceptance suite itself" claim was
false for `permits.active`.** The suite asserted the live value and a non-null
`supersedes_fact_id` — both stay true through unbounded same-snapshot churn, so a bug
that superseded a fact and wrote an identical successor every single run was invisible
to it. Real bug, not a suite gap alone: `load_permits`' `fresh_active = True if fresh is
not None else None` compared against a live jsonb value decoded to Python `False` (`None
== False` is `False`), so a parcel with no active permits and a live `permits.active =
false` fact was superseded and rewritten as `false` on every re-run, `supersession_reason
= 'world_change'`, forever. See [P11](P11-permits-active-churn-and-apn-degradation.md).

**Second correction (P12, 2026-08-17): "proven in the acceptance suite" was never the
same claim as "covered by CI," and nothing in this README said otherwise until now.**
`scripts/run_p5_acceptance.sh`/`check_p5_acceptance.py` were not referenced in `db.yml` or
`docs.yml` — confirmed by grep, zero matches — from the day P5 landed until `98cbda4`. P9
(`7c88d15`) changed `load_zoning`'s exception-closing behavior correctly and verified it
thoroughly on its own terms, but never ran this suite, because nothing prompted it to, and
broke two of its assertions in the process (finding #20, closed below). "Both CI gates
green" was true and honest at every commit in between — neither gate had ever covered this
suite, so its silence said nothing either way. That is the actual failure mode P12 exists
to name: a real, thorough, RED-first-verified fix can still silently break a *different*
real, thorough, RED-first-verified suite, if nothing structural connects the two. The suite
is a third CI gate now (`98cbda4`, pinned `c77ba5b`) specifically so this can't recur
unnoticed — see finding #20's closure for the RED/GREEN evidence, on the real runner, that
the gate actually catches this class of break.

**P5 gate — resolved.** Three items:

- Five local commits pushed (`37def22`, tracking `prompts/` itself).
- `§6` hole closed: SECTION_INDEX carries a `6` row again (build/ledgex_source.py
  `SECTION_INDEX` + `UNINDEXED_SUBSECTIONS`), verified against real `### 6.N` headings by
  `build_spec_index.py` rather than dropped from the index. Restoring §6's own top-level
  heading is still out of scope — the region immediately before §6.1 is pdftotext-mangled
  (task shapes reordered) — but a reader following the index now reaches §6.1 instead of
  finding nothing. SPEC_VERSION 1.28.
- `§6.3` restored (SPEC_VERSION 1.29): applied the same absence-at-origin test used to
  settle §8 — checked the earliest tracked spec text instead of assuming. §8's gap was
  empty in every version back to the initial commit; §6.3's gap was not — three orphaned
  checklist lines (a bullet style used nowhere else in the document) sat unclaimed exactly
  between §6.2 and §6.4, inside the same already-confirmed-mangled region. A "6.3
  Definition of done" heading was added directly above them — no new prose, only a
  heading on content already there. May be incomplete. §6.1's and §6.5's reading-order
  references to "§6.3 definition of done" now resolve.
- `§8`: never real. Confirmed against `text/LedgeX_Engineering_Reference_Spec_v1_7.txt`
  (the earliest version this repo's git history has — the initial commit), whose own
  "Section N —" markers already jump 5 → 7 → 9 with nothing between them. Every version
  since does the same. The "open finding" citing `§8` was always pointing at a section
  number with no corresponding section, not at content that went missing — most likely a
  stale reference to §3.3 (Canonical field vocabulary, which the same migration's own
  header names one line below its "§8" citation, and which is what actually defines
  `stale_after_days`/`required_for_file`, I7/I9). Two dangling `§8` cross-references remain
  unfixed, both out of scope for this pass: `db/migrations/0003_fields.sql`'s own header
  comment (a migration file — no changes under `db/` this pass) and the raw text's task-shape
  B step 1 (inside the same mangled region §6's heading sits in). Do not write §8 content to
  close this — there is nothing it was ever supposed to say.

**Current blocking state:** none. Everything through `4c66d2d` is pushed — both CI gates
green there, see above. Check before trusting a SHA named above in conversation anyway —
run `git log --oneline origin/main..HEAD` for the real, current list, per the standing
multiple-checkouts hazard.

**No longer current (P5 lifted it):** `load_zoning` and `load_permits` used to raise
`UniqueViolation` on `fact_one_current_per_source` against any changed snapshot (P4 step 4).
Both now reconcile via diff-against-`fact WHERE superseded_at IS NULL` (not `current_fact`,
which P1 made a best-effort, after-commit refresh — reading it could misclassify an
already-correct value as changed while it lags), same shape as parcels' own Phase B.

**P13 — done, pushed.** Closes findings #17 and #22 together, one package, per the design
argued across P11 §1(c) and P9's own scoping note for #17. Wired `scripts/
run_phaseb_acceptance.sh`/`check_phaseb_acceptance.py` into CI first (`105e2e7`) — same
gap P12 closed for the P5 suite, and this package changes exactly the path that suite
covers. **Run once, first, before any wiring or code change: green** (`exit 0`, `ALL
ASSERTIONS PASSED`) — worth keeping on record either way, and this time the standing
suite had *not* silently broken, unlike finding #20's P5 suite. Proved the new gate on
the real runner: `6c41103` (deliberate break) → `db.yml` run
[31985756226](https://github.com/devvtrivedi/ledgex-adu/actions/runs/31985756226),
`phaseb-acceptance: failure`; `c460792` (revert) → run
[31985836741](https://github.com/devvtrivedi/ledgex-adu/actions/runs/31985836741), green
again. Fixtures + assertions extended and shown RED against the real bug (`c115888`) —
`'99999003???'` and JSON `null` landing directly as live `fact.value`, a feature's
geometry silently unsuperseded — before the fix (`4bda739`) landed GREEN, three times,
confirmed on the real runner: run
[31986485026](https://github.com/devvtrivedi/ledgex-adu/actions/runs/31986485026), all
three `db.yml` jobs (`schema`, `p5-acceptance`, `phaseb-acceptance`) green. Full design,
evidence and the step-5 remediation report (0 affected rows on every reachable database)
in [P13-apn-resolvability-flip.md](P13-apn-resolvability-flip.md).

**P10 — done, pushed.** Reserved by finding #19 alone since P11's own header note
("Numbered P11, not P10: P10 is already reserved by README finding #19"); **widened here
from #19 alone to the whole class**, once #8 was recognized as the same defect —
`CONVENTIONS.md`'s "Shapes that keep recurring" section already named both as one shape
before this package started, and the fix technique for #19 (`COALESCE` over a
nullable-expression index key) and the fix technique for #8 (a `CASE`-guarded rewrite
plus DROP+ADD) share the same root cause closely enough that arguing and fixing them
separately would have re-derived the same "what does NULL do here" analysis twice.
Established both failures live against a real database first, not assumed from the
findings table's own text (#19 in particular: a fresh repro and a fresh number, not
finding #19's cited 157→314). Both fixed via new, explicitly-named migrations (`0048`,
`0049`) — `0038`/`0045` themselves untouched, forward-only. `db/tests/invariants.sql`
gained T79–T85 (floor 95→102), RED-first against a real pre-fix schema copy, GREEN after,
three times; fixing #19 surfaced and fixed a real latent test-fixture collision (`T5`/`T30`
silently sharing a detector key that the never-actually-enforcing old index had been
hiding). `db/schema.sql` regenerated, `docs/LEDGEX_SPEC.md` bumped to v1.33 with a real §12
row (0048/0049 referenced in §3.10/§3.12, `qa_check.py` confirmed still passing).
`CONVENTIONS.md`'s own "NULL inside a constraint" entry gained the actual requirement this
package exists to leave behind: any expression-keyed constraint must state, in its own
migration header, what it does when that expression evaluates NULL. Full design and
evidence in [P10-null-inside-a-constraint.md](P10-null-inside-a-constraint.md).

## Open findings (reconciled against `LedgeX_Handoff.md` §8, 2026-08-15)

The original handoff document (not kept in this repo; it predates `docs/`) had an §8
"Open findings" list that was never reviewed against real commits after P2 — every
package since just kept citing it as current. Reconciled entry-by-entry against the
actual tree at `bce39ae`/`4c66d2d`, reading the committed code rather than trusting
commit subjects. This table is now the live list; the handoff's §8 is superseded and
should not be re-read.

| # | Finding | Verdict | Evidence |
|---|---|---|---|
| 1 | Permit APN leading apostrophe (`'67620002`) silently dropped | **Closed** — `bd5db19` | `infra/values.canonicalize_identifier` strips it; used by `load_permits` (`scripts/ingest_zoning_permits.py:760`) |
| 2 | Null-zoning polygon (`FACILITYID=30392`) creates false ambiguities | **Closed** — `40b953d` | `classify_zoning_candidates` (v2.0) counts distinct non-blank `ZONING` values, not candidate rows — `scripts/ingest_zoning_permits.py:178-229` |
| 3 | `compose_property_file.py` selects by APN, 49 collisions | **Closed** — `6cebdaf` | `compose()` takes `parcel_id` only; `resolve_parcel_id_by_apn` refuses and names every candidate on a collision — `scripts/compose_property_file.py:112-168` |
| 4 | Loaders can't re-ingest a changed snapshot | **Closed** — `62cf90f` (P3), `8a7286e`/`4d0f7ea` (P5) | Confirmed for all three sources, not just two: `phase_e`'s Phase B reconciliation (`scripts/ingest_parcels.py:1022-1144`, new/changed/disappeared via TEMP staging + SQL diff) and `load_zoning`/`load_permits` (`scripts/ingest_zoning_permits.py:539-628`, `842-936`) all diff against live `fact` and supersede/insert for real — no same-snapshot short-circuit in the last two, on purpose (P5: classification is a function of snapshot × current parcel set) |
| 5 | CI counted a skipped test (S1) as PASS | **Closed** — `7b6aceb` | S1's skip branch moved out of `test_pass` into a separate `test_skipped` table, excluded from the pass floor — `db/tests/invariants.sql:318-337` |
| 6 | Refresh-failure hole: facts commit before `job_run` succeeds; a `current_fact` refresh failure permanently wedges `previous_successful_snapshot()` | **Closed** — `3bee5bd` | `job_run`'s terminal status now commits in the *same* transaction as the ledger rows, before refresh is attempted; refresh runs after, best-effort, and never re-marks `job_run` failed — `scripts/ingest_parcels.py` `finish_job_run_full`/`phase_e` |
| 7 | Migrations applied without `--single-transaction`, so a migration can partially commit | **Closed, no remaining path** | `make schema` loops `psql --single-transaction` per file (`Makefile:148-167`). `make migrate` (`scripts/migrate.py`) and `make migrate-baseline` (`scripts/migrate_baseline.py`, via the same imported `apply_one`) use psycopg2 `autocommit=False` with one `conn.commit()` per migration — equivalent per-file atomicity by a different mechanism. `migrate_verify.py` only ever applies migrations to a disposable reference DB, same `apply_one`. All four commands checked directly; none left uncovered. |
| 8 | `refusals[].code` accepts `[{}]`, `[{"code": null}]`, `["not-an-object"]` | **Closed** — `576ce9e` (P10) | Confirmed live against a real database first (all three shapes accepted, plus a fourth: `refusals` not an array at all crashed the INSERT outright instead of failing the CHECK). `db/migrations/0048_refusals_codes_valid_reject_null_shapes.sql` replaces `refusals_codes_valid()`'s body behind a DROP+ADD of the CHECK constraint (new name, `property_file_refusal_codes_known_shape_checked`, so existing rows actually get re-validated, not silently left under the old already-validated one) — an explicit `CASE` guards the non-array case (SQL-standard short-circuit, unlike `AND`/`OR`) so it now fails cleanly instead of crashing. §9 vocabulary preserved byte-for-byte; `qa_check.py`'s `check_refusal_codes_match_spec` confirmed still passing (it reads `0038`'s own file text, never edited). Queried every reachable database first — zero rows anywhere would have been rejected. RED-first (`db/tests/invariants.sql` T79-T83) then GREEN, three times, real runner. Full evidence in [P10-null-inside-a-constraint.md](P10-null-inside-a-constraint.md). |
| 9 | `db/tests/invariants.sql` commits fixtures and never cleans up | **Partially closed, by design** — P14 | Widened before fixing: not just the seed block (`BEGIN`:31/`COMMIT`:355) — psql's default autocommit means every individual test's fixture data commits permanently too, confirmed empirically (row counts exactly doubled across two runs before this package). Three fixture classes, not one: (1) idempotent seed reference rows, `ON CONFLICT DO NOTHING`, never accumulate — not actually part of this finding; (2) one fresh-uuid parcel per run plus every fact any test writes against it, **permanent by construction** (`fact_no_delete`/0017 + the FK, i.e. I4 working correctly) — teardown deliberately does not and cannot touch this class without weakening 0017/I4 itself; (3) `parcel_exception`/`property_file`/`property_file_fact`/`job_run`/`exception_evidence`/`source_feature_identity` — no trigger blocks any of them, confirmed by direct `DELETE`, simply never cleaned. Teardown now added for class 3 only, scoped to `test.*`/`TEST-*` fixtures, FK order worked out (children before parents, `reopened_from_id` NULLed first to break the self-referential chain regardless of depth) — proved on three consecutive runs: class 3 flat at zero after every run, class 2 still growing by exactly one run's worth each time (7 parcels/47 facts), confirming teardown reaches everything it should and nothing it shouldn't. Class 2's permanence is now an explicit, loud precondition at the top of the file itself, in the Makefile's `db-test` target, and in `db/README.md` — naming the exact mechanism (`make db-test`'s bare default pointing at `ledgex_schema_check`) that caused it. `ledgex_schema_check`'s existing contamination queried in full (40 parcel/324 fact, permanent; 40 parcel_exception/20 property_file/8 property_file_fact/8 job_run, removable) and reported, not remediated — proposed as its own future step. Full evidence in [P14-invariants-sql-teardown.md](P14-invariants-sql-teardown.md). |
| 10 | Snapshot dedup is check-then-insert, races under concurrent ingestion | **Closed** — P19 | `insert_snapshot()` in both scripts now `INSERT ... ON CONFLICT (id) DO NOTHING`, returning `(sid, inserted)` — `inserted` from the INSERT's own `cur.rowcount`, read before `commit()`. `snapshot_exists()` kept as an upload-skipping optimization only, both functions' docstrings state explicitly why it is not the authority; `run_one_fetch()` in both scripts now decides `job_run`'s terminal status (`succeeded`/`skipped_unchanged`) from `insert_snapshot()`'s own `inserted`, never from the earlier `SELECT` — under the race, the loser now correctly reports `skipped_unchanged` with no exception, instead of crashing the whole `job_run` on a bare PK violation. Upload idempotency checked, not assumed: the real MinIO bucket is Object-Locked (WORM, `COMPLIANCE` mode, ~100yr retention, confirmed live) — concurrent PUTs to the same content-addressed key never corrupt or error, each becomes its own byte-identical version, reads always return correct content regardless of which version is current. RED proved without threads — two sequenced psycopg2 connections, both `SELECT` seeing nothing, then both running the pre-fix bare-`INSERT` SQL directly: the second raised `psycopg2.errors.UniqueViolation` deterministically. GREEN: new `scripts/test_snapshot_race_invariant.py` (same two-connection, no-threads shape, against the real fixed `insert_snapshot()` in both scripts) — winner `inserted=True`, loser `inserted=False` with no exception, exactly one row. Wired into `db.yml`'s existing `schema` job (no fourth job — reuses that job's already-live, already-disposable `ledgex_ci` and its already-installed `psycopg2`), confirmed this is the ONLY thing in CI that exercises `insert_snapshot`/`snapshot_exists` at all (the acceptance suites bypass `phase_b`/fetch entirely, loading pre-fetched fixtures directly). New test file follows the honest, non-fabricated licence-seeding pattern P11 step 4 established, not the contamination shape it fixed. Two near-duplicate `insert_snapshot()` functions fixed separately, per script, not unified — extracting a shared primitive here would be scope creep, reported not absorbed (`core/store.py`/`core/exceptions.py` exist from a deliberate three-call-site extraction, not an opportunistic one). Full evidence in [P19-snapshot-dedup-race.md](P19-snapshot-dedup-race.md). |
| 11 | Loaders are not jurisdiction-scoped | **Still open** (still latent — one jurisdiction today) | `JURISDICTION_ID = "ca_san_jose"` is a hardcoded module-level constant in both `scripts/ingest_parcels.py:86` and `scripts/ingest_zoning_permits.py:123`, not a parameter — nothing filters or scopes by jurisdiction anywhere in either loader. |
| 12 | `job_run.schema_drift` stretched to carry the permit unmatched breakdown | **Closed** — P18 | Not just `load_permits` — queried every reachable database for every job_run row with a non-null `schema_drift` before writing anything: TWO real writers (`load_zoning` too, `{diff, exceptions_written, exceptions_skipped_already_open}`), both confirmed stretches of the declared meaning, and ZERO legitimate ones — `ingest_parcels.py`'s `phase_c` builds the one construction that DOES match 0012's "fields expected but missing," but never persists it (`phase_c` opens no `job_run` at all; its own dict is printed, then discarded by `__main__`). `db/migrations/0051_job_run_metrics.sql` adds `job_run.metrics` (nullable jsonb, `job_run_metrics_is_object` CHECK — must be a JSON object when present, no fixed global key set beyond that, argued explicitly against repeating `schema_drift`'s own mistake). `load_zoning`/`load_permits` rewritten to write `metrics`; `flag_invalid_geometry.py`'s two detectors and `ingest_parcels.py`'s `phase_e` (each already computing and printing a real breakdown with no durable record) now write `metrics` too — confirmed end-to-end against real fixture data via the `p5-acceptance` suite and a direct `flag_invalid_geometry.py` run, every writer's shape verified live in `job_run.metrics`. The 4 existing `schema_drift` rows left exactly as recorded, not migrated — argued both ways in 0051's own header. `db/tests/invariants.sql` gained T90-T91 (floor 106 → 108), RED against the pre-0051 schema, GREEN after, three times plus once fresh migrations-only. Full evidence in [P18-job-run-metrics.md](P18-job-run-metrics.md). |
| 13 | Detector reruns create duplicate open exceptions | **Partially closed** — `8a7286e`/`4d0f7ea` (P5), migration `0045` | The unique index `(parcel_id, detector_key, detector_version, detail->>'reason') WHERE outcome='open'` now exists for every detector, and `load_zoning`/`load_permits` pre-check `existing_open` before writing (`scripts/ingest_zoning_permits.py:635-680`) — a genuine no-op rerun for those two. `scripts/flag_invalid_geometry.py` (`4a931c7`, predates 0045) was never revisited: `flag_parcel_geometry`/`flag_zoning_source_geometry` build `exception_rows` unconditionally every run with no `existing_open` check (`scripts/flag_invalid_geometry.py:133-153`, `219-230`) — a rerun today hits 0045's unique index and raises `UniqueViolation`, crashing instead of no-op'ing. Found while reading detectors for P8 below, not part of the original list — real gap, not fixed here. **Not the same problem as P8** ([P8-exception-resolution-undefined.md](P8-exception-resolution-undefined.md)) either way: 0045 (where it applies) stops a *repeat* of an unchanged condition; nothing stops the condition itself from *changing* and leaving a stale exception open — that's P8, still unfixed. |
| 14 | Seeded `stale_after_days`/`required_for_file` "contradict §8 of the spec" | **No longer meaningful as stated** | §8 was already established (P5 gate, this README's own §5 note above) to have never existed in any tracked version of the spec — the citation was always a stale pointer, most likely meant for §3.3. `stale_after_days` isn't even set in the seed (`db/seeds/day4_sources.sql` never assigns it — always NULL); nothing there to check against a section with no content. If this needs re-litigating, it has to be re-posed against §3.3, not §8 — not done here, out of scope for a reconciliation pass. |
| 15 | `core/` a near-empty scaffold, so the jurisdiction-name blocklist grep scans almost nothing | **Closed** — P21 | `core/` now holds four real files: `store.py`, `exceptions.py`, and, as of this package, `model.py` (~450 lines, the first standalone domain module — `Fact`/`Parcel`/`Source`/`Licence`/`ParcelException`/`Refusal`/`Result[T]`) plus `tests/core/`. Run for real against this tree, not just the planted-break proof this row previously had no occasion to make: `build/check_jurisdiction_names.py` caught one live violation — a `Parcel` docstring literal, the word "San José" — before this package landed, fixed to a jurisdiction-neutral phrasing, then a clean re-run (`4 file(s) under core/ scanned, no blocklisted token found`). The blocklist grep is confirmed meaningful now, not asserted so. |
| 16 | Deferred deliberately (`parcel_lineage` split/merge, matching-key decision, `job_run` metrics column, `pipelines/` split) | **Metrics half done — P18; three items still deferred** | `job_run` metrics column landed (#12, closed, P18) — that item of this row is done. Still deferred, unchanged: `pipelines/` split's stated precondition ("Phase B is the thing that justifies it") is met (#4, closed) but the split itself hasn't been done — worth a conscious decision, not a rediscovery, next time it comes up. `parcel_lineage` split/merge and the matching-key question still await their trigger event (an observed split, an observed source change), neither of which has happened. |
| 17 | `parcel_apn_unresolvable`'s resolvability flip between snapshots is undetected — a feature whose APN goes from resolvable to unresolvable (or back) between two `ingest_parcels.py` runs isn't covered by that reconciliation pass at all | **Closed** — `4bda739` (P13), together with #22 | `scripts/ingest_parcels.py`'s `changed_rows` query joined `parcel.apn` INNER, so a parcel with no live fact could never enter it; the resolve-again direction was undetectable and its geometry changes were silently dropped (the other half of #22). `fa` is now a LEFT JOIN with a `CASE`-based changed-predicate (all four fact-present/absent × incoming-resolvable/unresolvable combinations worked out explicitly, verified 0 false positives on real 225K-parcel data via same-snapshot self-comparison). A resolve writes a NEW fact (nothing was live to supersede) and closes the open exception via a new, narrower `core/exceptions.close_exceptions_for_parcels()` — not `close_resolved_exceptions()`, which needs a full-recompute pass `phase_e` doesn't have, exactly as this row's own prior note anticipated. RED-first (real bug reproduced live: geometry silently unsuperseded, a resolve never detected) then GREEN, three times, on the real runner via the new `phaseb-acceptance` CI gate. Full evidence in [P13-apn-resolvability-flip.md](P13-apn-resolvability-flip.md). |
| 18 | A `detector_version` bump leaves every OLDER-version open exception permanently unclosable by P9's own closure mechanism | **Closed** — P16 | P9's exact `(detector_key, detector_version)` match kept, argued not abandoned — widening it would fabricate a `condition_cleared` claim the current rule never evaluated, the same failure class 0047 already refused elsewhere. Fixed instead with a new, honest disposition: `db/migrations/0050_exception_outcome_version_retired.sql` adds `exception_outcome` value `version_retired`, and `core/exceptions.retire_stranded_exceptions(cur, detector_key, retired_version)` — a THIRD closure function, not a modification of `close_resolved_exceptions()`/`close_exceptions_for_parcels()`/`relink_reopened_exceptions()`, all three of which stay exact-version-scoped, unchanged. `resolved_by='system:detector_version_retired'` (the retirement pass is the actor, not the original detector); `resolution_notes` names the retired version; `detail`/`exception_evidence`/`reopened_from_id` untouched — settled explicitly that a newer-version row must NOT link back to a stranded older one via `reopened_from_id` (a rule change is not a reopening), confirmed the existing code already gets this right by construction (both halves of `relink_reopened_exceptions()`'s query are bound to the same single `detector_version` parameter). `db/tests/invariants.sql` gained T86-T89 (floor 102 → 106): the new outcome value satisfies/violates the pre-existing 0015 biconditional exactly like every other outcome, the retirement UPDATE targets only the exact stranded version and leaves other versions untouched, a second run is a no-op — RED against the pre-0050 schema (`invalid input value for enum exception_outcome: "version_retired"`), GREEN after, three times plus once fresh migrations-only; class-2 rows kept growing linearly and class-3 stayed flat at 0 every run (P14's teardown unaffected). Run once for real against `ledgex_schema_check`, scoped to `(zoning_spatial_join_unresolvable, '1.0')`, after explicit confirmation: before-state re-derived independently (10,150 = 12 `multiple_containing_districts` + 10,138 `no_containing_district`, matching this row's own earlier-cited number without copying it), exactly 10,150 rows retired, every other `detector_key`/`detector_version`'s row count byte-identical before and after. Full evidence in [P16-detector-version-retirement.md](P16-detector-version-retirement.md). |
| 19 | `0045`'s partial unique index does not constrain what it appears to — it has never actually applied to `zoning_source_geometry_invalid` | **Closed** — `576ce9e` (P10) | Reproduced with a fresh number, not the cited 157→314: a minimal real repro (one deliberately self-intersecting zoning polygon classifying one real parcel via `ST_MakeValid` repair), P9's application guard bypassed, two real runs of `flag_zoning_source_geometry` against unchanged data — 1 row became 2, no `UniqueViolation`. Fixed via candidate (b) — `db/migrations/0049_parcel_exception_reason_coalesced.sql`, `COALESCE(detail->>'reason', '')` — argued against (a) (inventing a `reason` key going forward does nothing for rows already stored, and this detector has no natural sub-classification to justify one). `0006`'s `fact_one_current_per_source` COALESCE precedent checked, not assumed to transfer as-is: same technique, different justification (there NULL is a legitimate recurring domain state; here it's simply an absent key, uniform across 100% of this one detector's rows, confirmed to have zero effect on every other detector by reading every `exception_rows` call site). Existing databases queried first for duplicates — zero, everywhere reachable. RED-first (`db/tests/invariants.sql` T84-T85) then GREEN, three times, real runner; fixing this surfaced and fixed a real latent test-fixture collision (`T5`/`T30`) the never-enforcing old index had been hiding. Full evidence in [P10-null-inside-a-constraint.md](P10-null-inside-a-constraint.md). |
| 20 | `run_p5_acceptance.sh` cannot complete end-to-end on any database | **Closed** — `3af23f6`, `98cbda4`, `c77ba5b` (P12) | P9's own `condition_cleared` fix (`db/migrations/0047`, `core/exceptions.py`) intentionally changed `23707070`'s behavior; `check_p5_acceptance.py`'s `after-b`/`after-a2` assertions for that parcel still asserted the pre-P9 behavior. Confirmed against a live A1→B→A2 trace (not assumed) that P9 closes the correct, stale exception both directions, then rewrote both assertions to match (`3af23f6`). The suite now completes end-to-end for the first time: `scripts/run_p5_acceptance.sh` exits 0, `P5 ACCEPTANCE: ALL CHECKPOINTS PASSED`, three times as CONVENTIONS.md requires (twice seeded, once fresh migrations-only). Proved the new assertions have teeth locally, not just that the old ones stopped firing: deliberately skipped `close_resolved_exceptions` in `load_zoning`, confirmed the new assertion catches it (`got ('...', 'no_containing_district', 'open', None, None, ...)`), reverted, confirmed green. Then wired the suite into CI as a third gate (`98cbda4`, pinned `c77ba5b`) and proved *that* on the real runner too, not locally: pushed `065f3e5`, a deliberate reintroduction of P11's `permits.active` churn, to shared `main` — `db.yml` run [31984771169](https://github.com/devvtrivedi/ledgex-adu/actions/runs/31984771169) shows `p5-acceptance: failure` (`schema: success`, unaffected), with the exact predicted assertion failing (`got 3`). Reverted via `git revert` (`a9eafac`, content diffed byte-identical to the pre-break fix at `0317e02`'s `load_permits` block) — `db.yml` run [31984977677](https://github.com/devvtrivedi/ledgex-adu/actions/runs/31984977677) shows `p5-acceptance: success`. Minio pinned to `RELEASE.2025-09-07T16-13-09Z` afterward, confirmed still green: run [31985093236](https://github.com/devvtrivedi/ledgex-adu/actions/runs/31985093236). |
| 21 | Reconciliation reads in three call sites are not source-scoped (`ingest_zoning_permits.py:564-571`, `:884-891`; `ingest_parcels.py:1108-1120`) | **Closed** — P15 | `fact_one_current_per_source` (`0006`) is unique per source; none of these three queries filtered by `source_id`, so a second source holding a live fact for the same `(parcel, field)` made the comparison an arbitrary pick and could make a source skip a write it owed. Re-proved the no-op claim from scratch given P13's INNER→LEFT JOIN rewrite of `changed_rows` after P11's original proof — SQL-level (identical with/without-filter counts on real ~225K-parcel data) and real-script level (byte-identical `diff_counts`, identical downstream table counts across two parallel scratch databases). Proved it CAN fail, two different real shapes: `load_zoning`'s dict comprehension silently arbitrary-picks (a planted foreign-source fact won the key collision, the real source's own fact was never superseded); `ingest_parcels.py`'s LEFT JOIN doesn't silently pick, it duplicates — both the real and a planted foreign row satisfied "changed," and writing both crashed the job on `fact_one_current_per_source`'s own uniqueness constraint. Fixed via `AND source_id = %s` in the `ON` clause (not `WHERE`, which would silently revert the LEFT JOIN to an INNER JOIN). RED-first then GREEN, three times each, two new permanent CI-gated regression stages (`p5-acceptance`'s and `phaseb-acceptance`'s `after-source-scope` checkpoints) — no `db.yml` changes needed. P13's join-shape change did not alter the answer P11 originally recorded. Full evidence in [P15-source-scope-reconciliation-reads.md](P15-source-scope-reconciliation-reads.md). |
| 22 | `phase_e`'s CHANGED branch writes an APN degradation (resolvable → placeholder/blank) as a live `parcel.apn` fact instead of routing it through `is_unresolvable_apn` | **Closed** — `4bda739` (P13), together with #17 | Fixed as argued: a degrade now supersedes with no successor, raises a `parcel_apn_unresolvable` exception (reusing the existing `detector_key`/`detector_version`), and sets the `parcel.apn` cache column to `NULL` — reusing the existing supersede-before-insert write sequence, no second write path. RED-first against real fixtures extended for exactly this case (`db/fixtures/phaseb/`, four new synthetic features): `'99999003???'` and JSON `null` landing directly as live `fact.value`, reproduced on demand, not inferred — then GREEN, three times, real database. Also closed #23-style: queried every locally reachable database (`ledgex_schema_check` plus seven tier-2 scratch databases) for the actual damage pattern (a live `parcel.apn` fact containing `?` or JSON `null`) before landing the fix — **0 rows everywhere reachable**; remediation (supersede-with-no-successor, legal under `0007`/I4) proposed in [P13-apn-resolvability-flip.md](P13-apn-resolvability-flip.md) but not run, since nothing reachable needs it. The Supabase database (finding #23) remains the one unchecked exception. |
| 23 | The Supabase database named in `.env`'s `DATABASE_URL` could not be checked for the licence contamination finding #4/step-4 fixed at the source | **Unverified — genuinely unknown, not assumed clean** | No network reachability to `db.ckzvekwzyackwaimvazg.supabase.co` from the environment this pass ran in (`psql`: "could not translate host name"). If any of the five scripts fixed in this pass's licence-contamination commit was ever run against it before the fix landed, it now carries `cc0`/`cc_by_4_0` rows with `cleared_by='test'`, a fabricated `cleared_at`, and `observed_at` set to whatever moment that run happened — asserting counsel/owner clearance that `STANDING-BLOCKER.md` and `db/seeds/day4_sources.sql` both state does not exist. `0027` makes `licence` immutable, so if this is the case, no migration can correct it — rebuild (drop, re-migrate, reseed) is the only remedy, and this is explicitly the *least* rebuildable database in the project (not local scratch state). To settle it: from an environment with network access, `SELECT id, observed_at, cleared_by, cleared_at FROM licence WHERE id IN ('cc0','cc_by_4_0');` against that `DATABASE_URL` — `cleared_by`/`cleared_at` both `NULL` and `observed_at = '2026-07-31'` (matching `db/seeds/day4_sources.sql`) means clean; anything else means contaminated and rebuild-only. Not touched, per instruction — do not act on this row without that query run first, and without asking before any rebuild. |
| 24 | `ledgex_schema_check` carries removable class-3 and permanent class-2 fixture rows from repeated `db/tests/invariants.sql` runs | **Closed** — P17 | Re-queried, not cited from P14: before-state (ledger already at `0050`, P16's fix) — 24 fact-bearing (class-2) `test-%`-apn parcels, 324 facts (unchanged, permanent), 19 zero-fact `test-%`-apn parcel orphans (a new reclaimable class P17's namespace-scoped teardown reaches, that P14's `v_parcel_id`-scoped one structurally could not), and class-3: `parcel_exception` 40 (2 already `version_retired` — P16 incidentally touched a test-fixture row sharing the real zoning bump's `detector_key`/`version`; irrelevant to deletion), `property_file` 20, `property_file_fact` 8, `job_run` 8 — confirmed P16's 10,150 retired rows sit on real production parcels, never on `test-%`-apn ones, untouched by this. Ran `db/tests/teardown.sql` once, after explicit confirmation: exactly 40/20/8/8/19 reclaimed. After-state verified by direct query, not arithmetic: class-2 unchanged (24/324), class-3 all 0, real (non-`test-%`) parcel count independently queried (225,010 non-null-apn + 62 null-apn = matches the total exactly once class-3/orphan rows are subtracted — the first subtraction attempt was wrong by 62, caught by querying the third category instead of inferring it, per CONVENTIONS). Full evidence in [P17-invariant-suite-hygiene.md](P17-invariant-suite-hygiene.md). |
| 25 | The disposable-database enforcement question — `make db-test`'s bare default points at `ledgex_schema_check` | **Closed** — P18 | P17's recommended option (a) landed: `db-test` now reads its own `DB_TEST_DATABASE_URL` (default `postgresql://localhost/ledgex_test`), not `DATABASE_URL` — `schema`/`schema-dump`/`migrate`/`migrate-verify` confirmed unchanged, still exclusively `DATABASE_URL`, by grep of every `$(PSQL)`/`DATABASE_URL` reference in the `Makefile`. `ledgex_test` does not exist on a fresh clone, so the bare default now fails loud (`database "ledgex_test" does not exist`) instead of silently succeeding against `ledgex_schema_check` — confirmed directly, not assumed. `db.yml`'s own `db-test` step updated to pass `DB_TEST_DATABASE_URL="$DATABASE_URL"` instead of `DATABASE_URL=`, so CI keeps using its own already-fresh, already-disposable `ledgex_ci` explicitly rather than falling back to a `ledgex_test` that doesn't exist on the runner either — confirmed green on the real runner. (b) (opt-in flag) and (c) (disposability marker) not built, per P17's own recommendation — (c) remains the stronger, still-undecided fix for its own future package. |
| 26 | Teardown does not run when `ON_ERROR_STOP` aborts the suite — a failing run still accumulates class-3 rows | **Closed** — P17 | `db/tests/invariants.sql`'s inline teardown (placed after the pass-floor check, so ANY earlier failure aborted the whole psql invocation before ever reaching it) replaced with `db/tests/teardown.sql`, a standalone script `make db-test` now runs UNCONDITIONALLY — suite exit code captured, teardown run regardless, target exits with the suite's own captured code, never teardown's. Namespace-scoped (`apn ILIKE 'test-%'`, catching a real case inconsistency P14's `v_parcel_id` scoping never needed to notice — 6 of this file's 7 parcel-creating INSERTs use uppercase `TEST-`, one (T68) lowercase), which also means teardown can now see OTHER runs' rows, including a genuinely fact-free `test-%` parcel (traced to two real sources, T56 and T68) — explicitly filtered by `NOT EXISTS (SELECT 1 FROM fact ...)` before any parcel-level delete, never discovered by letting the FK reject a locked one, which would abort teardown itself under `ON_ERROR_STOP` and reintroduce the same masked-signal failure one level down. Proved RED for real: `T88`'s own assertion temporarily corrupted, `make db-test` run against a fresh scratch database — suite failed (`ERROR: FAIL T88...`, `make db-test` exit nonzero), teardown still ran and genuinely reclaimed real accumulated residue, confirmed by direct query (`parcel_exception`/`property_file` both 0 immediately after the failing run), not log text alone. `make`'s own process exit code is capped at 2 for any failing recipe (confirmed generic to GNU Make, not this design) rather than surfacing the suite's exact code (3) as `make`'s own exit status — the pass/fail signal every caller (including CI) actually keys on is preserved exactly; the specific code is preserved too, just as a printed value rather than `make`'s own process exit. GREEN three times plus once fresh migrations-only after restoring. Full evidence in [P17-invariant-suite-hygiene.md](P17-invariant-suite-hygiene.md). |
| 27 | `ledgex_schema_check`'s `schema_migrations` ledger keeps drifting behind its own migrations directory | **Reopened as a recurring condition — P22** | Three occurrences, not two, and all three found incidentally, never by anything looking for the condition itself: six migrations behind before P6 (`db/README.md`'s own decision-procedure section names this as the reason that procedure exists); two behind (missing `0048`/`0049`) at the start of P16, found while querying for finding #18, fixed via `make migrate` + `make migrate-verify` (`MATCH`, 49 migrations); one behind (missing `0051`) at the start of P21, found only because `make schema-dump` tried to *remove* `job_run.metrics` from the committed file — a regression that would have been silently accepted as "no diff to review" on a differently-shaped change. P16's fix applied the correction and no prevention — CLAUDE.md's own both-halves rule (a guarded migration alone / a seed fix alone are each half a fix) applies here too: correcting the drift a second time without addressing why it recurs is the same incomplete shape. **Argued as an evidence problem, not a tooling gap**, before writing: `make migrate-verify` already exists and already worked, both times it was run. What was missing both times is that nothing ran it *before* the database's state was trusted as evidence — every package in this repo's history that says "queried the real database" or "confirmed against ledgex_schema_check" is only as strong as that database's schema actually matching its own ledger, and a drifted database makes that claim silently weaker than it reads. A CI mechanism was considered and rejected: CI cannot see this at all, by construction — every run starts from an empty database and applies every migration fresh, so a shared *local* database's drift is invisible to the one place that could otherwise catch it automatically. Fixed at the evidence layer instead: `CONVENTIONS.md`'s evidence rules gained a new requirement, alongside the planted-input rule — run `make migrate-verify` before citing any local database as evidence, and state the result. Still recurring risk, not eliminated — a rule that has to be remembered is weaker than a mechanism that can't be skipped, and this finding stays open in spirit (the row is "reopened," not "closed") until or unless a future package finds a way to make this checked rather than remembered. |
| 28 | `ledgex-snapshots-locked` (the real, Object-Locked MinIO bucket P19 found) carries permanent fixture-derived objects from repeated local acceptance runs — `scripts/run_p5_acceptance.sh:25`/`run_phaseb_acceptance.sh:25` and `.env:11` all defaulted `OBJECT_STORE_BUCKET` there | **Closed** — P20 | Listed the real bucket directly, not estimated: 302 object *versions* across 20 distinct keys, ~2.16 GB total, `list_object_versions` (`list_objects_v2` alone undercounts — versioning is enabled, so it only shows each key's current version, 19 of 20 keys visible that way). Classified by exact byte-size match against `db/fixtures/p5/`/`db/fixtures/phaseb/`'s real file sizes: 8 keys match the CURRENT fixture files exactly (239 versions across them — `p5_permits_A/B.csv`, `p5_zoning_A/B.geojson`, `phaseb_permits.csv`, `phaseb_zoning.geojson`, `phaseb_A/B.geojson`); 7 more small keys (22496–23740 bytes, plus one 365-byte and one 0-byte key) match no *current* fixture size and are almost certainly earlier revisions of the same fixtures from before `phaseb_A.geojson`/`phaseb_B.geojson` were extended (40 more versions); P19's own idempotency-test key adds 5 versions at 34 bytes each (already disclosed there). The remaining ~2.15 GB (the overwhelming majority of total bytes) is 4 keys of real, production-scale content (one pair at ~210 MB, one at ~86 MB, one at ~5.7 MB) predating P13, not fixture-shaped — not attributed to the acceptance suites. Retention confirmed on a sample of both old and new keys: `Mode: COMPLIANCE`, `RetainUntilDate` ~100 years from each version's own upload time (e.g. a version uploaded 2026-08-17 retains until 2126-08-17) — unrecoverable by any principal, not attempted. Fixed at the source in the same commit: both acceptance runners now read their own `ACCEPTANCE_OBJECT_STORE_BUCKET` (default `ledgex-acceptance-scratch`, auto-created if missing, same idempotent shape `db.yml`'s own bucket-creation step already uses) and set `OBJECT_STORE_BUCKET` — the variable every function under test actually reads — FROM it, overriding whatever a sourced `.env` already exported; a same-named fallback (`${OBJECT_STORE_BUCKET:-safe-default}`) would not have worked, since `.env` unconditionally exports the real value before either script runs. Confirmed live: both suites run end-to-end with `.env` sourced and no override, writing into `ledgex-acceptance-scratch` only — the locked bucket's object count unchanged (still 19) after both runs. `.env`'s own default is unchanged, out of scope here (same as finding #25's `DATABASE_URL` default was for `schema`/`migrate`/etc.) — a developer invoking `insert_snapshot`/`upload_and_verify` some OTHER way still needs to know to override it themselves. |
| 29 | `docs/LEDGEX_SPEC.md` §2 contradicts itself on whether `core/` may import `infra/` — "core/* may import core/model and stdlib/third-party only" in one bullet, "Any of core/, commerce/, jurisdictions/, pipelines/, api/ may import infra/" two bullets later — and `.importlinter` enforces neither direction | **Closed — P23** | Decided, not averaged, and confirmed against git history rather than inferred: the first bullet's text is present verbatim at v1.7 (this repo's very first commit, before `infra/` existed at all); `infra/` itself was introduced at v1.21 (`6e7d6fe`), which added the diagram's `infra/` entry and the second bullet but never touched the older, by-then-stale first bullet. Both statements amended to agree — `core/* may import core/model, infra/, and stdlib/third-party only` — spec bumped 1.37 → 1.38, real §12 row. `infra/__init__.py`'s own docstring, which quoted the losing reading verbatim, fixed too. Enforced, not just documented: a new `.importlinter` "layers" contract (`core-commerce-layers-above-infra`, `core`/`commerce` as independent siblings above `infra/`) makes the resolved direction real in the one place a spec reading can't reach — RED-proven by planting `infra/env.py` importing `core.model` (both the new contract and the pre-existing `infra-is-a-leaf` one fired), and separately proven GREEN by planting `core/store.py` importing `infra.values` and confirming zero contracts objected (14 dependencies analyzed, up from 13) — both plants removed before landing. Retroactive effect on P22 recorded, not assumed either way: this resolution *would* have unblocked P22's Fact.value option (a) (native Python value, `insert_facts()` doing `json.dumps()` with `infra.values.decimal_default`) — not revisited, since option (b) (pre-encoded JSON text) stands on its own merits (stronger validation via a real `str` type plus a JSON-validity check, zero caller-side serialization changes) independent of whether the import was ever actually forbidden. |
| 30 | `scripts/run_p5_acceptance.sh` is not safe to rerun twice against the same already-populated database — `scripts/check_p5_acceptance.py:220-224`'s `check_permits_after_b` asserts parcel `23712112`'s `permits.active` fact is a brand-NEW fact (`supersedes_fact_id IS NULL`) after phase B, which is only true the first time the script's own A1/A2/B sequence runs against a given database; a second full run finds a live fact already there from the first run and correctly supersedes it instead, failing an assertion that encodes "first run" as an unstated precondition | **Closed — P23** | Scope established first, not assumed: `run_phaseb_acceptance.sh` tested directly (same-database rerun, fresh migrations-only DB) rather than presumed fine because P13 wired it into CI and nobody had complained — it has the identical property, and worse: not a soft assertion failure but an unhandled crash, `psycopg2.errors.UniqueViolation` on `parcel_exception_one_open_per_detector_reason_coalesced`, reproduced directly. Decided (b) over (a): making either suite genuinely rerunnable would mean rewriting its own A→B→A state-transition model to tolerate starting from state B, not a small fix, and not what these suites were ever designed to prove. Instead: both scripts' own headers now state loudly, as a precondition, that a fresh database is required per run (the same shape P14 used for `db/tests/invariants.sql`'s class-2 permanence note) — and `CONVENTIONS.md:54` corrected from "run every suite twice" to "twice, each against its own fresh database, never twice against the same one," scoped explicitly to suites that assert a one-time transition rather than a steady-state idempotent operation (`db/tests/invariants.sql`, `migrate`/`migrate-verify` are unaffected). Stated plainly, as a correction to the record, not only a rule change: the rule as literally written has been unsatisfiable for both suites since they existed, and every earlier package's own "ran it twice" for either suite already meant twice-on-independent-fresh-databases, never a literal same-database rerun (P12, P13, P19, P20, P22 all did this correctly in practice, just never named it as the only viable reading). |
| 31 | No job in `db.yml` or `docs.yml` had `timeout-minutes` set — GitHub's 360-minute default applied to all four | **Closed — P27** | Real, not hypothetical: the P26 build's `db.yml` `schema` job (run `32171649751`) was still `in_progress` after 5+ minutes against a historical baseline of ~1-2 minutes — the run had no bound and would have sat `in_progress` for up to six hours before anyone but a session actively polling it would notice. Cancelled by hand (`gh run cancel`); the local polling loop watching it had no bound either and was killed the same way. **The leading suspect (a lock wait in `scripts/test_snapshot_race_invariant.py`) was checked and disproven** — `insert_snapshot()` commits internally before returning, so there is no uncommitted row for a second connection to block on; reproduced locally, 1s, no hang. The real cause, read off the hung run's own per-step timestamps: `schema` and `phaseb-acceptance` both stalled 20+ minutes on the identical `Install postgresql-client-16` (`apt-get`) step while `p5-acceptance`'s identical step on the identical commit finished in 6 seconds — transient runner/mirror flakiness, not this repo's code; `test_snapshot_race_invariant.py` and `make conformance` never even started in the hung job (both `skipped`). Same class as this repo's own recurring silently-passing-gate findings (`docs.yml` red for a day through five packages unnoticed, #27's drifting ledger invisible to CI by construction, #10/#19's NULL-masked constraints) — the common shape is a gate that looks like it is still doing its job while actually reporting nothing. An unbounded job is the same failure at the infrastructure layer: it does not report a wrong answer, it reports no answer, for six hours, and nothing upstream distinguishes that from "still legitimately running." Fixed at both layers: `timeout-minutes` added to all four jobs (`schema: 20`, `p5-acceptance: 15`, `phaseb-acceptance: 15`, `qa: 15`), plus a tighter step-level `timeout-minutes: 5` on the three `Install postgresql-client-16` steps specifically — proven on the real runner via a deliberate `sleep 400` plant (step failed at 5m13s, not the job's 20-minute bound), and confirmed again for real, unplanted, when the identical apt-get stall recurred live during close-out and failed correctly at the same bound. Full evidence in [P27-ci-timeouts-and-lock-wait.md](P27-ci-timeouts-and-lock-wait.md). |
| 32 | `scripts/check_golden.py` and `scripts/check_conformance.py` independently seed overlapping `source` reference rows in `db.yml`'s shared, disposable CI database, and `make golden` runs first | **Closed — P26, recorded retroactively by P29** | Real, found while building `make conformance` (P26), not hypothetical: `check_golden.py`'s own `seed_reference_rows()` inserts a `ca_san_jose.parcels` row via `ON CONFLICT (id) DO NOTHING`, never setting `expected_fields` (defaults to `'[]'`). `db.yml`'s `schema` job runs `make golden` before `make conformance` — if golden's minimal row won the race, conformance's own seed (if it also used `DO NOTHING`) would silently no-op, leaving `expected_fields` empty, and the check conformance exists to run (`supplies:` matches live `expected_fields`) would fail for a reason that has nothing to do with the pack. Confirmed directly via a full CI-order local simulation (every `schema`-job step, in real order, against one fresh scratch database) before wiring anything into CI. Fixed at the source: `check_conformance.py`'s own `source` INSERT uses `ON CONFLICT (id) DO UPDATE SET expected_fields = EXCLUDED.expected_fields, ...` — order-independent by construction, safe against `ledgex_schema_check` too since the values match `db/seeds/day4_sources.sql` exactly, so a same-value UPDATE is a no-op in effect. Landed in `3980560`, never given its own findings-table row at the time — recorded here, retroactively, as part of P29's audit of P26's skipped close-out; not a new bug, the fix has been live since P26. Full evidence in `scripts/check_conformance.py`'s own `seed_reference_rows()` docstring and [P26-jurisdictions-pack-format.md](P26-jurisdictions-pack-format.md) section 3. |
| 33 | `make conformance` is wired into `db.yml` as a real CI gate but has never been demonstrated to fail — CONVENTIONS' own hard rule ("every check must be seen to fail at least once... on the real runner") is genuinely unsatisfied for it | **Closed — P30** | Found during P29's audit of P26's own skipped close-out: `git log` carried exactly one P26 commit (`3980560`) — the deliberate break-then-revert P26 section 4 originally described in the past tense never actually happened. Closed the standard way, on the real runner: `jurisdictions/ca_san_jose/sources.yaml`'s `zoning_districts` entry's `licence:` changed `cc_by_4_0` → `cc0` (both real, valid licences — a pure pack-vs-database disagreement, not a schema/import error any other gate in the same job would also catch; confirmed unaffected by finding #32's golden/conformance seeding race, since `check_golden.py`'s own seed touches only `ca_san_jose.parcels`, never `zoning_districts`). Predicted the exact assertion (`scripts/check_conformance.py:259-261`) and exact error text before pushing; verified locally first, then on the real runner, both matched exactly. Pushed (`9a45566`) — `db.yml` run [32196179966](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32196179966): `schema` job `failure`, specifically the `make conformance` step (`[FAIL] 'ca_san_jose.zoning_districts''s pack licence matches the live source row's own licence_id -- pack says 'cc0', database says 'cc_by_4_0'`), every earlier step in that job (`make schema` through `make test`) still `success`, `p5-acceptance`/`phaseb-acceptance` unaffected. Reverted (`2936f25`) — run [32196337985](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32196337985): `success`. Full prediction, evidence and the fork-scoping report this package also delivers in [P30-conformance-red-and-fork-report.md](P30-conformance-red-and-fork-report.md). |
| 34 | The one rule this repo seeds (P31, `ca_san_jose.adu_detached_max_height_city_standards.v1`) is sourced from a City guidance bulletin, not San José Municipal Code §20.80.175's own verbatim text — every real attempt to reach the ordinance text itself failed | **Open** | Real attempts, not a shortcut: `records.sanjoseca.gov/Ordinances/ORD30516.pdf` (302-redirects to a generic navid page, the document is gone); `library.municode.com/ca/san_jose/...` (both live and an Internet Archive snapshot — an Angular SPA shell, ~6-7KB, no ordinance text is present without client-side JS execution neither `curl` nor `WebFetch` performs); `www.sanjoseca.gov`'s own ADU pages (403 to automated fetches); a third-party PDF mirror (`aducalifornia.org`, also 403). The only fetchable Title 20 artifact found is a table of contents dated 1/29/2020, whose own ADU section numbers (20.30.460/470/480) are superseded by the City's own current Bulletin #210 (`UPDATED 03/05/2026`), which states ADUs are now governed by Chapter 20.80 Part 2.75 — City Development Standards at §20.80.175, State Development Standards at §20.80.176, historic-property standards at §20.80.175(E), JADU at §20.80.178. The seeded rule's own `citation` states plainly that it summarizes §20.80.175 via this bulletin, not the ordinance text — per finding #3's own standard, no citation was invented to paper over this gap. **Stays open until the ordinance text itself is read and this rule version is superseded** (`0013`'s one-way `effective_to`, a new version citing the Code directly) — not a defect to fix in code, a real external-access gap to close when the text becomes reachable. |
| 35 | Bulletin #210's own page 3: San José's City and State ADU Development Standards give materially different answers for the same conclusion (detached ADU max height: 25 ft under City standards, 18 ft under State) and an applicant must elect one — nothing in this schema records that election | **Closed — P34** | Found from a primary source (the bulletin itself, not a hypothetical): *"YOU HAVE A CHOICE: Design the ADU following either City Standards (Municipal Code 20.80.175) or State Standards (Municipal Code 20.80.176). The standards cannot be mixed; you must choose either all City standards or all State standards."* P32 chose the design (election as a request parameter, refusal as fallback); P33 reported it concretely; P34 built it. `db/migrations/0052_property_file_election.sql` adds `property_file.election` (nullable `text`, `CHECK (election IS NULL OR election IN ('city','state'))` — NULL means no conclusion in this file depended on an election, never "unknown," never a silent default to city). `db/migrations/0053_refusal_codes_election.sql` widens `refusals_codes_valid()` by two codes: `ELECTION_REQUIRED` (election omitted entirely) and `ELECTION_NOT_SUPPORTED` (election supplied but `scripts/compose_property_file.py`'s own `CONCLUSION_RULE_KEYS` — generalized from `{conclusion: rule_key}` to `{(conclusion, election): rule_key}` — has no entry for that pairing). Two codes, not one collapsed into `RULE_UNAVAILABLE`: that code asserts a `rule_key` WAS known and a real query against `rule` found no matching row — a temporal claim neither new code's own cause ever reaches. `compose()` gains an `election=None` parameter (request-scoped, never persisted to the fact ledger, I13 — confirmed against §7's own `user_assumption` vocabulary, not merely asserted) and validates it (`ValueError` on anything outside `("city","state")`) before ever reaching the database. Proven three ways distinct, not one path with three labels, on a real database (`scripts/test_compose_election.py`, wired into `db.yml`): `election=None` → `ELECTION_REQUIRED`, no `rule` query attempted; `election="state"` → `ELECTION_NOT_SUPPORTED`, no `rule` query attempted (no dict entry); `election="city"` against a synthetic jurisdiction with no seeded rule → a REAL query runs and correctly refuses `RULE_UNAVAILABLE`. `scripts/check_golden.py` gained a third fixture, `election_required` (RED-then-reblessed, diff shown: one new `"election": "city"` key on the two existing fixtures, the new fixture file), deliberately NOT a fifth member of SPEC.md sec 1.2's own four-class taxonomy — coverage reported as both counts, never folded into one. A second, State-standards rule was deliberately NOT seeded (HCD's own ADU Handbook is the real next source, not fetched or read here — its own later package, same pacing P31 used for the first rule). Spec bumped 1.41 → 1.42 (§3.12, §5, §6.6, §9, §12). Full evidence in [P34-election-parameter-build.md](P34-election-parameter-build.md). |
| 36 | The one real `rule` row had two independent `ON CONFLICT (id) DO NOTHING` seeders — `db/seeds/day4_sources.sql` and `scripts/check_golden.py` — finding #32's exact shape, reintroduced by P31 one package after #32 was fixed for `source` | **Closed — P32** | Byte-identical today, nothing enforced that; a citation/`pack_version` edit to one seeder alone would pass `make golden` silently (`ruleset_version` is only `rule_key@version`). Fixed at the source: `check_golden.py`'s `INSERT` now ends `ON CONFLICT (id) DO UPDATE SET` naming all fourteen non-key columns, same remedy P26 used for #32. Verified the trigger interaction before relying on it, not on faith: `0013`'s `rule_no_destructive_update()` does not fire on an identical-value `DO UPDATE` (both guards short-circuit on `IS NOT DISTINCT FROM`) — confirmed directly against the real row, `INSERT 0 1`, exit 0, no exception. Then proved the other half for real: one column deliberately drifted, immediate `ERROR: I18 violated: rule ... is immutable. Only effective_to may be set (NULL -> a date, once). A correction is a new rule row at version + 1, never an UPDATE.` **Stronger than #32's own remedy, not merely the same fix repeated**: `source` has no immutability trigger, so `DO UPDATE` there only removes the ordering race. `rule` does — `DO UPDATE` here makes any *future* drift between the two seeders impossible to land silently at all; the next `make golden` run after any edit raises `I18 violated` by name instead of quietly picking a winner. **P32's own record of why the drift proof was not pushed to CI was corrected by P33 — it was wrong, not merely imprecise.** P32 said the `ON CONFLICT` branch is "structurally unreachable on a single fresh CI database." False: `check_golden.py`'s `main()` calls `check_fixture` twice (`"refused"`, `"geometry-disabled"`), each calling `run_composition` → `seed_reference_rows()` — the same `rule INSERT` runs **twice** per `make golden`, so the second call hits `ON CONFLICT` on every real CI run. Confirmed empirically, not inferred: `pg_stat_user_tables` on a fresh database, before/after one `make golden` run — `n_tup_ins` 0→1, `n_tup_upd` 0→1, the second call's own real `UPDATE`. `0013`'s trigger genuinely fires against a real row on every CI run (identical-values direction, passes) — real, standing, accidental evidence nobody had claimed before. What is *actually* unreachable on CI is cross-seeder drift specifically (`day4_sources.sql` vs `check_golden.py`), because CI never runs `db/seeds/` — that narrower reasoning was sound and is why the break stayed unpushed; only its description was wrong. Full evidence in [P32-dual-seeder-and-rule-election-scope.md](P32-dual-seeder-and-rule-election-scope.md) section 1 and [P33-correct-36-close-37-design-35.md](P33-correct-36-close-37-design-35.md) section 1. |
| 37 | `make golden` performs an irreversible write — `rule_no_delete` blocks removal unconditionally, so every database `make golden` is run against now permanently carries the P31 rule row | **Closed — P33** | Finding #28's exact class (a routine check performing an irreversible write), found this time by reading the trigger rather than discovering it on a WORM bucket after the fact. P32 checked `ledgex_schema_check` clean; re-checked fresh for this fix (`make migrate-verify` first, 51 migrations `MATCH`) — still `0`, unchanged, since nothing ran `make golden` against it in between. **Closed via option (b), gated, not option (a)**: `check_golden.py`'s `seed_reference_rows()` now checks whether the rule row already exists before its `INSERT` — if absent and `GOLDEN_ALLOW_RULE_SEED` is not exactly `"1"`, it stops before writing anything, citing the exact permanence risk and how to proceed deliberately instead (`db/seeds/day4_sources.sql`, run as its own considered action). Gated by existence, not call count — correct regardless of which of finding #36's own two per-run seed calls reaches it first. `db.yml`'s `make golden` step sets `GOLDEN_ALLOW_RULE_SEED=1` (CI's `ledgex_ci` is disposable, confirming there costs nothing). Both directions proven on a real database: no override → `make: *** [golden] Error 1`, the exact message, **zero rows written**, confirmed by count; `GOLDEN_ALLOW_RULE_SEED=1` → proceeds normally, row count → 1; a third run with no flag at all, row already present → still proceeds normally (the gate stops blocking once the one truly first write has happened). Full evidence in [P33-correct-36-close-37-design-35.md](P33-correct-36-close-37-design-35.md) section 2. |
| 38 | `make golden` is now a real cross-seeder drift detector on any database where `db/seeds/day4_sources.sql` has also run — a capability nobody has claimed — and `db.yml`'s `schema` job could reach it by applying `db/seeds/` before `make golden`, closing finding #36's one remaining gap (cross-seeder drift specifically) | **Open, recorded only — P34** | `check_golden.py`'s own `rule` seed uses `ON CONFLICT (id) DO UPDATE SET` naming every non-key column (finding #36's fix) — on any database carrying both seed paths, any disagreement between the two seeders' literals raises `0013`'s `I18 violated` on the very next `make golden` run. Real today on `ledgex_schema_check` or a real production database post-launch; still not reachable in CI, because `db.yml`'s `schema` job never runs `db/seeds/` (CLAUDE.md's own documented rule). *For* a CI step applying `db/seeds/` before `make golden`: closes the one remaining gap in finding #36 at negligible cost — `day4_sources.sql` is small and idempotent, and `ledgex_ci` is already disposable. *Against*: blurs `db.yml`'s own repeatedly-documented "schema-only, never runs `db/seeds/`" boundary for every future reader who has internalized it as fact, to catch a documentation/maintenance risk (two seeders agreeing) rather than a correctness risk any customer-facing behavior depends on today. Deliberately not built — a change to the CI contract, scope creep for the package that found it (CONVENTIONS' "scope creep is reported, not absorbed"). Full argument in [P34-election-parameter-build.md](P34-election-parameter-build.md) section 7. |
| 39 | Nothing ties `property_file.election` to `ELECTION_REQUIRED`/`ELECTION_NOT_SUPPORTED` in `refusals` — a row can carry `election = 'city'` AND `ELECTION_REQUIRED`, or `election IS NULL` AND `ELECTION_NOT_SUPPORTED`, mutually contradictory, currently permitted | **Open, recorded only — P35** | Both one-way exclusions (`ELECTION_REQUIRED` present ⟹ `election IS NULL`; `ELECTION_NOT_SUPPORTED` present ⟹ `election IS NOT NULL`) hold structurally for `compose_property_file.py`'s own current writer — the refusal decision and the column write share the identical Python variable, read once, echoed once — so the contradiction is unreachable through the only writer today. The FULL biconditional (`election IS NULL` ⟺ `ELECTION_REQUIRED` present) does **not** hold structurally, only by coincidence: it is true only because "placement" is the sole, always-election-dependent conclusion this composer evaluates today — the exact "coincidence masks the bug until one side moves" shape README finding #22 already named once. Queried, not assumed: `ledgex_schema_check` (53 migrations, `MATCH`), 7 `property_file` rows, 2 with non-NULL `election`, 0 violating either proposed exclusion. Recommended, not built: a new migration backing a CHECK enforcing the two narrower, robust one-way exclusions (not the fragile full biconditional), same single-row `LANGUAGE sql IMMUTABLE` shape `refusals_codes_valid()` already uses — a CHECK, not a trigger, since nothing here needs `OLD`/`NEW` comparison. `election` has exactly one writer today, the same shape `job_run.schema_drift` had "zero legitimate writers" before 0051 found two reaching for it anyway — "unreachable through the only writer" is not "safe unenforced." Full argument in [P35-election-invariants-and-fk-report.md](P35-election-invariants-and-fk-report.md) section 3. |

Standing context that does not belong to any package:

- [CONVENTIONS.md](CONVENTIONS.md) — the hard rules every package inherits. Prompts reference
  it instead of restating it.
- [STANDING-BLOCKER.md](STANDING-BLOCKER.md) — why every composition still refuses. Not an
  engineering task.

## Session hygiene

Context is the scarcest resource in this project and most of it is spent before any work
starts. Measured:

| What | Size | Loaded when |
|---|---|---|
| `docs/LEDGEX_SPEC.md` | 223 KB (~56k tokens) | §1 only, every session (CLAUDE.md, since `9b071c4`) — everything else via `docs/SPEC_INDEX.md` |
| `db/tests/invariants.sql` | 199 KB | whenever a test is added |
| `db/schema.sql` | 63 KB | whenever schema is checked |
| all of `prompts/` | 100 KB | — |
| README + CONVENTIONS + one package | ~14 KB | what a session should actually load |

So: **one session per package, started cold.** Read this index, `CONVENTIONS.md`, and the
one active package. Do not carry a finished package's conversation into the next one — the
Review findings section exists so the next session does not need the transcript.

Grep `invariants.sql` and `schema.sql`; never read them whole. Same for the spec — start
at `docs/SPEC_INDEX.md` and read in full only the sections your change touches (§1 always,
per CLAUDE.md).

## How a package is written

Each file has three parts, in this order:

1. **What is actually wrong** — verified against a named commit, with file and line
   references. Never carried over from an earlier document without re-checking.
2. **The prompt** — a fenced block, paste-ready, nothing above or below it to edit out.
3. **In plain terms** — analogies. Skip when acting; read when deciding.

Packages landed under review also carry a **Review findings** section appended after the
fact. That section is the record of what the package got wrong, and it is what seeds the
next package.

## Adding a package

New file `P<n>-<slug>.md`, new row in the table above. Do not extend an existing package
once it has landed — findings go in its Review findings section and the fix goes in a new
package. Same forward-only discipline as `db/migrations/`, for the same reason: a package
that gets edited after it ran stops being a record of what was actually asked.
