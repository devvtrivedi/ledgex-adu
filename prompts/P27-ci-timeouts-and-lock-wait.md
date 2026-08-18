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

### 3. In plain terms

Two separate problems stacked on top of each other. The first is a missing seatbelt: no
CI job had a maximum runtime, so a hang and a six-hour job look identical from the
outside — GitHub just says "still running" either way. Fixed first, independent of cause,
because it's correct regardless of what turns out to be hung.

The second is the actual crash: `test_snapshot_race_invariant.py` deliberately races two
database connections to prove a dedup fix works (P19), but Postgres makes a second
`INSERT` wait for a first, still-open transaction touching the same key — even with `ON
CONFLICT DO NOTHING`, which only skips the conflict once it can see the other row's final
state. If the first connection is slow to commit for any reason, the second one just sits
there, and nothing was ever set up to time that out. A test that races two transactions on
purpose needs its own escape hatch from that exact race going wrong.
