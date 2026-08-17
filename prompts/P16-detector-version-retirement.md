## P16 — Finding #18: exceptions stranded by a detector_version bump

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Report-first (this package's
report is folded in below rather than duplicated as a separate file) — nothing built until
the design was settled and confirmed.

---

### 0. `ledgex_schema_check`'s ledger, fixed first

Its `schema_migrations` topped out at `0047`; `0048`/`0049` (P10) had never been applied —
confirmed live before touching anything else, not assumed. Second occurrence of this exact
failure shape, not the first: `db/README.md`'s own decision-procedure section already names
a six-migration pre-P6 drift as the reason `make migrate`/`migrate-verify` exist at all. This
time, two migrations behind. Fixed per that section's own "existing database with a
`schema_migrations` table already" case:

```
$ make migrate
applying 0048_refusals_codes_valid_reject_null_shapes.sql
applying 0049_parcel_exception_reason_coalesced.sql
applied 2 migration(s)

$ make migrate-verify
building reference from exactly the 49 migration(s) ledgex_schema_check's own ledger claims are applied
MATCH -- ledgex_schema_check's live schema is exactly what its ledger claims. 49 migration(s) verified.
```

Findings row #27 added for the drift itself.

---

### 1. The design (report, settled before any code was written)

**P9's exact `(detector_key, detector_version)` matching is kept, not widened.** Confirmed
by reading all three closure helpers directly: `close_resolved_exceptions`,
`close_exceptions_for_parcels` and `relink_reopened_exceptions` all bind `detector_version`
to a single parameter value in every `WHERE` clause — none can see a different version.
Widening any of them would write `condition_cleared`, or a reopening link, for a rule the
running detector never evaluated — the exact fabrication `0047`'s own header already
refused.

**Population re-established, not cited.** `ledgex_schema_check`, queried directly (after
the ledger fix above):

```
zoning_spatial_join_unresolvable | 1.0 | open              | 10150   (12 multiple_containing_districts + 10138 no_containing_district)
zoning_spatial_join_unresolvable | 2.0 | open              | 224645
zoning_spatial_join_unresolvable | 2.0 | condition_cleared | 46
parcel_apn_unresolvable          | 1.0 | open              | 54
parcel_geometry_invalid          | 1.0 | open              | 28
zoning_source_geometry_invalid   | 1.0 | open              | 157
```

(`test_detector`/`test_t73_detector` rows excluded — `db/tests/invariants.sql` fixture
residue, confirmed by grep, not real ingest output, per P14's taxonomy.)

Confirmed zoning is the only key that has ever bumped, two ways: `git log -p` on every
`DETECTOR_VERSION*` constant shows exactly one `-`/`+` pair, on
`DETECTOR_VERSION_ZONING_UNRESOLVABLE` (`1.0` → `2.0`) — every other constant was added once
and never touched again; and live data agrees, every other real `detector_key` has rows at
exactly one version.

**Mechanism shown, not assumed.** `0045`'s (then still-live, pre-`0049`) index —
`UNIQUE (parcel_id, detector_key, detector_version, (detail->>'reason')) WHERE outcome =
'open'` — has `detector_version` as part of the key, so a v1.0 open row and a v2.0 open row
for the identical `(parcel_id, reason)` don't collide:

```
parcel_id                            | reason                 | v1_open_id   | v2_open_id
0fecac1e-220f-448a-aaa0-09ace584b563 | no_containing_district | 86806209-... | 05d838fa-...
```

**Options argued:**
- **(b) leave open forever** — rejected, argued not treated as the default. Not a literal
  I12 violation (the outcome *type* stays closeable), but `outcome='open'` asserts "still
  tracked, could still resolve," which becomes false the instant the raising rule is
  retired. CONVENTIONS' "do not invent values to fill a silence," landing on the `open`
  value instead of a new one.
- **(c) a per-bump data pass, alone** — necessary as a *trigger*, not sufficient as a
  *disposition*: nothing honest to write with the existing outcome vocabulary. I14 does not
  block it — a version bump is already a human editing a source constant and redeploying;
  attaching a one-time reconciliation to that same action is not a customer-delivery queue.
- **(a) a new outcome value, `version_retired`, paired with (c)'s mechanism as its
  trigger** — wins. Deliberately not named with "superseded" (`0047`'s header reserves that
  word for `fact.supersedes_fact_id`-shaped lineage this table has no equivalent of).
  `resolved_by` for a row nothing evaluated: `'system:detector_version_retired'`, the
  retirement pass itself as the actor — not the original detector (never re-evaluated these
  rows) and not a person (I14). `unresolved` deliberately NOT reused: `0015`'s own header
  already gives it an established meaning ("looked and could not determine," a positive
  determination performed) that a version-retired row does not have.
- **Both existing closure helpers exempt, argued not asserted.** Neither answers "does this
  row's raising version still exist as a rule anything evaluates" — a fundamentally
  different question, on a different trigger (a version bump, not a regular ingest run),
  than either. The fix is a third, new function, not a change to either.
- **`reopened_from_id` — settled: no.** Already correct in existing code (both halves of
  `relink_reopened_exceptions`'s query bound to the same single `detector_version`
  parameter, confirmed by reading it). And it should stay that way: `reopened_from_id`
  models one rule's judgment recurring over time; a v2.0 row never previously evaluated and
  cleared this parcel, so it has no prior judgment to be "reopening." A rule change is not a
  reopening.

---

### 2. Built

**`db/migrations/0050_exception_outcome_version_retired.sql`** — `ALTER TYPE
exception_outcome ADD VALUE 'version_retired'` alone, following `0047`'s precedent exactly.
Header states: what the value means and how it differs from `condition_cleared`; why not
named with "superseded"; why `unresolved` was not reused; that this is an enum value, not an
expression-keyed constraint, so CONVENTIONS' NULL-clause requirement (P10) does not apply;
that a later application-level `UPDATE` referencing the literal, run in its own separate
transaction after `make schema` has already committed this migration, needs no migration of
its own — only DDL sharing *this* migration's own transaction would; IRREVERSIBLE, same as
`0047` (`ALTER TYPE ... ADD VALUE` has no `DROP VALUE`).

**`core/exceptions.retire_stranded_exceptions(cur, detector_key, retired_version)`** — one
set-based `UPDATE`, mirroring the two existing helpers' shape. Sets
`outcome='version_retired'`, `resolved_at=clock_timestamp()`,
`resolved_by='system:detector_version_retired'`, `resolution_notes` naming the retired
version. Scoped to `outcome='open'` rows at the exact `(detector_key, retired_version)`
given — every other version and every already-resolved row excluded by the `WHERE` clause
itself, not application-side filtering. `detail`, `exception_evidence`, `reopened_from_id`
untouched. Not wired into any ingest call site. `close_resolved_exceptions`,
`close_exceptions_for_parcels`, `relink_reopened_exceptions` unmodified.

`build/check_jurisdiction_names.py` run against the real tree after editing (not just a
planted-break proof): `JURISDICTION-NAME GREP PASSED — 3 file(s) under core/ scanned, no
blocklisted token found.`

Manual verification against a fresh scratch database before writing the permanent tests:
enum value present (`open, confirmed, false_positive, unresolved, condition_cleared,
version_retired`); a bare `version_retired` insert with NULL `resolved_at`/`resolved_by`
rejected by the pre-existing 0015 biconditional; three planted rows (two open at `1.0`, one
open at `2.0`, same `detector_key`) — the function retired exactly the two `1.0` rows,
left the `2.0` row open; a second call retired 0.

---

### 3. RED-first coverage

`db/tests/invariants.sql` T86-T89 (floor 102 → 106): T86 `version_retired` with a resolution
set satisfies 0015 (positive control); T87 without one is rejected by the same,
unchanged, biconditional (negative control); T88 the retirement `UPDATE` — SQL text checked
against `core/exceptions.py` at the time of writing, not merely assumed to match — retires
exactly the two targeted v1.0 rows and leaves a same-detector v2.0 row open; T89 a second run
of the identical `UPDATE` retires 0.

RED, real: migration `0050` temporarily removed from `db/migrations/`, full suite run —

```
### TEST T86: version_retired with resolution set satisfies 0015 (should succeed)
ERROR:  invalid input value for enum exception_outcome: "version_retired"
```

`ON_ERROR_STOP` aborted the run there, exit code 3, exactly as expected. Migration restored,
then GREEN three times on the same accumulating scratch database plus once against a fresh
migrations-only database with no seed — all four runs `exit=0`. Class-2/class-3 confirmed
each time, not assumed: `parcel`/`fact` grew linearly across the three accumulating runs (7
→ 14 → 21 parcels; 47 → 94 → 141 facts), `parcel_exception` stayed at 0 after every run's
teardown — the new tests did not reach class 2, and P14's teardown still reaches every class-3
row these tests add.

---

### 4. Retirement run against `ledgex_schema_check` — asked first, then executed

Before-state re-derived (not copied from this report's own earlier text): 10,150 = 12
`multiple_containing_districts` + 10,138 `no_containing_district`, all `outcome='open'` at
`detector_version='1.0'`. Confirmed and reported, then explicitly confirmed with the user
before either irreversible step against this shared database.

```
$ make migrate                      # applies 0050
applying 0050_exception_outcome_version_retired.sql
applied 1 migration(s)

$ make migrate-verify
MATCH -- ledgex_schema_check's live schema is exactly what its ledger claims. 50 migration(s) verified.

>>> retire_stranded_exceptions(cur, 'zoning_spatial_join_unresolvable', '1.0')
retired: 10150
```

After-state, full detector/version/outcome breakdown, not a sample:

```
parcel_apn_unresolvable          | 1.0 | open              | 54      (unchanged)
parcel_geometry_invalid          | 1.0 | open              | 28      (unchanged)
zoning_source_geometry_invalid   | 1.0 | open              | 157     (unchanged)
zoning_spatial_join_unresolvable | 1.0 | version_retired    | 10150  (was open)
zoning_spatial_join_unresolvable | 2.0 | open              | 224645  (unchanged)
zoning_spatial_join_unresolvable | 2.0 | condition_cleared | 46      (unchanged)
test_detector / test_t73_detector fixture rows                        (unchanged)
```

`resolved_by`/`resolution_notes` uniform (`system:detector_version_retired`, `detector_version
1.0 retired`) across all 10,150; `detail->>'reason'` sampled and confirmed untouched.

---

### 5. Close-out

`db/schema.sql` regenerated from a fresh `make schema` apply, `make schema-dump` clean on
the second run (`db/schema.sql is current — no diff.`).

Spec bumped 1.33 → 1.34: `text/LedgeX_Engineering_Reference_Spec_v1_33.txt` → `git mv` →
`..._v1_34.txt` (content edited before the rename, re-`git add`ed after a later post-rename
edit — the exact staging trap CONVENTIONS' evidence rules name, caught this time by checking
`git diff --cached --stat` before committing, not after), `SPEC_VERSION` bumped in
`build/ledgex_source.py`, §3.10 gained the `0050` paragraph, a new §12 row for 1.34 added.
`make docs` / `make site` regenerated; `website/index.html`'s hardcoded version string
hand-fixed (not touched by `make site`, same known gap as P10). `qa_check.py`:
`DOCUMENT QA PASSED ... every migration referenced and resolvable ...` — confirms
`check_spec_references_migrations` sees `0050`. `make check-boundary`: clean.

Finding #18 closed in `prompts/README.md`; finding #27 (the ledger drift) added. This P16
row added to the package table.
