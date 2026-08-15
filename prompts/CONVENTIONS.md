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
