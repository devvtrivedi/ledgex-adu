## P37 — Re-grade finding #40, then close its live member(s)

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Section 3 reports before writing.

---

### 1. One-line record fix: 0054's other NULL operand

`property_file_election_refusal_consistent(election, refusals)` has two NULL-sensitive
operands. 0054's own header reasoned about `election`'s NULL branch at length and never
mentioned `refusals`. Confirmed, not assumed: `db/schema.sql` shows `refusals jsonb DEFAULT
'[]'::jsonb NOT NULL`, and the live column on `ledgex_schema_check` (`\d property_file`) shows
the identical `not null`. `@>` is therefore total on that operand — the CHECK can never
evaluate to SQL NULL. Added to 0054's own header (a comment-only edit; no database anywhere
reachable from this session has recorded 0054's hash yet, so nothing depends on the file
staying byte-identical — confirmed before editing, not assumed).

---

### 2. Re-grading finding #40's four members

I8's actual text: *"Refusal is a typed return value, not an exception. Every runtime stage can
refuse deterministically."* The test applied to each member: is this a deterministic runtime
condition a stage can refuse, or a caller/programmer error? Not "is `api/` built."

**Line 225, election-vocabulary `ValueError` — CONFIRMED latent.** `election` is validated
against a two-element enum (`KNOWN_ELECTIONS`) at the Python boundary. No caller anywhere in
this codebase can trigger it today: the CLI's own `argparse` (`choices=KNOWN_ELECTIONS`)
already rejects a bad value before `compose()` is ever called; `check_golden.py` and the two
`scripts/test_compose_*.py` scripts pass hardcoded, always-valid literals. Stronger than
"nobody happens to call it wrong" — once `api/` exists (§11: FastAPI + Pydantic), request-shape
validation (is this one of two allowed strings) happens at the Pydantic request-model layer,
*before* `compose()` is ever invoked — a 422, not a call into this function at all. A bad
`election` reaching this `raise` would mean some *other*, non-request caller passed it directly,
which is definitionally the programmer error the code's own comment already names. I8 governs
runtime *stages* refusing a condition about the world (or about coverage/rights); it does not
govern HTTP request-body schema validation, a different, earlier boundary. Confirmed, not
overturned.

**Line 261, `raise SystemExit(f"no parcel with id={parcel_id!r}")`, inside `compose()` —
OVERTURNED. Live today, not latent.** A caller-supplied `parcel_id` that does not resolve is
not a code-contract violation — it is entirely ordinary, data-dependent runtime behavior: a
stale reference, a typo, a fabricated UUID, a reference to a jurisdiction/dataset not currently
loaded. Nothing about `parcel_id`'s validity is knowable from the caller's own contract the way
`election`'s enum membership is. This crashes the whole process *today*, for any caller of
`compose()` — `check_golden.py`, the CLI, a hypothetical future internal script — not merely
once `api/` exists. I8's text is a standing requirement about runtime stages, not a promise
that activates later. Live now.

**Line 333, "has no current facts" `SystemExit`, also inside `compose()` — OVERTURNED. Live
today, same reasoning, but a genuinely different condition from line 261, not graded
identically by default.** A resolved, real parcel with zero current facts (never ingested,
every fact superseded to nothing) is equally a data-dependent runtime condition, not a
programmer error. It differs from line 261 in kind, not merely in severity: line 261 is "the
referenced entity does not exist"; line 333 is "the entity exists but this composer holds no
data for it" — and, load-bearingly for section 4, the two differ in what can be *built* in
response: line 261 has no parcel to attach a `property_file` row to (the FK makes a row
structurally impossible); line 333's parcel is real, so a normal refused row is fully
buildable. Both graded live; each gets its own code and its own construction, not one answer
reused for both.

**`resolve_parcel_id_by_apn`'s own two `SystemExit`s (lines 187/190) — stays latent, and being
outside `compose()` changes the grade, not merely the location.** Neither is ever called by
`compose()` itself — only by `__main__`, the CLI's own convenience layer for a human typing
`--parcel-apn`. A future `api/`'s own L0 stage (address/APN → parcel_id resolution, per §5's
own stage table, with `PARCEL_NOT_FOUND`/`JURISDICTION_UNRESOLVED` already named for exactly
that job) would be new code built for that purpose, not a reuse of this CLI helper — this
function is not in the call graph any request handler would traverse. I8 governs runtime
stages of the compose pipeline; a human-facing CLI convenience wrapper that never sits on that
path is not one. Latent, correctly, and for a different reason than line 225 (line 225 is
latent because no *value* reaching it is exploitable; this is latent because no *caller path*
reaches it at all).

**Finding #40's row re-graded**, not treated as one class of four uniform members: two live
members closed this package (section 4), two members stay open, each with its own argument for
staying latent, not inherited from a blanket "no `api/` yet" excuse.

---

### 3. REPORT — which code(s) for the live members

**Not `PARCEL_NOT_FOUND`.** Checked verbatim before relying on it, not assumed from the name:
`docs/LEDGEX_SPEC.md:1977` (pre-P37) reads `PARCEL_NOT_FOUND | L0 | APN not present in any
parcel layer`. That is an address/APN *resolution* failure — the same L0 family as
`JURISDICTION_UNRESOLVED`. `compose():261` (pre-fix) is a by-ID lookup of an already-internal
`parcel.id` UUID — a condition that presupposes L0 already ran (or was bypassed via
`--parcel-id`), not L0 itself failing. Reusing `PARCEL_NOT_FOUND` would make one code carry two
claims a customer acts on differently — supply a different APN, versus re-check a stored
reference — the same reasoning 0053 used to keep `ELECTION_REQUIRED`/`ELECTION_NOT_SUPPORTED`
separate from `RULE_UNAVAILABLE` rather than folding them in because the name was adjacent.
**New code: `PARCEL_REFERENCE_UNKNOWN`, stage L0** (same stage family as `PARCEL_NOT_FOUND` —
both are "cannot even identify what this composition is about" — but a distinct code, distinct
claim). §9's own `PARCEL_NOT_FOUND` row and text are unchanged — no amendment needed, since its
scope was never wrong, only insufficient for a condition it never claimed to cover.

**"No current facts" gets its own answer, not the same one by default.** `COVERAGE_GAP`
("A required field could not be retrieved") and `INSUFFICIENT_COVERAGE` ("Too many required
fields unmet for the file to be meaningful") both presuppose a *required-fields* mechanism —
checked directly: this minimal composer has never built one (`unmet_fields` is written
`NULL`/empty by every caller today, no code anywhere computes "required fields for this
channel/conclusion"). Reusing either would assert a mechanism that does not exist — the same
invented-semantics risk finding #35/#36 already warned against for a different pair of codes.
Zero facts is a distinct, *prior* condition: not "some coverage, judged insufficient" but "no
coverage attempted or recorded at all." **New code: `PARCEL_NO_FACTS`, stage L8** (the stage
where "can this file be delivered at all" is decided, the same family `COVERAGE_GAP`/
`INSUFFICIENT_COVERAGE` occupy, without asserting their mechanism).

Two new codes, `db/migrations/0055_parcel_refusal_codes.sql` — same widening shape 0053 used
over 0038/0048.

---

### 4. Build

**Refuse-first, the P25/P31/P34 shape — but "touched" cannot mean the same thing for both live
members, and the design follows from that, not the other way round.**

`property_file.parcel_id` is `NOT NULL REFERENCES parcel(id)`. For `PARCEL_REFERENCE_UNKNOWN`
(the parcel genuinely does not exist), **no row can be written — confirmed, not assumed, and
designed accordingly rather than manufacturing one.** `compose()` returns
`Result.refuse(Refusal(code="PARCEL_REFERENCE_UNKNOWN", stage="L0", ...))` directly, in-memory,
before any cursor write. I6's touched-fact linkage does not apply — nothing was ever read,
because there was never a parcel to read facts *for*.

For `PARCEL_NO_FACTS` (the parcel is real), a row **is** written, following the existing
refuse-first pattern exactly: the new refusal folds into the same accumulating `refusals` list
GEOMETRY_TIER_DISABLED/L5's three outcomes already use (P25: accumulate, never short-circuit),
`touched` stays the empty list it genuinely is, the L8 rights-loop over zero touched facts
naturally produces zero `RIGHTS_BLOCKED` entries (nothing to block), and
`property_file_fact`'s own insert (`execute_values` over an empty list — confirmed directly,
not assumed, that psycopg2 handles this with no error) writes zero link rows. This is the
honest state, not a workaround: "touched" means exactly what it always meant, and here it is
correctly empty.

**`compose()`'s own return type gains a third shape**, documented in its own docstring:
`Result.refuse(...)` (no row, the one case above), `str` (a row was written — every other
refusal, unchanged), `None` (rights gate passed, nothing written — unchanged; `Result.ok(None)`
is itself structurally invalid per `core.model.Result.__init__`'s own guard, so this state was
never expressible as a `Result` and still is not). `__main__` updated to check
`isinstance(result, Result)` first.

**RED-first, on a real database, against the actual pre-P37 code, not inferred:**
```
$ python3 -c "... pre-P37 compose(), nonexistent parcel_id ..."
CONFIRMED RED: SystemExit raised: no parcel with id='9c212fa4-...'

$ python3 -c "... pre-P37 compose(), real parcel, zero facts ..."
CONFIRMED RED: SystemExit raised: parcel 55d2f827-... (apn='TEST-P37-RED-NOFACTS') has no
current facts -- nothing to compose or gate
```
GREEN, fixed code, same two scenarios:
```
PARCEL_REFERENCE_UNKNOWN: code=PARCEL_REFERENCE_UNKNOWN stage=L0, property_file row count: 0
PARCEL_NO_FACTS: property_file WRITTEN, codes=['GEOMETRY_TIER_DISABLED', 'PARCEL_NO_FACTS',
'RULE_UNAVAILABLE'], property_file_fact link count: 0
```
Permanent script test `scripts/test_compose_parcel_refusals.py` (real database, wired into
`db.yml` after `scripts/test_compose_election.py`), all assertions passing.

**Vocabulary widened**: `db/migrations/0055_parcel_refusal_codes.sql`, `core/model.py`'s
`REFUSAL_CODES` (23 codes now), `build/qa_check.py`'s `REFUSAL_CODE_MIGRATION` moved 0053 →
0055. Three new invariants (T103–T105): T103/T104 positive controls (the widened function
accepts each new code — T103 proves the *schema-level* vocabulary independent of whether
`compose()` itself ever writes that shape, since `PARCEL_REFERENCE_UNKNOWN` never does); T105
a fresh-literal negative control, T98's own lesson repeated — a widening that silently became
"accept everything" would leave every earlier rejection test green too, since none of them
assert anything about the vocabulary's *size*. Floor 119 → 122.

**Does `make golden` need a fixture? No, for two different reasons, not one default.**
`PARCEL_REFERENCE_UNKNOWN` produces no `property_file` row at all — there is structurally
nothing for golden's row-comparison mechanism to capture; the question does not apply the way
it applied to `election_required`. `PARCEL_NO_FACTS` *does* produce a row, so the question is
real, but `check_golden.py`'s own `make_fixture_parcel_and_fact()` is hard-coded to always
insert exactly one fact alongside its fixture parcel — supporting a zero-fact fixture would
require new golden-script infrastructure (a fact-less fixture builder) that does not exist
today, unlike `election_required`, which reused every existing piece of `check_golden.py`'s
machinery with just a different `election` argument. Building that infrastructure now, for one
edge case, would be exactly the anticipatory scope creep CONVENTIONS discourages when the
established alternative (a real-database script test, `ELECTION_NOT_SUPPORTED`'s own
precedent) already provides equivalent, real coverage. Not left silently uncovered — recorded
here as the explicit reason, per instruction.

**Spec bump 1.43 → 1.44** (§3.12 new paragraph for 0055, §9 two new rows placed by stage
family, §12 row), `.txt` rename verified by hash before committing. `make qa` clean, including
the refusal-code vocabulary sync.

---

### 5. Close-out

`make migrate-verify`, `make schema-dump` clean, `make test`, `make golden`, `make conformance`,
`make check-boundary` (`make qa` included) all green on a fresh migrations-only database.
`make db-test`: 122/122, exit 0. Both acceptance suites twice each, each against its own fresh
database. All four `db.yml`/`docs.yml` jobs to be confirmed green on the close-out commit.
