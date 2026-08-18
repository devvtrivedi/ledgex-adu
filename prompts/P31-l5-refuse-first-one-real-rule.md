## P31 — The prevention P30 skipped, then L5: refuse-first, one real rule

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)).

**Founder decisions, ratified, built against, not re-argued**: `rule.attestation_uri` is a
commit-pinned git object/URL (P30's recommendation). The `conclusions.yaml` gap is closed
via Shape 1 — a hardcoded, narrowly-scoped constant matching `core/calc.py`'s own
precedent, not a general mechanism. **A second jurisdiction forces this constant to be
rewritten — accepted knowingly, recorded here so a future reader does not mistake a
one-jurisdiction hardcode for a designed abstraction.**

---

### 1. The prevention P30 owed

P30's `9a45566` bundled its 214-line report doc into the same commit as the deliberate
break — `git revert` of that commit would have deleted the report along with the break.
Caught and hand-amended before push that time; the instance is fixed (`git diff b5ea1a3
HEAD` across `jurisdictions/`, `scripts/`, `core/`, `db/` is empty — confirmed, not
assumed). Nothing was done about *why* it was possible: `CONVENTIONS.md`'s own evidence
rule said only "break it, show it red, unbreak it, show it green," with no rule about what
such a commit may contain.

**Added**: a new rule in `CONVENTIONS.md`'s evidence-rules section — a deliberate-break
commit contains ONLY the break, so its revert is a pure, mechanical inverse; anything else
sharing that commit makes the revert destructive and any "evidence not work" annotation on
it false.

**`prompts/README.md`'s P30 row corrected**: it labeled `9a45566` as paired evidence
alongside `2936f25`, both "evidence not work" — false for `9a45566` specifically, which
carries this package's own real report doc. Corrected to say what `9a45566` actually
contains, and to name `2936f25` (confirmed via `git show --stat`: `sources.yaml`, one file,
a clean inverse) as the genuine evidence-only commit.

**Every other package's break/revert pair checked by `git show --stat`, not assumed pure
because P30's was the one found broken**:

| Package | Break | Revert | Break commit's own diff |
|---|---|---|---|
| P12 | `065f3e5` | `a9eafac` | `scripts/ingest_zoning_permits.py`, 1 file |
| P13 | `6c41103` | `c460792` | `scripts/ingest_parcels.py`, 1 file |
| P21 | `cc84fe6` | `896ce71` | `core/model.py`, 1 file |
| P25 | `f936232` | `8869f8d` | `core/calc.py`, 1 file |
| P27 | `6465b46` | `0c8145a` | `.github/workflows/db.yml`, 1 file |
| P28 | `9e702cd` | `c321b2f` | `scripts/check_liveness.py`, 1 file |

All six are pure, single-file, break-only commits, and all six reverts are exact inverses
(same file, opposite hunk direction, no other changes) — confirmed directly. **P30's
`9a45566` was the only impure one.** Not assumed to generalize from P30 alone; checked
individually, every one, before concluding the fix is scoped correctly to this one
instance.

---
