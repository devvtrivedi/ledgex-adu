# P60 Ledger — Turn CI On, Rotate the Credential, Close the Timezone Class

Live document, updated as work proceeds. Branch `p59-defect-clearance`, starting HEAD
`675ec82` (P59C addendum's own final commit). Source of truth for scope: the P60 prompt
itself (LEDGEX-P60-*.txt in the untracked prompt corpus).

## 1. Decision 6.1-revised

**Owner chose Option A: push the branch.** `git push -u origin p59-defect-clearance`.
`main` is left untouched — 0 commits added, no merge, no `workflow_dispatch:` trigger
added anywhere (not needed under Option A, and per the prompt's own instruction, not added
"for later" either, since an unused trigger on a since-diverged branch would read as a
working mechanism to a future session when it is not one).

Decided: 2026-08-26 (same day as the P59C addendum's own "Gates at 675ec82" block).

**Prediction, before pushing:** `git push -u origin p59-defect-clearance` succeeds (new
remote ref, plain push, exit 0); fires `db.yml` (3 jobs) and `docs.yml` (1 job, 2 steps)
against sha `675ec82`; given 10 packages of never-observed work, at least one red job is
expected, exact job unknown.

**Actual:** push succeeded, exit 0, no force needed (`* [new branch] p59-defect-clearance
-> p59-defect-clearance`). Both workflows fired within 7 seconds. Verified.

**What this means for the never-push posture going forward.** The posture is no longer
"never push, full stop" — it is now "never push `main` without review; a feature branch push
to observe CI is normal and expected." `db.yml`/`docs.yml` are `on: push` with no branch
filter (confirmed against `origin/main`'s own copy before this decision was made), so pushing
`p59-defect-clearance` fires both workflows immediately, using the BRANCH's own workflow
definitions (168 insertions ahead of `main`'s copy) — this is the first time those definitions
are themselves observed, not just the code they gate. Any future merge to `main` still goes
through its own review step; this decision does not authorize that merge, only the branch
push that makes CI observable before it happens. Every subsequent push in this ledger (runs
#3-#5, and P60-3/P60-4's own pushes below) falls under this same authorization — each is a
push to `p59-defect-clearance` alone, to observe CI, never to `main`.

## 2. CI runs

| # | workflow | sha | run URL | result | duration |
|---|---|---|---|---|---|
| 1 | docs | `675ec82` | https://github.com/devvtrivedi/ledgex-adu/actions/runs/32917569261 | **SUCCESS** — `qa` job, both `make qa` and `make check-boundary` steps green | 16s |
| 2 | db | `675ec82` | https://github.com/devvtrivedi/ledgex-adu/actions/runs/32917569309 | **FAILURE** — all 3 jobs red: `p5-acceptance` (P5 acceptance suite step), `phaseb-acceptance` (Phase B acceptance suite step), `schema` (test_c19_reconcile_identity_verified.py step) | schema 1m2s, p5 57s, phaseb 54s |

First observed run in this repository's history where "CI green"/"CI red" can be written
truthfully: `docs.yml` is **CI green** at `675ec82`; `db.yml` is **CI red** at `675ec82`.
Both verified via `gh run view`, not assumed from the push succeeding.

| 3 | db | `1134e6f` | https://github.com/devvtrivedi/ledgex-adu/actions/runs/32918694743 | **FAILURE** — `p5-acceptance` and `phaseb-acceptance` both **SUCCESS** (defects #2/#3 fixed); `schema` still red, but at a NEW step — `make conformance` (defect #4, previously masked entirely by #1) | — |
| 4 | docs | `f344a59` | https://github.com/devvtrivedi/ledgex-adu/actions/runs/32919210086 | **SUCCESS** | — |
| 5 | db | `f344a59` | https://github.com/devvtrivedi/ledgex-adu/actions/runs/32919210105 | **SUCCESS** — all 3 jobs (`schema`, `p5-acceptance`, `phaseb-acceptance`) | — |

**`db.yml` is CI green for the first time in this repository's history**, at `f344a59`, verified
via `gh run view --json conclusion,jobs` (all three job conclusions independently `"success"`),
not inferred from the run's own top-level status alone. Run #2 → #5 is the full P60-2 arc:
4 real defects found, each reproduced (or, for #1, precisely named as CI-only) before being
fixed, each fix proven locally before push, each push re-observed in real CI — see section 3.

## 3. Triage table

Failure text below is quoted verbatim (via `gh run view 32917569309 --log-failed`), not
paraphrased. All three reproduced locally against a fresh scratch database mirroring CI's own
setup (`make schema` on an empty db, then, where the failing step needs it, `db/seeds/
day4_sources.sql`), except #1, which is CI-only by construction (see its own row).

| # | workflow/job/step | failure (quoted from log) | reproduces locally? | class | disposition | fix commit | proving re-run |
|---|---|---|---|---|---|---|---|
| 1 | db / schema / `scripts/test_c19_reconcile_identity_verified.py` | `missing required environment variable: OBJECT_STORE_BUCKET` | **No** — verified. Ran the identical test against a fresh scratch db (`make schema` + `db/seeds/day4_sources.sql`, same order as CI) with the local dev MinIO (`docker ps` shows `ledgex_minio` already running) and `.env`'s `OBJECT_STORE_*` vars: exit 0, `[test] PASS`. | CI-only — plumbing, not a code defect. Named precisely: `db.yml`'s `schema` job (line 42-63) has an `env:` block with only `DATABASE_URL`/`PSQL`/`PG_DUMP`, and a `services:` block (line 29) with only `postgres` — no MinIO service, no `OBJECT_STORE_*` vars anywhere in that job. `test_c19_reconcile_identity_verified.py` needs both (its own docstring line 23: "a reachable MinIO (OBJECT_STORE_* env vars)"; `env("OBJECT_STORE_BUCKET")` at line 71). The step's own comment at db.yml:224-227 calls it "same after-seed, real-MinIO placement as C10 above" and a later comment at line ~233 claims OBJECT_STORE_* is "already configured job-wide" for "the C10/C19 steps above" — both **wrong**: C10 (`test_load_parcels_identity.py`) does not reference `OBJECT_STORE` at all (grepped, confirmed), and nothing configures those vars job-wide in `schema`. This test could never have passed in CI since the day C19 was wired in — unreachable until this run because CI itself was unreachable until P60-1. | FIXED | `63b6a6a` | run #3 (`1134e6f`) — `schema` job's C19 step, and the whole C20 group after it, ran clean; job failure moved to a NEW step (`make conformance`, defect #4) |
| 2 | db / phaseb-acceptance / "Phase B acceptance suite (new/changed/disappeared/reappeared)" | `psycopg2.errors.ForeignKeyViolation: insert or update on table "fact" violates foreign key constraint "fact_snapshot_licence_fk"` / `DETAIL:  Key (snapshot_id, licence_id)=(ca_san_jose.zoning_districts:sha256:97097c05115bbf206bb7b09724e31dab8c0574d85ba712cd159949b35c084686, cc_by_4_0) is not present in table "snapshot".` | **Yes** — verified. Ran `scripts/run_phaseb_acceptance.sh` against a fresh scratch db, identical traceback, identical constraint, identical key. | Ordinary defect — P59C's local gates missed it (this acceptance script was never actually exercised against the current codebase; the `phaseb-acceptance` CI job that would have caught it had never run before P60-1, same reachability gap as #1). `scripts/run_phaseb_acceptance.sh`'s finding-#21 "SOURCE-SCOPE CONFLICT SETUP" block (line 151-180) hand-writes a `fact` row citing the real `ca_san_jose.zoning_districts` snapshot but a hardcoded literal `licence_id = 'cc_by_4_0'` (line 170). P55 repointed every real ingest script's own `LICENCE_ID`/`LICENCE_ID_ZONING` from `'cc_by_4_0'` to `'cc_by_4_0_api_2026_08'` (confirmed: `scripts/ingest_zoning_permits.py:134`, `scripts/ingest_parcels.py:88`, both comment "P55: repointed from 'cc_by_4_0'") — so the `snapshot` row for this snapshot_id, registered by the real ingest during this same script's "SEED ZONING" step, now carries `licence_id='cc_by_4_0_api_2026_08'`, and `fact_snapshot_licence_fk` (a composite FK on `snapshot(id, licence_id)`) rejects any fact citing that snapshot_id under the old, no-longer-matching licence. `scripts/_phaseb_setup.py:65-69`'s own comment explicitly (and, per this finding, wrongly) says the old `cc_by_4_0` licence row was kept specifically so this hand-written INSERT could keep using it — that comment's premise didn't account for the snapshot-level FK, only the licence table's own existence. | FIXED | `960b418` | run #3 (`1134e6f`) — `phaseb-acceptance` job SUCCESS |
| 3 | db / p5-acceptance / "P5 acceptance suite (zoning + permits reconciliation)" | `[FAIL] after B: 23717099 permits.active = false (last permit disappeared), superseded, world_change -- got ('efd067e2-35b6-45d6-9847-da84baa9a48c', True, None, None)` and `[FAIL] after B: 23717099 permits.series_earliest retired, no successor -- got ('648f0899-e8a4-4d63-9e85-4c463bd2c96b', '2026-01-01', None, None)` | **Yes** — verified. Ran `scripts/run_p5_acceptance.sh` against a fresh scratch db, identical two failures (different UUIDs, same values/shape). Fixing them surfaced the SAME stale-licence defect class as #2, and the SAME stale-assertion class again for 23712112 — both fixed in the same commit, both re-proven locally before push (see commit message for the full RED/GREEN sequence). | Ordinary defect, in the TEST not the production code — same "never reachable in CI before P60-1" root cause as #2. `scripts/check_p5_acceptance.py` (lines 205-212, and the analogous 23712112 block) still asserted the OLD behavior: a permit that disappears from the source file supersedes `permits.active` to `false` with `supersession_reason='world_change'`. `scripts/ingest_zoning_permits.py`'s own C2 fix (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md; code + extensive comment at lines 1268-1311) deliberately **removed** exactly this "retire_with_false_successor" behavior: without a persisted per-permit identity, the ingest can no longer distinguish "this permit's row is just unattributable this run" from "this permit genuinely dropped off the export," so absence now leaves the live fact untouched and opens a `permit_attribution_lost` exception instead of ever fabricating a `false` value. The fixture data (`db/fixtures/p5/p5_permits_B.csv`/`p5_permits_A.csv`) genuinely omits these permits from one side, so the code takes exactly its new, documented, intentional path — the test's own expectation is the stale part, never updated when C2 landed. Also found and fixed while proving this GREEN: `scripts/run_p5_acceptance.sh`'s own finding-#21 setup hardcoded `licence_id='cc0'` (same class as #2, permits' own old licence id, pre-P55) on a fact citing the real `ca_san_jose.building_permits_active` snapshot. | FIXED | `1134e6f` | run #3 (`1134e6f`) — `p5-acceptance` job SUCCESS |
| 4 | db / schema / `make conformance` | `[FAIL] 'ca_san_jose.parcels''s supplies: matches the live source.expected_fields exactly -- pack has ['parcel.apn', 'parcel.geometry', 'parcel.source_parcel_id'] not in the database, database has [] not in the pack` (same shape for `ca_san_jose.zoning_districts`) | **Yes** — verified, by bisection. Replayed the `schema` job's exact step order against a fresh scratch db, checking `source.expected_fields` after every step: intact through `test_refresh_failure_invariant.py`, gone by the time `make golden` ran in a full non-stop replay — isolated to `test_snapshot_race_invariant.py` (the only step of the ones in between whose own `INSERT INTO source` omits `expected_fields`). | Ordinary defect, pre-existing and structurally old (not introduced by defects #1-3 or their fixes) — surfaced for the first time only because `make conformance` never got a chance to run in this job before (blocked upstream by defect #1). `scripts/test_snapshot_race_invariant.py`'s `seed_reference_rows_parcels()`/`seed_reference_rows_zoning()` `INSERT INTO source` for the REAL `ca_san_jose.parcels`/`ca_san_jose.zoning_districts` ids, `ON CONFLICT (id) DO NOTHING`, with no `expected_fields` in the column list — defaults to `'[]'` (0002's own column default). This script runs BEFORE `db/seeds/day4_sources.sql` in the `schema` job. `day4_sources.sql`'s own INSERT for the same two ids is what actually sets the real, corrected `expected_fields` — but it is ALSO `ON CONFLICT (id) DO NOTHING`, so it silently no-ops against the row this script already created, permanently leaving it empty for the rest of the job. The identical gap exists in `test_refresh_failure_invariant.py`/`test_zoning_ambiguity_invariant.py`/`test_apn_canonicalization_invariant.py`'s own `seed_reference_rows()` (this file's own docstring names them as the same copy-pasted pattern) — **not fixed**, named as a risk in the fix commit: currently harmless only because each runs AFTER `day4_sources.sql` in every job that wires it in today. | FIXED | `f344a59` | run #5 (`f344a59`) — `schema` job SUCCESS, `make conformance` step: `CONFORMANCE SUMMARY: PASSED (0 failure(s))` |

**Class summary:** 1 CI-only plumbing gap (never weakens what's checked — makes an already-written test reachable), 3 ordinary local-reproducible defects (1 in test setup code citing a stale licence id in two sibling scripts, 1 in test assertions never updated after a deliberate, documented behavior change, 1 in a fixture-seeding script's own incomplete `INSERT`). All four trace to the same root cause: no acceptance suite or downstream step in `db.yml` could ever have caught anything before this package, because CI itself was never reachable — #4 in particular was masked two layers deep (behind #1, which was itself the reason #2/#3 were also never observed). None required touching production ingest logic, and none is a gate-weakening — see the individual dispositions above for why each fix is a correction, not a relaxation. **`db.yml` reached full green (all 3 jobs) at run #5 (`f344a59`) — P60-2 is done; db.yml has never been red since.**

## 4. P60-3 rotation verification

**Old credential confirmed dead.** `.env`'s `DATABASE_URL` pointed at
`postgresql://***:***@db.ckzvekwzyackwaimvazg.supabase.co:5432/postgres?sslmode=require`
(masked here and everywhere — the real value was never printed, logged, or committed at any
point this session). Tested read-only (`SELECT 1`, output piped through `grep -v` to strip
any echoed connection string before it could reach a terminal) — connection failed at DNS:
`could not translate host name "db.ckzvekwzyackwaimvazg.supabase.co" to address: nodename nor
servname provided, or not known`.

That alone is ambiguous (could be a local DNS problem, not a dead project) — resolved by
testing a known-good control hostname on the same resolver: `host google.com` returned a real
address immediately; `host db.ckzvekwzyackwaimvazg.supabase.co` returned a hard **NXDOMAIN**
("Host ... not found: 3(NXDOMAIN)"), not a timeout or connection-refused. Local DNS resolution
works; this specific name does not exist. Verified — a per-project Supabase subdomain
returning NXDOMAIN (rather than resolving-but-refusing) is consistent with the project itself
having been deleted or the credential rotated at the platform level, not a transient issue.

**`.env` demoted.** `DATABASE_URL` changed to `postgresql://localhost/ledgex_schema_check`,
byte-identical to `.env.example`'s own documented shape. `.env` is listed in `.gitignore`
(`.env` and `.env.*`, both present) and `git log --all -- .env` returns empty — confirmed
never tracked, at any point in this repository's history, on any branch. The demotion itself
has no commit (nothing to commit — the file was never tracked and stays that way); `git status
--short -- .env` shows nothing, confirmed after the edit.

**`infra/env.py` corrected.** Its own "THE DEFAULT BINDING" docstring paragraph (P39) stated,
present tense, that the repo-root `.env`'s `DATABASE_URL` "points at a live remote database" —
true when written, false now. Corrected in the file's own established "Corrected DATE (Pxx)"
shape: commit `f6df3ab`. The paragraph's actual point (load_dotenv's upward search silently
binds whatever `.env` holds, on whatever machine, to any script run from the repo root) is
unchanged and is still the reason `refuse_remote()` exists — only the stale present-tense
claim about today's specific value was wrong.

**A-N9's `refuse_remote()`/`_is_local()` re-verified against the demoted URL, not just assumed
to still work.** Live, both checks: `_is_local(DATABASE_URL)` → `True`; `refuse_remote
(DATABASE_URL)` → does not exit (correctly allows it); `get_db()` connects successfully
(`SELECT current_database()` → `ledgex_schema_check`). All three run against the real,
demoted `.env` this session, not a synthetic string.

**Observation, not a P60-3 defect — recorded for P61.** The `ledgex_schema_check` this demoted
URL actually reaches is **not** the docker container `ledgex` this whole ledger's own database
work otherwise refers to (225,077 parcels, reachable only via `docker exec`, per P59C/P59C
addendum). `localhost:5432` is served by a **separate, local Homebrew-installed Postgres 16.14**
process (confirmed: `lsof -nP -iTCP:5432 -sTCP:LISTEN` shows Homebrew's postgres bound
specifically to `127.0.0.1`/`::1`, and Docker Desktop's own proxy bound only to the wildcard
address — a client connecting to `localhost` resolves `::1` first and lands on the Homebrew
server, never Docker's) — a genuinely different database that happens to share the name
`ledgex_schema_check`, currently holding just 1 `parcel` row. This is consistent with, not a
contradiction of, the already-established fact that the docker container's own
`ledgex_schema_check` is unreachable from the host on port 5432 (P59C) — it explains WHY: that
port is never actually docker's to answer, on this machine, for a plain `localhost` client.
Not a P60-3 problem (the acceptance criterion — `refuse_remote` correctly allowing a genuinely
local URL — holds regardless of which local server answers), and not something this pass was
asked to reconcile or fix; named here so a future session reaching for
`postgresql://localhost/ledgex_schema_check` does not mistake it for the docker container's
rich, real data.

## 5. P60-4 — the timezone class

**(a) `day4_sources.sql`'s own literals — fixed.** Nine bare `'YYYY-MM-DD'::timestamptz`
literals, re-verified by grep (not trusted from the prompt's own "nine" claim) — matched
exactly. Every one now carries an explicit UTC offset
(`'YYYY-MM-DDT00:00:00+00'::timestamptz`). RED/GREEN proven under two different `PGTZ`
settings against two independent fresh databases — see commit `9e092c3`'s own message for
the full transcript (bare literal: `2026-08-06 00:00:00` UTC under `PGTZ=UTC`,
`2026-08-05 10:00:00` UTC — a different calendar day — under `PGTZ=Pacific/Kiritimati`;
fixed literal: identical under both). This file is applied via plain `psql`, never through
`infra.env.get_db()` — so C7/AD1's own connection-level UTC fix never covered it; this was a
real, separate gap, not a duplicate of an already-closed one.

**(b) Partition of already-seeded data on `ledgex_schema_check` (docker container `ledgex`,
read-only via `docker exec`, never host port/remote — the real docker `ledgex_schema_check`,
not the separate Homebrew-served database of the same name section 4 names) — done, and
resolves cleanly.**

Every column any of the nine (pre-fix) literals, or migrations 0023/0056's own two additional
literals, ever populated — 9 + 3 = a full accounting, not a sample:

| table | mutability | column | rows | stored value (read live, `AT TIME ZONE 'UTC'`) | expected | match? |
|---|---|---|---|---|---|---|
| `licence` | **immutable** (0027) | `observed_at` | `cc0`, `cc_by_4_0`, `cc_by_4_0_api_2026_08`, `cc0_api_2026_08` | `2026-07-31 00:00:00` (all four) | `2026-07-31 00:00:00` | ✅ |
| `licence` | **immutable** (0027) | `observed_at` | `unknown` (0056's own INSERT) | `2026-08-22 00:00:00` | `2026-08-22 00:00:00` | ✅ |
| `rule` | **immutable** (0013) | `reviewed_at` | `ca_san_jose.adu_detached_max_height_city_standards.v1` | `2026-08-18 00:00:00` | `2026-08-18 00:00:00` | ✅ |
| `source` | mutable | `url_verified_at` | `ca_san_jose.parcels`, `.zoning_districts`, `.building_permits_active` (2 of these 3 also touched by 0023's own guarded UPDATE) | `2026-08-06 00:00:00` (all three) | `2026-08-06 00:00:00` | ✅ |

**Root cause of why every value is already correct, confirmed directly, not assumed:**
`SHOW TimeZone` on this exact database returns `Etc/UTC` — its own server default has always
been UTC. Every one of these literals was applied via plain `psql` with no `PGTZ` override (the
normal way this database has ever been seeded/migrated), so every bare literal happened to
resolve at UTC midnight anyway — the SAME real hazard section (a) and (d) prove is genuine
(a differently-configured server, or any session connecting with a non-UTC `PGTZ`, would have
produced a wrong value) simply never fired here, because the one condition it depends on
(a non-UTC session) was never present on this specific database.

**Consequence for pause points 3 and 4:** neither is reached. Pause point 3 (the immutable-row
rebuild decision) only exists to escalate a confirmed-wrong immutable value with no other fix —
there is none: both immutable-table rows (`licence`, `rule`) are already correct. Pause point 4
(any new migration, 0059) only exists to correct a confirmed-wrong mutable value — there is
none of those either: `source.url_verified_at` is already correct. **Nothing on this database
needs remediation.** This is a real finding, not a decision made on the owner's behalf — see
the final response for the explicit check-in on this reading before treating P60-4(b) as fully
closed (a different database or environment with a non-UTC server default, never checked here,
could still be affected; this pass's own scope was specifically `ledgex_schema_check`, per the
prompt's own instruction, not every database everywhere).

**(c) New documentation-pointer mechanism for migrations 0023/0056 — done.** `db/README.md`'s
new "Known timezone-literal defects in landed migrations" section (commit `69419f7`),
deliberately separate from B9 "Stale migration header claims" (B9's own scope: "a prose-only
staleness — nothing to fix, nothing broken" — the opposite of this). Records both migrations'
exact literal locations, states plainly this is a functional defect, and — updated by this same
pass, not left stale — records (b)'s own resolution: **verified already-correct on
`ledgex_schema_check`, not remediated because remediation was never needed there.**

**(d) Non-UTC CI leg — done, `timezone-non-utc` job in `db.yml`.** A dedicated job, not a pin
on any existing gate — builds a fresh database, applies `make schema` + `day4_sources.sql`
under `PGTZ=Pacific/Kiritimati` (UTC+14, deliberately extreme), then asserts every seeded
value is the exact correct UTC instant. Proven RED against the pre-fix file (git history,
commit `9e092c3~1`) under this same `PGTZ` — correctly caught 5 shifted timestamps — before
being proven GREEN and pushed. **Observed green in real CI**, run
https://github.com/devvtrivedi/ledgex-adu/actions/runs/32920032417 (`f344a59` → `2966084`,
all 4 `db.yml` jobs green including this new one). This workflow change needed another push
to be observed — Option A means only the branch's own pushes fire CI, and this one did,
immediately, same as every other push this session.

**(e) Static check for bare `::timestamptz` literals — done**, `build/check_timestamptz_literals.py`
(commit `5e6bee7`), modelled directly on `build/check_jurisdiction_names.py`'s own shape:
same `GRANDFATHERED` exact-site mechanism (the two known 0023/0056 sites) with its own
staleness self-check, wired into `make check-boundary`. Proven RED on a planted violation
(reverted, file confirmed byte-identical to before via `diff`), GREEN against the real tree
(59 files, only the 3 grandfathered sites, all `OK`), and the staleness self-check proven to
fire on a deliberately-wrong `GRANDFATHERED` entry. Two real false positives found and fixed
while proving this against the real tree, not assumed clean: a `--` comment line quoting the
old bare-literal pattern in prose, and `-infinity`/`infinity` (Postgres's own
timezone-independent sentinel values, not dates at all).

## 6. What P61 inherits

- **`db.yml` and `docs.yml` are both CI green**, verified live, not assumed — the branch's own
  workflow definitions have now actually run, repeatedly, not merely been read. Any future push
  to `p59-defect-clearance` (or a merge to `main`, still requiring its own review) fires both.
- **The credential is rotated and dead** (NXDOMAIN, ruled out as a local DNS issue first).
  `.env` is local-dev-only, matching `.env.example`. Nothing about local development changed in
  practice — `refuse_remote`/`_is_local` still correctly allow local URLs, `get_db()` still
  connects.
- **The timezone class is closed as a *class*, not just its three known instances.** A bare
  `::timestamptz` literal anywhere in `db/seeds/` or `db/migrations/` now fails `make
  check-boundary` (and CI's own `docs.yml` `qa` job, which runs that target) unless explicitly
  grandfathered — a fourth instance cannot land silently the way C7/AD1/day4 all once did.
  A dedicated non-UTC CI leg proves the seeding path specifically, on every push, going forward.
- **Two landed migrations (0023, 0056) carry a permanently-recorded, now-closed-as-correct
  functional defect** — `db/README.md`'s new section is the pointer, forever (append-only,
  same as B9), even though this pass found nothing to remediate on the one database checked.
- **An observation, not a defect, for whoever next reaches for
  `postgresql://localhost/ledgex_schema_check` on this machine**: it is a separate, near-empty
  Homebrew Postgres database, not the docker container's real 225,077-parcel one — see section
  4's own paragraph.
- **A named, out-of-scope risk**: `test_refresh_failure_invariant.py`/`test_zoning_ambiguity_
  invariant.py`/`test_apn_canonicalization_invariant.py`'s own `seed_reference_rows()` share
  `test_snapshot_race_invariant.py`'s pre-fix gap (an `INSERT INTO source` with no
  `expected_fields`) — harmless today only because each runs after `day4_sources.sql` in every
  job that wires it in; a future reordering could reproduce defect #4 exactly.
- **Pending the pause-point check-in in this pass's own final response**: whether P60-4(b)'s
  "nothing to remediate on `ledgex_schema_check`" finding is accepted as closing that item, or
  whether the owner wants other databases/environments checked too before it's called done.
