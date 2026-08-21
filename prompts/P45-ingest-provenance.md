# P45 — ingest provenance

Baseline: `main` at `e6cdf64` (P44's merge tip). Branch: `p45-ingest-provenance`,
cut from that commit. `main` was not touched — the decision to merge stays with
the dispatching session, per CONVENTIONS.

Commits on this branch: `c6a782d` (Fix 1-3, the source fix), `ae66c38` (the two
acceptance runners, a necessary consequence of Fix 3), `f1e675b`
(`scripts/audit_snapshot_provenance.py`), plus this close-out commit.

## 0. Decisions, reported before writing

**(a) Branch name.** `p45-ingest-provenance` — matches this package's own
title, no abbreviation needed.

**(b) What `phase_d` should take as input.** Required, explicit
`--snapshot-id`, matching `phase_e`'s own existing precedent exactly — no
default "newest" guess, verified or otherwise. Argument: `phase_d` and
`phase_e` both write permanent fact rows from the same kind of source file;
`phase_e`'s own docstring already states the reasoning this package needed —
"the loader is bound to the supplied `snapshot_id`... and refuses if those
bytes do not match `content_hash`." There is no principled reason for `phase_d`
to carry weaker discipline than the function sitting right next to it in the
same file, doing the same kind of thing. A "verify a guess, but still let the
guess through if it happens to check out" middle ground was considered and
rejected: it would still leave a caller free to omit `--snapshot-id` on any
run where the newest snapshot's bytes happened to be genuinely fresh, silently
reintroducing the guess on every run where nothing had gone wrong yet — the
exact condition under which nobody would notice until the one run where it
mattered.

**(c) The zoning/permits duplication question.**
`ingest_zoning_permits.py` has no `verified_snapshot_file`/`parse_s3_uri`
equivalent. Three options: (i) duplicate the two functions into
`ingest_zoning_permits.py`, unchanged in shape; (ii) extract them into a new
shared module both files import; (iii) parameterize `ingest_parcels.py`'s own
copies to accept a `source_id` and import them from there. Decided (i),
copy — not (ii) or (iii). `ingest_zoning_permits.py`'s own module docstring
already states this codebase's deliberate policy for exactly this situation:
cross-file plumbing is copied, not shared, until `core/connectors` exists to
hold it for real; a new shared module today would be a second, informal
version of that future module, built without the design work that should
attend it. `verified_snapshot_file` was copied with one real difference
(parameterized by `source_id`, since this file serves two sources, not one)
and `parse_s3_uri` copied unchanged.

**(d) The digest-mismatch policy.** Before Fix 1/3, an undetected mismatch
between two fetches' content could feed straight into a load with no signal at
all — a real, dangerous, silent condition. After the fix, `phase_d`/
`phase_zoning_load`/`phase_permits_load` all require an explicit
`--snapshot-id` and independently verify it against the object store, so a
mismatch between two fetches can no longer feed a load by accident — the two
snapshots sit in the database, independently correct under their own hashes,
and a later load must name exactly one of them. Given that, a digest mismatch
between two fetches is informative (the source genuinely changed between two
requests seconds apart — worth a human's attention) rather than dangerous.
Decided: loud, non-fatal. `phase_b` (both files) prints a `!`-bordered warning
block naming both snapshot ids when `digest1 != digest2`, but does not raise
or change the phase's exit code for that reason alone. Fix 2's own non-2xx
failure is a separate, fatal condition — the two are independent signals,
not the same check.

## 1. Fix 1 — `ingest_parcels.py` `phase_d`

Before (as `main` had it — see RED 1 below, run directly against the
unmodified code): `phase_d()` took no argument, read bytes from a **fixed**
local path (`SCRATCHPAD/parcels_fetch_1.geojson`) regardless of which fetch
that file actually held, and separately queried
`SELECT id, content_hash FROM snapshot WHERE source_id = %s ORDER BY
fetched_at DESC LIMIT 1` to pick a snapshot id to cite in every fact row it
wrote — `content_hash` was read and never used to check anything. Two
completely independent choices, silently correct only when the two happen to
agree.

After (`scripts/ingest_parcels.py:833`, `phase_d(snapshot_id)`): `--phase d`
now requires `--snapshot-id`. `verified_snapshot_file(conn, snapshot_id)`
(`scripts/ingest_parcels.py:128`, pre-existing — previously only called by
`phase_e`) reads the bytes FROM `snapshot.object_uri`, hashes them
incrementally, and raises `RuntimeError` naming both hashes if `content_hash`
or `byte_size` don't match, before `phase_d` ever touches the bytes.

## 2. Fix 2 — `run_one_fetch` / `phase_b`, both files

Before: `run_one_fetch` computed `ok = 200 <= http_status < 300`, used it only
to decide `job_run.status` (`'failed'` vs `'succeeded'`/`'skipped_unchanged'`),
then returned `(digest, sid)` — `ok` was discarded. `phase_b` never learned
whether either fetch had failed and always returned normally.

After (`scripts/ingest_parcels.py:382,444`;
`scripts/ingest_zoning_permits.py:416,464`): `run_one_fetch` returns
`(digest, sid, http_status, ok)`. C7 is unchanged — the snapshot row is
written unconditionally, before `ok` is ever inspected, exactly as before.
`phase_b` captures both fetches' `ok`/`http_status`, prints them, prints the
digest-mismatch warning from decision (d) above if applicable, closes the
connection, and only then — `conn.close()` happens BEFORE the check, so both
snapshot rows are durably committed no matter what happens next — raises
`SystemExit` if either fetch was non-2xx, naming both fetches' http_status
and pointing at the job_run rows above for detail. One failed fetch out of
two fails the whole phase.

## 3. Fix 3 — `ingest_zoning_permits.py` load paths

Identical shape to Fix 1, in `latest_snapshot()` (removed) /
`phase_zoning_load()` / `phase_permits_load()`: a fixed local path
(`zoning_districts_fetch_1.geojson` / `permits_fetch_1.csv`) paired with
whichever snapshot row `latest_snapshot` guessed was newest by `fetched_at`,
with no verification at all — not even a `content_hash` comparison, since
`latest_snapshot` never read the object store in the first place.

After (`scripts/ingest_zoning_permits.py:513,907,1163`):
`verified_snapshot_file(conn, snapshot_id, source_id)` (copied from
`ingest_parcels.py`, decision (c) above) does the same read-hash-compare
`ingest_parcels.py`'s own copy does. `phase_zoning_load(snapshot_id)` and
`phase_permits_load(snapshot_id)` both require it; `--phase load` now
requires `--snapshot-id` for both `--source zoning` and `--source permits`.

## 4. A caught regression: the two acceptance runners

`run_p5_acceptance.sh` and `run_phaseb_acceptance.sh` — both wired into
`db.yml`, push/PR-gated — called `ingest_zoning_permits.py --source {zoning,
permits} --phase load` with no `--snapshot-id`, relying on exactly the
`latest_snapshot()` guess Fix 3 removes. Left as committed, the very first
`--phase load` call in either script would have raised the new
`SystemExit("--phase load requires --snapshot-id...")` and failed CI the
moment Fix 1-3 landed — not a hypothetical, confirmed by tracing every call
site (`grep -n "phase load" scripts/run_p5_acceptance.sh
scripts/run_phaseb_acceptance.sh`) before this branch's second commit.

Fixed in `ae66c38`, as a necessary consequence of Fix 3 rather than a new
decision:
- `_p5_setup.py` already printed all five ids it computes (parcels, zoning A/B,
  permits A/B); `run_p5_acceptance.sh` already captured them into
  `ZONING_A_SID`/`ZONING_B_SID`/`PERMITS_A_SID`/`PERMITS_B_SID` but never used
  them — every one of its six `--phase load` call sites now passes
  `--snapshot-id` naming whichever fixture (A or B) is active at that point.
- `_phaseb_setup.py` computed a zoning and a permits snapshot id but only ever
  printed `"<A> <B>"` (parcels only) — it now prints all four, and
  `run_phaseb_acceptance.sh` reads and passes `$ZONING_SID`/`$PERMITS_SID` to
  its two `--phase load` calls.

Both scripts pass end to end after the fix — see section 6.

## 5. RED / GREEN evidence

All evidence below was gathered against local, throwaway Postgres databases
(`ledgex_p45_*`, created and dropped in this session) and the pre-existing
local scratch object store bucket, `ledgex-acceptance-scratch` — never the
real, Object-Locked bucket (`ledgex-snapshots-locked`) and never a live county
endpoint. `LEDGEX_ALLOW_REMOTE_DB` was never set; the one place a non-local
`DATABASE_URL` was used, it was to prove the refusal itself (section 5.4),
never to actually connect.

**On break/revert mechanics:** every "before" run below was gathered by
`git stash`-ing this branch's own Fix 1-3 commit's changes (restoring
`main`'s already-existing, unfixed code in the working tree), running the
before case, then `git stash pop` to restore the fix — never by committing a
broken version of the code. `main`'s tip already carries this package's bug;
nothing in this evidence gathering ever created a new broken commit that
needed a revert. CONVENTIONS' break/revert discipline governs a commit that
is itself the deliberate break; there is no such commit here to misapply it
to.

### 5.1 RED 1 — Fix 1, `phase_d`'s mis-attribution

Fixture: two `snapshot` rows for `ca_san_jose.parcels`. OLDER
(`...3e21b61f...`, `fetched_at`=10:00) genuinely matches a real, uploaded
21-feature GeoJSON file's bytes (`fileA`). NEWER (`...6edb56b4...`,
`fetched_at`=10:05) declares a *different* file's hash (`fileB`, a small,
unrelated GeoJSON) as its `content_hash`, but its `object_uri` points at the
exact same real object as OLDER — a corrupted row, by construction. `fileA`
was also placed on local disk at `SCRATCHPAD/parcels_fetch_1.geojson`.

**Prediction (before fix):** `phase_d()` picks NEWER by
`ORDER BY fetched_at DESC LIMIT 1`, prints
`using snapshot: ...6edb56b4...`, loads the local file (`fileA`'s real
content) successfully, and every fact row it writes cites the NEWER snapshot
id — despite the loaded bytes only matching OLDER. Exit 0.

**Observed**, running the unmodified (stashed) code:
```
using snapshot: ca_san_jose.parcels:sha256:6edb56b4b44ba96878ac27c4d815955d4923b001a46e2f32c636e69f88602d2b
...
=== PHASE D.3: inserting facts for 20 parcels ===
  inserted 40 fact rows (20 parcels x 2 fields)
...
EXIT CODE: 0
```
Query of one written fact row proves the mis-attribution directly:
`fact.snapshot_id = '...6edb56b4...'` (NEWER) but
`snapshot_object_uri = 's3://ledgex-acceptance-scratch/sha256/3e/3e21b61f...'`
— NEWER's own declared hash (`6edb56b4...`) does not match the real bytes
sitting at its own `object_uri` (`3e21b61f...`). Matches the prediction
exactly.

**Prediction (after fix):**
- `--phase d` with no `--snapshot-id` refuses before doing anything. Exit 1.
- `--phase d --snapshot-id <NEWER>` (the corrupted row) refuses inside
  `verified_snapshot_file`, naming both hashes. Exit 1.
- `--phase d --snapshot-id <OLDER>` (genuinely verified) succeeds, and the
  written facts correctly cite OLDER.

**Observed**, all three, against a fresh database with the fix restored:
```
=== sub-test A ===
--phase d requires --snapshot-id; loads must bind to an immutable snapshot row
EXIT CODE: 1

=== sub-test B (NEWER) ===
RuntimeError: snapshot byte hash mismatch for ca_san_jose.parcels:sha256:6edb56b4...:
object_uri bytes sha256=3e21b61f..., snapshot.content_hash=6edb56b4...
EXIT CODE: 1

=== sub-test C (OLDER) ===
using verified snapshot: ca_san_jose.parcels:sha256:3e21b61f...
...
  inserted 40 fact rows (20 parcels x 2 fields)
EXIT CODE: 0
```
The queried fact row after sub-test C cites `snapshot_id = '...3e21b61f...'`
with `snapshot_object_uri` pointing at the SAME hash's key — genuinely
consistent, not merely unflagged. Matches every prediction exactly.

### 5.2 RED 2 — Fix 2, a non-2xx fetch exits 0 pre-fix

A local HTTP server under this session's own control (never a live county
endpoint) returns 500 on its first request and 200 (with distinct real
content) on every request after. `phase_b()` was run via a small driver
script that imports `ingest_parcels` and overrides its `ENDPOINT_URL` module
global to point at `http://127.0.0.1:8765/` before calling `phase_b()` — no
CLI flag was added to the real script for this test-only redirect.

**Prediction (before fix):** FETCH 1 (500) records a snapshot with
`http_status=500` and `job_run.status='failed'`; FETCH 2 (200) records a
snapshot and `job_run.status='succeeded'`. `phase_b()` prints its summary and
returns normally. Exit 0, despite a `failed` job_run sitting in the database.

**Observed:**
```
job_run 5e8cf456... -> failed
job_run 12f465ad... -> succeeded
=== PHASE B SUMMARY ===
...
EXIT CODE: 0
```
Query, same database:
```
 status    | snapshot_id
 failed    | ...8722a4b3... (http_status=500)
 succeeded | ...f841a31d... (http_status=200)
```
Both snapshots are present (C7 held even pre-fix — this was never the C7 bug)
but the phase exited clean regardless.

**Prediction (after fix):** identical recording (C7 unaffected — proven by
the same query, not assumed), plus the digest-mismatch warning (the two
fetches' content genuinely differs), then `SystemExit` naming both statuses.
Exit 1.

**Observed:**
```
job_run ff75d89c... -> failed
job_run e3a7f7ec... -> succeeded
...
!!! SOURCE CHANGED BETWEEN FETCHES ...
phase b: at least one fetch was non-2xx (fetch 1 http_status=500, fetch 2 http_status=200) -- both snapshots are recorded (C7), but a phase that half-worked is not a phase that worked.
EXIT CODE: 1
```
Query, same database, run AFTER the non-zero exit:
```
 id            | http_status | byte_size
 ...8722a4b3... |         500 |        41
 ...f841a31d... |         200 |        59
```
Both snapshots present, both halves shown as required: C7 intact, phase
failed loudly. Matches every prediction exactly.

### 5.3 RED 3 — Fix 3, zoning path, same shape as RED 1

Identical construction to RED 1 (OLDER genuinely matches its own real object;
NEWER declares a different file's hash while pointing at OLDER's real
bytes), this time for `ca_san_jose.zoning_districts`
(`...672906fb...`/`...874872bc...`).

**Before**, unmodified code:
```
using snapshot: ca_san_jose.zoning_districts:sha256:874872bc...
  job_run started: 44b4622e...
  parsed 1 zoning features in 0.0s
  ...
job_run 44b4622e... -> succeeded (rows_in=0, rows_out=0)
EXIT CODE: 0
```
(Zero parcels existed in this fresh fixture database, so the spatial join and
every downstream count are legitimately zero — the load completes as a
no-op; the defect being demonstrated is entirely in which snapshot id gets
printed and would be cited, which happens before any of that join logic
runs.) NEWER (`874872bc...`) is what gets used, exactly the divergence shape
from RED 1, now in the second file.

**After:**
```
=== sub-test A (no --snapshot-id) ===
--phase load requires --snapshot-id; loads must bind to an immutable snapshot row
EXIT CODE: 1

=== sub-test B (NEWER, corrupted) ===
RuntimeError: snapshot byte hash mismatch for ca_san_jose.zoning_districts:sha256:874872bc...:
object_uri bytes sha256=672906fb..., snapshot.content_hash=874872bc...
EXIT CODE: 1

=== sub-test C (OLDER, genuine) ===
using verified snapshot: ca_san_jose.zoning_districts:sha256:672906fb...
...
job_run 5fc6927b... -> succeeded (rows_in=0, rows_out=0)
EXIT CODE: 0
```
Matches every prediction exactly.

### 5.4 RED 4 — the audit itself

Fixture database: three genuinely clean snapshot rows (one per real source —
parcels, zoning, permits — each matching its own real uploaded object,
`http_status=200`), plus exactly one deliberately corrupted snapshot (parcels
source, declaring `fileB`'s hash while `object_uri` points at `fileA`'s real
bytes — same shape as RED 1/3's planted divergence), plus one real parcel and
one real fact row citing the corrupted snapshot.

**Prediction:** 4 snapshots audited, 3 clean, exactly 1 flagged (byte
mismatch), 0 flagged by `http_status` (all four are 2xx), the flagged one
named exactly, exactly 1 fact row found citing it, naming the real parcel.

**Observed:**
```
snapshot rows found: 4
  MISMATCH    ca_san_jose.parcels:sha256:6edb56b4...  content_hash mismatch (row=6edb56b4..., observed=3e21b61f...)
  3 of 4 snapshots: bytes at object_uri match content_hash AND byte_size
  1 of 4 snapshots: flagged (mismatch or unreadable)
  0 of 4 snapshots: http_status was not 2xx
  direct query -- snapshots with a recorded 2xx http_status: 4 of 4
--- flagged snapshots ...: 1 ---
  ca_san_jose.parcels:sha256:6edb56b4...
--- facts citing a flagged snapshot ---
  ca_san_jose.parcels:sha256:6edb56b4...: 1 fact row(s)
    fact_id=ba75130f-...  field_key=parcel.apn  parcel_id=11111111-...  jurisdiction_id=ca_san_jose  apn=P45RED4-BAD-CITED
=== SUMMARY ===
snapshots audited:                          4
snapshots with clean bytes (hash+size match): 3
snapshots flagged (byte mismatch/unreadable): 1
snapshots flagged (non-2xx/missing status):   0
snapshots flagged (union of the two above):   1
fact rows citing a flagged snapshot:          1
distinct parcels among those fact rows:       1
fact rows with snapshot_id IS NULL (separate question, not flagged): 0
EXIT CODE: 0
```
Found exactly the one planted-bad snapshot, no false positives among the
three clean ones. Matches the prediction exactly.

Two more checks on the audit itself: run against a fresh migrations-only
database (0 snapshot rows) prints `No snapshot rows in this database.
Nothing to audit.` and exits 0, no error. Pointed at a non-local
`DATABASE_URL` (a fabricated hostname, never actually reachable — the guard
fires at the string-parsing level, before any connection attempt),
`infra.env.get_db()`'s existing guard refuses with its own standard message
and exit 1 — no second guard was written for this script.

## 6. Full suite runs

Per CONVENTIONS: every suite that models a one-time A→B(→A) transition run
twice, each against its own independent fresh database, plus once against a
fresh migrations-only database with no seed. `make migrate` was used to build
every database below; none were reused across runs.

**`run_p5_acceptance.sh`** (zoning/permits, A→B→A, self-contained — inserts
its own reference rows and snapshots): three independent runs
(`ledgex_p45_p5accept_run1`, `_run2`, `_migonly` — the last one migrations-only,
no `db/seeds/`), all exit 0, all print `P5 ACCEPTANCE: ALL CHECKPOINTS PASSED`,
123 `[PASS]` / 0 `[FAIL]` each run.

**`run_phaseb_acceptance.sh`** (parcels A→B→A plus zoning/permits seed):
three independent runs (`ledgex_p45_phaseb_run1`, `_run2`, `_migonly`), all
exit 0, 57 `[PASS]` / 0 `[FAIL]` each run.

Both suites exercise exactly the call paths this package changed
(`phase_e --snapshot-id`, `--source {zoning,permits} --phase load
--snapshot-id`) and both were RED before commit `ae66c38` (section 4) — the
`SystemExit` the new required argument raises, hit on the very first
`--phase load` call in either script, confirmed by re-reading the traceback
before fixing it, not merely predicted.

**Other gates**, once each (idempotent under a same-database rerun, or not
modeling a state transition — CONVENTIONS' own stated exemption):
- `make db-test` (`db/tests/invariants.sql`): exit 0.
- `make test` (`pytest tests/core/`): 168 passed, exit 0.
- `make conformance`: `CONFORMANCE SUMMARY: PASSED (0 failure(s))`, exit 0.
- `make golden`: refused by its own pre-existing `GOLDEN_ALLOW_RULE_SEED` gate
  (a permanent-write guard, unrelated to this package — `check_golden.py`
  calls none of the functions this package touched). Not re-run with the seed
  flag set: golden fixture correctness is out of this package's scope and
  planting a permanent rule row is not warranted just to exercise it.

## 7. The audit's finding, and whether it warrants a follow-up

The audit was run only against fixture/throwaway databases constructed for
this package's own evidence (section 5.4) — it was NOT run against any
database carrying real, previously-ingested production data (no such
database exists locally in a state safe to point this script at without a
separate, deliberate decision about which one and why). Its one real finding
in this package is therefore RED 4's own planted defect, found correctly and
exclusively.

**Reporting, not deciding, whether a follow-up is warranted:** this package's
own two Highs (Fix 1, Fix 3) describe a defect class — silent mis-attribution
between a loaded file's real bytes and the snapshot id a load cites — that
existed on `main` since these ingest scripts were first written, for every
`phase_d`/`phase_zoning_load`/`phase_permits_load` run before this branch.
Every fact row `main`'s history has ever written through those paths was
written under the OLD, unverified logic. This package's own SAFETY boundary
(no fact row inserted/updated/deleted, no live database queried) means
whether any REAL fact in a REAL database was ever actually mis-attributed
this way is, as of this report, unmeasured — not ruled out, not confirmed.
A follow-up package running `scripts/audit_snapshot_provenance.py` (already
built, already proven correct against a known-bad fixture) against the real
local dev database(s) this project already has, and reporting whatever it
finds, would answer that question directly. That follow-up is scoped
narrowly to running the audit and reporting — remediation, if the audit
finds anything, is explicitly its own decision and its own package, per this
one's own boundaries.

## Review findings

(none yet — filled in by review)
