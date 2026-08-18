## P24 — Adopt ParcelException, then report the build direction

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)).

---

### 1. The concrete half: `ParcelException` adopted

`core/exceptions.insert_exceptions` now takes `list[core.model.ParcelException]`, not
positional 7-tuples — P22's settled pattern, applied here, not reinvented: build the
tuple internally, refuse a bare tuple (`TypeError`), refuse a model carrying a field this
function does not write. Adopted at all 4 real call sites (6 construction sites across
`ingest_parcels.py` ×3, `ingest_zoning_permits.py` ×3, `flag_invalid_geometry.py` ×2).

**Two things checked, not assumed to transfer from P22:**

- **Unwritten fields.** `ParcelException` does **not** have nine the way `Fact` did. Of
  its 15 fields, 7 are written; of the 8 that are not, 7 are legitimately never
  caller-set at insert time (`id`/`detected_at`/`outcome` are DB-defaulted;
  `resolved_at`/`resolved_by`/`resolution_notes`/`reopened_from_id` are lifecycle state
  this module's own closure functions set later, never at detection). Exactly **one** —
  `ruleset_version` — is a real choice not yet forced by any caller, refused the same way
  Fact's nine were.
- **`detail`'s encoding contract, reproduced independently, not inherited.** Predicted
  and confirmed against a real scratch database: a native dict passed directly fails
  identically to Fact's dict case (`psycopg2.ProgrammingError: can't adapt type 'dict'`);
  a pre-encoded JSON string succeeds. But `detail` **resolves differently from
  `Fact.value`**: it already carries `dict[str, Any]` typing (committed since P21, not
  reopened here), and every real caller's payload is plain, Decimal-free, geometry-free
  strings — none of the geometry/`infra.values.decimal_default` need that blocked Fact's
  option (a) (P22, README finding #29) applies here. So `insert_exceptions()` does the
  `json.dumps()` itself — Fact's *rejected* option, correct here because nothing forces
  the alternative. Callers now pass a real dict (`detail={"reason": reason}`), not a
  pre-encoded string — a real, necessary call-site change, not optional (Pydantic's
  `dict[str, Any]` rejects a string outright, confirmed directly). A new
  `_check_detail_is_json_serializable` validator on `ParcelException` catches a
  non-serializable value at construction, matching `Fact.value`'s is-valid-JSON check in
  spirit.

**Proven, not asserted**: `tests/core/test_parcel_exception_adoption_hazard.py` —
same five-part shape as P22's Fact proof (historical hazard reproduced on a bare tuple,
adoption refuses the bare tuple, ordinary case works, a value-swap between correctly-named
fields is honestly **not** caught, the unwritten-field guard is refused). Both new guards
in `core/exceptions.py` (isinstance check, unwritten-field check) and the new
`detail`-serializability validator in `core/model.py` RED-proven individually (each
disabled, confirmed the one targeting test fails with the exact predicted failure mode,
restored). `flag_invalid_geometry.py` — untouched by either acceptance suite — exercised
directly against a deliberately self-intersecting geometry planted in a scratch database;
the real, unmodified `flag_parcel_geometry()` detected it and wrote a real
`ParcelException` through the adopted path (`detail: {"reason": "Self-intersection[1 1]"}`,
a genuine `ST_IsValidReason` message, not fabricated).

`core/exceptions.py:16`'s stale "tuple-not-type shape as core/store.insert_facts"
docstring — left stale by P22 pending this package — corrected.
`build/check_jurisdiction_names.py` re-run against the real tree: `4 file(s) under core/
scanned, no blocklisted token found`.

---

### 2. The report: what §14 says must ship, against what exists

§14 (read in full, first time this run) plus §15's A-1.3 and I10/I20.

**§14.1**: LD-1 through LD-3 are rights confirmations (city-limits, inspection/planning,
other named sources) blocking the facts/conclusions they cover. **LD-4 (3DEP
coverage/repeatability/accuracy) is explicitly, textually, NOT a Base Core launch
dependency** — §14.2's own first line. It blocks placement and geometry-dependent
conclusions *only*.

**§14.2**: Base Core is defined as "parcel identity/boundary, zoning, permit
information, known constraints, provenance, confidence, rights and explicit
unavailable-information treatment in **one coherent file**." Its own dependencies are
LD-5 (measured earliest permit-series date) through LD-9 (per-resource counsel
guidance) — none of which name geometry. Two explicit conclusion-level rules: conceptual
placement requires validated geometry and refuses (never substitutes an inferred
footprint) when LD-4 is unresolved; a cost scenario may use geometry-derived quantities
*or* clearly-disclosed user-supplied assumptions, and refuses only if neither is
available.

**Read plainly, this makes I10 not a degraded edge case but the literal expected shape
of Base Core today**: LD-4 is not required for launch, Base Core's own definition names
nothing geometry-dependent except the two conclusion types the spec calls out by name,
and everything else in Base Core (zoning, permit info, known constraints, provenance,
confidence, rights, explicit-unavailable treatment) has no geometry dependency at all.

**Against what exists**: `core/calc` (L7) does not exist — no file, no directory.
`core/compose` exists only as `scripts/compose_property_file.py`, whose only reachable
path is the refused fixture P20 built; `geometry_tier_used` is hardcoded `false`,
unconditionally, in the one INSERT that path has. `jurisdiction.geometry_tier_enabled`
(schema, defaults `false`) is read by zero lines anywhere in this repo (`grep -rn
"geometry_tier_enabled" --include="*.py" .` — zero hits outside an unrelated
`botocore` pricing file). I20's own A-1.3 schema (`footprint_provider_version`,
`footprint_provider_validation`, `jurisdiction.active_footprint_provider_version_id`,
`validate_footprint_provider_slot()`) is fully drafted in spec text and **entirely
unmigrated** — `grep -rn "footprint_provider" db/migrations/*.sql db/schema.sql` — zero
hits.

The findings queue confirms there is nothing left to *fix*: #11 is latent by design
(forced-by-need, not anticipated), #16 waits on trigger events, #23 is externally
blocked, #27 is a watch item (P23's own correction — the rule can be followed, not
mechanically enforced). The next work is building, not fixing, and this is the report
that decides what.

#### (a) Geometry-disabled Base Core (I10)

**What it would take.** `core/calc` doesn't exist, and neither does any notion of a
"conclusion" as a taggable thing in this codebase — the first real cost here is inventing
that concept, not writing the check itself. §14.2 already names the only two conclusion
*types* that need the tag: conceptual placement and cost scenario. The check itself is
trivial once the concept exists: if `jurisdiction.geometry_tier_enabled` is false (the
live default), refuse by name. **`GEOMETRY_TIER_DISABLED` already exists in §9's
vocabulary and in `core/model.REFUSAL_CODES`, at stage L7** — the exact layer that
doesn't exist. I10's "refuse by name" already has its name; it has no code path that
ever produces it.

**What it does *not* unblock, stated precisely so it isn't oversold**: not composed or
partial customer output. The rights gate (STANDING-BLOCKER.md, reconfirmed live below)
still refuses every real request before any geometry check would run. What this
genuinely unblocks is **I10 compliance coverage** — a fourth golden fixture class
(`tests/golden/ca_san_jose/geometry_disabled.json`, completing §6.6's four-class table
alongside composed/partial/refused), proving a request needing placement or a
geometry-derived cost scenario refuses specifically as `GEOMETRY_TIER_DISABLED`,
distinguishable from a blanket `RIGHTS_BLOCKED` refusal — not a new "composed" status.
I10's own required enforcement (§1: "base-core / no-fallback tests") currently has zero
tests; this would be the first.

**Depends on**: nothing external. `geometry_tier_enabled` already defaults false;
I20's provider-slot machinery is NOT a prerequisite — it only matters once geometry is
ever *enabled*, a separate, LD-4-gated question this does not need to answer.

**Cost, concretely**: a minimal `core/calc` stub (a `Conclusion` shape with a
geometry-dependent flag, and the two named conclusion types wired to check
`geometry_tier_enabled` and return a `Result.refuse(Refusal(code="GEOMETRY_TIER_DISABLED",
stage="L7", ...))`) — the design cost is in shaping what a "conclusion" object looks
like generally, since this is its first instance, not in the check logic itself.
Composer wiring to surface that refusal in `property_file.refusals`. One new golden
fixture plus a `check_golden.py` extension, following P20's own established,
low-risk pattern closely. **Startable today.**

#### (b) Composed and partial golden fixtures

**Confirmed live, not restated from STANDING-BLOCKER.md's prose**: `licence_channel` —
every row for both real licences (`cc0`, `cc_by_4_0`) is `allowed = false` across all six
channels, each with an explicit rationale citing "counsel/owner sign-off Pending per the
audit's diligence register, Evidence Index p.36." `licence.cleared_by`,
`cleared_at`, `evidence_uri` are genuinely `NULL` for both — queried directly, not
inferred. LD-1's own `city_limits` source (named "BLOCKS EVERYTHING" in the spec) isn't
even registered as a `source` row yet (`SELECT ... WHERE id LIKE '%city_limits%'` — zero
rows). **No evidence anywhere in a reachable database would legitimately justify flipping
any channel today** — this is not an engineering backlog item sized wrong; it is
genuinely waiting on one external actor's signature that has not happened.

**Cost**: not a sizing question. Zero engineering work available to do here that
wouldn't mean fabricating a clearance that does not exist — exactly what P20's own
close-out already refused to do for the identical reason. **Not startable today, by
anyone, regardless of resourcing.**

#### (c) `jurisdictions/ca_san_jose` as a real pack

**What exists**: nothing — `jurisdictions/` is not a directory in this repository at
all (confirmed via `find`), not even the `_schema/` subdirectory §2's own diagram
names. `make conformance` is fully unimplemented (`exit 1`, "no packs exist").

**What §7.1 already gives for free**: a fully-drafted `sources.yaml` (jurisdiction id,
pack_version, portals, and a `sources:` list with every field a pack loader would need)
— transcribing this into a real file is close to mechanical, low cost, low risk.

**What is genuinely undesigned**: the "mapping from source property to field_key" that
§2 says belongs in `jurisdictions/` has no drafted shape anywhere in the spec — §7.1
covers *what* each source supplies, never *how* a raw property becomes that field. That
mapping today is live, working Python in `scripts/ingest_parcels.py` and
`scripts/ingest_zoning_permits.py` — real code this session has spent multiple packages
hardening (P3–P13's own reconciliation, dedup and supersession fixes all live in it).
Moving it means: (1) designing a new declarative pack-file format for source-property→
field_key mapping (a real design decision needing its own report-before-writing pass,
not a known quantity to transcribe), (2) building `jurisdictions/_schema/` (JSON Schema
validation for pack files, doesn't exist), (3) building `make conformance` genuinely
from nothing (§1.2: "sources, mappings, rights, dependency cascades, endpoint
liveness" — five real sub-checks, currently zero), and (4) rewriting the ingest
scripts' already-correct, already-tested mapping logic to read from the new pack instead
— real regression risk to working code, the same category of risk P22 explicitly
declined to take on for `Fact` adoption in the loaders themselves.

**Cost**: substantially larger and more speculative than (a) — three new subsystems
(pack schema, pack loader, conformance suite) plus an undesigned mapping-format decision
plus a refactor of working code, versus (a)'s one new minimal module and zero touched
working code. **Technically startable today** (no external blocker), but the largest,
least-scoped of the three.

#### Recommendation

**(a)**. Fully unblocked, smallest and most precisely scoped of the three, touches no
already-working code, and closes a real, currently-empty compliance gate — I10 is a
named invariant with required enforcement ("base-core / no-fallback tests") that has
zero tests today. (b) cannot be started by engineering at all. (c) is real, needed
eventually (`make conformance` has to exist before Phase 2 can add a second
jurisdiction), but carries an undesigned sub-decision and real regression risk that (a)
does not — better sized as its own, later, report-before-writing package once (a) has
established what a "conclusion" object looks like in this codebase, which (c)'s own
conformance suite will eventually need to validate against too.

**Not started.** This package is the report; building (a) is a decision for the next one.

---

### 3. Close-out

`make migrate-verify` against `ledgex_schema_check` (51 migrations, `MATCH`), then a
clean `make schema-dump` — no schema change, as expected; this package touches
`core/exceptions.py`, `core/model.py`, three `scripts/*.py` files, and `tests/core/`,
nothing under `db/`. Both acceptance suites run three times each, each against its own
fresh database per `CONVENTIONS.md:54` as corrected in P23 — all green.
`tests/core/` (161 tests) green via `make test`. `make check-boundary` (5 import-linter
contracts, jurisdiction-name grep, `qa_check.py`) green throughout.
