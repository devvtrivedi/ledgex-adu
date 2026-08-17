## P15 — Bookkeeping, then finding #21: source-scope the three reconciliation reads

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)).

---

### Part 1 — Bookkeeping (not a package on its own)

Three rows added to the [Open findings](README.md#open-findings-reconciled-against-ledgex_handoffmd-8-2026-08-15)
table (#24, #25, #26) documenting things P14 left only in narrative/package-file form:
`ledgex_schema_check`'s exact before-state, the disposable-database enforcement question P14
deliberately left undecided, and that teardown does not run when `ON_ERROR_STOP` aborts the
suite (already noted in `invariants.sql`'s own comment, not previously in this table). One
commit, `prompts/` only — `721a138`.

---

### Part 2 — Finding #21: source-scope the three reconciliation reads

**The finding, restated precisely.** `scripts/ingest_zoning_permits.py`'s `load_zoning` and
`load_permits` each build a `live` dict — `{(parcel_id, field_key): (fact_id, value) for ...}`
— from a plain `SELECT ... WHERE field_key IN (...) AND superseded_at IS NULL`, no
`source_id` filter. `scripts/ingest_parcels.py`'s `changed_rows` query joins `fact` the same
way. `fact_one_current_per_source` (`0006`) is unique *per source* — nothing stops a second
source from holding its own live fact for the same `(parcel, field)` at the same time. None
of these three reads distinguish "my own prior fact" from "some other source's current fact."

#### Step 2 — reproving the no-op, not taking P11's word for it

P11 first argued this was safe as a no-op on real data. P13 then rewrote
`ingest_parcels.py`'s `changed_rows` join from INNER to LEFT with a CASE-based predicate —
a different query shape than the one P11's proof was run against. Re-proved from scratch,
both ways:

**SQL-level, against `ledgex_schema_check`'s real ~225K-parcel/~1.1M-fact data.** "One
source per field" still holds post-P13, checked directly (`COUNT(DISTINCT source_id)` per
`field_key`, all 6 relevant fields — `parcel.apn`, `parcel.geometry`, `zoning.district`,
`zoning.district_verbatim`, `permits.active`, `permits.series_earliest` — every one exactly
1). With/without-filter row counts identical for all three reads: zoning `live` map 886=886,
permits `live` map 6984=6984, `changed_rows` LEFT JOIN (self-comparison technique reused
from P13) 0=0.

**Real-script level, not just SQL simulation.** Two scratch databases, both schema+seed,
`p15_noop_a` run with the current (then-unfiltered) code, `p15_noop_b` run with
`AND source_id = %s` added to all three reads (`fa`'s filter in the `ON` clause for
`ingest_parcels.py`'s LEFT JOIN specifically — not `WHERE`, which would silently collapse
the LEFT JOIN back into an INNER JOIN for rows where no live fact exists at all, exactly the
regression P13 fixed). Same P5 fixture sequence (parcels load, zoning A, permits A) against
both. Every `diff_counts` line byte-identical:

```
permits.active: same=0 different=0 new=2 retired-no-successor=0
permits.series_earliest: same=0 different=0 new=2 retired-no-successor=0
zoning.district: same=0 different=0 new=21 retired-no-successor=0
zoning.district_verbatim: same=0 different=0 new=21 retired-no-successor=0
new: 29  changed: 0 (apn=0, geometry=0)  reappeared: 0  disappeared: 0
resolvable APN: 27  unresolvable: 2 (blank=2, placeholder=0)
```

And every downstream table count identical between the two databases: `parcel` 29/29,
`fact` 131/131, `parcel_exception` 10/10, `source_feature_identity` 29/29, `job_run` 3/3.

**P13's join-shape change did not alter the answer P11 originally recorded.** Still a safe
no-op on current data, confirmed at both the SQL and real-script level, post-P13.

#### Step 3 — proving it can fail, for real, on a real loader run

A pure-SQL `db/tests/invariants.sql` `DO $$ ... $$` block cannot exercise this bug: the
failure lives in Python-level reconciliation logic (`load_zoning`/`load_permits`'s dict
comprehension, `phase_e`'s per-row processing loop), not in a constraint or trigger a bare
SQL script can assert against directly. This belongs in the acceptance suites, where a real
loader run already exists to drive it — same precedent as P13, which added its own new
assertions to `check_phaseb_acceptance.py` rather than inventing a SQL-only check for a
Python-level bug.

**Two genuinely different failure shapes, not one repeated twice** — the two affected
scripts fail differently, which is itself informative:

**`ingest_zoning_permits.py`'s `live` dict — silent arbitrary pick.** Real fixture: parcel
`58705049` (an existing `p5_zoning_B.geojson` CLUSTER2 parcel, real supersession expected
A→B), a second live `zoning.district` fact planted from a different real source
(`ca_san_jose.building_permits_active`, value `'R-3'`, matching what B is about to bring for
the real source too) alongside the genuine `ca_san_jose.zoning_districts` fact (`'R-2'`).
Pre-fix code: the dict comprehension's last-fetched row won — the foreign `'R-3'` row —
so the real source's own incoming `'R-3'` read back as "already same," and its own `'R-2'`
fact was **never superseded**, confirmed directly:

```
42493fc6...  "R-2"  ca_san_jose.zoning_districts        <- still live, never touched
da0975cc...  "R-3"  ca_san_jose.building_permits_active <- planted, wins the dict key
```

Post-fix: the real source's own fact correctly superseded to `'R-3'`, the foreign fact
untouched. Now a permanent stage in `scripts/run_p5_acceptance.sh` ("SOURCE-SCOPE CONFLICT")
+ new assertions in `scripts/check_p5_acceptance.py` (`after-source-scope`) — proven RED
against `/tmp/izp_before_p15.py` (pre-fix), GREEN against the working tree, three times each
(twice seeded scratch, once fresh migrations-only), on real fixture data.

**`ingest_parcels.py`'s `changed_rows` LEFT JOIN — a crash, not a silent miscompare.**
Different bug shape than the dict pattern: a SQL JOIN doesn't silently overwrite on a key
collision, it emits one row per match. Planting a second live `parcel.apn` fact for
`source_feature_id 568` from a foreign source (value `'99999999FOREIGN'`, differing from
both the real source's current live value and its next incoming value) makes **both** the
real row and the foreign row satisfy the query's "differs from incoming" predicate — two
`changed_rows` entries for one feature. The processing loop attempts to write a new
superseding fact for both. Pre-fix, this crashes the whole `job_run` on a real constraint,
`fact_one_current_per_source` (two new facts for the same `(parcel_id, field_key,
source_id)` in one batch):

```
psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint
"fact_one_current_per_source"
DETAIL: Key (parcel_id, field_key, COALESCE(source_id, '~derived'), COALESCE(method_version, '~'))
        =(1e611c59-..., parcel.apn, ca_san_jose.parcels, ~) already exists.
```

Post-fix, the foreign row is invisible to the LEFT JOIN entirely (filtered in the `ON`
clause), one row, correct supersession, no crash. Now a permanent stage in
`scripts/run_phaseb_acceptance.sh` + new assertions/mode in
`scripts/check_phaseb_acceptance.py` (`after-source-scope`) — proven RED against
`/tmp/ip_before_p15.py`, GREEN against the working tree, three times each. Fixing this
surfaced a real, unrelated scoping gap in two of `check_phaseb_acceptance.py`'s own
pre-existing `after-a2` assertions (an unfiltered `JOIN fact` that would have double-counted
the planted foreign row) — scoped by `f.source_id = 'ca_san_jose.parcels'` to match what
their own comments already claimed ("A → B successor → A2 successor", a single-source
chain), not weakened; re-verified the original three-row/new-id assertions still hold
post-fix.

**`load_permits`'s `live` map not separately re-proven with its own fixture** — same dict-
comprehension pattern, same fix shape, same mechanism as `load_zoning`'s proven case;
building a third near-identical fixture would exercise the same code path a second time
without adding evidence. The SQL-level and real-script no-op proofs in Step 2 already cover
it at the "does the filter change anything today" level; the "can it fail" mechanism is
identical to the zoning case above, not independently re-derived.

#### Built

`AND fa.source_id = %s` added to `ingest_zoning_permits.py`'s `load_zoning`/`load_permits`
`live`-map queries and to `ingest_parcels.py`'s `changed_rows` `LEFT JOIN fact fa` (`ON`
clause, not `WHERE` — preserves LEFT JOIN semantics for rows with no live fact at all) and
`JOIN fact fg` clauses, parameter tuples updated accordingly. New permanent regression
coverage: `scripts/run_p5_acceptance.sh` + `scripts/check_p5_acceptance.py`'s
`after-source-scope` checkpoint (zoning); `scripts/run_phaseb_acceptance.sh` +
`scripts/check_phaseb_acceptance.py`'s `after-source-scope` mode (parcels). Both wired into
already-existing CI gates (`p5-acceptance`, `phaseb-acceptance`) — no `db.yml` changes
needed, the new stages are additional steps inside scripts CI already runs end-to-end.

#### Close-out

Finding #21 closed in `prompts/README.md` with this evidence. All four CI jobs (`schema`,
`p5-acceptance`, `phaseb-acceptance`, `docs`) confirmed green on the real GitHub Actions
runner after push — run IDs in the README row.
