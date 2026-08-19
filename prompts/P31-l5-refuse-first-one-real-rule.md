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

### 3. One real rule, sourced from Bulletin #210

**The ordinance text itself could not be read — real, repeated attempts, not a shortcut.**
Before the founder supplied Bulletin #210 directly, six real URLs across four distinct
sources were tried and failed: `records.sanjoseca.gov`'s direct ordinance PDF (302-redirects
to a dead generic page), Municode's live viewer and an Internet Archive snapshot of the same
page (both an unrendered Angular SPA shell, ~6-7KB, no ordinance text without client-side
JS execution), `sanjoseca.gov`'s own ADU pages (403 to automated fetches), a third-party PDF
mirror (also 403). Recorded as finding #34 (`prompts/README.md`), status **Open** — not a
defect this package can close, a real external-access gap that stays open until the
ordinance text itself becomes reachable.

**Bulletin #210, read directly, page 3** (full content in
`jurisdictions/ca_san_jose/evidence/bulletin-210-adu-universal-checklist-2026-03-05.pdf`,
committed `6dca93c`): City of San José, Planning/Building/Code Enforcement, "ADU Universal
Checklist," header `BULLETIN #210 UPDATED 03/05/2026 SUBJECT TO CHANGE`. Part 3's table,
Single-Family Properties, City Development Standards, Detached ADU (New or Conversion),
Maximum Height cell: `1st Story: 18 ft` / `2nd Story: 25 ft`, Maximum # Stories: `2`.

**The one real rule seeded** (`db/seeds/day4_sources.sql`, `ON CONFLICT (id) DO NOTHING`,
same idempotent shape every other row in that file already uses):

| Column | Value |
|---|---|
| `id` | `ca_san_jose.adu_detached_max_height_city_standards.v1` |
| `jurisdiction_id` | `ca_san_jose` |
| `rule_key` | `adu.detached.max_height.city_standards` — names the **City** regime explicitly (finding #35), never the universal answer |
| `version` | `1` |
| `effective_from` | `2026-03-05` — the bulletin's own `UPDATED` date, i.e. the date the City *published* this standard, explicitly NOT a claim about the ordinance's own legal effective date (unknown) |
| `effective_to` | `NULL` |
| `citation` | `City of San José Bulletin #210, "ADU Universal Checklist," updated 03/05/2026, Part 3 (Single-Family Properties, City Development Standards, Detached ADU) -- summarizing San José Municipal Code Section 20.80.175, not its verbatim text.` |
| `params` | `{"first_story_max_ft": 18, "second_story_max_ft": 25, "max_stories": 2}` |
| `source_text_uri` | `https://github.com/devvtrivedi/ledgex-adu/blob/6dca93c.../jurisdictions/ca_san_jose/evidence/bulletin-210-....pdf` |
| `review_mode` | `solo_founder_attestation` (`reviewed_by = authored_by`, both `devtrivedi06@gmail.com`) |
| `attestation_uri` | `https://github.com/devvtrivedi/ledgex-adu/blob/6dca93c.../jurisdictions/ca_san_jose/evidence/attestation-....md` |

**What `attestation_uri` resolves to, and what a reader in 2030 does with it**: the exact,
byte-identical attestation file committed alongside the bulletin in `6dca93c` — a plain-text
record of what was read (the bulletin's page 3 cell, named precisely), what is and is not
claimed (the bulletin was read directly; §20.80.175 itself was not), and why the bulletin is
admissible now. Resolving it requires nothing but this repository's own git history — no
account, no external service, no retention policy to outlive; `git show
6dca93c...:jurisdictions/ca_san_jose/evidence/attestation-....md` (or the GitHub blob URL
stored in the column) returns the identical bytes forever, by construction.

**Verified against a fresh scratch database, seed applied end to end**: `db/seeds/
day4_sources.sql` run against a freshly-migrated database — the rule row inserted cleanly,
`SELECT` confirms all values match the table above exactly.

**0013's `rule_no_update`/`rule_no_delete` triggers, fired against a real row for the first
time ever — proven directly, exact exception text shown, not summarized:**

```
UPDATE rule SET citation = 'tampered' WHERE id = 'ca_san_jose.adu_detached_max_height_city_standards.v1';
ERROR:  I18 violated: rule ca_san_jose.adu_detached_max_height_city_standards.v1 is
immutable. Only effective_to may be set (NULL -> a date, once). A correction is a new
rule row at version + 1, never an UPDATE.

DELETE FROM rule WHERE id = 'ca_san_jose.adu_detached_max_height_city_standards.v1';
ERROR:  I18 violated: rule ca_san_jose.adu_detached_max_height_city_standards.v1 cannot
be deleted. A correction is a new rule row at version + 1, never a DELETE.
```

The legitimate one-way transition also confirmed, on the same real row, both directions:
`UPDATE ... SET effective_to = '2027-01-01'` succeeded once; a second attempt to change it
again (`'2028-01-01'`) was rejected with the identical "already set" exception `db/tests/
invariants.sql`'s own synthetic I18e test already asserts.

**`db/tests/invariants.sql` checked, not assumed to be missing this coverage**: it already
carries five real tests for exactly this trigger pair — I18a (UPDATE `reviewed_by`
rejected), I18b (UPDATE `params` rejected — proves every column is locked, not just review
evidence), I18c (DELETE rejected), I18d (the one legitimate `effective_to` transition
succeeds), I18e (a second `effective_to` change is rejected) — against synthetic `test-i18*`
fixture rows, the same convention every other test in that file uses (real production data
is never a target for a destructive-attempt test in a suite that must also run, unmodified,
against CI's own fresh migrations-only database, where this real rule row does not exist at
all). **Not lacking, so no new invariants.sql test was added and the 108-test pass floor is
unchanged** — what is genuinely new is not more test coverage of the mechanism, but the
first real, non-synthetic row for that already-proven mechanism to protect, demonstrated
directly above.

**`RULE_UNAVAILABLE` proven for the right reason, both branches of the window, against the
real row — not an empty table masquerading as one:**

```
select_effective_rule(cur, "ca_san_jose", "adu.detached.max_height.city_standards", 2026-01-01)
  -> REFUSED: No rule effective for jurisdiction_id='ca_san_jose',
     rule_key='adu.detached.max_height.city_standards' as of 2026-01-01.
     (before effective_from 2026-03-05 -- the real row exists, the window excludes it)

select_effective_rule(cur, "ca_san_jose", "adu.detached.max_height.city_standards", 2099-01-01)
  -> OK: Rule(id='ca_san_jose.adu_detached_max_height_city_standards.v1', version=1,
     citation='...', effective_from=2026-03-05, effective_to=None)
     (GOLDEN_AS_OF -- see section 4)
```

---
