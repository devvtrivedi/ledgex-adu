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
- **Every push/PR-gated CI workflow must be green before a package starts, verified on
  the real runner, not locally.** This repo has three workflow files: `db.yml`,
  `docs.yml`, and (P28) `liveness.yml` -- but only the first two are push/PR-gated, and
  this rule is scoped to those two. `docs.yml` runs `make qa` and `make check-boundary` as
  two separate steps -- different targets, and a green `make qa` says nothing about
  whether `make check-boundary` (import-linter, `build/check_jurisdiction_names.py`, then
  `qa_check.py` again) was ever run. Check the actual GitHub Actions run for the commit a
  package starts from; a local re-run of the same commands is not the same evidence (this
  session's own `pg_dump` version mismatch is exactly the kind of local/CI divergence that
  makes "I ran it locally" insufficient). `docs.yml` was red for about a day, through five
  packages, because nothing checked it before any of them started -- every `make qa GREEN`
  report in that window was honest and real, for a narrower target than the one CI
  actually gated on. `liveness.yml` is deliberately excluded from this precondition: it is
  `schedule:`/`workflow_dispatch`-only, checking a third-party endpoint's uptime that no
  commit in this repo can fix -- see `prompts/P28-liveness.md` section 2 for the full
  argument. Check it when the work at hand actually touches ingest or a jurisdiction pack,
  not as an unconditional gate on starting unrelated work.
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
- **A deliberate-break commit contains ONLY the break, nothing else.** Its revert must be
  a pure inverse — mechanical, reviewable as exactly "undo this and nothing else." Any real
  work sharing that commit (a report doc, an unrelated fix) makes the revert destructive
  (it deletes that work too, whether or not anyone notices) and makes a "deliberate break +
  revert, evidence not work" annotation false for the commit it's attached to. Found for
  real, not hypothetical: P30's own `9a45566` bundled its 214-line report doc into the same
  commit as the break — caught and hand-amended before push that time, but the row's own
  "evidence not work" label would have told a later session filtering out evidence commits
  to skip the one commit the report actually landed in. Land the break alone; land anything
  else that needs to travel with it in a separate commit, before or after.
- **Show output, not summaries.** Counts, statuses and "verified" claims need the query or
  command output beneath them. A docstring asserting that a reproduction happened is
  testimony, not evidence.
- **Predict before running.** State the expected outcome and exit code first.
- **Never infer a category from arithmetic.** If three buckets should balance, query the
  third rather than subtracting.
- **Run every suite twice**, and once against a fresh migrations-only database with no seed.
  CI never runs `db/seeds/`. **Twice means twice, each against its own fresh database, never
  twice against the same one** — this has been the actual, honest interpretation for
  `run_p5_acceptance.sh`/`run_phaseb_acceptance.sh` since they existed, not a new rule
  (P23, README findings #29/#30): both assert a specific A→B state *transition*, not a
  steady-state idempotent operation, and a completed run leaves the database in state B,
  not A — a second run against that same database starts from the wrong state and its own
  assertions, written for a first run, read as if starting from A again. Confirmed
  directly, not assumed from either suite going unquestioned: a same-database rerun
  produces a failed assertion in `run_p5_acceptance.sh`
  (`check_p5_acceptance.py:220-224`) and an unhandled `UniqueViolation` crash in
  `run_phaseb_acceptance.sh`. Every earlier package's own "ran it twice" for these two
  suites already meant twice-on-independent-fresh-databases, never a same-database
  rerun — this is a correction to the record, not only a rule change going forward. Both
  suites now state this loudly as a precondition in their own header, the same shape P14
  used for `db/tests/invariants.sql`'s own class-2 permanence note. A suite that genuinely
  is idempotent under a same-database rerun (`db/tests/invariants.sql`,
  `migrate`/`migrate-verify`) is unaffected — this exception is scoped to suites that model
  a one-time transition, not a blanket weakening of "twice."
- **Run `make migrate-verify` before citing any local database as evidence, and state the
  result.** "Queried the real database" is only as strong as the claim that its schema is
  what its own ledger says — and CI cannot see this gap at all: every CI run starts from an
  empty database and applies every migration fresh, so a shared local database drifting
  behind its own `schema_migrations` ledger is invisible to CI by construction. Only a
  session that stops and checks catches it before citing that database's row counts, live
  constraint behavior, or "confirmed against a real database" as proof. Found three times so
  far, all incidentally, never by anything looking for it: six migrations behind before P6,
  two behind (missing `0048`/`0049`) at the start of P16, one behind (missing `0051`) at the
  start of P21 (README finding #27 — reopened as a recurring condition, not a one-time
  incident, P22). `make migrate-verify` already exists and already works; the missing half
  was never tooling, it was remembering to run it before trusting what the database says.
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
- **NULL inside a constraint silently disables it.** A constraint written over an expression
  that can be NULL is not enforcing what its name says for the rows where it is NULL, and
  nothing reports that — it just quietly never fires for them. Two live instances, argued
  together and fixed together in one package (P10): 0038's `refusals_codes_valid()`, where
  `elem->>'code' NOT IN (...)` evaluated SQL NULL (not true) for every shape missing a
  `code` key, so `NOT EXISTS` reported clean on exactly the rows that should have failed
  (README finding #8, closed by 0048 — DROP+ADD on a CASE-guarded rewrite, not a same-named
  `CREATE OR REPLACE` left under the old constraint, so existing rows actually get
  re-validated); 0045's partial unique index on `detail->>'reason'`, which never actually
  constrained `zoning_source_geometry_invalid` — that detector's `detail` never sets a
  `reason` key at all, so the expression was NULL for every one of its rows, and NULLs
  never conflict with each other in a unique index (README finding #19, closed by
  0049 — `COALESCE(detail->>'reason', '')`, the same technique 0006's
  `fact_one_current_per_source` already uses for `source_id`/`method_version`, though not
  always for the same underlying reason — check whether the NULL is a legitimate, recurring
  domain state or simply an omission before assuming the precedent transfers unchanged).
  **Requirement, not just a pattern to recognize:** any constraint or index keyed on an
  expression rather than a plain `NOT NULL` column must state, in its own migration's
  header comment, what that expression does when it evaluates NULL — whether that's genuinely
  impossible for the column it reads (say why), or possible and handled (say how, e.g. a
  `COALESCE` sentinel), or possible and NOT handled (say so as a known gap, not a silent
  omission). "The constraint compiled" is not evidence it constrains anything on the rows
  where its key expression is NULL — say what happens there, explicitly, every time.

## The four-tier authority model — D5 (P63A/P63B, 2026-09-02)

Ratified by the owner as a written convention, derived from
~/Desktop/ledgex-p63-evidence/P63A-DESIGN-PACKET.md §14.6. Four tiers, in decreasing order of
authority over what the codebase must currently do:

- **Tier 1 — current normative requirements.** The spec's invariants (§1), safety and rights
  boundaries, architectural contracts. What LedgeX is required to do now.
- **Tier 2 — executable current state.** Schema, code, migrations, tests, runtime contracts.
  Implements and verifies Tier 1; evolves prospectively through controlled changes (a new
  migration, a new invariant).
- **Tier 3 — internal evidentiary record.** `fact`, `snapshot`, `licence`/`licence_channel`,
  `exception_evidence`, `db/README.md`'s append-only correction sections and their kin.
  Append-only or otherwise preserved to reconstruct source lineage, rights state, and
  material decisions. Preserves evidence; does not itself dictate future implementation.
- **Tier 4 — historical development record.** Prior prompts, packages, handoffs, audits,
  superseded specifications, migration commentary. Explain repository history. **They are
  evidence of prior state, not precedent binding future architecture.**

**A Tier-4 artifact going stale because the system legitimately evolved is not itself a
defect.** A prompt, handoff, or audit that asserted something true on the day it was written,
and is no longer true because a later, deliberate change superseded it, needs no correction
and no apology — that is the system working, not failing. This is *distinct* from a Tier-2
mechanism whose own claim about itself goes stale (e.g. a migration header's prose describing
its own behavior incorrectly) — that kind of staleness belongs in `db/README.md`'s
"Stale migration header claims" section (B9), because it is a live artifact whose own
self-description can mislead; a superseded Tier-4 document is not that.

**No new enforcement machinery accompanies this entry.** No check, script, CI step, or gate
verifies that a historical artifact "knows" it has been superseded, and none should be built
for that purpose — a convention that arrives with a tool to enforce it is not a convention,
it is Tier-2 pretending to be Tier-1. Judgment about which tier a given document occupies, and
whether a stale Tier-4 claim matters, stays a human (or an agent reading this file) reading and
deciding, the same way every other convention in this file already works.
