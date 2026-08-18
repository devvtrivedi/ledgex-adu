## P27 — Bound the CI jobs, then find what actually hung

### 1. What is actually wrong

Neither `db.yml` nor `docs.yml` set `timeout-minutes` on any job — `schema`,
`p5-acceptance`, `phaseb-acceptance` (`db.yml`) and `qa` (`docs.yml`), four jobs, zero
bounds. GitHub's own default (360 minutes) applies to all four by omission, not by
decision — nobody chose six hours, nothing in this repo's history discusses it.

This stopped being theoretical during the P26 build push (`3980560`): `db.yml` run
`32171649751` (the `schema` job) was still `in_progress` after 5+ minutes against a
historical baseline of ~1-2 minutes for that job. Left alone it would have sat
`in_progress`, consuming a runner, reporting nothing, for up to six hours — indistinguishable
from "still legitimately running" to anything not actively polling it. The local
`until gh run view ... ; sleep 15; done` loop watching it had the identical property: no
bound of its own, so it would have blocked the session for the same six hours.

### 2. The prompt

```
P27: bound the CI jobs, then find what actually hung.
Read prompts/CONVENTIONS.md. Standard hard rules apply.

--- 0. Stop the bleeding, before diagnosing ---
Cancel run 32171649751 and kill the local `until gh run view ... sleep 15` loop. Neither
has a bound: db.yml and docs.yml set timeout-minutes on zero jobs, so GitHub's 360-minute
default applies, and the polling loop will happily wait all six hours.

--- 1. Add timeout-minutes to every job, and record the finding ---
Both workflows, all four jobs. Historical runtimes are ~5 minutes, so a bound in the
15-25 range is generous and still fails fast. Add a findings row: an unbounded CI job is
a gate that cannot fail promptly, which is the same class as the silently-passing gates
this repo has fixed four times -- it does not report a wrong answer, it reports no answer
for six hours.

Land this first, on its own, even before the diagnosis. It is correct regardless of what
turns out to be hung.

--- 2. Diagnose: the leading suspect is a lock wait, not a slow step ---
scripts/test_snapshot_race_invariant.py opens two connections, both SELECT, then both
INSERT. PostgreSQL blocks a duplicate-key INSERT against an UNCOMMITTED conflicting row
until the first transaction ends -- and ON CONFLICT DO NOTHING does NOT avoid that wait.
It blocks on the uncommitted tuple exactly the same way.

If connection A's transaction is still open when B inserts, B waits indefinitely. Verify
before fixing: reproduce locally with a deliberate delay between A's INSERT and A's
COMMIT, and confirm B hangs rather than erroring. Predict the outcome first.

Check make conformance too -- it is new to the schema job in P26 and unproven under CI
timing.

--- 3. Fix the actual cause, and make the class impossible ---
If it is the lock wait: set lock_timeout and statement_timeout on the test's own
connections so a wait fails loudly with a named error instead of hanging. A test that can
hang is not a test; it is a coin flip on runner timing, and it passed locally only
because your ordering happened to differ.

Whatever the cause, the fix must make it fail fast rather than merely making it pass this
time. Prove it: reintroduce the hang deliberately, confirm the job now fails within the
new bound rather than running to the timeout, revert in the immediately following commit.

--- 4. Close out ---
Confirm all four CI jobs green AND that total wall-clock is back near its historical
~5 minutes -- a green run that took 40 minutes is still a finding, not a pass. Add the
P27 row.

Then report: whether any other test in the suite can block on an uncommitted row the same
way. The two acceptance suites both run real loaders against real databases; if any of
them can wait on a lock with no timeout, they have the same latent hang and nobody would
know until a runner was slow enough to expose it.
```

### 3. Diagnosis: the named suspect checked out clean; the real cause was elsewhere

The prompt's leading suspect was `scripts/test_snapshot_race_invariant.py`'s own
`INSERT ... ON CONFLICT DO NOTHING` race — plausible on its face, since Postgres does
make a second `INSERT` wait on a first, uncommitted transaction touching the same key.
**Checked, not assumed, and it does not hold against the current code**: `insert_snapshot()`
(`scripts/ingest_parcels.py:311-350`, and `scripts/ingest_zoning_permits.py`'s twin) calls
`conn.commit()` itself, unconditionally, before returning. `conn_a`'s row is already
committed by the time `conn_b`'s `insert_snapshot()` call even starts — there is no
uncommitted row for it to block on. Predicted before running: exit 0, all PASS, under a
few seconds. Reproduced against a fresh migrations-only scratch database
(`p27_scratch`, all 51 migrations applied): 1 second, all 12 assertions PASS, no hang.
The hypothesis is falsified for this code as it stands, not merely unconfirmed.

**The real cause, read directly off GitHub's own per-step timestamps for the hung run
(`32171649751`), not inferred**: the `schema` and `phaseb-acceptance` jobs both hung at
the identical step, `Install postgresql-client-16` (`sudo apt-get update && sudo apt-get
install -y postgresql-client-16`) — started `18:33:51`/`18:33:49`, still running when
cancelled at `18:54:31`/`18:54:29`, ~21 minutes. Every step after it, including
`scripts/test_snapshot_race_invariant.py` and `make conformance`, shows `skipped` — neither
one had even started. `p5-acceptance`, running the byte-identical step on the byte-identical
commit in the same job matrix, finished it in 6 seconds. Same push, same step, same runner
pool, two different outcomes — this is a transient apt/mirror stall on the GitHub-hosted
runner, external infrastructure this repo's code has no part in, not a bug in
`test_snapshot_race_invariant.py`, `make conformance`, or anything else in the tree.

Per `CONVENTIONS.md`'s "never change a constraint, test, or threshold to make something
pass" and "if something turns out to be impossible as specified, that is a finding" — no
`lock_timeout`/`statement_timeout` was added to `test_snapshot_race_invariant.py`. There is
no bug there to hardcode a fix for; doing so anyway would be exactly the kind of unearned
defensive code CONVENTIONS argues against, dressed up as a fix for an incident it didn't
cause. Instead, `db.yml`'s three `Install postgresql-client-16` steps (`schema`,
`p5-acceptance`, `phaseb-acceptance`) each got their own `timeout-minutes: 5`, tighter than
the job-level bound — a repeat of this exact stall now fails, by name, in the Actions UI,
in minutes, rather than quietly consuming the whole job's 15-20 minute budget before
anyone can tell which step actually stalled.

`make conformance` (the prompt's other named suspect) ran and passed cleanly, in the
already-confirmed-green step 1 run (`32173747500`) — never exposed to any hang.

### 4. In plain terms

Two separate problems, and only one of them turned out to be where the prompt expected.
The first is a missing seatbelt: no CI job had a maximum runtime, so a hang and a
legitimately slow six-hour job would have looked identical from the outside. Fixed first,
independent of cause, because it's correct regardless of what turns out to be hung — and
it was.

The second is the actual cause, and it wasn't the database race that looked like the
obvious candidate. `test_snapshot_race_invariant.py` races two connections on purpose, but
the function under test already commits between them — so by the time the second
connection tries to insert, there's nothing left uncommitted to wait on. The real hang was
one level below any of this repo's own code: `apt-get` itself sat there for twenty minutes
on two of three jobs while the third finished in six seconds, on the same push. Bounding
the one step that actually stalled, tightly, is the honest fix — inventing a database lock
bug that isn't there would have fixed nothing and hidden the real, external cause.
