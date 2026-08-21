## P43 — land the viewer tree, then gate it

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)), with one explicit, narrow
override stated by the prompt itself: commit/push authority to `audit-fixes` only, never
`main`. Prompt as issued: `LEDGEX-P43-LAND-AND-GATE-THE-VIEWER.txt` plus its resume,
`LEDGEX-P43-RESUME.txt` (repo root, both unmodified — neither committed, see §5).

**Read first, per CLAUDE.md:** `docs/LEDGEX_SPEC.md` §1 in full (§1.1, §1.2 especially), §6.1–6.7
— all already read in full this session; re-confirmed against §1.2's exact table (below)
rather than recalled, since the spec question turns on its precise wording.

---

### 0. Precondition, verified fresh both times this package ran (not transcribed)

Before Task A/B this session, and again independently before Task B's own push, both queried
directly via `gh run list --json ... -q`, not read from any earlier report:

```
db.yml   run 32314117415  conclusion: success  headSha: c52a266f871aad95a57a86f2ecdd3e2236a162d6
docs.yml run 32314117407  conclusion: success  headSha: c52a266f871aad95a57a86f2ecdd3e2236a162d6
```

`https://github.com/devvtrivedi/ledgex-adu/actions/runs/32314117415` and `.../32314117407`.
Both match baseline `c52a266` exactly (full SHA compared, not the short form). Precondition
held both times; work proceeded.

---

### 1. STEP 0 — the three decisions, as reasoned and ratified by the dispatching session

Recorded here, not re-litigated, per the resume prompt's own instruction.

**D1 — commit split: ONE commit for the whole P39–P42 chain.** P41 and P42 both edit files
P40 created (`api/main.py`, `api/static/viewer.html`,
`scripts/seed_internal_test_licences.py`), so a per-package split is a per-hunk split, not a
per-file one — and reconstructing hunk-level authorship after the fact, for work that was
never checkpointed between packages as it was actually written, is itself a form of
invention. One commit, message naming all four packages and pointing at each package's own
report, is the honest representation of how this tree came to exist.

**D2 — CI slot: `db.yml`'s `schema` job, after `scripts/test_compose_parcel_refusals.py`
(then lines 240–241), before `make test` (then lines 251–252).** That window sits strictly
after the migrations-only work (`make db-test`, `test_snapshot_race_invariant.py` — both
must stay genuinely migrations-only, confirmed by reading their own preconditions) and
alongside the other seed-dependent script suites this job already runs in that same stretch
(`day4_sources.sql` before `make golden`, the three `test_compose_*.py` scripts) — the
existing precedent for where a seed-dependent step belongs, not an invented new shape.

**D3 — no spec bump, no §12 row.** §1.2's table, re-read verbatim this session:

> ### 1.2 Seven make targets
> | Target | ... |
> | **make check-boundary** | ... | **make schema** | ... | **make schema-dump** | ... |
> **make conformance** | ... | **make test** | ... | **make golden** | ... | **make liveness** | ... |

Seven named targets, no more. `make db-test` — real, push-gated, running in `db.yml` since
P6/P18 — has never been one of them, and no package that added or extended it bumped the
spec for that reason. `db/seeds/day4_sources.sql`, `test_snapshot_race_invariant.py`, and
now `scripts/seed_internal_test_licences.py` are the same shape: real CI-wired checks §1.2
does not enumerate. `make viewer-test` follows that exact, already-established precedent.
This package changes no schema, adds no invariant, no refusal code, no endpoint contract, and
changes no behavior the spec describes — no bump, no §12 row. A no-bump decision that leaves
no trace is indistinguishable from nobody having asked, so it is written down here rather
than skipped silently.

---

### 2. TASK A — local GREEN, then RED (a), before any git operation

Predicted before each run.

```
$ SEED_INTERNAL_TEST_LICENCES=1 python3 scripts/seed_internal_test_licences.py   # predicted: exit 0
... 17 rows, all "wrote" (fresh database) ...
seed exit: 0

$ make viewer-test PYTHON=python3   # predicted: exit 0, 5/5 PASS
[PASS] facts[] is non-empty (the seed's own permitted rows)
[PASS] omitted_for_rights[] is non-empty (P42's own blocked fixture)
[PASS] the blocked entry cites the REAL cc_by_4_0 licence
[PASS] no permitted fact carries the real cc_by_4_0 licence
[PASS] blocked sentinel value does not appear anywhere in the serialized response
All assertions passed
exit: 0
```

**RED (a).** `api/main.py`'s `get_parcel_facts`, one line inverted:

```
-        if allowed_by_licence.get(licence_id, False):
+        if not allowed_by_licence.get(licence_id, False):
             permitted.append(row)
```

Predicted: the blocked fixture's sentinel lands in `facts`, the two permitted `internal_test`
facts land in `omitted_for_rights`; 3 of 5 assertions fail (the two that check *which* list a
specific licence_id landed in, plus the sentinel-leak check itself); the two bare
non-emptiness checks still pass, since inversion doesn't empty either list, just swaps their
contents. Run:

```
[PASS] facts[] is non-empty (the seed's own permitted rows)
[PASS] omitted_for_rights[] is non-empty (P42's own blocked fixture)
[FAIL] the blocked entry cites the REAL cc_by_4_0 licence -- got [...internal_test.cc0, internal_test.cc_by_4_0...]
[FAIL] no permitted fact carries the real cc_by_4_0 licence -- got [{'licence_id': 'cc_by_4_0', 'value': 'BLOCKED FIXTURE VALUE - MUST NOT RENDER', ...}]
[FAIL] blocked sentinel value does not appear anywhere in the serialized response -- LEAK: 'BLOCKED FIXTURE VALUE - MUST NOT RENDER' found in serialized response body
3 failure(s)
exit: 2 (make's own wrapping of the script's exit 1)
```

Predicted exactly. This is the proof that matters: the assertion is load-bearing, not merely
green by construction.

**Revert, verified by grep, not eyeballed:**

```
$ grep -n "not allowed_by_licence.get" api/main.py
(no output, exit 1)
$ grep -n "if allowed_by_licence.get(licence_id, False):" api/main.py
389:        if allowed_by_licence.get(licence_id, False):
$ make viewer-test PYTHON=python3   # green again
All assertions passed
exit: 0
```

**Hard gate before Task B**, full-tree check: `grep -rn "RED (a) probe\|not allowed_by_licence" . --include="*.py"` returned exactly one match — `scripts/compose_property_file.py:322`'s own, pre-existing, *correct* `blocked_by_licence` computation inside `evaluate_rights_gate` (computing the blocked set is supposed to use `not allowed`; this line has been there since P40 and is unrelated to the probe, which only ever touched `api/main.py`). Confirmed by reading it directly: it is the real, intended `evaluate_rights_gate` logic, not a break fragment. `api/main.py`'s own line 389 confirmed at the exact original text. No fragment of the deliberate break survived anywhere.

---

### 3. TASK B — landing the chain

**Branch state, checked before touching it:**

```
main            = c52a266f871aad95a57a86f2ecdd3e2236a162d6
audit-fixes     = 25cc71e511375a93512012f1fac529e8e4023bfa   (local)
origin/audit-fixes = 3af0f8a12515e3f505598285677115fb5e2c2ed8

git log --oneline main..audit-fixes         -> (empty)
git log --oneline audit-fixes..main         -> 191 commits (the entire history since 25cc71e)
git merge-base audit-fixes main             -> 25cc71e511375a93512012f1fac529e8e4023bfa
  (equals audit-fixes's own hash -- audit-fixes IS a pure ancestor of main)

git log --oneline origin/audit-fixes..audit-fixes -> 25cc71e ("Fix: complete Makefile, ...")
git log --oneline audit-fixes..origin/audit-fixes -> (empty)
```

`audit-fixes` had **not** diverged from `main` in the sense the prompt's stop condition
names — it carried zero commits `main` does not have (`main..audit-fixes` empty), confirmed
by `merge-base` equality, not just the empty log. The one local/origin hash difference was a
single, already-superseded local commit (25cc71e) that is itself an ancestor of `main` — its
content already fully exists in `main`'s history. Not a divergence to reconcile; a stale
branch pointer sitting behind `main` with nothing unique on it. Moving it forward loses
nothing.

Action taken, reported rather than silent: `git checkout -B audit-fixes` — repoints the
*local* `audit-fixes` ref to the current commit (`c52a266`, same as `main`) while leaving the
working tree, index and every uncommitted change completely untouched (a new/repointed
branch at your current HEAD never touches files; this is not the same operation as checking
out a *different*, divergent branch, which the prompt correctly flags as dangerous with
uncommitted changes in play, and which was not done here).

**HAZARD 1 — staged explicitly, no `git add -A`.** `.env` confirmed gitignored fresh
(`git check-ignore -v .env` → `.gitignore:1:.env`) before anything else. Committed:

```
.importlinter  Makefile  infra/env.py  prompts/README.md  requirements.txt
scripts/compose_property_file.py  api/  prompts/P39-...md  P40-...md  P41-...md  P42-...md
scripts/seed_internal_test_licences.py  scripts/test_viewer_rights_gate.py
```

Deliberately **excluded**, and why: `LEDGEX-P41-P42-FIX-PROMPTS.txt`,
`LEDGEX-P43-LAND-AND-GATE-THE-VIEWER.txt`, `LEDGEX-P43-RESUME.txt`,
`LEDGEX-VIBE-CODE-PROMPTS.txt`, `PROMPT-P39-compose-transaction-and-db-binding.txt`,
`PROMPT-P40-internal-viewer.txt` — dispatch/authoring artifacts (paste-ready prompt bundles
and their frozen single-prompt copies), never treated as commit candidates by any package in
this chain; each package's own report already cites them as "repo root, unmodified"
*reference*, not as something meant to enter the repository. `LEDGEX_REVIEW_2026-08-20.md` —
a pre-existing third-party audit document, source material that motivated this chain, not a
package deliverable. `prompts/P40-section0-decisions.md` — a precursor draft of P40's own
§0, fully superseded by and folded into `prompts/P40-internal-viewer.md`; keeping both would
leave two files claiming to be "P40 section 0." `.import_linter_cache/`, `.pytest_cache/` —
each self-ignores via its own tool-generated `.gitignore` (`git status --ignored` confirms
`!!` on both; neither is named in the repo's own root `.gitignore`, which doesn't need to
name them). `.venv-ingest-scratch/` — genuinely empty (`find -mindepth 1` returns nothing);
git does not track empty directories at all, so there was never a decision to make here.

Diff scanned for secrets before committing (`git diff --cached | grep -iE
"password|secret|token|..."`, then a tighter pass for connection-string/hostname shapes) —
clean; the only hits were prose describing *that* `.env` names a remote database, never the
value itself.

**Committed:** `7a99bd4` — *"Land P39-P42: compose() transaction fix, infra.env remote-DB
guard, internal viewer, seed script, review fixes"* (15 files, 3327 insertions, 26 deletions;
full per-package breakdown in the commit body). Verified against the actual committed
content, not just the file list (`git show HEAD:api/main.py`, `git show
HEAD:scripts/test_viewer_rights_gate.py`) — both present and correct.

**Pushed** (`git push origin audit-fixes`) — fast-forward, no force (origin/audit-fixes was
an ancestor of the new tip). Predicted before pushing: this is the first time CI has ever
compiled `api/`, so a specific, checkable risk was worth confirming ahead of time rather than
finding out from a red run:

- `Literal[*KNOWN_EXCEPTION_OUTCOMES]` (P41) needs PEP 646 star-unpacking, landed in Python
  3.11; `db.yml` pins `'3.11'` in all three jobs. Verified against **real interpreters**,
  installed locally for exactly this check (not theorized): `python3.10 -m py_compile
  api/main.py` → `SyntaxError: invalid syntax` at that exact line; `python3.11 -m py_compile
  api/main.py` → clean. Both confirmed, not assumed from PEP version history alone.
- `requirements.txt` (fastapi, uvicorn, pydantic) vs. `scripts/requirements.txt`
  (psycopg2, dotenv): the `schema` job installs `-r scripts/requirements.txt -r
  requirements-test.txt`, and `requirements-test.txt` itself does `-r requirements.txt` (read
  directly, not inferred) — so `schema` gets all of it transitively.
  `p5-acceptance`/`phaseb-acceptance` install `requirements.txt` directly. All three CI jobs
  can import `api.main`; confirmed by building a real Python-3.11 venv locally and running
  the *exact* `pip install -r scripts/requirements.txt -r requirements-test.txt` command
  `db.yml` runs, then `import api.main` — succeeded cleanly, `KNOWN_EXCEPTION_OUTCOMES`
  resolved, the module-level `VIEWER_CHANNEL` guard did not fire.

**CI result, job level, both workflows, both steps of `docs.yml` reported separately:**

```
db.yml   run 32432042136  conclusion: success
  schema: success   p5-acceptance: success   phaseb-acceptance: success
docs.yml run 32432042140  conclusion: success
  qa job: success  ->  make qa: success   make check-boundary: success
```

`https://github.com/devvtrivedi/ledgex-adu/actions/runs/32432042136` and `.../32432042140`.
Every prediction held; `api/` compiled and ran clean on the real 3.11 runner the first time
it was ever asked to.

**HAZARD 2 — the two pushes sequenced deliberately, not landed together.** The chain above
was pushed and observed green **alone**, before the `db.yml` wiring was written at all, so a
red result would have had exactly one candidate cause (the newly-compiled `api/` itself), not
two (the chain *and* a new workflow step landing simultaneously). Only after that clean result
was `db.yml` edited.

**D2's slot wired**, `scripts/seed_internal_test_licences.py` (with `SEED_INTERNAL_TEST_LICENCES=1`)
then `make viewer-test`, both confirmed installed dependencies per the check above. The
workflow's own comment states explicitly why the seed's permanent writes are harmless in this
one job and would not be anywhere else: `ledgex_ci` is built from empty at the top of this
exact job and torn down with the runner at the end, so a permanent row in it is only ever
permanent for the length of one job — the same reasoning `GOLDEN_ALLOW_RULE_SEED=1` already
relies on immediately above it in the same job.

Verified locally, end to end, in the *exact* new step order, under **real Python 3.11**, on a
fresh database, before pushing this second commit — 14/14 steps pass.

**Committed** `1ed40da`, **pushed**, **CI result, job level:**

```
db.yml   run 32432275317  conclusion: success
  schema: success (incl. scripts/seed_internal_test_licences.py: success, make viewer-test: success)
  p5-acceptance: success   phaseb-acceptance: success
docs.yml run 32432275348  conclusion: success  (make qa: success, make check-boundary: success)
```

`https://github.com/devvtrivedi/ledgex-adu/actions/runs/32432275317` and `.../32432275348`.

---

### 4. STEP 3 — RED (b): CI actually runs it

The **same** one-line inversion as RED (a), committed **alone** — `git diff --stat` before
staging showed exactly `api/main.py | 2 +-`; nothing else was staged. Commit `b8183ce`,
message: *"DELIBERATE BREAK (P43 CI-gate proof) -- invert the rights-gate split in
api/main.py's get_parcel_facts"*. Pushed.

Predicted: the `schema` job fails at the `make viewer-test` step, same 3 failures as the
local RED (a) transcript, same sentinel-leak text, `make` exit 1 wrapped to process exit 2.

**Real runner, run `32432393292`, job `schema`, step `make viewer-test`, verbatim:**

```
[PASS] facts[] is non-empty (the seed's own permitted rows)
[PASS] omitted_for_rights[] is non-empty (P42's own blocked fixture)
[FAIL] the blocked entry cites the REAL cc_by_4_0 licence -- got [...internal_test.cc0, internal_test.cc_by_4_0...]
[FAIL] no permitted fact carries the real cc_by_4_0 licence -- got [{'licence_id': 'cc_by_4_0', 'value': 'BLOCKED FIXTURE VALUE - MUST NOT RENDER', ...}]
[FAIL] blocked sentinel value does not appear anywhere in the serialized response -- LEAK: 'BLOCKED FIXTURE VALUE - MUST NOT RENDER' found in serialized response body
3 failure(s)
make: *** [Makefile:401: viewer-test] Error 1
##[error]Process completed with exit code 2.
```

Job-level: `{"conclusion":"failure","jobs":[{"name":"schema","conclusion":"failure"},
{"name":"p5-acceptance","conclusion":"success"},{"name":"phaseb-acceptance","conclusion":"success"}]}`
— exactly the one job touched, the other two (which never import `api/`) unaffected, exactly
as expected. Confirmed running real Python 3.11.16 on the runner (`pythonLocation:
/opt/hostedtoolcache/Python/3.11.16/x64`, printed in the step's own env block).

**Red run:** `https://github.com/devvtrivedi/ledgex-adu/actions/runs/32432393292`

**Revert — pure mechanical inverse, `git revert --no-edit b8183ce`:**

```
$ git revert --no-edit b8183ce
[audit-fixes 8d8e4b5] Revert "DELIBERATE BREAK (P43 CI-gate proof) -- ..."
 1 file changed, 1 insertion(+), 1 deletion(-)
$ grep -n "if allowed_by_licence.get" api/main.py
389:        if allowed_by_licence.get(licence_id, False):
```

Nothing else rode along in either the break commit or the revert — no report doc, no unrelated
fix, matching the exact mistake CONVENTIONS records against P30's `9a45566` and naming it as
the thing not to repeat. Pushed.

**CI result, job level:**

```
db.yml   run 32432575596  conclusion: success
  schema: success   p5-acceptance: success   phaseb-acceptance: success
docs.yml run 32432575602  conclusion: success
```

**Green run:** `https://github.com/devvtrivedi/ledgex-adu/actions/runs/32432575596`

---

### 5. Final state

Five commits on `audit-fixes`, on top of `c52a266`, none on `main`:

```
7a99bd4  Land P39-P42: compose() transaction fix, infra.env remote-DB guard, internal viewer, seed script, review fixes
1ed40da  db.yml: wire scripts/seed_internal_test_licences.py + make viewer-test into the schema job (P43)
b8183ce  DELIBERATE BREAK (P43 CI-gate proof) -- invert the rights-gate split in api/main.py's get_parcel_facts
8d8e4b5  Revert "DELIBERATE BREAK (P43 CI-gate proof) -- invert the rights-gate split in api/main.py's get_parcel_facts"
e10220a  P43 close-out: land-the-viewer report, real commit hashes in prompts/README.md
```

`e10220a` (this report plus the `prompts/README.md` hash update) confirmed green on its own
CI run too, job level: `db.yml` run `32432801805` (`schema`/`p5-acceptance`/`phaseb-acceptance`
all `success`), `docs.yml` run `32432801798` (`make qa`/`make check-boundary` both `success`).

`main` is untouched: still exactly `c52a266`, confirmed by never running any command in this
package that could move it (no checkout of `main`, no commit while `main` was checked out —
the very first action of Task B was moving *local* `audit-fixes`, not touching `main`'s own
ref).

Not committed, deliberately, per §3's HAZARD 1: the six `LEDGEX-*.txt`/`PROMPT-P*.txt`
dispatch files (including this package's own two prompt files), `LEDGEX_REVIEW_2026-08-20.md`,
and `prompts/P40-section0-decisions.md`. All still sit in the working tree, untracked, exactly
as before.

`prompts/README.md` updated: the P39–P42 rows now read "landed on `audit-fixes`, not yet
merged to `main`" with hash `7a99bd4`; a new P43 row added with `1ed40da`/`b8183ce`/`8d8e4b5`.

**The next package is finding #45** (the `.importlinter` repair — the stale
`i15-commerce-no-core-store` blacklist plus the layers contract being stricter than §2 — and
the `core/rights.py` extraction it unblocks). Deliberately out of scope here, as it was for
P40 through P42, and still debt rather than risk for exactly as long as
`evaluate_rights_gate` stays the one function both `compose()` and `api/` call — confirmed
true today, unchanged by this package.

---

### Review findings

*(empty — appended after review)*
