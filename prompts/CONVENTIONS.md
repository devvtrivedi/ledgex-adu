# Conventions every package inherits

Referenced by each prompt as "standard hard rules apply" rather than restated in full.
If a package needs to override one of these, it says so explicitly and gives the reason.

## Hard rules

- **Never change a constraint, test or threshold to make something pass.** If the honest
  answer is "this needs a migration and a spec bump," stop and report.
- **Report before writing** on anything carrying a design decision, and on any schema
  change without exception. Migrations are forward-only and cannot be edited after merge.
- **If something turns out to be impossible as specified, that is a finding.** Stop and say
  so rather than engineering around it.
- **Do not invent values to fill a silence.** "We no longer observe this" and "this is now
  false" are different claims and must not be written as the same fact.
- **Scope creep is reported, not absorbed.** If a fix requires touching a shared primitive
  or a second source, say so before writing, not in the summary afterward.
- **Every CI workflow must be green before a package starts, verified on the real
  runner, not locally.** This repo has two: `db.yml` and `docs.yml`. `docs.yml` runs
  `make qa` and `make check-boundary` as two separate steps -- different targets, and a
  green `make qa` says nothing about whether `make check-boundary` (import-linter,
  `build/check_jurisdiction_names.py`, then `qa_check.py` again) was ever run. Check the
  actual GitHub Actions run for the commit a package starts from; a local re-run of the
  same commands is not the same evidence (this session's own `pg_dump` version mismatch
  is exactly the kind of local/CI divergence that makes "I ran it locally" insufficient).
  `docs.yml` was red for about a day, through five packages, because nothing checked it
  before any of them started -- every `make qa GREEN` report in that window was honest
  and real, for a narrower target than the one CI actually gated on.
- **A delegated agent reports; it does not commit or push to `main` on its own.** The
  decision to commit, and the decision to push to shared `main`, stay with the session
  that dispatched it -- a push to shared `main` is exactly the kind of hard-to-reverse,
  shared-state action that needs a check-in before, not after. Recorded because it already
  happened once: during the §8 reconciliation pass (2026-08-15), one of three parallel
  investigation agents was scoped to five items and report back, and instead wrote the
  full findings table itself, committed (`7320763`, `15e1a43`), and pushed to `main`
  without asking first. The content held up -- cross-checked against the other two
  independent agents' findings and against a real CI run before the dispatching session
  decided to keep it rather than redo the work -- but that it happened to be correct this
  time is not the same as the process being sound. Same class of incident as the three
  rename-verification failures below: a step that produced a good-looking result without
  the check that was supposed to gate it.

## Evidence rules

- **Every check must be seen to fail at least once.** Break it deliberately, show it red,
  unbreak it, show it green. Include the diff of the deliberate break. A test only ever
  observed green is a comment.
- **Show output, not summaries.** Counts, statuses and "verified" claims need the query or
  command output beneath them. A docstring asserting that a reproduction happened is
  testimony, not evidence.
- **Predict before running.** State the expected outcome and exit code first.
- **Never infer a category from arithmetic.** If three buckets should balance, query the
  third rather than subtracting.
- **Run every suite twice**, and once against a fresh migrations-only database with no seed.
  CI never runs `db/seeds/`.
- **Mark every item verified / unverified / assumed.** Those three words, no others.
- **Verify a commit's contents with `git show --stat` before reporting it as landed.**
  `git status` after the commit is not enough. This has failed three times now, in
  different ways, none caught by the step that declared success: a `git add` with one file
  path already renamed away failed silently and staged nothing, committing an empty-diff
  rename bundled into an unrelated commit; staging one file at a time across two fixes left
  a single commit mixing both; a `git mv`-staged rename plus a later content edit to that
  same file, added with a stale second pathspec that failed silently, landed as another
  empty-diff rename with the real fix never committed at all. `git show --stat` on the
  actual commit is necessary but was not, on its own, sufficient the third time --
  read the actual committed FILE CONTENT (`git show <sha>:<path>`) for the specific
  lines the commit claims to add, not just the file list, when a rename is anywhere in
  the diff.
- **Proving a check can fail on planted input does not establish that it passes on real
  input.** A widened or newly-added check proven RED-then-GREEN against a deliberately
  planted violation has only shown the check *can* fire -- not that the tree it is about
  to start guarding is actually clean. `330a91b` widened `build/check_jurisdiction_names.py`'s
  BLOCKLIST, planted violations, confirmed RED, reverted them, and never ran the widened
  check against the real `core/` files afterward. The next package tripped it for real
  (`bd5db19`) and it stayed red for about a day, through five more packages, before anyone
  looked. After widening or adding any check, run it against the actual tree once, for
  real, and show that result -- not just the deliberate-break proof.

## Shapes that keep recurring in this repo

Named so a prompt can point at one in three words.

- **Arbitrary pick.** `fetchone()` over a multi-row result, or a dict overwrite that keeps
  whichever row arrived last. Silent, and looks correct in every test with one candidate.
  Found in `compose_property_file` (APN collisions) and again in the zoning fix's
  `ZONINGABBREV` path.
- **Proxy drift.** A column or check that measures something adjacent to what matters —
  counting polygon rows when the question is distinct classifications, or reusing a
  `confidence_rule_id` field to carry a free-text reason.
- **Cross-source assertion.** Writing a fact for source B's field using source A's snapshot,
  licence and endpoint. The per-source unique index does not catch it.
- **The test that encodes the bug.** An acceptance test written after the implementation,
  asserting what the code does rather than what was asked. Green, and worthless.
- **Both halves of a data fix.** A guarded migration alone is a permanent no-op on fresh
  installs; a seed fix alone leaves existing databases wrong. Both, every time — and once a
  table is immutable, neither is available and the answer is rebuild.
