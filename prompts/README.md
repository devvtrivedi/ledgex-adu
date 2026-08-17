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
| 9 | `db/tests/invariants.sql` commits fixtures and never cleans up | **Still open** | Seed data transaction is `BEGIN` (line 31) … `COMMIT` (line 355) — committed, not rolled back. No `DELETE FROM test.*` / `TRUNCATE` anywhere in the file (checked, zero matches). Every re-run adds more permanent `test.*`-namespaced rows to whatever database it's pointed at. |
| 10 | Snapshot dedup is check-then-insert, races under concurrent ingestion | **Still open** | `snapshot_exists()` (plain `SELECT`) followed by a separate `insert_snapshot()` (plain `INSERT`, no `ON CONFLICT`) in both `scripts/ingest_parcels.py:269-317` and `scripts/ingest_zoning_permits.py:336-372`. Two concurrent fetches of the same new content would both see "not exists" and one would hit a bare PK violation instead of a handled no-op. |
| 11 | Loaders are not jurisdiction-scoped | **Still open** (still latent — one jurisdiction today) | `JURISDICTION_ID = "ca_san_jose"` is a hardcoded module-level constant in both `scripts/ingest_parcels.py:86` and `scripts/ingest_zoning_permits.py:123`, not a parameter — nothing filters or scopes by jurisdiction anywhere in either loader. |
| 12 | `job_run.schema_drift` stretched to carry the permit unmatched breakdown | **Still open** | `load_permits`'s own comment names this explicitly as a reach beyond the column's declared meaning ("fields expected but missing" vs. a per-row match-outcome distribution) and states the honest fix is a general `metrics` jsonb column, not added because it's a schema change — `scripts/ingest_zoning_permits.py:806-841` |
| 13 | Detector reruns create duplicate open exceptions | **Partially closed** — `8a7286e`/`4d0f7ea` (P5), migration `0045` | The unique index `(parcel_id, detector_key, detector_version, detail->>'reason') WHERE outcome='open'` now exists for every detector, and `load_zoning`/`load_permits` pre-check `existing_open` before writing (`scripts/ingest_zoning_permits.py:635-680`) — a genuine no-op rerun for those two. `scripts/flag_invalid_geometry.py` (`4a931c7`, predates 0045) was never revisited: `flag_parcel_geometry`/`flag_zoning_source_geometry` build `exception_rows` unconditionally every run with no `existing_open` check (`scripts/flag_invalid_geometry.py:133-153`, `219-230`) — a rerun today hits 0045's unique index and raises `UniqueViolation`, crashing instead of no-op'ing. Found while reading detectors for P8 below, not part of the original list — real gap, not fixed here. **Not the same problem as P8** ([P8-exception-resolution-undefined.md](P8-exception-resolution-undefined.md)) either way: 0045 (where it applies) stops a *repeat* of an unchanged condition; nothing stops the condition itself from *changing* and leaving a stale exception open — that's P8, still unfixed. |
| 14 | Seeded `stale_after_days`/`required_for_file` "contradict §8 of the spec" | **No longer meaningful as stated** | §8 was already established (P5 gate, this README's own §5 note above) to have never existed in any tracked version of the spec — the citation was always a stale pointer, most likely meant for §3.3. `stale_after_days` isn't even set in the seed (`db/seeds/day4_sources.sql` never assigns it — always NULL); nothing there to check against a section with no content. If this needs re-litigating, it has to be re-posed against §3.3, not §8 — not done here, out of scope for a reconciliation pass. |
| 15 | `core/` a near-empty scaffold, so the jurisdiction-name blocklist grep scans almost nothing | **No longer accurate as stated, not independently fixed** | `core/` now holds `store.py` (`insert_facts`) and `exceptions.py` (`insert_exceptions`), real shared logic both ingest scripts call — grew organically during P3-P5, not from a targeted fix for this finding. Still small (126 lines total); whether it's *enough* coverage for the blocklist to mean something was never re-asked. |
| 16 | Deferred deliberately (`parcel_lineage` split/merge, matching-key decision, `job_run` metrics column, `pipelines/` split) | **Unchanged, still deferred** | `job_run` metrics column is the same fact as #12 above. `pipelines/` split's stated precondition ("Phase B is the thing that justifies it") is now met (#4, closed) but the split itself hasn't been done — worth a conscious decision, not a rediscovery, next time it comes up. `parcel_lineage` and the matching-key question still await the trigger event (an observed split, an observed source change) neither of which has happened. |
| 17 | `parcel_apn_unresolvable`'s resolvability flip between snapshots is undetected — a feature whose APN goes from resolvable to unresolvable (or back) between two `ingest_parcels.py` runs isn't covered by that reconciliation pass at all | **Closed** — `4bda739` (P13), together with #22 | `scripts/ingest_parcels.py`'s `changed_rows` query joined `parcel.apn` INNER, so a parcel with no live fact could never enter it; the resolve-again direction was undetectable and its geometry changes were silently dropped (the other half of #22). `fa` is now a LEFT JOIN with a `CASE`-based changed-predicate (all four fact-present/absent × incoming-resolvable/unresolvable combinations worked out explicitly, verified 0 false positives on real 225K-parcel data via same-snapshot self-comparison). A resolve writes a NEW fact (nothing was live to supersede) and closes the open exception via a new, narrower `core/exceptions.close_exceptions_for_parcels()` — not `close_resolved_exceptions()`, which needs a full-recompute pass `phase_e` doesn't have, exactly as this row's own prior note anticipated. RED-first (real bug reproduced live: geometry silently unsuperseded, a resolve never detected) then GREEN, three times, on the real runner via the new `phaseb-acceptance` CI gate. Full evidence in [P13-apn-resolvability-flip.md](P13-apn-resolvability-flip.md). |
| 18 | A `detector_version` bump leaves every OLDER-version open exception permanently unclosable by P9's own closure mechanism | **New, still open** — surfaced while settling P9's own design question, not part of the original handoff list | P9's close helper matches exact `(detector_key, detector_version)`, same shape `existing_open` already used (`scripts/ingest_zoning_permits.py:638-639`) — deliberately, not an oversight: cross-version closing would assert `condition_cleared` (the current run determined this is false) for a condition the running detector's CURRENT rule never actually evaluated, since the old row was classified under a different rule. Confirmed live, not hypothetical: `ledgex_schema_check` carries 10,150 real open `zoning_spatial_join_unresolvable` rows at `detector_version='1.0'` that `db/migrations/0047`'s closure mechanism will never touch. Not a new gap P9 created — `0045`'s own migration comment already named and explicitly deferred this exact consequence of scoping its unique index by `detector_version`. Own package, later: would need a decision on how (or whether) to migrate/reconcile the specific stale rows a version bump leaves behind, which P9 was never scoped to make. |
| 19 | `0045`'s partial unique index does not constrain what it appears to — it has never actually applied to `zoning_source_geometry_invalid` | **Closed** — `576ce9e` (P10) | Reproduced with a fresh number, not the cited 157→314: a minimal real repro (one deliberately self-intersecting zoning polygon classifying one real parcel via `ST_MakeValid` repair), P9's application guard bypassed, two real runs of `flag_zoning_source_geometry` against unchanged data — 1 row became 2, no `UniqueViolation`. Fixed via candidate (b) — `db/migrations/0049_parcel_exception_reason_coalesced.sql`, `COALESCE(detail->>'reason', '')` — argued against (a) (inventing a `reason` key going forward does nothing for rows already stored, and this detector has no natural sub-classification to justify one). `0006`'s `fact_one_current_per_source` COALESCE precedent checked, not assumed to transfer as-is: same technique, different justification (there NULL is a legitimate recurring domain state; here it's simply an absent key, uniform across 100% of this one detector's rows, confirmed to have zero effect on every other detector by reading every `exception_rows` call site). Existing databases queried first for duplicates — zero, everywhere reachable. RED-first (`db/tests/invariants.sql` T84-T85) then GREEN, three times, real runner; fixing this surfaced and fixed a real latent test-fixture collision (`T5`/`T30`) the never-enforcing old index had been hiding. Full evidence in [P10-null-inside-a-constraint.md](P10-null-inside-a-constraint.md). |
| 20 | `run_p5_acceptance.sh` cannot complete end-to-end on any database | **Closed** — `3af23f6`, `98cbda4`, `c77ba5b` (P12) | P9's own `condition_cleared` fix (`db/migrations/0047`, `core/exceptions.py`) intentionally changed `23707070`'s behavior; `check_p5_acceptance.py`'s `after-b`/`after-a2` assertions for that parcel still asserted the pre-P9 behavior. Confirmed against a live A1→B→A2 trace (not assumed) that P9 closes the correct, stale exception both directions, then rewrote both assertions to match (`3af23f6`). The suite now completes end-to-end for the first time: `scripts/run_p5_acceptance.sh` exits 0, `P5 ACCEPTANCE: ALL CHECKPOINTS PASSED`, three times as CONVENTIONS.md requires (twice seeded, once fresh migrations-only). Proved the new assertions have teeth locally, not just that the old ones stopped firing: deliberately skipped `close_resolved_exceptions` in `load_zoning`, confirmed the new assertion catches it (`got ('...', 'no_containing_district', 'open', None, None, ...)`), reverted, confirmed green. Then wired the suite into CI as a third gate (`98cbda4`, pinned `c77ba5b`) and proved *that* on the real runner too, not locally: pushed `065f3e5`, a deliberate reintroduction of P11's `permits.active` churn, to shared `main` — `db.yml` run [31984771169](https://github.com/devvtrivedi/ledgex-adu/actions/runs/31984771169) shows `p5-acceptance: failure` (`schema: success`, unaffected), with the exact predicted assertion failing (`got 3`). Reverted via `git revert` (`a9eafac`, content diffed byte-identical to the pre-break fix at `0317e02`'s `load_permits` block) — `db.yml` run [31984977677](https://github.com/devvtrivedi/ledgex-adu/actions/runs/31984977677) shows `p5-acceptance: success`. Minio pinned to `RELEASE.2025-09-07T16-13-09Z` afterward, confirmed still green: run [31985093236](https://github.com/devvtrivedi/ledgex-adu/actions/runs/31985093236). |
| 21 | Reconciliation reads in three call sites are not source-scoped (`ingest_zoning_permits.py:564-571`, `:884-891`; `ingest_parcels.py:1108-1120`) | **Still open, confirmed latent, not P4's remaining scope** | `fact_one_current_per_source` (`0006`) is unique per source; none of these three queries filter by `source_id`, so a second source holding a live fact for the same `(parcel, field)` makes the comparison an arbitrary pick and can make a source skip a write it owed. `0044` (P4) catches the cross-source *supersession*; it does not catch this silent wrong-comparison, a different code path than the DISAPPEARED-branch cross-source write P4 actually fixed. Confirmed safe as a no-op on today's data by direct count (identical before/after `AND source_id = %s` on the real 1.1M-fact dataset), and confirmed latent (exactly one `source_id` per field today) — not applied under P11 per CONVENTIONS' scope-creep rule; a future package's job. |
| 22 | `phase_e`'s CHANGED branch writes an APN degradation (resolvable → placeholder/blank) as a live `parcel.apn` fact instead of routing it through `is_unresolvable_apn` | **Closed** — `4bda739` (P13), together with #17 | Fixed as argued: a degrade now supersedes with no successor, raises a `parcel_apn_unresolvable` exception (reusing the existing `detector_key`/`detector_version`), and sets the `parcel.apn` cache column to `NULL` — reusing the existing supersede-before-insert write sequence, no second write path. RED-first against real fixtures extended for exactly this case (`db/fixtures/phaseb/`, four new synthetic features): `'99999003???'` and JSON `null` landing directly as live `fact.value`, reproduced on demand, not inferred — then GREEN, three times, real database. Also closed #23-style: queried every locally reachable database (`ledgex_schema_check` plus seven tier-2 scratch databases) for the actual damage pattern (a live `parcel.apn` fact containing `?` or JSON `null`) before landing the fix — **0 rows everywhere reachable**; remediation (supersede-with-no-successor, legal under `0007`/I4) proposed in [P13-apn-resolvability-flip.md](P13-apn-resolvability-flip.md) but not run, since nothing reachable needs it. The Supabase database (finding #23) remains the one unchecked exception. |
| 23 | The Supabase database named in `.env`'s `DATABASE_URL` could not be checked for the licence contamination finding #4/step-4 fixed at the source | **Unverified — genuinely unknown, not assumed clean** | No network reachability to `db.ckzvekwzyackwaimvazg.supabase.co` from the environment this pass ran in (`psql`: "could not translate host name"). If any of the five scripts fixed in this pass's licence-contamination commit was ever run against it before the fix landed, it now carries `cc0`/`cc_by_4_0` rows with `cleared_by='test'`, a fabricated `cleared_at`, and `observed_at` set to whatever moment that run happened — asserting counsel/owner clearance that `STANDING-BLOCKER.md` and `db/seeds/day4_sources.sql` both state does not exist. `0027` makes `licence` immutable, so if this is the case, no migration can correct it — rebuild (drop, re-migrate, reseed) is the only remedy, and this is explicitly the *least* rebuildable database in the project (not local scratch state). To settle it: from an environment with network access, `SELECT id, observed_at, cleared_by, cleared_at FROM licence WHERE id IN ('cc0','cc_by_4_0');` against that `DATABASE_URL` — `cleared_by`/`cleared_at` both `NULL` and `observed_at = '2026-07-31'` (matching `db/seeds/day4_sources.sql`) means clean; anything else means contaminated and rebuild-only. Not touched, per instruction — do not act on this row without that query run first, and without asking before any rebuild. |

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
