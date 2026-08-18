## P26 — The jurisdictions/ pack format, and one real ca_san_jose pack

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Report before writing — this
designs a format every future jurisdiction inherits.

Read in full: §1, §2's `jurisdictions/` tree, §7 (San José source list), §1.2's
`conformance` row.

---

### 1. Scope: format + one pack. NOT rewiring the loaders

§2 says the source-property-to-field_key mapping belongs in `jurisdictions/`; it
currently lives in `scripts/ingest_parcels.py`/`scripts/ingest_zoning_permits.py` as
working, CI-gated code. **That move is explicitly not this package.** Two independent
reasons, not one:

- **Regression risk.** Moving working, well-tested mapping logic out of scripts that P3
  through P25 have hardened is real risk to code that currently works, separable from
  designing a format.
- **The format itself doesn't exist to move code into.** §7.1 and §7.2 fully draft
  `sources.yaml` and `licences.yaml`'s own content — this package mostly transcribes
  them. `field_map.yaml` (the actual source-property→field_key crosswalk) is named twice
  in the spec (§6.1's task shapes A and B) but its own file *format* has no drafted shape
  anywhere. Designing that format now, with no real caller yet, would be exactly the
  "anticipated, not forced by need" scope this whole codebase argues against — and
  building a rewiring package on top of an invented, untested format would compound that
  risk rather than separate it.

Both are reported, not absorbed: `field_map.yaml`'s format, and the loader rewiring that
would consume it, are a later package's decision, made when something actually needs it.

---

### 2. The format decision

**Layout**: `jurisdictions/_schema/{sources,licences}.schema.json` +
`jurisdictions/ca_san_jose/{sources,licences}.yaml` — exactly §2's own named tree, no
new directories invented.

**Format: YAML, confirmed, not inferred.** §2's own diagram names `ca_state/`'s files as
`adu.yaml`, `sb9.yaml`; §7.1/§7.2's own headers are literally titled
`jurisdictions/ca_san_jose/sources.yaml` and `.../licences.yaml`. Every file extension
named anywhere in the spec for this tree is `.yaml`.

**What a source pack file must declare**: transcribed from §7.1's own fully-drafted
shape — `id`, `display_name`, `steward`, `method` (mirrors the live `access_method`
enum), `licence`, `phase_status` (mirrors `source_phase_status`), `phase_status_reason`,
`supplies` (this file's own name for `source.expected_fields`), plus optional
`cadence_stated`, `earliest_record_date`, `url_verified_at`, `active`, `notes`,
`excluded`. A licence pack file: `id`, `display_name`, `restriction`/`commercial_use`/
`redistribution` (mirror the live enums), `channels` (the four required + two optional
C9 channels), optional `attribution_text`/`note`. Both shapes are JSON-Schema-validated
against `db/schema.sql`'s real column types and enum values directly, not an
independently invented shape.

**I17, honored literally, and what it actually found.** "Pack content comes verbatim
from §7 and the stored evidence, never from a summary" — read as two sources that must
agree, not one. They didn't. **`sources.yaml` (§7.1) has one real, undeniable drift from
the database.** §7.1's own `ca_san_jose.parcels` entry lists
`supplies: [parcel.apn, parcel.geometry, parcel.lot_area_gis, parcel.situs_address]`. The
live `source.expected_fields` for that same row — confirmed directly, `SELECT id,
expected_fields FROM source WHERE jurisdiction_id='ca_san_jose'` — is `["parcel.apn",
"parcel.geometry", "parcel.source_parcel_id"]`. §7.1 predates two real corrections:
migration 0026 (`scripts/ingest_parcels.py`'s own Phase C inspection of the real
~210MB GeoJSON found neither `lot_area_gis` nor `situs_address` anywhere in the feature
set) and migration 0035 (`parcel.source_parcel_id` added, confirmed unique and fully
populated). The pack was built from the *corrected*, database-verified value, not §7.1's
un-updated draft — and §7.1's own text is corrected in the same package, not left to
silently keep disagreeing (spec bump below).

**What stops the pack and the seed disagreeing going forward — the actual design
question, not a promise.** §0.2's "one owned Python object, N importers" pattern doesn't
apply directly: these are two *data* artifacts (a YAML pack, a SQL-seeded database), not
two code artifacts computing the same logic. The applicable precedent is P21/P22's
extract-and-diff shape (used for refusal codes, three encodings, diffed pairwise) —
applied here as `make conformance`'s own new check: the pack's declared `supplies:` is
diffed against the live `source.expected_fields` on every CI run, for every active
source. The drift above was found *because this check was being built*, before it
existed to catch anything — the mechanism is what changes going forward, not vigilance.

---

### 3. `make conformance`, real for one pack, P20's coverage discipline kept exactly

§1.2's pass condition: "Every enabled pack passes; no rights broadening or silent
missing dependency." Built for what a pack can actually assert today:

1. Both YAML files validate against their own JSON Schema.
2. Every **active, `ca_san_jose`-owned** source's `licence` exists in the live `licence`
   table and matches the live source row's own `licence_id`.
3. Every field_key that source `supplies` exists in `field_definition`.
4. That `supplies:` list matches the live `source.expected_fields` **exactly** — the
   drift-prevention check itself.

**Scoped to active, owned sources deliberately — checked, not assumed to generalize.**
This pack declares 26 sources; only 5 are `phase_status: active`, and of those, 2
(`us_fema.nfhl`, `us_nrcs.soil_survey`) are federal sources reused across future
jurisdictions with no `jurisdiction_id` scheme to register them under yet — a real,
separate, unbuilt piece of schema design, not something this pack got wrong. Requiring
every one of the other 21 blocked/deferred/excluded sources to have a live database row
would make conformance permanently unpassable for a reason unrelated to pack
correctness — the identical `phase1_deferred` precedent `field_definition` itself
already uses.

**A second, real ordering bug found and fixed while proving this end-to-end, not
hypothetical.** `scripts/check_golden.py`'s own seed also inserts a
`ca_san_jose.parcels` row (`ON CONFLICT DO NOTHING`, never setting `expected_fields`).
CI's `schema` job runs `make golden` before this check, in the same shared, disposable
database — simulated locally end-to-end, in the real CI step order, before wiring
anything in: golden's minimal row won the race, and the exact check this package exists
to run failed for a reason that had nothing to do with the pack. Fixed by making this
seed's own `source` insert `ON CONFLICT DO UPDATE` — order-independent by construction,
not by hoping nothing upstream changes again.

**Coverage named explicitly, every run, pass or fail — same discipline `make golden`/
`make test` already use (P20/P21):** rights broadening against Plan 2.1.4 Appendix K
(§7.3's own `test_licences_not_broader_than_appendix_k`, no machine-readable copy of
Appendix K exists in this repo to diff against), dependency cascades (no
conclusion-dependency graph exists anywhere in this codebase — `core/calc` has exactly
one gate, P25's geometry check, unrelated to source dependencies), mappings
(`field_map.yaml`, deliberately not designed by this package, §1), endpoint liveness
(`make liveness`, §6.4, its own separate, still-unbuilt target — this script makes no
network calls).

---

### 4. Proven, and jurisdiction-name scoping confirmed, not assumed

**RED, local**: planted a field_key absent from `field_definition`
(`parcel.NONEXISTENT_FIELD`) into `sources.yaml`'s `parcels` entry — confirmed exactly
the two predicted checks failed (field-existence, expected_fields-match), everything
else stayed green. Restored, reconfirmed clean.

**`build/check_jurisdiction_names.py`'s scoping confirmed directly, not assumed**:
`CORE_DIR = ROOT / "core"`, `CORE_DIR.rglob("*.py")` — reads the source, not the
behavior alone. Run against the real tree after `jurisdictions/` was populated with 26
real jurisdiction names, source stewards and place names: `5 file(s) under core/
scanned, no blocklisted token found` — unaffected, exactly where these names belong.

**Wired into CI. NOT broken for real on the runner at the time — this line was written as a
plan and never executed; correcting it here rather than leaving it stand as a false
completed-past-tense claim (found during P29's audit of this package's own skipped
close-out).** `git log` carries exactly one P26 commit, `3980560` — no break, no revert,
ever pushed under this package itself. The only real-runner evidence this package had at
the time was the local RED proof above and the main build's own CI outcome (below).
CONVENTIONS' own hard rule ("every check must be seen to fail at least once... on the real
runner") was genuinely unsatisfied for `make conformance`'s CI-wired gate at the time P29
audited this — recorded then (finding #33, P29) as an open gap, not fabricated shut. See
`prompts/P29-close-p26-correct-p28-scope-fork.md` for that decision, and
`prompts/P30-conformance-red-and-fork-report.md` for where #33 was actually closed: a real
deliberate break (a pack-vs-database licence mismatch, not a schema/import error) pushed,
confirmed red on the real runner, reverted, confirmed green — `db.yml` runs
`32196179966`/`32196337985`.

---

### 5. Close-out (backfilled by P29 — this section was never run)

No schema change — `make migrate-verify` (51 migrations, `MATCH`) then a clean `make
schema-dump` against `ledgex_schema_check`, confirmed before and after (a `template_
postgis`-derived scratch database was tried for the same two checks during end-to-end
CI simulation and produced a false diff from baked-in TIGER/topology extensions no
migration in this repo adds — a property of that template, not of anything this package
changed; not committed, `ledgex_schema_check` remains the authoritative check).

Spec bumped 1.39 → 1.40, real §12 row. §7.1's own stale `parcels` `supplies:` list
corrected in the same package as the pack file that now agrees with it. §1.2's
`conformance` row and §2's `jurisdictions/` tree annotation both updated to state what
now exists and what deliberately doesn't (`field_map.yaml`). Both acceptance suites,
three times each, each against its own fresh database — unaffected (neither touches
`jurisdictions/` or the composer). `make test` (167 tests), `make golden` (2/4 classes)
and `make conformance` (1 real pack) all green via `make`, in the real CI step order,
simulated end-to-end before wiring anything in — all of this is real, done at the time,
just never written up as a completed close-out.

**Real runner, checked against `gh run list` for commit `3980560` itself, not assumed**:
`docs.yml` run `32171649780` — `success`. `db.yml` run `32171649751` — `cancelled`, not
`success`: this is the exact run P27 later diagnosed as an apt-get mirror stall (finding
#31), unrelated to anything this package changed, but it means `3980560`'s own `db.yml`
run never actually completed green — only later commits building on top of it (starting
with P27's `1da54bd`) did. Re-run directly during this P29 pass via `gh run rerun
32171649751`, now that P27's fix is in place: `schema`/`p5-acceptance`/`phaseb-acceptance`
all `success` — this exact commit's `db.yml` run is now genuinely green, not merely
superseded by a later one.

The real seeding-order bug this package found while building `make conformance` (finding
#32) was fixed in this same commit but never given its own findings-table row — added
retroactively by P29.

---

### 6. Report, do not act: the next gate to stop lying

With `make conformance` real, `make test`'s own six named areas (review, entitlement,
outcome observation, provider slot, edge guard, billing independence) are the only
`§1.2` claim left entirely unbacked by any real check — `make check-boundary`, `make
schema`, `make schema-dump`, `make golden` and `make conformance` all now do genuine,
scoped work; `make test` still runs only `core/model`'s own shape tests plus P25's
`core/calc` tests, honestly named as covering none of those six on every run.

**What stops the lying next, concretely, is not one gate — it's picking which of the
six has a real trigger event**, the same standard P24's own report already applied to
Base Core's build direction: `commerce/` doesn't exist (empty scaffold since day one);
review/entitlement/billing independence are all commerce-schema features with zero
rows, zero code, and — per STANDING-BLOCKER.md, unchanged — no rights-cleared channel to
exercise them against even if built. Outcome observation (A-1.2, Track B) has a fully
drafted schema in §15 already, not yet migrated, and depends on real permit facts a
composed file has actually matched against — which doesn't exist while composition
itself is refused-only. The provider slot (I20, A-1.3) has the same property P25's own
close-out already established: fully drafted schema, zero migrations, and no forced
need until geometry is ever enabled, which nothing requires yet.

**The honest answer is that none of the six is buildable today for the same underlying
reason candidate (b) of P24's report already named**: every one of them is gated,
directly or through `commerce/`, on the identical external rights-clearance event
`STANDING-BLOCKER.md` has recorded, unchanged, since before P20. **The cost of building
any one of them now would be the cost of fabricating the state that unblocks it** — the
one thing this entire session has refused to do, consistently, since finding #3.
**Cost of doing nothing further here**: `make test`'s own six-area gap stays honestly
named, exactly as it is today, until the external clearance this whole project has been
correctly refusing around finally happens — at which point the real trigger event for
several of these gates, and P24's own composed/partial fixtures, arrives at the same
time, for the same reason, and is worth planning as one package, not six separate ones
guessed at now.
