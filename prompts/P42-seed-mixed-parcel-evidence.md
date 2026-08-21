## P42 — the seed produces its own mixed-parcel proof

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Prompt as issued:
`LEDGEX-P41-P42-FIX-PROMPTS.txt`, second of its two prompts (repo root, unmodified).
Baseline: P40's uncommitted working tree, plus P41's fixes to `api/main.py` (both already
uncommitted, still working-tree-only).

**Not committed.** Working tree only, per CONVENTIONS' "a delegated agent reports; it does
not commit or push to `main` on its own." Changed: `scripts/seed_internal_test_licences.py`.
New: `scripts/test_viewer_rights_gate.py`. A Review findings section appended to
`prompts/P40-internal-viewer.md` (its body untouched).

**Read first, per CLAUDE.md:** `docs/LEDGEX_SPEC.md` §1 in full, §1.1 especially — already
read in full earlier this session (P39/P40/P41); re-confirmed against §1.1's own line ("a
fact used to resolve jurisdiction participates in composition even if it is not rendered")
rather than re-read cold, since the file has not changed.

---

### 1. What was actually wrong, verified before writing anything

P40's own headline proof — one parcel, one channel, a real blocked fact next to a permitted
`internal_test` fact — was real but not reproducible from the seed script alone. Confirmed
directly, not inferred: fresh migrations-only database, `db/seeds/day4_sources.sql` applied,
`scripts/seed_internal_test_licences.py` run with its opt-in set, then `GET
/v1/parcels/<seeded parcel>/facts`:

```json
{ "facts": [ {"field_key": "internal_test.viewer_field_cc0", ...},
             {"field_key": "internal_test.viewer_field_cc_by_4_0", ...} ],
  "omitted_for_rights": [] }
```

Empty. The seed's own parcel lived entirely inside `internal_test.viewer_demo` and carried
only `internal_test.*` facts — nothing for the gate to block. P40's own report already
disclosed the mixed parcel was hand-built ("plus one additional evidence-only fact ...
inserted directly onto ... a different real `ca_san_jose` parcel"), so this was never a false
claim — but the report's closing sentence ("reproducible by any reader with `DATABASE_URL`
pointed at a seeded database") was not true until this package.

**The gate itself was never in question.** §0 of the source prompt already re-proved it
independently (planting a real `cc_by_4_0` fact onto the seeded parcel by hand and
re-querying: `internal_test.*` facts visible, the planted `cc_by_4_0` fact blocked, its value
absent from the response) before asking for this fix — this package is "make the seed produce
that parcel by construction," not a bug hunt.

---

### 2. The fix

`scripts/seed_internal_test_licences.py` now plants exactly one additional fact — the
"blocked fixture" — on the SAME demo parcel it already creates, alongside the two
`internal_test.*`-licensed facts it already seeded:

- `source_id`, `snapshot_id`, `field_key`: all fresh `internal_test.*` rows this script owns
  (`internal_test.viewer_source_blocked_fixture`, a matching snapshot, `internal_test.
  viewer_field_blocked_fixture`) — exactly like every other row in the script.
- `licence_id`: the literal string `cc_by_4_0` — the real licence's own primary key, cited
  the same way any other fact in this database already cites it. **This is the only thing
  about the fixture that touches anything real**, and the script's own docstring says so in
  those words, precisely because "seeds a real licence" reads alarming without that sentence
  next to it. No `licence` or `licence_channel` row belonging to `cc0`/`cc_by_4_0` is ever
  written, updated, or read for mutation.
- Value: the sentinel string `"BLOCKED FIXTURE VALUE - MUST NOT RENDER"` — obviously fake,
  greppable, and exactly what §3's assertion (and the new test script) search for.

Constraint satisfied as required: the snapshot's `licence_observed_id` is `cc_by_4_0`
(matching `fact_snapshot_licence_fk`'s (snapshot_id, licence_id) pair), and the new source's
`jurisdiction_id` is `internal_test.viewer_demo` (matching the parcel's own jurisdiction, per
`fact_source_jurisdiction_fk`/`fact_parcel_jurisdiction_fk`).

**The existing parcel-uniqueness idempotency fix (P40) keeps holding, verified, not assumed**
(§3, item 5): the new blocked-fixture rows use the identical `ON CONFLICT DO NOTHING` /
`WHERE NOT EXISTS` pattern the rest of the script already established, and the parcel lookup
is unchanged (`ORDER BY id`, never a bare `fetchone()` on an unordered result).

**The closing summary line, corrected.** It used to say "every fact seeded above IS allowed
on this channel" — no longer true, and leaving it would have reproduced exactly the kind of
overstated claim this package exists to fix. Now: `"{N} fact(s) permitted on 'api' ...; 1
fact BLOCKED on 'api' by the REAL cc_by_4_0 licence, deliberately -- that block is the proof
the gate works, not a bug."`

**`prompts/P40-internal-viewer.md`'s reproducibility sentence — corrected via its own Review
findings section, not by editing its body** (that file is the record of what was actually
built and asked for): states plainly that the sentence was not true before this package, is
true now, and names the exact two-step reproduction (seed, then `GET
/v1/parcels/<id>/facts`) — or the one-line non-interactive form, `scripts/
test_viewer_rights_gate.py` (§4 below).

---

### 3. Evidence

**Item 1 — RED, current (pre-fix) seed, fresh database:**

```
$ (fresh db) → make schema → day4_sources.sql → SEED_INTERNAL_TEST_LICENCES=1 python3 scripts/seed_internal_test_licences.py
$ GET /v1/parcels/9bae0a4c-1d11-4d9c-a782-7975c3b5d8d9/facts
"omitted_for_rights": []
```

Predicted empty; confirmed empty. The proof's own precondition, absent, exactly as claimed.

**Item 2 — GREEN, same procedure, fresh database, after the fix:**

```
$ (fresh db) → make schema → day4_sources.sql → SEED_INTERNAL_TEST_LICENCES=1 python3 scripts/seed_internal_test_licences.py
$ GET /v1/parcels/d29a4119-7012-4dbc-96cd-982938bbb539/facts
"facts": [ {"field_key": "internal_test.viewer_field_cc0", ...},
           {"field_key": "internal_test.viewer_field_cc_by_4_0", ...} ],
"omitted_for_rights": [ {"field_key": "internal_test.viewer_field_blocked_fixture",
                          "licence_id": "cc_by_4_0", "reason": "Licence 'cc_by_4_0' forbids
                          channel 'api' (§7.3, I6) ..."} ]
```

Predicted 2 permitted / 1 blocked (`licence_id=cc_by_4_0`); confirmed exactly.

**Item 3 — the actual I6 assertion, automated, not eyeballed:**

```python
sentinel = "BLOCKED FIXTURE VALUE - MUST NOT RENDER"
assert sentinel not in response_body          # PASS
assert len(data["facts"]) == 2                # PASS
assert len(data["omitted_for_rights"]) == 1   # PASS
assert data["omitted_for_rights"][0]["licence_id"] == "cc_by_4_0"   # PASS
```

All four pass. This same assertion is now also a real, re-runnable script — §4.

**Item 4 — refusal, predicted and confirmed, exit codes shown:**

```
$ python3 scripts/seed_internal_test_licences.py          # no opt-in
refusing to seed internal_test.* licence rows into 'ledgex_p42_final': ...
exit: 1

$ SEED_INTERNAL_TEST_LICENCES=1 python3 scripts/seed_internal_test_licences.py
... wrote ... (17 rows, including the 4 new blocked-fixture rows)
exit: 0
```

**Item 5 — three runs, parcel count, skip reporting:**

Run 1: every row `wrote` (17 rows total, up from 13 pre-P42 — 4 new: source, snapshot,
field_definition, fact for the blocked fixture). Runs 2 and 3: every row `skipped (already
exists)`, byte-identical output between run 2 and run 3.

```
$ SELECT count(*) FROM parcel WHERE apn LIKE 'INTERNAL_TEST%';
count
-----
    1
```

One parcel, after three runs. The P40 idempotency fix holds under the new rows too.

**Item 6 — real licence rows, queried and diffed, not asserted:**

```
$ diff p42_licence_before.txt p42_licence_after.txt
$ echo $?
0
```

Captured before the seed ran (post-`day4_sources.sql`, pre-seed) and after three seed runs:
both `licence` rows (`cc0`, `cc_by_4_0` — `cleared_by`/`cleared_at` still `NULL` on both) and
all 12 `licence_channel` rows (`channel`/`allowed`/`rationale` verbatim) byte-identical.

**Item 7 — wired into a real script, not left as a one-off transcript. Reported, not silently
decided either way.** Built `scripts/test_viewer_rights_gate.py`: locates the seed's own
parcel (refuses loudly, naming the exact command to run first, if it isn't there — never
seeds it itself, since the seed's opt-in gate exists precisely so nothing triggers that
permanent write as a side effect), calls `api.main.get_parcel_facts` directly as a plain
function (no HTTP layer, no new `httpx` test-client dependency), and serializes the result
through the SAME `Pydantic` `response_model` (`ParcelFactsResponse`) FastAPI itself would use
to build the real wire response — so "the sentinel does not appear in the serialized
response" is tested against the actual production serialization path. RED-first proven, not
just shown green: run against the pre-fix seed's own parcel (`ledgex_p42_red`), it correctly
**fails** (`omitted_for_rights[] is non-empty` and `the blocked entry cites cc_by_4_0`, exit
1); run against the post-fix parcel, all 5 checks **pass** (exit 0).

```
[FAIL] omitted_for_rights[] is non-empty (P42's own blocked fixture) -- empty ...
[FAIL] the blocked entry cites the REAL cc_by_4_0 licence -- got []
2 failure(s)  (pre-fix database)

[PASS] facts[] is non-empty ...
[PASS] omitted_for_rights[] is non-empty ...
[PASS] the blocked entry cites the REAL cc_by_4_0 licence
[PASS] no permitted fact carries the real cc_by_4_0 licence
[PASS] blocked sentinel value does not appear anywhere in the serialized response
All assertions passed  (post-fix database)
```

**Whether to wire it into `db.yml`: considered, decided against, for now.** `api/`'s
dependencies (`fastapi`/`uvicorn`, added P40) already transitively install in CI
(`requirements-test.txt` pulls in root `requirements.txt`), so the mechanism would work.
Not done anyway: `api/` as a whole has never been given a CI-wiring decision — every one of
its other routes remains completely untested in CI, and P40's own report explicitly scopes
this viewer as internal-only, not CI-gated. Wiring in *this one* script would be a partial,
inconsistent signal (one route tested, six not) and would require CI to also run the seed
script against its own disposable database as a new, deliberate step (a reasonable pattern —
it already does the equivalent for `make golden` via `GOLDEN_ALLOW_RULE_SEED=1` — but a
decision that belongs to whatever package eventually decides `api/`'s whole CI strategy, not
one smuggled in alongside a seed-script fix). Recorded here so this is a decision, not an
oversight.

---

### 4. Full gate set, twice, each against its own fresh migrations-only database

TCP DSNs throughout (`postgresql://postgres:x@127.0.0.1:5432/...`) — `make migrate-verify`
fails against a unix-socket DSN for the pre-existing, unrelated reason README finding #44
already names; not touched here.

```
=== ledgex_p42_gate1 (fresh) ===                      === ledgex_p42_gate2 (fresh) ===
  PASS  make schema                                     PASS  make schema
  PASS  make migrate-verify (MATCH, 55)                 PASS  make migrate-verify (MATCH, 55)
  PASS  make db-test                                    PASS  make db-test
  PASS  test_snapshot_race_invariant                    PASS  test_snapshot_race_invariant
  PASS  db/seeds/day4_sources.sql                       PASS  db/seeds/day4_sources.sql
  PASS  make golden (GOLDEN_ALLOW_RULE_SEED=1)           PASS  make golden (GOLDEN_ALLOW_RULE_SEED=1)
  PASS  test_compose_geometry_tier_used                  PASS  test_compose_geometry_tier_used
  PASS  test_compose_election                            PASS  test_compose_election
  PASS  test_compose_parcel_refusals                     PASS  test_compose_parcel_refusals
  PASS  make test                                        PASS  make test
  PASS  make conformance                                 PASS  make conformance
  PASS  make schema-dump                                 PASS  make schema-dump
  PASS  lint-imports                                     PASS  lint-imports
  PASS  check_jurisdiction_names                         PASS  check_jurisdiction_names
  PASS  seed_internal_test_licences (opt-in)              PASS  seed_internal_test_licences (opt-in)
  PASS  test_viewer_rights_gate                           PASS  test_viewer_rights_gate
  --> 16 passed, 0 failed                                --> 16 passed, 0 failed
```

Both against the real `docker` `postgis/postgis:16-3.4` container (`ledgex`) already running
on this machine — the same one every prior package this session used, the same image `db.yml`
itself uses. `db.yml`/`docs.yml` were confirmed green on the real GitHub Actions runner for
baseline `c52a266` earlier this session (P39; runs `32314117415`/`32314117407`) — not
re-checked here, since no commit has landed since and nothing in this package is CI-wired
(§3, item 7).

---

### 5. Stated plainly, per this package's own instruction

- **This viewer is internal-only and must not be exposed beyond localhost until entitlement
  exists.** Unchanged from P40 — nothing in this package touches `api/main.py`'s auth
  posture (or lack of one).
- **`internal_test.*` licences are a testing workaround and assert nothing about `cc0`'s or
  `cc_by_4_0`'s real rights position.** Reconfirmed by direct query (§3, item 6): both real
  licence rows and all 12 real `licence_channel` rows byte-identical before and after this
  package's own writes.
- **LD-1 remains open, and every real fact remains rights-blocked — including the new
  fixture fact, which is the demonstration of exactly that, not an exception to it.** The one
  new fact this package adds that cites a real licence id is deliberately, permanently
  blocked on every channel, the same as every other real fact in this database. It exists to
  prove the block is real, not to create a path around it.

---

### 6. Deferred, not touched, recorded so it is not lost

Unchanged from the source prompt's own closing section: real clearance, when it arrives,
cannot be recorded on `cc0`/`cc_by_4_0` themselves (both immutable), and every fact already
in the ledger stays permanently bound to a licence id whose channels are permanently `false`
— the only exit is a full re-ingest writing superseding facts against a new licence id, which
needs its own runbook before clearance arrives, not after. Separate package. Nothing in P42
touches it; the `internal_test.` namespace continues to exist precisely so this and prior
packages could proceed without pretending that problem is solved.

---

### Review findings

*(empty — appended after review)*
