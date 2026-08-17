## P12 — The P5 acceptance suite asserts a bug P9 already fixed, and nothing would have caught it

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Report-first: this package
establishes which side of a RED assertion is wrong, and whether the suite that caught it
belongs in CI. It does not edit `check_p5_acceptance.py`. That is the next pass.

Started from `7552690` (P11 landed, pushed; `db.yml` and `docs.yml` both green on the real
runner at that commit — checked via `gh run list`, not a local re-run).

---

### 1. What is actually wrong

#### 1(a) — which side is wrong: the test, not `close_resolved_exceptions`

`scripts/check_p5_acceptance.py`'s `check_zoning_after_b` (currently :103-107) and
`check_zoning_after_a2` (currently :133-135) assert that parcel `23707070` carries BOTH
`no_containing_district` and `multiple_containing_districts` open simultaneously, at both
checkpoints. The comment above the first assertion says this in as many words: "nothing
auto-resolves the now-stale A-era exception when the underlying condition changes...
Both stay open simultaneously; this assertion documents that deliberately."

That comment was true when it was written — during P5, before P8/P9 existed. It is no
longer true. `db/migrations/0047` + `core/exceptions.py`'s `close_resolved_exceptions()`
(P9, `7c88d15`) is exactly the fix for this gap: `load_zoning` now closes any open
exception for the current `(detector_key, detector_version)` whose `(parcel_id, reason)`
is not in the current run's own `still_true_pairs`. P9's own writeup (`prompts/README.md`,
the "P9 — built" paragraph) explicitly names this exact parcel and fixture
(`23707070` in P5's own fixtures) as the case it verified against, both directions, before
shipping.

CONVENTIONS.md's first hard rule — never change a constraint, test, or threshold to make
something pass — makes "the test encodes a since-fixed gap" and "the code changed and the
test just wasn't updated" indistinguishable from the RED output alone. Both look identical:
an assertion written against old, correct-at-the-time behavior, now failing. The only way
to tell them apart is to check whether the NEW behavior is the one that's actually correct
— not assume it from the fact that a migration landed.

**Confirmed against the fixtures and a live run, not assumed from reading the code.**
Traced `23707070` through A1 → B → A2 on a fresh migrations-only database, querying
`parcel_exception` directly after each step:

After A1 (baseline, zero-match under snapshot A):
```
reason                  | outcome | resolved_by | reopened_from_id
no_containing_district  | open    |             |
```

After B (snapshot B makes it ambiguous — 2+ real classifications):
```
reason                          | outcome            | resolved_by                       | reopened_from_id
no_containing_district          | condition_cleared  | zoning_spatial_join_unresolvable  |
multiple_containing_districts   | open               |                                   |
```
The exception `close_resolved_exceptions` closed is `no_containing_district` — the A-era
reason, no longer true this run. The exception it left open is `multiple_containing_districts`
— this run's own actual finding. That is the *correct* pair to close/leave-open, the exact
opposite of what the `after B` assertion requires (both open).

After A2 (revert to snapshot A — zero-match again):
```
id            | reason                          | outcome            | resolved_by                       | reopened_from_id
b0de4549...   | no_containing_district          | condition_cleared  | zoning_spatial_join_unresolvable  |
a85146db...   | multiple_containing_districts   | condition_cleared  | zoning_spatial_join_unresolvable  |
4e28bf68...   | no_containing_district          | open               |                                   | b0de4549...
```
`multiple_containing_districts` (B's finding, no longer true) closes. A fresh
`no_containing_district` row opens — and `reopened_from_id` points at `b0de4549...`, the
*original* A1 exception with that exact reason, not at the B-era row that just closed and
not left `NULL`. `relink_reopened_exceptions()` matches on `(parcel_id, reason)`, not "most
recently closed row for this parcel" — confirmed live, not read off the SQL and trusted.

**Verdict: the code is right, the assertions are stale.** Updating them to assert
`condition_cleared` for whichever reason is no longer true, and `open` for whichever reason
the current run actually found, is the test catching up to a fix that already shipped and
was already verified when it shipped — not a threshold moved to make something pass. The
bug the comment describes (P5 item 5 — nothing auto-resolves a stale exception) is real,
was real, and is now fixed; the assertion just never learned that.

#### 1(b) — why nobody noticed: the suite that would have caught this is not run by anything

P9 (`7c88d15`) is recorded in `prompts/README.md` as "done, pushed," with a thorough
RED-first writeup — including, per its own narrative, reconstructing this exact
`23707070` scenario against pre-P9 code (both exceptions open, confirmed) and post-P9 code
(the stale one closes) as part of proving the fix correct. P9 verified the *mechanism*
directly. What it did not do — because nothing prompted it to — is run
`scripts/run_p5_acceptance.sh`, the standing regression suite for the subsystem it was
changing, end to end. If it had, this exact break would have surfaced at `7c88d15` itself,
not five commits and one full package later.

This is not a P9 process failure in isolation. It is structural: `run_p5_acceptance.sh` and
`check_p5_acceptance.py` are not referenced anywhere in `.github/workflows/db.yml` or
`.github/workflows/docs.yml` — confirmed by grep, zero matches. CONVENTIONS.md's own
standing rule is "every CI workflow must be green before a package starts, verified on the
real runner" for *those two* gates. Both were green, honestly, at every commit between
`7c88d15` and this one. That was never false. It also never said anything about this
suite, because this suite isn't one of the two things being checked. The same failure
shape CONVENTIONS.md already names for `docs.yml` sitting red for a day "because nothing
checked it before any of them started" applies here with one difference that makes it
worse: `docs.yml` was at least eventually checked by *something* and caught. Nothing
checks the P5 acceptance suite at all, ever, unless a session happens to have a live
PostgreSQL + object store and chooses to run it — P11's own audit didn't (no PostgreSQL in
that environment), which is exactly why finding #20 wasn't caught during P11 either; it
surfaced only because this pass's own verification work happened to run the suite for real.

**Should `run_p5_acceptance.sh` be wired into CI? Recommendation: yes, as a third gate —
but sequenced after this package's own fix, and the cost is real, not hidden.**

What it would take:
- **A new service container.** `db.yml`'s `db` job already runs a `postgis/postgis:16-3.4`
  service; the P5 suite additionally needs an S3-compatible object store
  (`OBJECT_STORE_URL`/`ACCESS_KEY`/`SECRET_KEY`, currently `minio` locally). A
  `minio/minio` service container is the direct analogue — needs its own health check
  (`/minio/health/live`, not `pg_isready`) and, unlike the Postgres service, minio does not
  auto-create a bucket: a step equivalent to `db.yml`'s "Create clean database" would need
  to create `ledgex-snapshots-locked` before the suite runs (`mc mb` or a boto3
  `create_bucket` call). `.env`'s own comment notes the real bucket needs Object Lock
  enabled at creation time (COMPLIANCE mode) — worth checking whether the suite's own
  snapshot-insert path depends on lock being enabled or merely uploads bytes; if the
  latter, CI's throwaway bucket doesn't need to replicate that setting to exercise the
  suite correctly, only the real R2 bucket does.
- **A hardcoded local path.** `run_p5_acceptance.sh` and `run_phaseb_acceptance.sh` both
  invoke `.venv-ingest/bin/python3` directly — a virtualenv path that exists on a
  developer's machine but that `db.yml` never creates (it installs
  `scripts/requirements.txt` straight into the runner's system Python via
  `actions/setup-python`). Either the workflow creates a `.venv-ingest` matching that exact
  path, or the two shell scripts stop hardcoding it (e.g. `${PYTHON:-.venv-ingest/bin/python3}`,
  same override pattern the `Makefile` already uses for `PYTHON`/`PSQL`/`PG_DUMP`). This is
  a second concrete adaptation the scripts need, independent of the service-container cost.
- **Sequencing.** Wiring this in before fixing 1(a) would turn `db.yml` red on the first
  push after landing it — a self-inflicted version of the exact failure this finding is
  about. The stale-assertion fix has to land first.
- **Marginal cost once both of the above are done is small.** The fixture set is 25
  parcels, a handful of zoning/permit rows — not the 225K-parcel production scale
  `db.yml`'s other steps never touch. Expect low-single-digit-minutes of added CI time, not
  a meaningfully slower gate.

**If it can't be wired in** (bandwidth, or a reason not visible from here — e.g. a
decision that CI service-container credentials for an object store carry more risk than
the coverage is worth): the weaker alternative is a separate, explicitly-scheduled
workflow (`schedule:` cron, or `workflow_dispatch` run on a cadence) that is not a
PR-blocking gate but still runs automatically rather than depending on a session
incidentally having Postgres available. That is strictly better than the current state —
"nothing ever runs this unless a human happens to" — but it inherits the same class of
risk CONVENTIONS.md already recorded for `docs.yml`'s day-long red window: a scheduled,
non-blocking check can go red and stay red through several packages before anyone reads
its output, because reading it was never a precondition for starting work the way the two
real gates are. Blocking is the only form of this that actually satisfies "every CI
workflow must be green before a package starts, verified on the real runner" — a schedule
satisfies "someone will eventually see it," not that.

`scripts/run_phaseb_acceptance.sh` (P3's suite) has the identical structural gap for the
same reason (not referenced in either workflow) — not investigated further here, out of
scope for this report, but worth naming so it isn't rediscovered from scratch: whatever CI
wiring decision this package settles on for P5's suite is very likely the same decision
Phase B's suite needs.

---

### 2. The prompt

```
P12: the P5 acceptance suite is right that P9 broke something -- it's just pointed at the
wrong target. Two stale assertions in scripts/check_p5_acceptance.py encode a bug P9
already fixed on purpose (see this file's own section 1(a) for the live-run confirmation
that P9 closes the correct exception, both directions). Standard hard rules apply.

--- 1. Fix the two stale assertions ---
check_zoning_after_b (:103-107) and check_zoning_after_a2 (:133-135) assert that parcel
23707070 carries BOTH no_containing_district and multiple_containing_districts open
simultaneously. Per this package's section 1(a), the correct behavior (confirmed against a
live run) is: whichever reason was true in the PREVIOUS run and is NOT true this run closes
(condition_cleared, resolved_by='zoning_spatial_join_unresolvable'); whichever reason IS
true this run is open. Rewrite both assertions to check that, including the
reopened_from_id linkage after A2 (confirmed to point at the original A1 exception, not the
B-era one, not NULL). Show RED against current code (the two assertions as they exist
today, which is what this package established are wrong) is the WRONG framing here --
instead show that the OLD assertions are the ones currently red, and the NEW assertions you
write are green against the current, already-shipped, already-correct code. Do not touch
core/exceptions.py or load_zoning -- this is a test-only fix, per section 1(a)'s verdict.

Then run the whole P5 acceptance suite via scripts/run_p5_acceptance.sh (the actual wrapper
script, not a manual step-by-step reproduction) three times as CONVENTIONS.md requires --
twice against a seeded scratch database, once against a fresh migrations-only database with
no seed -- and confirm it now reaches "P5 ACCEPTANCE: ALL CHECKPOINTS PASSED" for the first
time since P9 landed.

--- 2. Wire the suite into CI, or decide explicitly not to ---
Per this package's section 1(b): recommended as a third CI gate, sequenced after step 1
above (wiring it in first would turn db.yml red on push). Needs: a minio service container
in db.yml with its own health check and a bucket-creation step (ledgex-snapshots-invalid --
mirror db.yml's own "Create clean database" step's shape); and a fix to
run_p5_acceptance.sh/run_phaseb_acceptance.sh's hardcoded .venv-ingest/bin/python3 (an
override pattern, same as the Makefile's PYTHON/PSQL/PG_DUMP, is the obvious shape -- report
before choosing a different one). If the decision is not to wire it in, say why explicitly
and set up the scheduled-workflow alternative instead -- do not leave it silently
unreachable again.

--- 3. Phase B's suite has the same gap ---
scripts/run_phaseb_acceptance.sh is not referenced in either workflow either, for the same
reason. Confirm whether it needs the identical treatment or has a reason not to, before
closing this package.
```

---

### 3. In plain terms

**1(a)** is a compliance checklist item that says "the safety guard must still be missing"
— written back when the guard genuinely was missing, as an honest record of a known gap.
Someone then built the guard, on purpose, tested it thoroughly, shipped it. The checklist
was never told. It still fails its own item every time the guard does its job, and read on
its own, a failing checklist item looks exactly the same whether the guard is broken or the
checklist is stale — the only way to tell is to go look at the guard.

**1(b)** is that checklist living in a binder nobody opens. Two other binders (`db.yml`,
`docs.yml`) get checked before every job starts, religiously, and both said "fine" the
whole time — truthfully, because neither of them was ever the binder with this item in it.
