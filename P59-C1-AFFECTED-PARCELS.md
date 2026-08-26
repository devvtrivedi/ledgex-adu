# C1 — affected-parcel evidence capture (read-only, before any remediation)

Captured per owner instruction, before any UPDATE touches these rows. `migrate-verify`
was run against every database below before this capture (see P59-LEDGER.md's header) --
all MATCH at 56 migrations.

S1 query (as originally captured): `SELECT count(*) FROM parcel WHERE geom IS NOT NULL AND
centroid IS NOT NULL AND NOT ST_Intersects(geom, centroid);`

**Corrected (A-N14, P59C).** The query above uses `NOT ST_Intersects`; the code's own
predicate (`populate_interior_centroids`'s residual check, and the zoning join's own
exclusion) uses `NOT ST_Contains`. `ST_Contains` is strictly broader than `ST_Intersects`
here (a centroid ON the boundary intersects but does not "contain"-satisfy interiority),
so the counts below (1,213 / 1,057) are **lower bounds** on what a remediation run using
the code's own predicate will recompute -- not exact targets, and not to be presented as
either. The code-predicate verification query, for P61 to actually run:

```sql
SELECT count(*) FROM parcel
 WHERE geom IS NOT NULL AND centroid IS NOT NULL
   AND NOT ST_Contains(geom, centroid);
```

**Corrected (AD4, P59C addendum).** The query above, run raw against `ledgex_schema_check`
(docker container `ledgex`), counts **fixture/test parcels too** — that database holds 35
identity-less fixture/golden-test parcels inside its 225,077 total (P59C's own
parcel-count reconciliation, `P59C-LEDGER.md`'s "Group S" section: every one traced by name
to a known test fixture script, e.g. `TEST-P25-GEOM-*`, `TEST-C4-*`, `GOLDEN-*-FIXTURE`,
`TEST-C2-*` — some of those fixtures are deliberately geometry-pathological). A raw count
against this database is **not** the success criterion P61 should read literally: a non-zero
result could mix real remediation residue with fixture parcels that were never meant to be
remediated, reading as worse or better than the real state depending on which way the
fixtures happen to fall on a given run.

The same identity partition P59C already established for this exact database (S2: every
identity-less parcel is fixture/golden-test residue, zero unaccounted; cited, not re-derived)
excludes them:

```sql
SELECT count(*) FROM parcel p
 WHERE p.geom IS NOT NULL AND p.centroid IS NOT NULL
   AND NOT ST_Contains(p.geom, p.centroid)
   AND EXISTS (SELECT 1 FROM source_feature_identity sfi WHERE sfi.parcel_id = p.id);
```

Run read-only (`BEGIN; SET TRANSACTION READ ONLY; ... ROLLBACK;`, via `docker exec`, current
as of this addendum): raw count **1,213**; identity-restricted (real-only) count **1,213**;
fixture-attributable share of the raw count **0**. On this database, today, the two numbers
happen to coincide — none of the 35 fixture parcels currently satisfy `geom IS NOT NULL AND
centroid IS NOT NULL AND NOT ST_Contains(...)` (most have no geometry set at all). That is a
fact about the CURRENT fixture population, not a guarantee: a future fixture with real,
pathological geometry could change it, which is exactly why P61's own verification should run
the identity-restricted form above, not the raw one — a query that happens to agree with its
safer form today is not evidence the safer form is unnecessary.

## Per-database counts

| database | migrate-verify | S1 count (non-interior centroid) | of those, with a LIVE zoning.district fact |
|---|---|---|---|
| ledgex_schema_check | MATCH (56) | 1213 | **1057** |
| ledgex_test | MATCH (56) | 0 | 0 |
| ledgex_golden | MATCH (56) | 0 | 0 |
| ledgex_smoke | MATCH (56) | 0 | 0 |
| ledgex_schema_check_pre_p55_20260823 | MATCH (56) | 1213 | 0 (no zoning.district facts on this pre-P55 snapshot's affected set) |
| ledgex_smoke_pre_p55_20260822 | MATCH (56) | 0 | 0 |

Only `ledgex_schema_check` carries live, currently-served `zoning.district` facts
derived from a non-interior centroid. The other databases either have zero affected
parcels, or (the pre_p55 schema_check copy) have the same geometry defect but never
had zoning ingested against it.

## Full detail: ledgex_schema_check's 1,057 affected facts

`P59-C1-affected-facts-ledgex_schema_check.csv` (this directory) — one row per
currently-live (`superseded_at IS NULL`) `zoning.district` fact whose parcel's stored
centroid is not interior to its own geometry. Columns: `parcel_id, fact_id, value,
snapshot_id, licence_id, confidence, recorded_at, superseded_at`.

Captured via (read-only, SELECT/COPY TO STDOUT only):
```sql
SELECT p.id AS parcel_id, f.id AS fact_id, f.value, f.snapshot_id, f.licence_id,
       f.confidence, f.recorded_at, f.superseded_at
FROM fact f
JOIN parcel p ON p.id = f.parcel_id
WHERE f.field_key = 'zoning.district' AND f.superseded_at IS NULL
  AND p.geom IS NOT NULL AND p.centroid IS NOT NULL AND NOT ST_Intersects(p.geom, p.centroid)
ORDER BY p.id;
```

All 1,057 rows: `snapshot_id = ca_san_jose.zoning_districts:sha256:eae7823a2...`
(the 86MB/13,691-feature real snapshot, same one S5 downloaded), `licence_id =
cc_by_4_0_api_2026_08`, `confidence = high`, `recorded_at = 2026-08-23 22:07:26`,
`superseded_at = NULL` on every row (never yet corrected).

Full id list of all 1,213 geometrically-affected parcels (superset of the 1,057 --
includes 156 with no live zoning.district fact, e.g. zero_match/ambiguous outcomes):
`s1_affected_parcel_ids.txt` in the session scratchpad (not copied into the repo --
regenerable at any time from the S1 query; the fact-bearing CSV above is the
durable, load-bearing evidence).

## C1 remediation — enumerated, NOT executed this pass

This is a plan, not work performed. Executing it is a separate authorization
(fact-writing against a real database) from this evidence capture.

1. Fix `parcel.centroid` for the 1,213 affected parcels on `ledgex_schema_check`
   using the same logic as `scripts.ingest_zoning_permits.populate_interior_centroids()`
   (already landed, code-only, this pass) -- i.e. re-run the fixed
   `scripts/ingest_zoning_permits.py --phase zoning` ingest against
   `ledgex_schema_check`, which calls that function itself as its own first step.
2. That same ingest run's existing full-reclassification-every-run behavior
   (load_zoning has no same-snapshot short-circuit -- see that function's own
   docstring) will then recompute zoning classification for every parcel using the
   now-corrected centroids, and its existing diff/supersede logic will supersede
   (never update -- I4) any of the 1,057 facts above whose new classification
   differs from the old, wrong one. No new supersession code is needed; this is the
   ingest's own existing reconcile path, exercised for real for the first time
   since the parcel geometry it depends on will have changed.
3. Requires: the real `ca_san_jose.zoning_districts` snapshot bytes (already
   confirmed present at `s3://ledgex-snapshots-locked/sha256/ea/eae7823a2...`,
   downloaded once already for S5 into the scratchpad), a `snapshot_id` argument,
   and running the ingest as a real job_run against `ledgex_schema_check` with
   `DATABASE_URL` explicitly overridden to the local container (never the `.env`
   default -- see the safety note in P59-LEDGER.md).
4. **Corrected (A-N12, P59C).** The command below was wrong: `--phase zoning` is
   not in the script's argparse surface (`--source {zoning,permits}` and
   `--phase {b,load}` are two separate flags) -- the original form died on first
   contact, safely (`SystemExit: 2`, before opening a connection), but P61 is the
   pass that runs this under owner authorization and it should not have to
   discover the correct flags for the first time then. Corrected command (still
   not run this pass):
   `DATABASE_URL="postgresql://postgres:x@localhost:5432/ledgex_schema_check" \
   .venv-ingest/bin/python3 scripts/ingest_zoning_permits.py --source zoning \
   --phase load \
   --snapshot-id ca_san_jose.zoning_districts:sha256:eae7823a22e72537d5738d473c6c8289e0e2af78e76be782ea5e432fdd5d04ba`
   Verified argparse accepts this exact form: run against a deliberately
   nonexistent database (`DATABASE_URL=postgresql://dev@localhost/ledgex_does_not_exist_dryrun`),
   it parses cleanly, dispatches to `phase_zoning_load()`, and fails only at
   `get_db()`'s connection attempt (`psycopg2.OperationalError: ... database
   "ledgex_does_not_exist_dryrun" does not exist`) -- proving the flags parse and
   dispatch correctly without ever reaching a real database or writing anything.
5. Expected result: the **identity-restricted** code-predicate query (AD4, above — not the
   raw form) returns 0 on `ledgex_schema_check` afterward, and at least the 1,057
   facts in the CSV above each show a non-null `superseded_at` with a real
   successor fact citing the corrected centroid's classification (or, for parcels
   whose correct classification happens to match the old one, no change at all --
   the diff is real, not assumed to flip every row). Re-check the fixture-attributable
   share at verification time too (AD4's third query) -- do not assume it is still 0.

**Until this remediation runs, C1 is not FIXED** -- the code defect is closed and
proven, but the live, currently-served wrong facts on `ledgex_schema_check` remain
uncorrected and the map phase remains stop-ship on this specific point. See
P59-LEDGER.md's C1 row.
