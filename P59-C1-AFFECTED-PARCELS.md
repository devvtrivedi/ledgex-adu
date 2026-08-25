# C1 — affected-parcel evidence capture (read-only, before any remediation)

Captured per owner instruction, before any UPDATE touches these rows. `migrate-verify`
was run against every database below before this capture (see P59-LEDGER.md's header) --
all MATCH at 56 migrations.

S1 query: `SELECT count(*) FROM parcel WHERE geom IS NOT NULL AND centroid IS NOT NULL
AND NOT ST_Intersects(geom, centroid);`

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
5. Expected result: S1 returns 0 on `ledgex_schema_check` afterward, and the 1,057
   facts in the CSV above each show a non-null `superseded_at` with a real
   successor fact citing the corrected centroid's classification (or, for parcels
   whose correct classification happens to match the old one, no change at all --
   the diff is real, not assumed to flip every row).

**Until this remediation runs, C1 is not FIXED** -- the code defect is closed and
proven, but the live, currently-served wrong facts on `ledgex_schema_check` remain
uncorrected and the map phase remains stop-ship on this specific point. See
P59-LEDGER.md's C1 row.
