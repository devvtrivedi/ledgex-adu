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
| P8 | [Nothing resolves a `parcel_exception` when its condition changes](P8-exception-resolution-undefined.md) | confirmed finding, not fixed | — |

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
| 8 | `refusals[].code` accepts `[{}]`, `[{"code": null}]`, `["not-an-object"]` | **Still open** | `refusals_codes_valid()` (0038) is `elem->>'code' NOT IN (...)`; on all three shapes `elem->>'code'` evaluates to SQL `NULL`, `NULL NOT IN (...)` is `NULL` (not true), so the offending row never satisfies the `WHERE` and `NOT EXISTS` reports clean — `db/migrations/0038_refusals_code_check.sql:69-92`. 0038 only closed the *vocabulary* gap (typo'd/invented codes), not the *shape* gap. |
| 9 | `db/tests/invariants.sql` commits fixtures and never cleans up | **Still open** | Seed data transaction is `BEGIN` (line 31) … `COMMIT` (line 355) — committed, not rolled back. No `DELETE FROM test.*` / `TRUNCATE` anywhere in the file (checked, zero matches). Every re-run adds more permanent `test.*`-namespaced rows to whatever database it's pointed at. |
| 10 | Snapshot dedup is check-then-insert, races under concurrent ingestion | **Still open** | `snapshot_exists()` (plain `SELECT`) followed by a separate `insert_snapshot()` (plain `INSERT`, no `ON CONFLICT`) in both `scripts/ingest_parcels.py:269-317` and `scripts/ingest_zoning_permits.py:336-372`. Two concurrent fetches of the same new content would both see "not exists" and one would hit a bare PK violation instead of a handled no-op. |
| 11 | Loaders are not jurisdiction-scoped | **Still open** (still latent — one jurisdiction today) | `JURISDICTION_ID = "ca_san_jose"` is a hardcoded module-level constant in both `scripts/ingest_parcels.py:86` and `scripts/ingest_zoning_permits.py:123`, not a parameter — nothing filters or scopes by jurisdiction anywhere in either loader. |
| 12 | `job_run.schema_drift` stretched to carry the permit unmatched breakdown | **Still open** | `load_permits`'s own comment names this explicitly as a reach beyond the column's declared meaning ("fields expected but missing" vs. a per-row match-outcome distribution) and states the honest fix is a general `metrics` jsonb column, not added because it's a schema change — `scripts/ingest_zoning_permits.py:806-841` |
| 13 | Detector reruns create duplicate open exceptions | **Partially closed** — `8a7286e`/`4d0f7ea` (P5), migration `0045` | The unique index `(parcel_id, detector_key, detector_version, detail->>'reason') WHERE outcome='open'` now exists for every detector, and `load_zoning`/`load_permits` pre-check `existing_open` before writing (`scripts/ingest_zoning_permits.py:635-680`) — a genuine no-op rerun for those two. `scripts/flag_invalid_geometry.py` (`4a931c7`, predates 0045) was never revisited: `flag_parcel_geometry`/`flag_zoning_source_geometry` build `exception_rows` unconditionally every run with no `existing_open` check (`scripts/flag_invalid_geometry.py:133-153`, `219-230`) — a rerun today hits 0045's unique index and raises `UniqueViolation`, crashing instead of no-op'ing. Found while reading detectors for P8 below, not part of the original list — real gap, not fixed here. **Not the same problem as P8** ([P8-exception-resolution-undefined.md](P8-exception-resolution-undefined.md)) either way: 0045 (where it applies) stops a *repeat* of an unchanged condition; nothing stops the condition itself from *changing* and leaving a stale exception open — that's P8, still unfixed. |
| 14 | Seeded `stale_after_days`/`required_for_file` "contradict §8 of the spec" | **No longer meaningful as stated** | §8 was already established (P5 gate, this README's own §5 note above) to have never existed in any tracked version of the spec — the citation was always a stale pointer, most likely meant for §3.3. `stale_after_days` isn't even set in the seed (`db/seeds/day4_sources.sql` never assigns it — always NULL); nothing there to check against a section with no content. If this needs re-litigating, it has to be re-posed against §3.3, not §8 — not done here, out of scope for a reconciliation pass. |
| 15 | `core/` a near-empty scaffold, so the jurisdiction-name blocklist grep scans almost nothing | **No longer accurate as stated, not independently fixed** | `core/` now holds `store.py` (`insert_facts`) and `exceptions.py` (`insert_exceptions`), real shared logic both ingest scripts call — grew organically during P3-P5, not from a targeted fix for this finding. Still small (126 lines total); whether it's *enough* coverage for the blocklist to mean something was never re-asked. |
| 16 | Deferred deliberately (`parcel_lineage` split/merge, matching-key decision, `job_run` metrics column, `pipelines/` split) | **Unchanged, still deferred** | `job_run` metrics column is the same fact as #12 above. `pipelines/` split's stated precondition ("Phase B is the thing that justifies it") is now met (#4, closed) but the split itself hasn't been done — worth a conscious decision, not a rediscovery, next time it comes up. `parcel_lineage` and the matching-key question still await the trigger event (an observed split, an observed source change) neither of which has happened. |

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
