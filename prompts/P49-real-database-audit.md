# P49 — run the provenance audit against the real local databases

P45 built `scripts/audit_snapshot_provenance.py` and proved it works by
planting a bad snapshot in a throwaway fixture database and watching the
audit find exactly that one. That left the actual question unanswered: has
the provenance bug P45 fixed ever fired against real data? This package asks,
read-only, and stops at the answer.

Baseline: `main` at `4109d8c`, in sync with origin. Branch:
`p49-real-database-audit`, cut from that commit. `main` not touched.

## STEP 0 — reported before running anything, approved before proceeding

### 0(a) Database enumeration

Every local Postgres database (`psql -l`, excluding `postgres`/`template0`/
`template1`/`template_postgis`) queried for `SELECT count(*) FROM snapshot`,
`SELECT count(*) FROM fact`, not assumed from name:

```
ledgex_p39_scratch         | 1|1
ledgex_p39v_green          | 1|1
ledgex_p39v_red            | 1|1
ledgex_p39v_run1           | 27|70
ledgex_p39v_run1_test      | NO snapshot/fact table
ledgex_p39v_run2           | 26|69
ledgex_p39v_run2_test      | NO snapshot/fact table
ledgex_p40_gate1           | 22|67
ledgex_p40_gate2           | 22|67
ledgex_p40_refactor_after  | 9|9
ledgex_p40_refactor_before | 9|9
ledgex_p40_seedtest        | 2|2
ledgex_p41_gate1           | 24|67
ledgex_p41_gate2           | 24|67
ledgex_p42_final           | 3|3
ledgex_p42_gate1           | 27|70
ledgex_p42_gate2           | 27|70
ledgex_p42_green           | 3|3
ledgex_p42_red             | 2|2
ledgex_p43_ci_sim          | 27|70
ledgex_p43_maketest        | 3|3
ledgex_schema_check        | 24|1135140
p22_isolate                | 5|330
p22_isolate2               | 5|330
p22_p5_run1/2/3            | 5|250  (each)
p22_phaseb_run1/2/3        | 4|169  (each)
p22_scratch                | 10|401
p23_phaseb_idem            | 4|171
p24_p5_run1/2/3            | 5|250  (each)
p24_phaseb_run1/2/3        | 4|169  (each)
p24_scratch                | 4|44
p25_golden                 | 2|6
p25_golden_verify1         | 2|8
p25_golden_verify2         | 2|4
p25_p5_run1/2/3            | 5|250  (each)
p25_phaseb_run1/2/3        | 4|169  (each)
p25_scratch                | 4|4
p25_test_final             | 8|19
p26_ci_sim                 | 19|62
p26_final                  | 6|13
p26_fresh                  | 0|0
p26_p5_run1/2/3            | 5|250  (each)
p26_phaseb_run1/2/3        | 4|169  (each)
```

**63 databases total. Exactly one is a real working database:
`ledgex_schema_check`** (24 snapshot rows, 1,135,140 fact rows). CLAUDE.md's
own text names it "the local dev database, matching the Makefile's own
`DATABASE_URL` default" — but that alone is a naming claim, not evidence, so
it was checked, not assumed:

- `make migrate-verify` first, per CONVENTIONS: `MATCH — ledgex_schema_check's
  live schema is exactly what its ledger claims. 55 migration(s) verified.`
  Trustworthy as evidence.
- Of its 24 snapshot rows, **8 are real**: `source_id` is
  `ca_san_jose.{parcels,zoning_districts,building_permits_active}` (no `test`
  anywhere in the name), `fetched_at` spans **2026-08-07 to 2026-08-17** (real
  multi-day ingest history, not one test run), and every one points at
  `s3://ledgex-snapshots-locked/...` — the real bucket, confirmed by real
  credentials (`.env`) and a real `head_object` (one object, 210,298,303
  bytes, confirmed present). Total real bytes across all 8:
  **302,729,322 bytes (~289 MiB)**.
- The other **16 are test/fixture rows**: `test.*`/`ca_san_jose.test_source*`/
  `test_other_jurisdiction.*` source_ids, `object_uri` pointing at buckets
  literally named `test` (7 rows, 1 byte each) or `bucket` (9 rows, 100 bytes
  each — matching `db/tests/invariants.sql`'s own hardcoded
  `'s3://bucket/test'` fixture snapshot exactly).

**Every other database (62) is a per-package disposable evidence artifact,
confirmed by content, not just name.** Several of them — `ledgex_p43_ci_sim`,
`ledgex_p42_gate1`, `ledgex_p41_gate1`, `ledgex_p39v_run1` — do carry rows
with real-looking `source_id`s (`ca_san_jose.parcels`,
`ca_san_jose.zoning_districts`), so name alone was not trusted. Checked
directly:

```
ledgex_p43_ci_sim's ca_san_jose.parcels/zoning_districts snapshots:
  s3://test-bucket/sha256/dd/...
  s3://test-bucket/sha256/82/...
  s3://golden-fixture-bucket/sha256/39/...
  s3://golden-fixture-bucket/sha256/07/...
  s3://golden-fixture-bucket/sha256/36/...
```

Fabricated bucket names (`test-bucket`, `golden-fixture-bucket`) that do not
exist in the real MinIO instance — synthetic fixture construction (the same
technique used in this session's own earlier evidence-gathering), never a
real fetch. None of the 62 reference the real bucket at all.

**Proposal, approved before proceeding: audit `ledgex_schema_check` only,
skip all 62 others** — they cannot answer the question this package exists
to answer (auditing them produces only fake-bucket noise) while still
costing real GetObject-attempt overhead.

### 0(b) Cost, stated before incurred

24 `GetObject` calls total against `ledgex_schema_check`: 8 real reads
streaming ~289 MiB combined; 16 reads against buckets (`test`, `bucket`) that
do not exist, failing fast with effectively zero bytes transferred (the
audit's own `unreadable` category — see STEP 2).

### 0(c) Read-only re-verification

```
$ grep -niE "INSERT |UPDATE |DELETE |TRUNCATE|ALTER |COPY |\.commit\(" scripts/audit_snapshot_provenance.py
(no output)
```

Zero write-capable statements. Every `cur.execute` in the file uses a
hardcoded `SELECT` string, including the one parameterized helper
(`count_direct`), called only three times, all with literal `SELECT count(*)
FROM ...` strings from within this same file — never with external input.
The script ends `conn.rollback()` then `conn.close()`, never a commit.

No pre-existing read-only Postgres role was available for this database, and
one was not created for this package: `CREATE ROLE` is itself a DDL write
against the real working database's cluster, outside this package's own
minimal-footprint intent. Stated plainly per the prompt's own instruction:
the read-only guarantee here rests on the grep above, not on a
database-enforced role.

## STEP 1 — the remote instance is out of scope

`LEDGEX_ALLOW_REMOTE_DB` was never set for any command run in this package.
`.env`'s live Supabase `DATABASE_URL` was never used, connected to, or
touched. **The remote instance remains unaudited** — this package's result is
not a claim about it, and README finding #23 (what state that database is
actually in) remains open, separately.

## STEP 2 — run it

**Prediction, before running:** 24 snapshot rows total. The 8 real
`ca_san_jose.*` snapshots' fact counts (675,138 / 431,714 / 27,936 — see 0(a))
are far beyond `phase_d`'s own 20-parcel sample size, meaning they were
loaded via `phase_e`, which already had `verified_snapshot_file()` protection
*before* P45 started (P45 Fix 1 was specifically about `phase_d`; `phase_e`
was already safe). Predicted: all 8 real snapshots clean (hash+size match,
`http_status=200`, already confirmed by direct query in 0(a)). The 16
fixture-bucket rows predicted `unreadable` (nonexistent buckets), not hash
mismatches. Exit code: 0 (the script has no pass/fail exit semantics — a
reporting tool, not a gate).

```
$ DATABASE_URL="postgresql://postgres:x@localhost:5432/ledgex_schema_check" \
  OBJECT_STORE_URL="http://localhost:9000" \
  OBJECT_STORE_ACCESS_KEY="ledgex_ingest_dev" \
  OBJECT_STORE_SECRET_KEY="ledgex_dev_throwaway_2026" \
  python3 scripts/audit_snapshot_provenance.py

=== SNAPSHOT PROVENANCE AUDIT ===
snapshot rows found: 24

--- per-snapshot byte verification (re-read object_uri, hash, compare) ---
  UNREADABLE  ca_san_jose.test_source:sha256:6807ac29ca72075c1cc37bbdb1ed367c967981c0c74c969d045ab5e5664f7774  reason=object_store_error:NoSuchBucket
  UNREADABLE  ca_san_jose.test_source:sha256:cff19b2a105a07f128fe53e3bef1b5fd2c0820dccfc0f65f94fd767418751fcb  reason=object_store_error:NoSuchBucket
  UNREADABLE  ca_san_jose.test_source:sha256:bef91ddbcb9895f41aa49c95501153f3d1ad4f5dc2c6f532fe488693c7e49664  reason=object_store_error:NoSuchBucket
  UNREADABLE  ca_san_jose.test_source:sha256:af9a79c43ff57207f122898e73ab04eb8178f6d05ad9e9a0287566337fc68fe3  reason=object_store_error:NoSuchBucket
  UNREADABLE  ca_san_jose.test_source:sha256:5a18494e33506d3d5c610d6e65e699b4f500767fd0c95f9ed40f64bd88987f37  reason=object_store_error:NoSuchBucket
  UNREADABLE  ca_san_jose.test_source:sha256:65886d9ab8d523000964f9ee2238a74c6a3fa60a9a6fc11691dc90ab5efa0f28  reason=object_store_error:NoSuchBucket
  UNREADABLE  ca_san_jose.test_source:sha256:46e29d1835533f9dfef783161eba2d64f8caf1b6a7024c3e5b48aba24b74fb19  reason=object_store_error:NoSuchBucket
  UNREADABLE  ca_san_jose.test_source_b:sha256:2892e288adb59f59419b9351ed48cbb14e45d0556547da33f3543e5e85b71c8d  reason=object_store_error:NoSuchBucket
  UNREADABLE  test_other_jurisdiction.test_source:sha256:ea9ca0e4800afb999739746f473257ee491bc425f267ef6046b4a016d234184a  reason=object_store_error:NoSuchBucket
  UNREADABLE  test.p21_source_bulk:sha256:1111111111111111111111111111111111111111111111111111111111111111  reason=object_store_error:NoSuchBucket
  UNREADABLE  test.p21_source_derived:sha256:2222222222222222222222222222222222222222222222222222222222222222  reason=object_store_error:NoSuchBucket
  UNREADABLE  test.p21_source_direct:sha256:0000000000000000000000000000000000000000000000000000000000000000  reason=object_store_error:NoSuchBucket
  UNREADABLE  test.p34_election_source_39940930_state:sha256:615707ed250e430893c7d5bb707a8e4a5d31b6f0f2c147b994d29f9aceb57ba4  reason=object_store_error:NoSuchBucket
  UNREADABLE  test.p34_election_source_602223c5_none:sha256:67194be8aacc46c99cafd1259c51999c0626e5bd9e3a4436b76fa2b5708cbc2e  reason=object_store_error:NoSuchBucket
  UNREADABLE  test.p34_election_source_81e634ed_city:sha256:ff956daf66f443228916dfab7cf6b3787b9f56207ae046f4a56866d19efa21e1  reason=object_store_error:NoSuchBucket
  UNREADABLE  test.p34_election_source_878df471_invalid:sha256:bf124c8e97174f5aa210ff5a457ea50a004d00599d484664bac626688799df93  reason=object_store_error:NoSuchBucket

  8 of 24 snapshots: bytes at object_uri match content_hash AND byte_size
  16 of 24 snapshots: flagged (mismatch or unreadable)

--- per-snapshot http_status ---

  0 of 24 snapshots: http_status was not 2xx (NULL counts as not-2xx)

  direct query -- snapshots with a recorded 2xx http_status: 24 of 24

--- flagged snapshots (byte mismatch/unreadable UNION non-2xx status): 16 ---
  [the same 16 ids listed above]

--- facts citing a flagged snapshot ---
```

**The join through to `fact` and parcels, in full** (this is the part that
says how big a problem is — every line reviewed, pattern shown below rather
than reproducing the complete 261-row listing, which is uniform beyond this
point):

```
  ca_san_jose.test_source:sha256:46e29d1835...: 27 fact row(s)
    fact_id=259ed6f6-...  field_key=test.t48_field  parcel_id=7e740883-...  jurisdiction_id=ca_san_jose  apn=TEST-2362368d-a828-4e3a-810e-411bca330e1e
    fact_id=464d04db-...  field_key=test.t49_field  parcel_id=7e740883-...  jurisdiction_id=ca_san_jose  apn=TEST-2362368d-a828-4e3a-810e-411bca330e1e
    [... 25 more rows, same shape: test.* field_key, TEST-<uuid> apn ...]
  ca_san_jose.test_source:sha256:5a18494e33...: 9 fact row(s)
  ca_san_jose.test_source:sha256:65886d9ab8...: 145 fact row(s)
  ca_san_jose.test_source:sha256:6807ac29c7...: 16 fact row(s)
  ca_san_jose.test_source:sha256:af9a79c43f...: 16 fact row(s)
  ca_san_jose.test_source:sha256:bef91ddbcb...: 16 fact row(s)
  ca_san_jose.test_source:sha256:cff19b2a10...: 16 fact row(s)
  ca_san_jose.test_source_b:sha256:2892e288...: 0 facts cite this snapshot
  test.p21_source_bulk:sha256:1111...: 6 fact row(s)
    fact_id=becf80b4-...  field_key=test.p21_field  parcel_id=fbf6e045-...  jurisdiction_id=test_jurisdiction_p21  apn=TEST-P21-PROVENANCE
    [... 5 more, same jurisdiction_id/apn ...]
  test.p21_source_derived:sha256:2222...: 0 facts cite this snapshot
  test.p21_source_direct:sha256:0000...: 6 fact row(s)
  test.p34_election_source_39940930_state:...: 1 fact row(s)
  test.p34_election_source_602223c5_none:...: 1 fact row(s)
  test.p34_election_source_81e634ed_city:...: 1 fact row(s)
  test.p34_election_source_878df471_invalid:...: 1 fact row(s)
  test_other_jurisdiction.test_source:...: 0 facts cite this snapshot

  total fact rows citing a flagged snapshot: 261

=== SUMMARY ===
snapshots audited:                          24
snapshots with clean bytes (hash+size match): 8
snapshots flagged (byte mismatch/unreadable): 16
snapshots flagged (non-2xx/missing status):   0
snapshots flagged (union of the two above):   16
fact rows citing a flagged snapshot:          261
distinct parcels among those fact rows:       40

fact rows with snapshot_id IS NULL (separate question, not flagged): 91

=== UNCOVERED BY THIS AUDIT ===
  - Whether the bytes a load actually PARSED at the time matched what is stored now: ...
  - job_run rows are not examined here at all ...
  - A snapshot with NO fact citing it is not itself flagged as a problem by this audit ...
  - No remediation is attempted or proposed by this script. See prompts/P45-ingest-provenance.md
    for whether these findings warrant a follow-up package.
EXIT: 0
```

**Reading the join output, not just the counts:** every one of the 261
citing fact rows carries either a `test.*`-prefixed `field_key` with a
`TEST-`-prefixed `apn` (the `ca_san_jose.test_source*` snapshots — several
nominally carry `jurisdiction_id=ca_san_jose`, since these fixtures reuse the
real jurisdiction id for convenience, but the `field_key`/`apn` shapes are
unambiguous test constructs, not real facts) or a `test_jurisdiction_p21`/
`test_p34_election_*` `jurisdiction_id` with a `TEST-P21-PROVENANCE`/
`TEST-P34-ELECTION-*` `apn` (the `test.*` snapshots). **Zero of the 261
citing rows carry a real `ca_san_jose.parcels`/`zoning_districts`/
`building_permits_active` `source_id`.** By elimination (24 total − 16
flagged = 8 clean), the 8 real production snapshots are exactly the 8 that
were never flagged. Prediction confirmed exactly: 8/8 real clean, 16/16
flagged as `unreadable` (never a hash mismatch, never a non-2xx status), exit
0.

**Result:** no evidence this bug ever mis-attributed a real fact's
provenance in the one real database examined.

## STEP 3 — close-out

Findings #46 and #47 (P45's two ingest findings) amended with a P49
addendum in `prompts/README.md`, stating the distinction explicitly: "the
fix is in place" (P45's own claim) and "the fix is in place AND no
historical damage was found" (this package's claim, scoped to
`ledgex_schema_check` only, not the remote instance) are different, and only
the second is settled here.

`prompts/README.md`'s P48 row corrected: `67a9d78` was labeled "merge one"
where it was merge two (merge one was p45's fast-forward, which produced no
merge commit of its own) — the P48 report itself already had the order
right, so the row contradicted the document it cited. Unrelated correction,
riding along per the dispatching session's own instruction, called out here
and in the commit message rather than left unexplained.

P49 package row added.

## Evidence

**No new gate is added by this package, so there is no new check to break
deliberately.** CONVENTIONS' see-it-fail rule applies to checks this package
introduces; it introduces none — the audit itself was already proven to fail
correctly, by P45, against a planted row.

`make qa` / `make check-boundary`, predicted green (this package edits only
its own report and `prompts/README.md`, nothing `qa_check.py` or
import-linter validate), then run locally:

```
$ make qa
DOCUMENT QA PASSED — ...
$ make check-boundary
...
Contracts: 5 kept, 0 broken.
...
DOCUMENT QA PASSED — ...
```

Both green, as predicted. Pushed; both push/PR-gated workflows confirmed
green on the real runner for the branch tip — job level for `db.yml`,
`make qa` and `make check-boundary` separately for `docs.yml` (URLs and
results in the close-out commit's own report addendum, gathered the same
way as every prior package this session).

## Boundaries respected

Read only: zero `INSERT`/`UPDATE`/`DELETE` against any database (re-verified,
0(c)); zero object-store writes (the script only ever calls `GetObject`).
No remediation, no supersession, no spec bump, no migration — the audit
found nothing to remediate against real data, and if it had, this package
would have stopped and reported rather than designing a fix.
`LEDGEX_ALLOW_REMOTE_DB` stayed unset for every command; the remote instance
was never touched. No live county endpoint fetched, no ingest phase run.
No behavior change to any script, route or gate. `main` not touched. The
viewer's posture is unchanged (127.0.0.1, no auth, `VIEWER_CHANNEL="api"`,
LD-1 still open — every real `licence_channel` row remains `allowed=false`,
so the viewer still shows values only for the seeded `internal_test.*`
facts; this is the rights gate working as designed, not a defect).

## Review findings

(none yet — filled in by review)
