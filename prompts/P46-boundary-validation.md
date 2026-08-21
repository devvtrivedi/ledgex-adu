# P46 — boundary validation

Baseline: `main` at `e6cdf64`. **P45 has not landed on `main`** — it exists only
on the unmerged branch `p45-ingest-provenance`, per that package's own explicit
boundary ("`main` is not touched," merge decision left to the dispatching
session). P46 touches neither file P45 touched (`scripts/ingest_parcels.py`,
`scripts/ingest_zoning_permits.py`, `scripts/audit_snapshot_provenance.py`,
the two acceptance runners) nor `prompts/README.md`'s findings #46/#47, which
exist only on P45's own branch — so this package branches directly off `main`
at `e6cdf64`, not off `p45-ingest-provenance`.

**Cross-branch numbering note, stated explicitly because it isn't visible from
this branch's own copy of `prompts/README.md` (which stops at #45):** P45 (the
same working session, immediately prior) already claimed findings #46 and #47
on its own branch. Reading *this* branch's table alone would suggest #46 is
free; it is not, once both branches are eventually merged. This report uses
#48/#49 to avoid a collision the dispatching session would otherwise have to
resolve by hand at merge time. If P45 is abandoned rather than merged, or
merges with different numbers, these two rows need renumbering — flagged here
so that renumbering isn't a surprise.

Branch: `p46-boundary-validation`, cut from `main` at `e6cdf64`.

## 0. Decisions, reported before writing

**FIX 1 approach.** Reuse P41's own `Literal[*KNOWN_X]` pattern exactly —
a module-level tuple read live from the database (`SELECT enum_range(NULL::
job_status)`), the parameter's type changed to `Literal[*KNOWN_JOB_STATUSES]
| None`. No new mechanism invented; this is deliberately the same shape as
`get_exceptions`' own `outcome` parameter, 25 lines away in the same file.

**FIX 2 — what stops instance #4.** Conclusion, argued in full in section 2:
**nothing new beyond FIX 1's own pattern.** The full enumeration below found
exactly one unvalidated enum-backed parameter in the entire file; both of the
file's enum-backed parameters are now `Literal`-validated against a tuple
sourced from a live `enum_range()` query, and P39's own argument against a
`qa_check.py` diff for `KNOWN_CHANNELS` (drift is impossible without a
migration, and a migration already gets reviewed) transfers cleanly to
`job_status` and `exception_outcome` — neither is any less immutable outside
a migration than `output_channel` was.

**FIX 3 — docstring only, not a behavior change.** Argued in full in section 3.
Making the invalid-channel exit also roll back `conn` would mean `compose()`
reaching into and discarding a caller's own pre-existing, uncommitted
transaction as a side effect of a validation error detected before `compose()`
has done any work — a *stronger* claim on the caller's connection than today's
code makes, not a weaker one, and none of the five real call sites need it.

## 1. FIX 1 — `/v1/job-runs`'s `status`

`api/main.py`, `KNOWN_JOB_STATUSES` (new module-level constant, next to the
pre-existing `KNOWN_EXCEPTION_OUTCOMES`): read live —
`SELECT enum_range(NULL::job_status)` against `ledgex_schema_check` returned
`{running,succeeded,failed,skipped_unchanged}`, matching the description
string the route already carried (that string was already accurate; the type
enforcing it did not exist). `get_job_runs`'s `status` parameter changed from
`str | None` to `Literal[*KNOWN_JOB_STATUSES] | None`, `Query`'s description
built from the same tuple (`f"filter: {'|'.join(KNOWN_JOB_STATUSES)}"`) so the
accepted values and the documented ones can never disagree.

Not graded a refusal per §9: a malformed query string is §9's own
"invalid-request (400)" (FastAPI's `Literal` validation actually returns 422,
Starlette's own convention for a request-validation failure — still squarely
in the error/4xx class §9 draws the line at, not a business answer about
property data).

## 2. FIX 2 — enumerating the whole class

Every route in `api/main.py`, every caller-supplied parameter (path, query;
no route in this file has a body), enumerated from the route definitions
themselves, not from a `grep 'Query('` count (that grep returns 2; the real
count of caller-supplied parameters across the file is 6, across 3 routes —
the other 5 routes take none):

| Route | Parameter | Kind | Reaches | Validated? | Where / against what |
|---|---|---|---|---|---|
| `GET /` | — | — | — | n/a | no parameters |
| `GET /v1/rights` | — | — | — | n/a | no parameters |
| `GET /v1/sources` | — | — | — | n/a | no parameters |
| `GET /v1/job-runs` | `status` | Query, optional | `job_run.status` (enum `job_status`) | **Was not — FIX 1, this package** | Now `Literal[*KNOWN_JOB_STATUSES]`, tuple read live from `enum_range(NULL::job_status)` |
| `GET /v1/exceptions` | `outcome` | Query, default `"open"` | `parcel_exception.outcome` (enum `exception_outcome`) | Yes — P41 Fix 1 | `Literal[*KNOWN_EXCEPTION_OUTCOMES]`, tuple read live from `enum_range(NULL::exception_outcome)`; re-confirmed live this package, unchanged: `{open,confirmed,false_positive,unresolved,condition_cleared,version_retired}` |
| `GET /v1/exceptions` | `detector_key` | Query, optional | `parcel_exception.detector_key` (`text`, **not** an enum) | Yes, trivially | No enum exists to violate; any string is a legal bound comparison, matches zero rows or some — confirmed live: `?detector_key=totally_made_up_key` → `200 {"data":[]}`, never an error |
| `GET /v1/exceptions` | `detector_version` | Query, optional | `parcel_exception.detector_version` (`text`, **not** an enum) | Yes, trivially | Same as `detector_key` — plain text column, no enum |
| `GET /v1/property-files` | — | — | — | n/a | no parameters |
| `GET /v1/parcels/{parcel_id}/facts` | `parcel_id` | Path, required | Cast to `uuid` (function argument inside `current_fact_at`, not an enum column) | Yes — P41 Fix 3(i) | Explicit `uuid.UUID()` boundary check (400 if malformed) + existence `SELECT` (404 if absent) before `current_fact_at()` ever runs; confirmed live: malformed → `400 {"detail":"parcel_id='not-a-uuid' is not a valid UUID."}`; well-formed but absent → `404 {"detail":"No parcel exists with id=...."}` |
| `GET /v1/parcels/{parcel_id}/facts` | `as_of` | Query, optional | Plain `timestamptz` argument to `current_fact_at(ts)` — **not an enum column at all** | Yes, by framework type coercion | Pydantic/FastAPI's own `datetime.datetime` parsing rejects a malformed value automatically; confirmed live: `?as_of=not-a-date` → `422`, `"msg":"Input should be a valid datetime or date, invalid character in year"` — no bespoke code exists or is needed |
| `GET /v1/schema` | — | — | — | n/a | no parameters |

**Result: exactly one gap existed in the whole file (`/v1/job-runs`'s
`status`), now closed. Every other caller-supplied value either touches no
enum at all, is already validated at the boundary by an explicit check
(`parcel_id`), or is already validated by the same `Literal` pattern this
package just extended to the one remaining case.** "Already fine" is reported
with its own live evidence above, not asserted.

**What stops instance #4 — options weighed:**

- **(a) A shared constant + validation helper.** Considered and rejected: there
  is no repeated *logic* to extract. `Literal[*KNOWN_X]` **is** the validation
  mechanism; there is no bespoke code around it to factor into a helper
  function. The repeated element is a *convention* (name the tuple `KNOWN_X`,
  read it live via `enum_range()`, comment where it came from), and that
  convention now has two live, working examples sitting in the same file —
  the artifact a future author would actually copy from is already there.
- **(b) A `qa_check.py` diff against live enums.** Considered and rejected,
  and P39's own argument for rejecting this shape for `KNOWN_CHANNELS`
  transfers cleanly: `job_status` and `exception_outcome`, like
  `output_channel`, are Postgres enums — immutable outside a forward-only
  migration (CLAUDE.md), and every migration in this repo already goes
  through review. A diff check would only ever fire on a migration that added
  or removed a member without a matching Python update — the exact drift
  CLAUDE.md's own migration discipline already exists to catch, one layer up.
  The opposite failure (Python ahead of the database — impossible; nothing
  writes an enum member from Python) doesn't exist, and the failure this
  *would* catch already self-announces: a caller trying a newly-added, DB-valid
  member gets an incorrect 422 naming the *old*, stale member list — loud,
  user-visible, not silent.
- **(c) A test that walks the routes and asserts every enum-backed parameter
  rejects a non-member.** Considered, and this is the one genuinely close
  call. Proving FastAPI's own request-validation layer actually rejects a bad
  value (not just that the Python type annotation reads `Literal[...]`)
  requires exercising the real ASGI/Starlette pipeline — calling the route
  function directly, the way `scripts/test_viewer_rights_gate.py` already
  does for the rights gate, does **not** work here: Python does not enforce
  `Literal` at runtime, so a direct function call would pass a bad string
  straight through and prove nothing about the boundary this fix actually
  added. That leaves `fastapi.testclient.TestClient`, which needs `httpx` —
  and this codebase has already explicitly declined that exact dependency
  once, for the identical tradeoff, in `test_viewer_rights_gate.py`'s own
  docstring ("without adding a new test-only HTTP client dependency... just to
  reach code this script can call directly"). Adding it now, for a class that
  the enumeration above shows has exactly two members, both already fixed,
  isn't proportionate: the dependency cost is real and paid forever; the
  protection bought is "catches a future author who writes `str | None`
  instead of copying either of the two `Literal[*KNOWN_X]` examples already
  sitting in this file" — a mistake code review already catches on sight (a
  bare `str` type next to two `Literal[...]` ones is visually different).
- **(d) Nothing further — the class is small, bounded, and now swept.**
  Chosen. Two enum-backed caller-supplied parameters exist in this ~460-line
  file, both now validated the same way, both tuples read live and commented
  with where they came from. A future third one has two working examples to
  copy in the same file it would be added to.

**RED/GREEN for "whatever FIX 2 lands":** FIX 2's own conclusion is that no
new mechanism is warranted beyond FIX 1's `Literal` addition — so there is no
separate FIX-2-specific guard to break. FIX 1's own guard (`status`'s
`Literal[*KNOWN_JOB_STATUSES]`) is the thing that exists, and section 4 shows
it broken (pre-fix, real 500) and fixed (post-fix, real 422) against the
running viewer.

## 3. FIX 3 — `compose()`'s two exit paths, a downgrade

**What the review reported (Medium):** "invalid `channel` can leave a caller
transaction open. Validation occurs before the rollback `finally` block."

**What is actually true, checked against the real code
(`scripts/compose_property_file.py:379` before this package's edit, now
further down after the docstring grew):** the `raise ValueError` for an
unknown channel fires *before* `try:`, so the `finally` rollback does not run
on that path — that half of the review's claim is correct. But nothing is
*poisoned* by this. Before P39 (README finding #42), an invalid channel
reached the `licence_channel` query and left the connection in
`TRANSACTION_STATUS_INERROR` — an aborted transaction that broke the *next*
call with `InFailedSqlTransaction`. That was the bug P39 closed, by moving the
check to the boundary, before `conn` is touched at all. Today, the
invalid-channel path doesn't open, commit or roll back anything — it leaves
`conn` in exactly the state the caller already had it in. `compose()` does not
roll back a transaction it never opened, and does not leave one aborted
either. The placement is deliberate; P39's own error message
(`scripts/compose_property_file.py`, the `ValueError` text itself) already
argues for it.

**What was actually wrong, and is the real, narrower defect:** the docstring's
first paragraph claimed one uniform guarantee ("this function never returns,
and never raises, leaving a transaction open on `conn`") covering both exits.
That is true of the *valid*-channel exit (the `try/finally` ends whatever
transaction is open, unconditionally) and not a meaningful claim about the
*invalid*-channel exit, which never opens the `try/finally` at all — a reader
who internalized "compose() ends the transaction" would be wrong about the
second exit specifically: if a caller had its own uncommitted work open
*before* calling `compose()` with a bad channel, that work stays open,
untouched, after the `ValueError` propagates.

**Fix applied:** docstring only, no behavior change. The opening section now
describes both exits explicitly (quoted in full from the real diff):

> THIS WRAPPER HAS TWO EXITS WITH DIFFERENT TRANSACTION GUARANTEES, not one
> uniform guarantee — read both before assuming either applies to the other:
>
>   - VALID channel (in KNOWN_CHANNELS): ... this wrapper's own `finally` ends
>     whatever transaction is left open on `conn` before compose() returns...
>   - INVALID channel (not in KNOWN_CHANNELS): raises ValueError BEFORE the
>     try/finally begins... compose() does not open, commit or roll back
>     anything on this path...

and the `PRECONDITION ON THE CALLER` paragraph is now explicitly scoped to the
valid-channel exit ("the invalid-channel exit touches no transaction at all,
so it carries no such precondition").

**Why behavior was NOT changed instead (the option the prompt asked to weigh):**
making the invalid-channel exit also roll back `conn` would mean `compose()`
reaching into and discarding whatever transaction the *caller* had open,
purely because of an input-validation error `compose()` detected before doing
any of its own work — a *stronger*, more surprising claim on the caller's
connection than the current code makes, not a weaker one. None of the five
real call sites (`check_golden.run_composition`, `test_compose_election._seed`,
`test_compose_parcel_refusals` (both call sites),
`test_compose_geometry_tier_used._seed`) need this: an invalid channel
reaching `compose()` today is a hardcoded-literal programming error, caught in
development, not a runtime condition arriving from outside that a caller's own
transaction discipline needs to be defended against.

No behavior changed; every one of `test_compose_election.py`,
`test_compose_geometry_tier_used.py`, `test_compose_parcel_refusals.py`,
`test_compose_collision_invariant.py` still passes unmodified (section 4).

## 4. Evidence

All evidence gathered against a local, throwaway database
(`ledgex_p46_viewer`, created and dropped in this session) and the real,
running viewer (`uvicorn api.main:app --host 127.0.0.1 --port 8420`), never
exposed beyond localhost. As with P45, every "before" run below was gathered
by `git stash`-ing this branch's own fix, restoring `main`'s already-unfixed
code, then `git stash pop` to restore it — never a committed broken version.

### 4.1 `status=succeded` — the 500, then the 422

Fixture: `job_run` seeded with one row per real `job_status` member (running
x1, succeeded x2, failed x2, skipped_unchanged x1 — six total).

**Prediction (before):** an unhandled
`psycopg2.errors.InvalidTextRepresentation`, surfacing as HTTP 500.

**Observed**, real response against the running (unfixed) viewer:
```
HTTP/1.1 500 Internal Server Error
content-type: text/plain; charset=utf-8

Internal Server Error
```
Server-side traceback (uvicorn log), confirming the exact cause:
```
File "/Users/dev/Desktop/ledgex-adu/api/main.py", line 185, in get_job_runs
    cur.execute(...)
psycopg2.errors.InvalidTextRepresentation: invalid input value for enum job_status: "succeded"
LINE 1: ...drift, error, metrics FROM job_run WHERE status = 'succeded'...
```

**Prediction (after):** FastAPI's own `Literal` validation rejects the value
before the route body runs. HTTP 422, `application/json`, naming the
parameter and every accepted value.

**Observed**, real response against the running (fixed) viewer:
```
HTTP/1.1 422 Unprocessable Content
content-type: application/json

{"detail":[{"type":"literal_error","loc":["query","status"],
"msg":"Input should be 'running', 'succeeded', 'failed' or 'skipped_unchanged'",
"input":"succeded", ...}]}
```
Matches both predictions exactly.

### 4.2 Every real member still filters correctly

Against the fixed viewer, real counts against the six-row fixture:
```
status=running             -> count: 1  ['running']
status=succeeded            -> count: 2  ['succeeded', 'succeeded']
status=failed                -> count: 2  ['failed', 'failed']
status=skipped_unchanged     -> count: 1  ['skipped_unchanged']
status omitted (unfiltered)  -> count: 6  ['failed','failed','running','skipped_unchanged','succeeded','succeeded']
```
Every count matches the fixture exactly; omitting `status` still returns the
full, unfiltered list.

### 4.3 The rest of the enumeration table, confirmed live (not assumed)

```
as_of=not-a-date                          -> 422, "invalid character in year"
parcel_id=not-a-uuid                      -> 400, "is not a valid UUID"
parcel_id=00000000-...-000000000000       -> 404, "No parcel exists with id=..."
outcome=bogus (exceptions)                -> 422, literal_error naming all six real members
detector_key=totally_made_up_key          -> 200, {"data":[]}  (never an error -- no enum to violate)
```

### 4.4 `make viewer-test`

Seeded `scripts/seed_internal_test_licences.py` (opt-in,
`SEED_INTERNAL_TEST_LICENCES=1`) against the same fixture database, then:
```
[PASS] facts[] is non-empty (the seed's own permitted rows)
[PASS] omitted_for_rights[] is non-empty (P42's own blocked fixture)
[PASS] the blocked entry cites the REAL cc_by_4_0 licence
[PASS] no permitted fact carries the real cc_by_4_0 licence
[PASS] blocked sentinel value does not appear anywhere in the serialized response

All assertions passed
VIEWER-TEST EXIT: 0
```

### 4.5 `compose()`'s own test suite, confirming FIX 3 changed no behavior

Run against a fresh, independently seeded database
(`ledgex_p46_compose_check`):
```
test_compose_collision_invariant.py   -> PASS, exit 0
test_compose_election.py              -> All assertions passed, exit 0
test_compose_geometry_tier_used.py    -> All assertions passed, exit 0
test_compose_parcel_refusals.py       -> All assertions passed, exit 0
```

## 5. Boundaries respected

No schema change, no migration, no new refusal code — §9 was read, not
touched. `/v1/job-runs`'s `status` rejects a bad value as a 422
(invalid-request), never as a refusal; no new §9 row was invented. No route's
behavior changed beyond rejecting a value that could previously only ever
have 500'd (the `status` case) — every already-valid value for every
parameter still behaves exactly as before (section 4.2). The viewer's posture
is unchanged: 127.0.0.1 only, no auth, `VIEWER_CHANNEL="api"` untouched, LD-1
untouched. `evaluate_rights_gate` was not read for modification, only
enumerated as "no parameter reaches it" (it takes no caller-supplied enum
parameter at all — `channel` is `VIEWER_CHANNEL`, a module constant, never a
query parameter, per D1). `main` was not touched.

## Review findings

(none yet — filled in by review)
