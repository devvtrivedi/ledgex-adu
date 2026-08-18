## P23 — Two contradictions in the authority layer: findings #29 and #30

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). §2 is generated —
`docs/LEDGEX_SPEC.md` is never hand-edited; the versioned `text/*.txt` source and
`build/ledgex_source.py` are.

I17: the Spec and Rules are authoritative only when read verbatim from the filesystem. A
verbatim read that yields two incompatible answers is worse than a code bug — every
downstream decision citing it inherits the ambiguity silently, and P22 hit exactly that
in the middle of real work.

---

### 1. Finding #29 — may `core/` import `infra/`?

§2 contradicted itself: "core/* may import core/model and stdlib/third-party only" in
one bullet, "Any of core/, commerce/, jurisdictions/, pipelines/, api/ may import
infra/" two bullets later — and the repo-layout diagram and `infra/__init__.py`'s own
docstring both sided with the second reading.

**Decided, not averaged — confirmed against git history, not inferred.** The first
bullet's text is present verbatim in this repo's very first commit (`313a2b6`, v1.7) —
before `infra/` existed at all; the earliest `git show <sha>:text/*.txt | grep infra`
against that commit finds nothing but unrelated "infrastructure" prose (A-1.4's edge
guard). `infra/` was introduced at `6e7d6fe` (spec 1.21, "Added infra/"), which added
the diagram's `infra/` entry and the second bullet in the same commit — and never
touched the older, by-then-stale first bullet. The older line predates `infra/`'s
existence by fourteen version bumps; it meant "no domain dependencies" at a time when
`infra/` was not a thing to have an opinion about, and nobody went back to update it
once `infra/` landed.

**Amended so no verbatim read can land on the losing reading**: both statements now
read `core/* may import core/model, infra/, and stdlib/third-party only`. Spec bumped
1.37 → 1.38, real §12 row recording the git-history evidence, not just the decision.
`infra/__init__.py`'s own docstring — which quoted the losing reading verbatim as if
authoritative — corrected too, since it was carrying the same contradiction inline.
`text/*.txt` rename verified with `git show <sha>:<path>` after landing, not just
`git status` — the trap named in CONVENTIONS.md's evidence rules has now fired five
times; not making it six.

**The part that matters more than the wording**: nothing enforced either answer.
`.importlinter` had contracts for `core -> jurisdictions/api/pipelines/geo/commerce`,
`commerce -> core.store`, and `infra` as a leaf (forbidding `infra` from importing
anything under this repo) — but nothing about `core -> infra` in either direction. Added
a new `layers` contract (`core-commerce-layers-above-infra`): `core | commerce` as
independent siblings above `infra/`. This is the one import-linter contract shape that
states the resolved rule in both directions at once — higher layers may import lower,
never the reverse — rather than another one-directional `forbidden` contract that would
have left the *permissive* half of the decision just as undocumented in the linter as it
was in prose.

**Proven both ways, per CONVENTIONS.md's planted-input rule** — not just RED:

- Planted `import core.model` at the top of `infra/env.py`. `lint-imports`: **BROKEN**,
  both the new layers contract and the pre-existing `infra-is-a-leaf` contract fired,
  naming the exact edge (`infra.env -> core.model`). Removed, confirmed green again.
- Planted `import infra.values` into `core/store.py`. `lint-imports`: **still green** —
  5 contracts kept, 0 broken, 14 dependencies analyzed (up from 13) — proving the
  decided direction genuinely works, not merely that nothing currently exercises it.
  Removed before landing; nothing in this package actually needs `core/` to import
  `infra/` today, so the real import stays out, only the proof that it *could* work is
  recorded.

**Retroactive effect on P22, recorded as asked, not assumed either way.** P22's Fact.value
design decision blocked option (a) — `value` holding a native Python value with
`insert_facts()` doing `json.dumps(..., default=infra.values.decimal_default)` — on
exactly this ambiguity. This resolution *would* have unblocked it: `core/store.py`
importing `infra.values` is now confirmed, mechanically, to work. **Not revisited
anyway** — P22's chosen option (b), `value` as pre-encoded JSON text with its own
is-valid-JSON validator, stands on its own merits independent of the import question:
zero caller-side serialization changes, and stronger construction-time validation via a
real `str` type (rejecting native `bool`/`dict`/`None` immediately) than option (a) would
have added. The import blocker made the decision easier at the time; it was never the
only reason to prefer (b).

---

### 2. Finding #30 — a suite that cannot satisfy CONVENTIONS.md:54

"Run every suite twice" is a standing evidence requirement. `run_p5_acceptance.sh`
cannot be rerun against an already-populated database —
`scripts/check_p5_acceptance.py:220-224` asserts a first-run-only shape (parcel
`23712112`'s `permits.active` fact is a brand-new fact, `supersedes_fact_id IS NULL`,
after phase B — only true the first time).

**Scope established first, not assumed.** Tested `run_phaseb_acceptance.sh` directly —
not presumed safe because P13 wired it into CI and it has run repeatedly without
complaint. It has the identical property, and worse: not a soft assertion failure but an
**unhandled crash** on rerun —

```
job_run ... -> failed: duplicate key value violates unique constraint
"parcel_exception_one_open_per_detector_reason_coalesced"
psycopg2.errors.UniqueViolation: ...
```

**Decided (b) over (a).** Making either suite genuinely rerunnable against its own
post-run state would mean rewriting its state model to tolerate starting from state B
instead of state A — both scripts assert an A→B(→A) *transition*, not a steady-state
idempotent operation, and a completed run leaves the database already past the state
every assertion assumes. Not a small fix, and not what either suite was ever designed to
prove.

**Fixed at the precondition, loudly, the shape P14 already established for
`db/tests/invariants.sql`'s class-2 permanence note**: both scripts' own headers now
state directly that a fresh database is required per run, and describe the exact failure
mode (a failed assertion for P5, a crash for Phase B) so the next person hits documentation,
not a surprise.

**`CONVENTIONS.md:54` corrected**, not just reworded: "run every suite twice" now reads
"twice, each against its own fresh database, never twice against the same one" —
explicitly scoped to suites that assert a one-time transition, not a blanket weakening.
`db/tests/invariants.sql` and `migrate`/`migrate-verify` are unaffected; they remain
genuinely idempotent under a same-database rerun, and continue to be run that way.

**Stated plainly, as a correction to the record, not only a rule change**: the rule as
literally written has been unsatisfiable for both acceptance suites since they existed.
Every earlier package's own "ran it twice" for either suite — P12, P13, P19, P20, P22 —
already meant twice against independent fresh databases in practice; none of them ever
literally reran against the same populated database, because doing so would have failed
exactly as reproduced here. This closes the gap between what the rule said and what every
honest run has actually done, rather than asking future packages to keep silently doing
the right thing while citing a rule that says something narrower.

---

### 3. Close-out

`make migrate-verify` against `ledgex_schema_check`, then a clean `make schema-dump` —
no schema change expected or found; this package touches spec text, `.importlinter`,
two shell script headers, and `CONVENTIONS.md`, nothing under `db/`. `make check-boundary`
(import-linter — 5 contracts now, jurisdiction-name grep, `qa_check.py`) green throughout.
`text/*.txt` rename verified via `git show <sha>:<path>` after commit, not just
`git status --short`.

Findings #29 and #30 both closed. No new findings opened by this package — both were
already-numbered, already-open items from P22; this package resolves them, not surfaces
more.
