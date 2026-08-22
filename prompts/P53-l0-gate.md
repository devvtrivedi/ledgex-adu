# P53 — give the L0/LD-1 jurisdiction gate a real runtime representation (Phase 1: design)

Scope: **design only, per the P53 prompt's own hard stop. No implementation in this
commit.** This pass changes what `_compose()` emits and will change `tests/golden/*.json`
`payload_hash` values by design — that gets Phase 2's RED-first treatment, not a same-pass
implementation.

## 1. Audit

### 1.1 P52 §5's three counts, reconfirmed live (`ledgex_schema_check`, Docker `ledgex`, 2026-08-22)

```
SELECT count(*) FROM source WHERE id='ca_san_jose.city_limits';                        -- 0
SELECT count(*) FROM field_definition WHERE field_key='jurisdiction.incorporated';     -- 0
SELECT count(*) FROM fact WHERE field_key='jurisdiction.incorporated';                 -- 0
SELECT count(*) FROM licence WHERE id='unknown';                                       -- 0
SELECT id, tier, boundary_source_id, supported, geometry_tier_enabled FROM jurisdiction;
  ca_san_jose | blocked | NULL | t | f
  (plus six test.*/test_* jurisdictions, all tier='blocked', boundary_source_id NULL)
```

All four counts are still zero. Nothing has changed since P52 Phase 1.

### 1.2 Where an L0 check would have to sit in `_compose()`

Traced directly (`scripts/compose_property_file.py`):

- Line 448: `SELECT id, jurisdiction_id, apn FROM parcel WHERE id = %s` — `jurisdiction_id`
  comes straight off the parcel row (a plain FK set at ingest time). `PARCEL_REFERENCE_
  UNKNOWN` is checked here — the only other L0 refusal that exists today, and it is a
  *by-id lookup* failure, unrelated to jurisdiction boundary resolution.
- Line 463: `SELECT pack_version, geometry_tier_enabled FROM jurisdiction WHERE id = %s` —
  this is the ONLY other jurisdiction-table read in the whole function. `tier` and
  `boundary_source_id` are never selected here today.
- Line 526–530: `SELECT id, field_key, licence_id, value FROM current_fact_at(%s) WHERE
  parcel_id = %s` — builds `touched`, the exact same fact set the I6 gate (`evaluate_
  rights_gate`, line 564) consumes. This is the natural, already-existing place to check
  for a `jurisdiction.incorporated` fact — no new query needed, `touched` already has
  everything required (see §4).
- Line 576 onward: `refusals = []`, then `.append()`-ed in order: L7 geometry (578–579),
  `PARCEL_NO_FACTS` (583–584), L5 election/rule (592–595), L8 rights (617–624). This list
  is never short-circuited (P25's own report: refusals accumulate). The new L0 check's
  refusal belongs in this same list, appended once, alongside the rest.

### 1.3 Does anything gate on `jurisdiction.tier`?

**No — confirmed by exhaustive grep, not assumed.** `grep -rn "tier" scripts/ core/ api/
infra/` turns up exactly two hits outside `geometry_tier_*` naming, both unrelated
(`core/calc.py`'s geometry-tier refusal text; `scripts/local_up.py`'s own comment about a
Postgres container tag that happens to contain the substring "tier2"). `_compose()`'s only
`SELECT ... FROM jurisdiction` (line 463) never selects `tier` at all. **`jurisdiction.
tier='blocked'` is a second, completely dormant notional gate — the same shape as LD-1,
just never named as one.** Out of scope for this pass (the prompt scopes this to LD-1/
`city_limits` specifically), but recorded here as a P53-adjacent finding, not silently
absorbed — see §9 open question 4.

### 1.4 A second dormant column, found while tracing this

`jurisdiction.boundary_source_id` (schema.sql:940, FK to `source(id)`, added at genesis
in 0002 with the comment `-- FK added after source exists`) is referenced **nowhere** in
any `.py`/`.sql`/`.yaml` file outside its own DDL — confirmed by grep across the whole
repo. `db/seeds/day4_sources.sql`'s own `jurisdiction` INSERT does not set it. This column
was declared and never wired — exactly the shape §0 of the prompt predicted, and it turns
out to be the load-bearing piece of the recommended design (§4).

## 2. The four obstacles

### Obstacle 1 — no `licence` row with `id='unknown'`

Confirmed: zero rows. `source.licence_id` is `NOT NULL REFERENCES licence(id)`, so no
`city_limits` source row (of any shape) can exist until this row does. It is **permanent**
(0027's `licence_no_update`/`licence_no_delete` are unconditional raises, no carve-out —
confirmed by reading the trigger bodies directly, not assumed) — it must be right once.

**Resolution: yes, explicit `false` `licence_channel` rows, all six channels, following
0030's own reasoning verbatim.** 0030's header: *"allowed=false, not a deleted row: absence
already denies under default-deny (0002), but an explicit false with a rationale records
the decision and preserves the audit trail."* Consistency with that precedent outweighs the
six extra rows. **Caveat, stated honestly:** under the recommended design (§4, D-C), these
`licence_channel` rows are **not load-bearing for this pass's own enforcement mechanism** —
the new check never calls `evaluate_rights_gate` for `'unknown'`, because no fact ever cites
it (Obstacle 3). They exist purely for the same audit-trail reason 0030 gives, and so that
IF a future fact ever does cite `'unknown'` (e.g. an interim identification before full
clearance), default-deny is already explicit rather than silently absent.

### Obstacle 2 — `source_endpoint_required` blocks the naive row

Confirmed constraint (`db/schema.sql:1185`): `CHECK (method = 'manual' OR endpoint_url IS
NOT NULL)`. `sources.yaml` declares `city_limits` as `method: direct` with no URL — that
row, as declared, cannot be inserted.

**Resolution: `method='manual'`.** This is not a workaround chosen for convenience — see
Obstacle 3, which makes it the *only* option consistent with not fabricating an endpoint.

### Obstacle 3 — I13 makes `method='manual'` a dead end for facts, and that is the point

Confirmed: `core/model.py`'s `FactMethod = Literal["direct", "bulk", "derived"]` — `manual`
(and `portal`) can never be a fact's method. So a `method='manual'` `city_limits` row can
**never** produce a `jurisdiction.incorporated` fact. This is Obstacle 3 exactly as posed:
a source row alone is not a gate.

**Resolution: do not attempt to make it one.** The recommended design (§4) does not depend
on this source ever producing a fact — it uses the source row only as `jurisdiction.
boundary_source_id`'s FK target, i.e. as a declared, structural pointer ("this is what
would satisfy the gate"), while the actual enforcement is refuse-on-absence (D-B's
mechanism). This is deliberate, not a limitation discovered after the fact: a
`method='manual'` source was never going to be ingestable, so the design was chosen to not
need it to be.

### Obstacle 4 — golden fixtures change, and the blast radius is bigger than "regenerate JSON"

Confirmed by reading `scripts/check_golden.py`'s own comparison logic, not assumed:

- `payload_hash` is computed by `_compose()` itself
  (`json.dumps(payload, sort_keys=True)` — sorts dict keys, **not** list order) and stored
  literally in each fixture. Adding a refusal changes it, unconditionally, for every
  fixture. Expected, not a bug.
- **More important, and easy to miss:** `check_golden.py`'s `check_fixture()` hardcodes
  `expected_count = 3 if expect_election_required else 2` (line ~568) and asserts
  `len(actual_refusals) == expected_count` **before** the full normalized compare. Adding a
  fourth refusal (LICENCE_UNKNOWN) makes every fixture's actual count 3 (was 2) or 4 (was
  3) — **this assertion fails even after the JSON fixtures are `--bless`ed**, because it is
  a literal in `check_golden.py`'s own Python source, not data read from the fixture file.
  `scripts/check_golden.py` itself must change (`expected_count = 4 if
  expect_election_required else 3`, plus a new `_licence_unknown_refusal()` helper and a
  positive assertion block, following the exact pattern already used for
  `_rights_blocked_refusal`/`_geometry_tier_disabled_refusal`/`_election_required_refusal`)
  — this is not optional cleanup, it is required for `make golden` to pass at all once the
  composer changes. Recorded here so Phase 2 does not discover it mid-implementation and
  mistake it for an unexplained failure.
- `--bless` (an existing, already-built flag: `scripts/check_golden.py --bless`) is the
  correct, already-existing regeneration mechanism — no new tooling needed.

## 3. Recommended design

### D-A. Ingest-and-block

**For:** uses existing machinery end to end; the gate blocks by the exact same mechanism
(I6/`evaluate_rights_gate`) as `cc0`/`cc_by_4_0` today; no new concept in the composer.
**Against:** requires ingesting data under an **unidentified** licence — this repo has only
ever ingested identified-but-blocked licences (`cc0`, `cc_by_4_0`); ingesting under
`'unknown'` is a step beyond current practice and, per Obstacle 3, is not even reachable
today (no real, verified endpoint has been found or confirmed for San José's city-limits
layer — inventing one would violate the hard constraint against fabricating an endpoint).
**Verdict: not viable for this pass.** It may become viable once a real endpoint is found
and verified, which is future work, not this pass's job.

### D-B. Require-and-refuse

**For:** no unidentified-licence data ever enters the database; enforced today, with zero
dependency on a published endpoint; fails closed by construction (the correct default for a
safety gate); keeps working unchanged once a real fact eventually exists (same code path,
new data). **Against, as posed in the prompt:** introduces a "required input missing"
concept the composer does not have today. **Refined against, found during design:** a
*naive, unconditional* version of D-B (require the fact for every jurisdiction,
unconditionally) would add a new refusal to every `test.*`/`internal_test.*` synthetic
jurisdiction used by unrelated tests too (`scripts/test_compose_election.py`, `scripts/
test_compose_geometry_tier_used.py`, `scripts/test_compose_collision_invariant.py`, `scripts/
test_compose_parcel_refusals.py`) — checked directly: none of them assert an exact refusal
*count* or assert the *absence* of unlisted codes, so none would actually fail, but it is a
larger, more diffuse behavior change than the prompt asks for (every jurisdiction that will
ever exist, forever, gated on the same requirement, whether or not it was ever meant to
model this).

### D-C (recommended). D-B's mechanism, activated by `jurisdiction.boundary_source_id`

Refuse-on-absence (D-B), but **only for a jurisdiction that has actually declared which
source is supposed to satisfy the gate** — i.e. `boundary_source_id IS NOT NULL`. This
pass sets it for `ca_san_jose` only. Every other jurisdiction (every existing test fixture)
keeps `boundary_source_id NULL` and is completely unaffected — zero collateral risk to any
unrelated test's refusal set, addressing D-B's own refined objection above.

This uses `jurisdiction.boundary_source_id` as more than documentation: setting it is what
*turns the gate on* for that jurisdiction. That is exactly the "existing column, not a new
concept" invitation in §0 of the prompt, taken as literally as the schema allows. It also
resolves cleanly into D-A later: once a real `city_limits` source is eventually ingested
(D-A, in a future pass), `boundary_source_id` is already pointed at the right id (or gets
repointed at a new one, per 0027's own new-row-not-update discipline if the licence changes)
and the *exact same* absence-check starts finding a real fact — no composer code changes
again.

**Setting `boundary_source_id` requires a `city_limits` source row to exist** (FK target),
which requires the `'unknown'` licence row (Obstacle 1) and `method='manual'` (Obstacles
2/3) — so D-C is not "D-B plus decoration," it is the version of D-B whose activation
switch happens to also force every one of the four obstacles to be resolved coherently, with
a real, inspectable row a human can query (`SELECT boundary_source_id FROM jurisdiction
WHERE id='ca_san_jose'`) rather than a fact buried in composer logic.

**This is the recommended design.**

## 4. The exact `licence` row, field by field

```sql
INSERT INTO licence (
  id, display_name, restriction, commercial_use, redistribution,
  attribution_text, terms_url, evidence_uri, observed_at, cleared_by, cleared_at, notes
) VALUES (
  'unknown',                          -- exact id licences.yaml §7.2 and sources.yaml's
                                       -- own `licence: unknown` comment already use; not
                                       -- invented, matching what a reader of either file
                                       -- would already expect to find.
  'Licence not yet observed',         -- verbatim from licences.yaml §7.2's display_name
                                       -- for this exact id.
  'unknown', 'unknown', 'unknown',    -- restriction/commercial_use/redistribution: the
                                       -- honest value for a licence never observed --
                                       -- matches licences.yaml §7.2 exactly.
  NULL,                                -- attribution_text: nothing to attribute; the text
                                       -- is unknown, not absent-by-choice.
  NULL,                                -- terms_url: no terms page exists to link; the
                                       -- licence has not been identified, let alone found.
  NULL,                                -- evidence_uri: nothing retained; there is nothing
                                       -- to retain yet.
  '<the date this row is actually created>',  -- observed_at: SEE THE OPEN QUESTION BELOW.
  NULL, NULL,                          -- cleared_by/cleared_at: no clearance is possible
                                       -- for an unidentified licence.
  'LD-1 gate source (jurisdictions/ca_san_jose/sources.yaml: ca_san_jose.city_limits). '
  'Licence text never observed -- id and every column value match licences.yaml sec 7.2 '
  'verbatim, not independently invented. See prompts/P53-l0-gate.md.'
);
```

**Open question the schema itself does not resolve (flagged, not decided here):**
`observed_at timestamptz NOT NULL` has no honest value for a licence that, by definition,
has never been observed. The two candidate readings are genuinely different claims:
(a) "the date we observed the licence's *terms*" — never true, cannot be filled honestly;
(b) "the date we recorded that the terms are *unknown*" — a real, dateable fact about this
row's own creation, not a fabrication. **Recommendation: reading (b)**, i.e. `observed_at`
= the date this row is actually inserted, with a code/migration comment making that
distinction explicit so a future reader does not mistake it for "we looked at the licence
on this date." This is the audit's proposed reading, not a decision — see §9 question 1.

**Six `licence_channel` rows, all `allowed=false`,** rationale following 0030's exact
wording pattern: *"LD-1: gate source unconfirmed, licence text never observed (§1.1). No
channel is ever cleared for an unidentified licence — identifying it requires a new licence
row (0027), never an UPDATE to this one."*

## 5. Refusal semantics

**`LICENCE_UNKNOWN`, stage L0.** Confirmed already in every vocabulary copy —
`core/model.py`'s `REFUSAL_CODES`, and the DB `refusals_codes_valid()` CHECK across every
widening (`db/migrations/0038`, `0048`, `0053`, `0055`, and `db/schema.sql` itself) — and
confirmed, by grep, **never emitted by any code path today**. §9's own table already
describes exactly this case, verbatim: *"Default deny. Applies at L0 when a gate source is
unconfirmed (§1.1)."* No new code, no spec bump, no §12 row needed. `RIGHTS_BLOCKED` was
considered and rejected — it means "a licence forbids this field," which presupposes a fact
exists to forbid; here nothing exists to gate on at all, which is `LICENCE_UNKNOWN`'s own
documented meaning, not RIGHTS_BLOCKED's.

**Exact new check, stated precisely (not implemented in this pass):**

```python
# after jurisdiction row is read (now also selecting boundary_source_id)
# and after `touched` is built (already fetched for the I6 gate, reused, not re-queried):
if boundary_source_id is not None and not any(
    field_key == "jurisdiction.incorporated" for _, field_key, _, _ in touched
):
    refusals.append({
        "code": "LICENCE_UNKNOWN",
        "stage": "L0",
        "message": (
            f"Jurisdiction {jurisdiction_id!r} declares boundary_source_id="
            f"{boundary_source_id!r} as the source that resolves jurisdiction "
            f"boundary, but no current jurisdiction.incorporated fact exists for "
            f"this parcel -- default deny (sec 1.1, sec 9)."
        ),
        "detail": {
            "jurisdiction_id": jurisdiction_id,
            "boundary_source_id": boundary_source_id,
            "field_key": "jurisdiction.incorporated",
        },
    })
```

No new query: `touched` already comes from the same `current_fact_at()` call the I8 gate
consumes (line 526–530). `evaluate_rights_gate`/`core/rights.py` are untouched — this check
never calls them and never reads `licence_channel`.

## 6. Golden fixture impact — before/after, concretely

All three real fixtures (`refused.json`, `geometry_disabled.json`, `election_required.json`)
seed `ca_san_jose` (`ip.JURISDICTION_ID`). Once `boundary_source_id` is set for that
jurisdiction (§7's seeding note) and no `jurisdiction.incorporated` fact exists (true today,
and true after this pass — nothing is ingested), **every one of the three fixtures gains
one additional `LICENCE_UNKNOWN` refusal.**

`refused.json`, refusals array — before (2 entries) → after (3 entries):

```jsonc
// BEFORE
"refusals": [
  {"code": "GEOMETRY_TIER_DISABLED", "stage": "L7", ...},
  {"code": "RIGHTS_BLOCKED", "stage": "L8", ...}
]
// AFTER
"refusals": [
  {"code": "LICENCE_UNKNOWN", "stage": "L0",
   "detail": {"jurisdiction_id": "ca_san_jose",
              "boundary_source_id": "ca_san_jose.city_limits",
              "field_key": "jurisdiction.incorporated"}, ...},
  {"code": "GEOMETRY_TIER_DISABLED", "stage": "L7", ...},
  {"code": "RIGHTS_BLOCKED", "stage": "L8", ...}
]
```

Same shape change for `geometry_disabled.json` (2→3) and `election_required.json` (3→4).
Every `payload_hash` in all three fixtures changes as a direct, mechanical consequence —
regenerate via `scripts/check_golden.py --bless` (existing flag, not new tooling) as its own
narrated step (§6 of the P53 Phase-2 instructions), never silently.

**A finding that must be resolved before `--bless` produces a fixture that means anything in
CI, not after:** `db/seeds/day4_sources.sql` **is** run before `make golden` in CI
(`.github/workflows/db.yml`'s `schema` job, step `db/seeds/day4_sources.sql`, added in P36
specifically to close the "two independent seeders can silently disagree" gap — README
finding #38) — this directly **contradicts** `CLAUDE.md`'s current claim that *"CI (db.yml)
applies every migration to an empty database and never runs db/seeds/"*, which is stale as
of that P36 change; recorded here as found, not fixed (fixing `CLAUDE.md` is not this pass's
job — flagged in §9). Because seeding order is real and both `db/seeds/day4_sources.sql` and
`scripts/check_golden.py`'s own `seed_reference_rows()` independently create `ca_san_jose`
(`ON CONFLICT (id) DO NOTHING`), **whichever one sets `boundary_source_id` must guarantee
the same value regardless of which seeder runs first**, exactly the class of bug this repo
has already found and fixed twice (finding #32 for `source` rows in `check_conformance.py`;
finding #36/P36 for the `rule` row in `check_golden.py`, both now using `ON CONFLICT ... DO
UPDATE` specifically so seeding order can never matter). `jurisdiction`/`source` carry no
immutability trigger (confirmed directly — no `*_no_update` trigger exists for either), so
`DO UPDATE` is safe there; `licence` **is** immutable (0027, unconditional), so the
`'unknown'` row must stay `DO NOTHING` with byte-identical values in both seeders, the same
pattern already established for `cc_by_4_0` in `check_golden.py`'s own `seed_reference_
rows()`. **Concretely: `scripts/check_golden.py`'s `seed_reference_rows()` needs three new
statements — the `'unknown'` licence (`DO NOTHING`, byte-identical to `db/seeds/
day4_sources.sql`), the `city_limits` source (`DO UPDATE`), and `UPDATE jurisdiction SET
boundary_source_id = ...` (or an equivalent `DO UPDATE` on the jurisdiction INSERT) — or
`make golden` run against a schema-only, unseeded database would silently NOT exercise the
new gate at all, while CI (which does seed first) would.** This is a real, non-obvious
correctness requirement for Phase 2, not an edge case to skip.

**Where the new rows are seeded, and why not a migration:** neither `cc0`/`cc_by_4_0`
themselves nor the `ca_san_jose` jurisdiction row were ever introduced via migration in
this repo's history — only `db/seeds/day4_sources.sql` creates new legitimate rows;
migrations are reserved for schema changes and for correcting rows a seed already got wrong
(0023, 0026, 0030 are all corrections, not introductions). This pass adds new rows and
updates a column that starts `NULL` everywhere (no existing row to "correct") — the
established precedent is a seed-file addition, not a migration. Recommended: extend
`db/seeds/day4_sources.sql` with the `'unknown'` licence, its six `licence_channel` rows,
the `city_limits` source row, the `jurisdiction.incorporated` `field_definition` row, and
`UPDATE jurisdiction SET boundary_source_id = 'ca_san_jose.city_limits' WHERE id =
'ca_san_jose'`.

## 7. The negative control, specified concretely

**File:** `scripts/test_compose_l0_gate.py` (matches the established `scripts/
test_compose_*.py` naming and fixture-construction convention — modelled directly on
`scripts/test_compose_parcel_refusals.py`'s own `_seed_jurisdiction`/fresh-`test.*`-suffix
pattern).

**Negative control (the one P52 §5 item 5 requires):**
1. Seed a fresh `test_p53_l0_<uuid suffix>` jurisdiction with `boundary_source_id` set to a
   fresh, disposable test source (itself citing a **fully-cleared** test licence —
   `licence_channel.allowed=true` for the channel under test, the same "test fixture:
   unrestricted on channels, isolates the dimension under test" shape `db/tests/
   invariants.sql`'s own 0029 fixtures already use).
2. Seed one parcel under that jurisdiction with exactly one fact — `field_key='parcel.apn'`
   — citing that same fully-cleared test licence. No `jurisdiction.incorporated` fact.
3. Call `cpf._compose()` (or `cpf.compose()`) for that parcel.
4. **Assert:** `LICENCE_UNKNOWN` (stage `L0`) is present in `refusals`, **and**
   `RIGHTS_BLOCKED` is **absent** — proving the refusal holds for a reason wholly
   independent of licence clearance. This is the exact scenario the prompt names: "cc0/
   cc_by_4_0 locally cleared, jurisdiction unresolvable, composition still refuses."

**Companion positive test (proves the gate is a real two-sided condition, not a permanent
one-way block dressed up as a gate):** same fixture, but this time the parcel **also**
carries a fact with `field_key='jurisdiction.incorporated'` (test-fixture-only, citing the
same fully-cleared test licence). **Assert:** `LICENCE_UNKNOWN` is **absent**. Without this
test, a PASS that hardcodes "always refuse for this jurisdiction" would pass the negative
control while not actually being a gate.

**Untouched-jurisdiction control (proves D-C's scoping claim, §3):** a third fixture,
identical shape, but `boundary_source_id` left `NULL` (the default every other test
jurisdiction already uses). **Assert:** `LICENCE_UNKNOWN` is **absent**, confirming the gate
does not fire for a jurisdiction that never declared it needs one — this is what makes D-C
safe for every pre-existing `test.*` fixture across the suite (§3's own collateral-impact
argument, made concrete).

## 8. What this would not prove

- That a real `city_limits` endpoint exists, is machine-readable, or has been verified —
  explicitly not attempted (Obstacle 3's own resolution avoids needing one for this pass).
- That `jurisdiction.tier='blocked'` is now enforced — it remains exactly as dormant as
  today (§1.3); this pass does not touch it.
- That the `'unknown'` licence row's `observed_at` semantics (§4) are correct — flagged as
  an open interpretive question, not resolved by this design.
- That every consumer of `property_file.refusals` (any future viewer surface, any future
  customer-facing rendering) handles a fourth refusal code gracefully — only the composer
  and its own tests are covered by this design.
- That PASS 3 (clearing `cc0`/`cc_by_4_0`) is safe or ready — this pass clears nothing and
  says nothing about that decision.
- That this pass's `check_golden.py` seeding fix (§6) is the only place seeding order could
  matter — only the paths this design actually traced were checked; a full audit of every
  script that seeds a `jurisdiction` row was not performed beyond the four `scripts/
  test_compose_*.py` files and `check_golden.py`/`check_conformance.py` named above.

## 9. Open questions for the owner

1. `licence.observed_at` for the `'unknown'` row (§4): bless reading (b) — "the date we
   recorded the terms are unknown," i.e. this row's own creation date — or is a different
   convention preferred?
2. Confirm the recommended seeding location (`db/seeds/day4_sources.sql`, no new migration —
   §6) rather than a migration, given the precedent argument made there.
3. Should `CLAUDE.md`'s stale claim about CI never running `db/seeds/` (contradicted by
   `db.yml`'s own post-P36 state, found in §6) be corrected as part of this pass, or is that
   a separate, later documentation pass?
4. `jurisdiction.tier='blocked'` is a second dormant gate (§1.3), the same shape as LD-1 was.
   Should a P54-shaped pass be scheduled for it, or is `tier` intentionally decorative in a
   way LD-1 was not (worth the owner's explicit statement either way, so it is a decision on
   record rather than an unexamined gap)?
5. D-A (real ingest) is explicitly not viable for this pass (Obstacle 3) — is finding and
   verifying a real San José city-limits endpoint worth scheduling as its own future pass, or
   does D-C's declarative-but-unfilled gate serve the jurisdiction adequately for the
   foreseeable term?
