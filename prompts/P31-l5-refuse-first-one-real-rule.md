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

### 0. Section numbers corrected before anything else

Searched the whole repo (`grep -rn "20\.30\.46\|20\.30\.47\|20\.30\.48"` across every
`.md`/`.txt`/`.py`/`.yaml`/`.sql` file) — **zero matches.** The stale SJMC 20.30.460/470/480
numbers were never actually written into any file in this repository; nothing to correct.
The City's own Bulletin #210 (below) is the real, current source used throughout this
package: ADUs are governed by Chapter 20.80 Part 2.75 — City Development Standards at
20.80.175, State Development Standards at 20.80.176, historic-property standards at
20.80.175(E), JADU at 20.80.178.

---

### 2. L5, refuse-first — design, reported before writing

**Where L5 lives.** `docs/LEDGEX_SPEC.md`'s own §2 repository-layout diagram names
`core/rules/ L5` — but that diagram's own text explicitly warns against taking the
directory form literally: *"Three layers have real code as of P21 -- core/store.py (L4),
core/exceptions.py (L6), core/model.py -- each a flat file, not a core/<name>/ directory
the layer diagram below implies... Every other layer below remains unbuilt."* P25 already
established the precedent for what "unbuilt layer, built for real" looks like:
`core/calc.py`, a flat file, not `core/calc/`. L5 follows the identical precedent:
**`core/rules.py`**, a flat file, promoted to a directory only if and when a second
concern inside L5 forces one — not anticipated here.

**Exact signature**:
```python
def select_effective_rule(cur, jurisdiction_id: str, rule_key: str, as_of: date) -> Result[Rule]
```
Matches `core/store.py`/`core/exceptions.py`'s own established convention exactly (`cur`,
not `conn` — confirmed by reading both files' real signatures, not assumed). `Rule` is a
new, small Pydantic model in `core/model.py` (the single place `Fact`/`ParcelException`/
`Refusal` already live, P21's own "one owned object" precedent) — `id`, `rule_key`,
`version`, `citation`, `pack_version`, `effective_from`, `effective_to`, mirroring
`rule`'s own real columns directly, not an invented shape. On no rule effective at
`as_of`, returns `Result.refuse(Refusal(code="RULE_UNAVAILABLE", stage="L5", ...))` —
`RULE_UNAVAILABLE` already a real member of `core/model.REFUSAL_CODES`
(`core/model.py:228`), never before raised by any code, confirmed by grep before this
package. On a match, `Result.ok(Rule(...))` carrying the selected row's real identity.

**I1 compliance, checked not assumed.** `select_effective_rule` itself takes
`jurisdiction_id`/`rule_key` as bare parameters — no jurisdiction name, no rule content,
appears anywhere in `core/rules.py`'s own source, the identical shape
`core/calc.py`'s `geometry_tier_enabled` parameter already uses for the same reason.

**Where the Shape 1 constant legally lives — checked against the actual enforcement, not
assumed.** `build/check_jurisdiction_names.py`'s own `BLOCKLIST` includes the literal
string `"ca_san_jose"`, scoped to `CORE_DIR = ROOT / "core"` — confirmed by reading the
script directly. A `CONCLUSION_RULE_KEYS = {"placement": "ca_san_jose...."}` constant
placed inside `core/rules.py` would contain a blocklisted token and **fail
`make check-boundary`** the moment it landed — this is not a style preference, it is a real
enforcement question with a checkable answer. `check_jurisdiction_names.py`'s own
docstring states the intended boundary plainly: *"scripts/, infra/, jurisdictions/ are
expected to name jurisdictions and source fields; that's their job. Only core/ is supposed
to be free of them."* The constant lives in **`scripts/compose_property_file.py`** — the
exact same home `ingest_parcels.py`/`ingest_zoning_permits.py` already use for their own
jurisdiction-scoped `SOURCE_ID`/`JURISDICTION_ID` constants, not a new precedent.
`compose_property_file.py` is already the caller that owns `jurisdiction_id` (reads it
from the `parcel`/`jurisdiction` tables directly) and is not `core/` — confirmed via
`make check-boundary` after landing (§ close-out), not merely argued.

**Recorded explicitly, per the founder's ratified decision**: `CONCLUSION_RULE_KEYS` is a
**hardcoded, one-jurisdiction, one-conclusion dict — not a general mechanism.** A second
jurisdiction's own rule for the same conclusion forces this exact constant to be rewritten
(at minimum, keyed on `jurisdiction_id` too) — accepted knowingly, now, so a future reader
does not mistake one dict entry for a designed abstraction. `jurisdictions/ca_san_jose/
conclusions.yaml` (§7.4) remains undesigned, unbuilt, and is not what this package builds.

**Built and proven, RED-then-GREEN, before any rule row exists anywhere in the table.**
`core/model.Rule` (a small, frozen Pydantic model mirroring `rule`'s own real columns —
`id`, `jurisdiction_id`, `rule_key`, `version`, `citation`, `pack_version`,
`effective_from`, `effective_to`) and `core/rules.select_effective_rule(cur,
jurisdiction_id, rule_key, as_of) -> Result[Rule]`. `tests/core/test_rules.py`, a real-
database test (`DATABASE_URL`-gated, same shape every other real-DB test in `tests/core/`
already uses) against its own synthetic `test_jurisdiction_p31_l5` fixture: confirmed
GREEN first (passed, 0.20s), then a deliberate bug planted (the refusal branch disabled
via `if False:`) — confirmed RED, `TypeError: cannot unpack non-iterable NoneType object`,
the test catching the break rather than the break silently returning nothing — reverted,
reconfirmed GREEN. `168 passed` for the full `tests/core/` suite afterward (167 before this
package, +1).

**`make check-boundary` run for real, not assumed** — and it earned its keep: the first
draft of this module's own docstrings named a real jurisdiction id and two real property
names in prose (explaining *why* the constant lives elsewhere, and citing precedent by
name) — `build/check_jurisdiction_names.py` correctly failed on exactly those tokens
(`core/rules.py:14`, `:26`, `:50`, `:51`), matching its own documented design ("a docstring
or comment naming the city in prose leaks the same information a literal identifier
does"). Reworded to describe the same reasoning without the literal tokens; re-run,
`JURISDICTION-NAME GREP PASSED -- 6 file(s) under core/ scanned, no blocklisted token
found.`

---
