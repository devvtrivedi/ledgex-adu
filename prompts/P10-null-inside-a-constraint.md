## P10 — The NULL-inside-a-constraint class: findings #8 and #19, one package

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). This package was reserved by
finding #19 alone (see P11's own header note: "Numbered P11, not P10"); widened here to
the whole class once #8 was recognized as the same defect, argued twice in
`prompts/CONVENTIONS.md`'s own "Shapes that keep recurring" section before this package
started.

---

### 1. Both failures established for real, before designing anything

**#8.** Predicted ACCEPTED (the bug), then run against a real database: `property_file`
rows with `refusals = '[{}]'`, `'[{"code": null}]'` and `'["not-an-object"]'` were all
accepted by the CHECK that exists to reject an unknown code — `elem ->> 'code'` evaluates
SQL NULL for all three shapes, and `NULL NOT IN (...)` evaluates NULL, not true. A fourth
shape, established the same way rather than assumed: `refusals` not an array at all
(`'{}'`, `'"just-a-string"'`) does **not** go through this NULL mechanism — it raises a
hard runtime error from `jsonb_array_elements()` ("cannot extract elements from an
object"/"...from a scalar"), fired unconditionally from `refusals_codes_valid()` itself,
and independently from `file_refusal_reason`'s own `jsonb_array_length(refusals)` call
whenever `status='refused'`. A worse failure mode than a clean CHECK violation, not a
better one.

**#19.** README cites 157→314 from an earlier session; this package's own instruction was
explicit — get a new number, don't cite that one. Built a minimal, real repro: one
deliberately self-intersecting zoning polygon, uploaded as a real snapshot, classifying
one real parcel via `ST_MakeValid` repair through the actual spatial join
`flag_zoning_source_geometry` re-derives. Bypassed P9's `parcel_id`-keyed application
guard (temporary, reverted, not committed) and ran the real script twice against
unchanged data: 1 row became 2, no `UniqueViolation`, `0045`'s index never fired.
Confirmed directly, not inferred: `SELECT ... GROUP BY ... HAVING count(*) > 1` showed two
open rows for the same `(parcel_id, detector_key, detector_version)`.

---

### 2. Reported before writing either migration

**#19's two candidates, argued:**
- (a) Give `zoning_source_geometry_invalid` a real `'reason'` key going forward.
  Rejected — does nothing for rows already stored, and this detector has exactly one
  condition with no natural sub-classification the way
  `zoning_spatial_join_unresolvable` genuinely has two (`no_containing_district` vs
  `multiple_containing_districts`, which legitimately coexist open for the same parcel —
  `0045`'s own point in existing). Inventing a `'reason'` value here is either a
  duplicate of `zoning_source_reason` under a second key for no dedup benefit, or one
  constant literal for every row this detector will ever write — at which point it is a
  `COALESCE` sentinel by another name, done in application code instead of the
  constraint.
- (b) Key the index on `COALESCE(detail->>'reason', '')`. Chosen — no change to what any
  detector writes, and, being an index rebuild rather than an application convention,
  applies retroactively: `CREATE UNIQUE INDEX` validates existing rows, so any database
  already carrying the silent-doubling duplicates would fail to apply this migration
  until remediated (checked, see below — none did).

**Precedent checked, not assumed to transfer wholesale:** `0006`'s
`fact_one_current_per_source` already uses exactly this `COALESCE` technique for
`source_id`/`method_version`. Same mechanism, different justification: there, NULL
`source_id` is a legitimate, permanent domain state (a derived fact has no source, by
I2's two-path design, on every derived fact that will ever exist). Here, NULL
`detail->>'reason'` is simply that one detector's shape never had the key, uniform across
100% of its own rows — confirmed to have zero effect on every *other* detector's rows
(`parcel_geometry_invalid`, `zoning_spatial_join_unresolvable`, `parcel_apn_unresolvable`
(P13), `parcel_disappeared_from_source`) by reading every `exception_rows` call site, not
assumed: all four already set a real, non-null `'reason'`.

**#8's TRAP, settled before writing:** `ALTER TABLE ... ADD CONSTRAINT` validates
existing rows. Queried every database reachable from this session
(`ledgex_schema_check`, 24 real `property_file` rows, plus seven tier-2 scratch
databases) for any row the tightened shape check would reject — **zero, everywhere**.
The fix is DROP+ADD (new constraint name, forcing real re-validation), not a same-named
`CREATE OR REPLACE FUNCTION` left silently under the old, already-validated constraint —
had any offending row existed, this migration would have failed to apply and
remediation would have been reported as its own step, not absorbed here.

**#19's same trap, checked the same way:** queried every reachable database for
`(parcel_id, detector_key, detector_version, COALESCE(reason,''))` groups with
`count(*) > 1` among open rows — zero, everywhere.

**§9 vocabulary preserved:** `0048`'s replacement function copies `0038`'s 19-code list
byte-for-byte. `build/qa_check.py`'s `check_refusal_codes_match_spec` reads `0038`'s own
file text specifically (hardcoded path) and `0038` is never edited (forward-only) — the
check keeps passing unchanged, confirmed by running it, not assumed.

---

### 3. Built, RED-first, both halves

`db/tests/invariants.sql` gained T79–T85 (floor 95 → 102): four negatives + one positive
control for #8's shape rejection, one negative + one positive control for #19's
duplicate rejection. RED against a real pre-`0048`/`0049` schema copy (migrations
0001–0047 only) — real output, the suite aborting at the first genuine failure under
`ON_ERROR_STOP` (same shape every prior package's RED-first proof has shown). GREEN
after, three times: twice fresh migrations-only, once reseeded mid-run (102/102/103 — S1
counts when seeded).

Fixing #19 surfaced a real, latent test-fixture bug the *never-actually-enforcing* old
index had been hiding: two unrelated earlier tests (`T5`, `T30`) both used the generic
`'test_detector'/'v1'` key with no `'reason'` for the same shared fixture parcel, silently
never colliding under the old bare-expression index. Gave `T30` its own `detector_key` —
scoping the fixture, not weakening the new constraint, which is now doing exactly its
documented job. `T60`/`T73` updated to assert the renamed constraint/index (same
behavior, new names from the DROP+ADD).

`db/schema.sql` regenerated; `make schema-dump` confirmed no diff.

---

### 4. The rule written down

Exactly three expression-keyed constraints/indexes exist in `db/migrations/` — verified
directly (`grep -n -- "->>" db/migrations/*.sql`), not taken from any earlier report:
`0038:73` (broken, fixed by `0048`), `0045:71` (broken, fixed by `0049`), `0006:67` (the
correct one, `COALESCE`-guarded from the start). `prompts/CONVENTIONS.md`'s existing "NULL
inside a constraint silently disables it" entry gained the actual requirement: any
constraint keyed on an expression, not a plain `NOT NULL` column, must state in its own
migration's header what it does when that expression evaluates NULL — impossible (say
why), possible and handled (say how), or possible and unhandled (say so as a known gap).
`0048` and `0049`'s own headers satisfy this themselves, not just argue for it.

---

### 5. Findings #8 and #19 — closed

See `prompts/README.md`'s Open findings table and P10 row for commit SHAs and CI run IDs.
