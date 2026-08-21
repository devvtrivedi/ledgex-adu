## P41 — P40 review fixes

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Prompt as issued:
`LEDGEX-P41-P42-FIX-PROMPTS.txt` names this as its first prompt (repo root, unmodified).
Baseline: P40's own uncommitted working tree (`api/`,
`scripts/seed_internal_test_licences.py`, plus P39's still-uncommitted changes to
`infra/env.py` and `scripts/compose_property_file.py`). Nothing in this repo is committed
anywhere in this chain — this package changes `api/main.py` and `api/static/viewer.html`
only, on top of that same uncommitted tree.

**Not committed.** Working tree only, per CONVENTIONS' "a delegated agent reports; it does
not commit or push to `main` on its own."

**Read first, per CLAUDE.md:** `docs/LEDGEX_SPEC.md` §1 (all 20 invariants, §1.1), §4, §9 —
all already read in full earlier this same session (P39/P40); re-confirmed against the exact
lines cited below rather than re-read cold, since the file has not changed.

---

### 1. What was actually wrong — four fixes, verified independently before writing anything

#### Fix 1 — `/v1/exceptions`'s `outcome` documents a fake vocabulary and isn't validated

Confirmed. Live `exception_outcome` enum, read from a real database (`ledgex_p40_gate1`),
not transcribed from this prompt or any migration comment:

```
SELECT enum_range(NULL::exception_outcome);
{open,confirmed,false_positive,unresolved,condition_cleared,version_retired}
```

`true_positive` and `suppressed` (named in the old `Query(...)` description string) are not
members; `confirmed`, `unresolved`, `condition_cleared`, `version_retired` (real members) were
undocumented.

**A correction to this prompt's own RED claim, found by re-verifying rather than trusting
it.** The prompt states the pre-fix behavior for an invalid `outcome` is "`{"data": []}`, HTTP
200." Run directly against a real database, pre-fix, that is not what happens:

```
$ curl -s -w "\nHTTP %{http_code}\n" "http://127.0.0.1:8421/v1/exceptions?outcome=true_positive"
Internal Server Error
HTTP 500
```

```
psycopg2.errors.InvalidTextRepresentation: invalid input value for enum exception_outcome: "true_positive"
```

`parcel_exception.outcome` is a real Postgres ENUM column, confirmed with `\d parcel_exception`
and by running the raw query directly (`psql ... -c "SELECT count(*) FROM parcel_exception
WHERE outcome = 'true_positive';"` raises the identical error). A bound parameter compared
against an enum column is type-checked at bind time regardless of table contents — this isn't
session-specific, it's how Postgres enums work, so this should be reproducible against any
copy of this schema. The underlying finding (undocumented, unvalidated vocabulary, silently
or loudly wrong either way) is exactly as real either way; only the concrete failure mode
differs (a loud 500, not a silent empty 200) — recorded honestly rather than reproduced to
match the prompt's claim.

**Decision, reported before writing:** `Literal[*KNOWN_EXCEPTION_OUTCOMES]` on the `outcome`
`Query` parameter, giving FastAPI's own validation machinery the boundary check — a 422, not
a hand-rolled 400. Chosen over a manual `ValueError`/`HTTPException(400, ...)` for three
reasons: (a) it is genuinely free — no bespoke validation code, self-documents in `/docs`
automatically; (b) 422 (Unprocessable Entity) is the correct HTTP semantic for "syntactically
fine, semantically not a member of the accepted set," which is exactly this condition, and is
FastAPI's own idiomatic mechanism for it; (c) this app does not claim to implement §4's
contract (P40's own report says so explicitly) and is not bound by §4.1's literal "400" text —
that convention governs the *customer-facing* `api/` §4 describes, not this internal tool.
`KNOWN_EXCEPTION_OUTCOMES` (module-level tuple, §2 below) and the `Literal` type share the
same object via `Literal[*KNOWN_EXCEPTION_OUTCOMES]` (confirmed this unpacking form validates
correctly with Pydantic's `TypeAdapter` before relying on it) — there is exactly one place
this vocabulary is written, not two that could drift, which is the whole shape Fix 1 exists to
avoid repeating.

**`detector_key`/`detector_version`, confirmed still bound parameters, not string-interpolated
— read directly, not assumed:**

```python
    if detector_key:
        clauses.append("detector_key = %s")
        params.append(detector_key)
    if detector_version:
        clauses.append("detector_version = %s")
        params.append(detector_version)
    ...
    cur.execute(f"SELECT ... WHERE {where} ...", params)
```

The f-string only ever interpolates `where`, which is built from the fixed literal strings
`"outcome = %s"` / `"detector_key = %s"` / `"detector_version = %s"` — never a caller-supplied
value. Every actual value flows through `params`, psycopg2's own parameter-binding path.
Unchanged by this package; confirmed, not touched.

#### Fix 2 — `evaluate_rights_gate`'s docstring asserted a check `api/` didn't perform

Confirmed: `grep -n "KNOWN_CHANNELS" api/main.py` returned nothing before this fix (shown
in §2). No live bug — `VIEWER_CHANNEL = "api"` already is a real `output_channel` member —
but a docstring asserting a check happened is testimony, not evidence (CONVENTIONS, verbatim),
and a future reader relies on that sentence being true.

**Took (a), as recommended:** validate `VIEWER_CHANNEL` against `cpf.KNOWN_CHANNELS` at
module import time, `raise SystemExit` on mismatch. One line of real logic. Makes the
docstring's own claim true, and turns a future typo or an enum-membership change into a
loud, immediate startup failure — nothing ever serves a request on an invalid channel,
compared to (b) (correct the docstring to describe a weaker guarantee), which would have left
the actual risk (silently gating real fact values on a channel that doesn't exist) exactly as
unguarded as it was, just honestly described instead of fixed.

#### Fix 3 — four minors in `api/main.py`

**(i) malformed `parcel_id` → 400; well-formed-but-nonexistent → 404, not empty 200.**
Confirmed RED: `GET /v1/parcels/not-a-uuid/facts` → `psycopg2.errors.
InvalidTextRepresentation: invalid input syntax for type uuid` → HTTP 500, and — worth
stating explicitly, per the prompt's own instruction — **contained**: the per-request
connection's `finally` in `_db()` rolled it back and closed it; the *next* request against
the same running server succeeded normally, unlike P39's Finding A/B (a poisoned *shared*
connection killing every subsequent call). The per-request-connection design (§4 of P40's own
report) paid for itself here for real, not just in theory.

Fixed with `uuid.UUID(parcel_id)` in a `try/except ValueError` at the very top of the route,
before any query runs, raising `HTTPException(400, ...)` naming the bad value. For the second
half — well-formed UUID, no such parcel — chose **404**, not an empty 200: this codebase
already draws exactly this distinction one layer down, in `compose_property_file.py` itself
(`PARCEL_REFERENCE_UNKNOWN` vs. `PARCEL_NO_FACTS`, P37/README finding #40) — a parcel that
does not exist is a different, more specific condition than a real parcel with zero current
facts, and collapsing both into one 200 here would erase a distinction the composer already
considers worth keeping. Costs one extra existence-check query (`SELECT 1 FROM parcel WHERE
id = %s`), run before `current_fact_at()`.

**(ii) `FactEnvelopeLite`, declared and unused → wired in as `response_model`.** Not just
`FactEnvelopeLite` alone (the route's real top-level shape is a wrapper: `facts` and
`omitted_for_rights`, two differently-shaped lists, not a bare list of facts) — added
`OmittedForRights` and `ParcelFactsResponse`, and set `response_model=ParcelFactsResponse` on
the route. **A regression this same edit had to catch, not a hypothetical:** `FactEnvelopeLite`
did not declare `is_derived` (the I9 field P40 added). Wiring `response_model` in without
adding it would have made Pydantic silently *strip* `is_derived` from every response —
deleting the I9 derived-fact signal from the API while the code that computes it kept running,
untested, unnoticed. Added `is_derived: bool` to `FactEnvelopeLite` in the same edit; confirmed
present in a real response body in §4/§5 below.

**(iii) named constant, not a bare `0`.** `_db()`'s `if conn.get_transaction_status() != 0:`
→ `!= psycopg2.extensions.TRANSACTION_STATUS_IDLE` (imported `psycopg2.extensions`), matching
`compose_property_file.py`'s own P39 fix for the identical check, verbatim.

**(iv) `/v1/schema`'s unguarded `re.match(...).group(1)` → handled explicitly.** Confirmed
latent, not live, against the real tree before touching it (all 55 files on disk match the
convention). Chose skip-and-report: non-matching filenames are collected into a new
`unrecognized_files` list, returned in both response branches (ledger-present and
ledger-absent), and surfaced in the HTML viewer's Schema state screen. Proven with a real
temporary file, removed immediately after (§2 below) — `db/migrations/` is unchanged from
before this test (`ls | wc -l` → 55, same as before).

#### Fix 4 — the `api/ → scripts/` dependency, recorded, not fixed

Not a code change. Added as its own paragraph to **`prompts/P40-internal-viewer.md`'s Review
findings section** (not its body, per instruction): states that `api/main.py` imports
`compose_property_file` from `scripts/` for `evaluate_rights_gate`, that `.importlinter`
cannot and does not see that edge today (`scripts/` is not in `root_packages`), that this
disappears once finding #45 is repaired and the gate moves to `core/rights.py`, and reports
— without doing — whether `scripts/` should be added to `root_packages` now. **Decided
against, for now:** the dependency is real and D4's own principle argues for tracking it, but
`scripts/` has no `__init__.py` (every file in it, including four working ingest/test
scripts, is imported via `sys.path` manipulation), import-linter's actual handling of that
shape as a `root_packages` entry is untested here, and the blast radius of finding out — every
other file in `scripts/` becoming subject to whatever contract governs it — is wider than the
one import this package cares about. Recorded, not absorbed.

---

### 2. Evidence

**Fix 2, before/after, pure inverse:**

```
$ grep -n "KNOWN_CHANNELS" api/main.py     # BEFORE this package's fix
(no output)
```

Probe: temporarily set `VIEWER_CHANNEL = "not_a_real_channel"`, attempted import —

```
api/main.py's VIEWER_CHANNEL='not_a_real_channel' is not one of
compose_property_file.KNOWN_CHANNELS=('free_snapshot', 'paid_property_file', 'api',
'bulk_export', 'analytics', 'model_training') -- refusing to start. ...
exit: 1
```

Reverted; confirmed the string `"not_a_real_channel"` no longer appears anywhere in
`api/main.py` (grep, not eyeballed) before moving on.

**Fix 1, RED → GREEN, then all six real values, predicted before running:**

```
GREEN (predicted: 422, names the parameter and the six real values)
$ curl -s -w "\nHTTP %{http_code}\n" ".../v1/exceptions?outcome=true_positive"
{"detail":[{"type":"literal_error","loc":["query","outcome"],
"msg":"Input should be 'open', 'confirmed', 'false_positive', 'unresolved',
'condition_cleared' or 'version_retired'", ...}]}
HTTP 422

All six real values (predicted: every one HTTP 200):
open -> HTTP 200
confirmed -> HTTP 200
false_positive -> HTTP 200
unresolved -> HTTP 200
condition_cleared -> HTTP 200
version_retired -> HTTP 200
```

**Fix 3(i), RED → GREEN, plus the unchanged-valid-parcel check, predicted before running:**

```
GREEN malformed (predicted: 400, names the value)
$ curl -s -w "\nHTTP %{http_code}\n" ".../v1/parcels/not-a-uuid/facts"
{"detail":"parcel_id='not-a-uuid' is not a valid UUID."}
HTTP 400

GREEN well-formed, nonexistent (predicted: 404)
$ curl -s -w "\nHTTP %{http_code}\n" ".../v1/parcels/00000000-0000-0000-0000-000000000000/facts"
{"detail":"No parcel exists with id='00000000-0000-0000-0000-000000000000'."}
HTTP 404

Valid parcel (predicted: 200, unchanged shape, is_derived present)
$ curl -s ".../v1/parcels/<real-uuid>/facts"
HTTP 200 -- 30 facts returned, each carrying "is_derived": true|false correctly
(3 of the 30 are method="derived" and read is_derived:true; the other 27 read false)
```

**Fix 3(iv), a real temporary file, removed immediately after:**

```
$ touch db/migrations/README_not_a_migration.sql
$ curl -s .../v1/schema
{"...","unrecognized_files":["README_not_a_migration.sql"],"on_disk_count":55,...}
HTTP 200   -- predicted, no AttributeError, on_disk_count unaffected
$ rm db/migrations/README_not_a_migration.sql
$ ls db/migrations | wc -l
55   -- back to exactly what it was before the probe
```

**Evidence item 5 — the one that matters most.** Re-ran the mixed-parcel check from P40's own
report (parcel `43576680-60bb-45d6-a78f-b6847f9b3967`, real `cc_by_4_0` fact `parcel.apn`
alongside the `internal_test.cc_by_4_0` evidence fact P40 seeded onto it), against the
**post-fix** code, channel `api`:

```json
{
  "facts": [ { "field_key": "internal_test.evidence_field",
               "value": "visible via api (internal_test.cc_by_4_0)", ... } ],
  "omitted_for_rights": [ { "field_key": "parcel.apn", "licence_id": "cc_by_4_0", ... } ]
}
```

Asserted programmatically, not eyeballed — read the real blocked value straight out of the
database (`SELECT value FROM fact WHERE parcel_id = ... AND licence_id = 'cc_by_4_0'` →
`"GOLDEN-REFUSED-FIXTURE"`), then searched the raw serialized response body for that exact
string:

```python
assert blocked_value not in body   # PASS
assert any(f["field_key"] == "internal_test.evidence_field" for f in data["facts"])       # PASS
assert any(o["field_key"] == "parcel.apn" for o in data["omitted_for_rights"])             # PASS
assert not any(f["field_key"] == "parcel.apn" for f in data["facts"])                      # PASS
```

All four pass. Fix 1 and Fix 3 did not weaken the rights gate: the blocked fact's value
appears nowhere in the response body, under any key, and the split is exactly right.

---

### 3. Full gate set, twice, each against its own fresh migrations-only database

TCP DSNs used throughout (`postgresql://postgres:x@127.0.0.1:5432/...`), per this package's
own note that `make migrate-verify` fails against a unix-socket DSN for an unrelated,
pre-existing reason (README finding #44) — not touched here.

```
=== ledgex_p41_gate1 (fresh) ===              === ledgex_p41_gate2 (fresh) ===
  PASS  make schema                             PASS  make schema
  PASS  make migrate-verify (MATCH, 55)         PASS  make migrate-verify (MATCH, 55)
  PASS  make db-test                            PASS  make db-test
  PASS  test_snapshot_race_invariant            PASS  test_snapshot_race_invariant
  PASS  db/seeds/day4_sources.sql               PASS  db/seeds/day4_sources.sql
  PASS  make golden (GOLDEN_ALLOW_RULE_SEED=1)  PASS  make golden (GOLDEN_ALLOW_RULE_SEED=1)
  PASS  test_compose_geometry_tier_used         PASS  test_compose_geometry_tier_used
  PASS  test_compose_election                   PASS  test_compose_election
  PASS  test_compose_parcel_refusals            PASS  test_compose_parcel_refusals
  PASS  make test                               PASS  make test
  PASS  make conformance                        PASS  make conformance
  PASS  make schema-dump                        PASS  make schema-dump
  PASS  lint-imports                            PASS  lint-imports
  PASS  check_jurisdiction_names                PASS  check_jurisdiction_names
  --> 14 passed, 0 failed                       --> 14 passed, 0 failed
```

Both against the real `docker` `postgis/postgis:16-3.4` container (`ledgex`) already running
on this machine, the same one P39/P40 used and the same image `db.yml` itself uses.
`db.yml`/`docs.yml` were confirmed green on the real GitHub Actions runner for baseline
`c52a266` earlier this session (P39; runs `32314117415`/`32314117407`) — not re-checked here,
since no commit has landed since and nothing in this package is CI-wired.

---

### 4. Nothing else found

No additional findings surfaced while making these four fixes beyond the RED-claim
discrepancy already recorded in Fix 1 above (a correction to this prompt's own evidence, not
a new code defect). Everything else matched what the prompt described, verified independently
before being acted on.

---

### Review findings

*(empty — appended after review)*
