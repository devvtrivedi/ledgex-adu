# P48 — merge P45, P46 and P47 into `main`

Three finished branches, none merged; `main` had been sitting at `e6cdf64`
since P44. This package landed all three and corrected the status claims the
merges made false.

**Final state:** `main` at `e8ebe04`, in sync with `origin/main`, green on the
real runner at its tip.

## 0. Decisions

Recorded with their reasoning, as decided by the dispatching session before
the package started.

**D7 — order: p45 first, then p47.** P45 carries the only two High findings
in the set (ingest provenance), and it was the branch that still
fast-forwarded cleanly from `e6cdf64`. P47 second, in one merge, because p46
was already inside it — merging p46 separately would have added a commit
that said nothing.

Topology, measured rather than assumed:

```
main e6cdf64
├── p45-ingest-provenance   3344194   (forked from main, independent)
└── p46-boundary-validation 991a14d
    └── p47-tooling-and-sockets 567bf89

git merge-base --is-ancestor p46 p47   -> true
git merge-base --is-ancestor p45 p47   -> false
git merge-base p45 p47                 -> e6cdf64
```

Two things to merge, not three.

**D8 — the second merge used `--no-ff`, a deliberate departure from P44's
D4.** P44 chose a fast-forward because `main` was a strict ancestor and this
repo's history is linear. After the first merge that stopped being true of
p47: `main` had moved, so p47 could only arrive as a rebase or as a merge
commit.

A rebase would have rewritten all nine p46/p47 commits with new hashes.
`prompts/README.md`'s package rows and both close-out reports cite those
hashes by value, and this repo has already spent three separate rounds of
work getting recorded hashes to match reality — a rebase would have
invalidated every one of them in a single command. Hash integrity was worth
more than linearity.

So `main` now has its first non-linear node, on purpose. The reasoning is in
the merge commit message (`67a9d78`), not only in this report.

**D9 — the README conflict was resolved by keeping both sides.** The finding
numbers never collided: P45 added #46 and #47, P46 added #48 and #49, P47
rewrote the status cells of #44 and #45. Any resolution that dropped,
renumbered or merged a row would have been wrong.

## 1. Preconditions — fresh, before the first merge

Per CONVENTIONS' push/PR-gated-workflow rule, against all three commits
involved: the merge target and both branch tips. Six conclusion sets, all
from real runs on the GitHub runner, none transcribed from an earlier
package.

- `e6cdf64` (merge target) — `db.yml`: schema, p5-acceptance,
  phaseb-acceptance, all `success`
  ([32434687026](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32434687026));
  `docs.yml`: `make qa` success, `make check-boundary` success
  ([32434686880](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32434686880)).
- `3344194` (p45 tip) — `db.yml`: all three jobs `success`
  ([32438058507](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32438058507));
  `docs.yml`: both steps `success`
  ([32438058528](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32438058528)).
- `567bf89` (p47 tip) — `db.yml`: all three jobs `success`
  ([32440178547](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32440178547));
  `docs.yml`: both steps `success`
  ([32440178278](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32440178278)).

`docs.yml`'s two steps are reported separately on purpose: they are different
targets, and a green `make qa` says nothing about whether `make
check-boundary` ran. `check-boundary` is also the target P47's own contract
work lives under.

Topology re-verified against origin at this point; all four refs matched
their `origin/` counterparts exactly. `p45-ingest-provenance..main` was
empty, so the fast-forward was still available. Working tree clean apart
from the known untracked `LEDGEX-*.txt` / `PROMPT-*.txt` scratch files.

## 2. Merge one — p45, fast-forward

`main`: `e6cdf64` → `3344194`.

`--ff-only` was used as the guard, not as decoration: had `main` moved, it
would have refused loudly rather than quietly producing a merge commit.

Run on `main` after the push — predicted identical to the branch run (a
fast-forward changes no content, and both workflows are bare `on: push /
pull_request` with no branch filters or `if:` conditions, verified in P44).
Prediction held:

- `db.yml`: schema, p5-acceptance, phaseb-acceptance all `success`
  ([32501474070](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32501474070)).
- `docs.yml`: `make qa`, `make check-boundary` both `success`
  ([32501473998](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32501473998)).

## 3. Merge two — p47, `--no-ff`

`main`: `3344194` → `67a9d78`.

**Conflict, predicted before it was created:** `prompts/README.md` and
nothing else. p45 touches ingest, the audit script and the two acceptance
runners; p46/p47 touch `api`, `core`, `infra`, migrate and compose. Only the
README overlapped.

**Actual:** `prompts/README.md` only, confirmed by `git diff --name-only
--diff-filter=U` immediately after the merge. Prediction held. Two conflict
regions inside that one file:

- **Package table** — both sides inserted a row at the same point. Both
  kept, verbatim, in order P45 / P46 / P47.
- **Findings table** — both sides carried a row for #45; only p47 had
  updated its content. Kept p47's updated version, alongside p45's new
  #46/#47 and p47's new #48/#49.

Sequence #40–#49 confirmed unbroken afterwards: no gap, no duplicate, no
drop. Zero code changes were made to resolve the conflict — the boundary
that would have turned this from a merge into something else.

Run on `main` after the push:

- `db.yml`: [32502047457](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32502047457)
- `docs.yml`: [32502047434](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32502047434)

## 4. The combined tree — the thing no CI had ever seen

Neither branch's CI knew the other existed. Full suite, locally, on the
merged tree before pushing:

- `make qa` — green
- `make check-boundary` — green, 5/5 contracts KEPT
- `make test` — green, 168 passed
- `make viewer-test` — green
- `make golden` — green
- `make conformance` — green
- all four `compose()` test scripts — green
- both acceptance runners — 3 runs each (twice against independent fresh
  databases, once migrations-only); 123/0 and 57/0 PASS/FAIL every time

**Cross-checks specific to this combination:**

1. **The rights gate survived two branches editing around it.** P47 moved
   `evaluate_rights_gate` into `core/rights.py`; P46 edited `api/main.py`.
   After the merge: exactly one definition, exactly two call sites, and
   `api/` importing nothing from `scripts/`.
2. **Correction to this package's own prompt.** P48 stated that
   `seed_internal_test_licences.py` and the two acceptance runners "feed the
   same CI job." They do not. They feed the same *workflow* (`db.yml`)
   across three separate jobs — `schema`, `p5-acceptance`,
   `phaseb-acceptance`. Recorded rather than quietly worked around: the
   prompt asserted a fact about CI structure that was wrong, and the check
   was run against what is actually there.
3. **P46's boundary validation still holds with P47's imports in place.**
   `/v1/job-runs?status=succeded` still returns 422; a real enum member
   still returns 200.

## 5. Status truth — after the merges, not before

`main`: `67a9d78` → `e8ebe04`.

Landed as its own commit after both merges, per P44's D6: a pre-staged
version would have asserted "merged" while sitting unmerged, which is a
claim this repo does not let a document make. Two pushes to `main` was the
honest cost.

The diff was exactly the three package-row status cells — "done, on branch
`p4x-...`, not merged" → "done, pushed" — plus P47's row gaining the merge
commit with D8's one-clause reason.

**Stale-phrase sweep**, seven patterns, case-insensitive: "not merged", "on
branch", "uncommitted", "working tree only", "awaiting review", "not yet
committed", "not yet merged". Only those three package rows were live hits.
Finding #31's P26 narrative and finding #49's technical use of "uncommitted"
are historical/descriptive prose and were left unchanged — the same
judgement call the P43 close-out correction made, for the same reason.

`make qa` and `make check-boundary` predicted and run locally before the
push.

Run on `main` at the new tip:

- `db.yml`: [32502265491](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32502265491)
- `docs.yml`: [32502265579](https://github.com/devvtrivedi/ledgex-adu/actions/runs/32502265579)

## 6. Final state, verified independently

Not transcribed from the merge session's own report — re-read from the
repository afterwards.

```
* e8ebe04 P48 STEP 5: correct the three package-row statuses the merges
|         just made false
*   67a9d78 Merge p47-tooling-and-sockets into main (--no-ff, deliberate)
|\
| * 567bf89 ... p47 (6 commits) ...
| * 991a14d ... p46 (4 commits) ...
* | 3344194 ... p45 (5 commits) ...
```

- `main` = `e8ebe04` = `origin/main`.
- Findings table: 40 41 42 43 44 45 46 47 48 49 — unbroken, no duplicates.
- Package rows P45, P46, P47 all read "done, pushed".
- Exactly one merge commit in the history.
- All three branches still exist (`p45-ingest-provenance`,
  `p46-boundary-validation`, `p47-tooling-and-sockets`), plus `audit-fixes`.
  None deleted — they are the record of how this landed.

**What is true of `main` now that was not true before:** it carries P45, P46
and P47's work with a real green run at its tip, and it is no longer a
linear history.

## 7. Still open

- **The remediation decision from P45's audit.** P45 was scoped to audit and
  report, deliberately: fact rows are immutable (0017, 0007/0040), so
  correcting wrongly-attributed provenance is a supersession rather than an
  update, and probably a spec bump with a §12 row. The audit's result is in
  `prompts/P45-ingest-provenance.md`; the decision it feeds is still the
  dispatching session's.
- **LD-1** — unchanged by any of this. Every real `licence_channel` row is
  still `allowed=false`, so the viewer still shows values only for the
  `internal_test.*` seeded facts.

## Review findings

(none yet — filled in by review)
