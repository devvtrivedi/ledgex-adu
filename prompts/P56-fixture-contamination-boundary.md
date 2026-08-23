# P56 — The fixture-contamination boundary, Phase 1: design gate only

Findings #50, #52 (corrected) and #53 (`prompts/README.md`) are three symptoms of one
missing boundary: nothing in the ingest path distinguishes test or fabricated material from
real San José bytes before either reaches the source ids production reads from. This
document is the design. **It contains no migration, no seed change, no ingest change, no
guard, no test file.** No database was dropped, written to (other than the two disposable
scratch databases named explicitly below), or modified in preparing it.

Branch: `p56-fixture-boundary`, created from `p55-scoped-unblock` at `c34f49e`. Not merged
to `main`. Not pushed. The four files modified by P55's own close-out
(`prompts/P55-scoped-unblock.md`, `prompts/README.md`, `scripts/_p55_stage6_prep.py`,
`scripts/_p55_stage6_replay.py`) are left exactly as they were — uncommitted, untouched.

**Read this first, because it changes the shape of everything below it.** §2's own
blast-radius query, run as instructed, found a **third** writer with the identical defect —
`scripts/check_golden.py` — that neither #53 nor the P56 prompt's own reconstruction named.
It is not hypothetical: it contaminated the freshly-rebuilt `ledgex_schema_check` **today**,
during this repo's own Stage 7 gate run (`make golden`), the same database P55's close-out
described as clean. The design in §3/§4 is built around three confirmed writers, not one.

---

## §1. Audit — live counts, 2026-08-23, `ledgex_schema_check` (local Docker, `postgres`
## user) unless stated otherwise

Standing hygiene completed before any of the below: `pwd` confirmed
`~/Desktop/ledgex-adu`; `git branch` (local only) confirmed `p55-scoped-unblock` at
`c34f49e`, 21 commits ahead of `main`; `git status --porcelain` confirmed the exact four
modified files and the untracked corpus the prompt named; the one stale lock
(`.git/index.lock.stale.5`) cleared, no `tmp_obj_*` present; `make migrate-verify` against
`ledgex_schema_check` returned `MATCH — 56 migration(s) verified`; `make local-up` confirmed
the viewer already healthy against the correct database.

Every claim in §1–§5 of the P56 prompt is re-verified below, in the order the prompt raises
it, not assumed:

- **The four modified/untracked files**: confirmed exactly as named, byte-for-byte the same
  set (`prompts/P55-scoped-unblock.md`, `prompts/README.md`,
  `scripts/_p55_stage6_prep.py`, `scripts/_p55_stage6_replay.py`, plus the untracked
  `LEDGEX-*.txt`/`.md` corpus and `prompts/P40-section0-decisions.md`). Left untouched.
- **`request='{}'::jsonb` cannot come out of the real ingest path**: confirmed directly.
  `scripts/ingest_parcels.py:336` builds `{"url": ..., "method": "GET", "params": {}}` on
  every real fetch; `:340` is the only `INSERT INTO snapshot` in that file, and it uses this
  variable, not a literal. `scripts/ingest_zoning_permits.py`'s own `verified_snapshot_file()`
  (read below, §2) resolves content by `snapshot.object_uri`, never touches `request`.
- **At least 26 `INSERT INTO snapshot` statements across 17 files**: recounted precisely —
  **27 statements across 17 files.** Full list in §4's writer inventory.
- **`run_p5_acceptance.sh`/`run_phaseb_acceptance.sh` carry no database guard**: confirmed
  by reading both files in full. Neither references `DATABASE_URL` anywhere except a
  docstring comment describing what the caller must already have set. No refusal, no
  `_is_local` check, no dedicated variable — the exact absence the prompt's §2.5 claims.
  This is the load-bearing half of §3 and it holds.
- **`core/` contains no jurisdiction-specific logic relevant to this family** (I1, C3):
  `grep -rn "'ca_san_jose'" core/ scripts/ingest_parcels.py scripts/ingest_zoning_permits.py`
  returns **zero** hardcoded string literals in `core/`; the two ingest scripts each carry
  exactly one module-level constant (`JURISDICTION_ID = "ca_san_jose"` /
  `SOURCE_ID_ZONING`/`SOURCE_ID_PERMITS`), read once, used consistently. This matters for §3
  and §5: nothing in the reconciliation path is hardwired to the literal string in a way a
  namespaced jurisdiction would trip over — it is hardwired to compare against it, which is
  the opposite problem and the one this design solves.

---

## §2. The reconstruction — CONFIRMED, refined in one place, and extended by one
## unanticipated finding

The cloud session's reconstruction was built from file bytes alone, no database, no object
store. Checked against both, directly, 2026-08-23.

### 2.1–2.3 — P1 through P4, each checked

**P1 — CONFIRMED.** Queried `ledgex_schema_check_pre_p55_20260823` (read-only, no write of
any kind issued against it in this pass):

```
id                                                          byte_size   fetched_at
ca_san_jose.zoning_districts:sha256:ea709a04...             817         2026-08-17 00:28:25.434207+00
ca_san_jose.building_permits_active:sha256:15b57694...      153         2026-08-17 00:28:25.434207+00
```

Both `request='{}'`. Byte sizes match `db/fixtures/p5/p5_zoning_B.geojson` (817 bytes) and
`p5_permits_B.csv` (153 bytes) exactly, and `fetched_at` sits within 369ms of `b98138f0`'s
own `fetched_at` (00:28:25.803505+00) — a single batch write, not three independent fetches.

**P2 — CONFIRMED, with one correction to the prompt's own reasoning.** All four `p5_*`
fixture files on disk hash to the wave's own snapshot ids, exactly:

```
699ec193... = db/fixtures/p5/p5_zoning_A.geojson   (loaded)
ea709a04... = db/fixtures/p5/p5_zoning_B.geojson   (never loaded)
70bf19c1... = db/fixtures/p5/p5_permits_A.csv      (loaded)
15b57694... = db/fixtures/p5/p5_permits_B.csv      (never loaded)
```

`db/fixtures/phaseb/phaseb_A.geojson` today hashes to `dfa0fa82...`, 29 features — not
`b98138f0`, as the prompt already knew. `git log --follow` on that file returns exactly two
revisions:

```
c115888  2026-08-16 18:49:39 -0700  29 features  sha256=dfa0fa82...  (current)
62cf90f  2026-08-14 12:08:02 -0700  25 features  sha256=b98138f0...  (matches the wave)
```

`62cf90f`'s own committed blob is **byte-identical** to `b98138f0` (diffed directly, not
inferred from the hash alone — see P3). **The prompt's own speculation was wrong in its
specific mechanism, not its prediction.** It guessed the 25-feature version "may have been
edited in place and never committed" — it was not. Both revisions are ordinary, clean git
commits, three days apart. `62cf90f` (2026-08-14) predates the wave (2026-08-17) by three
days; `c115888` (2026-08-17 01:49:39 UTC) landed **81 minutes after** the wave started
(00:28:25 UTC) — unrelated P13 fixture-extension work, not a cover-up, not an accident tied
to the wave at all. The file's own on-disk mtime (2026-08-17 01:47:23 UTC) sits two minutes
before that commit's own authored timestamp, consistent with a normal edit-then-commit, not
an edited-and-abandoned file.

**P3 — CONFIRMED, byte-for-byte, for all five wave snapshots including `b98138f0`.** Fetched
every object directly from MinIO (`ledgex-snapshots-locked`, real credentials from the
`ledgex_minio` container, not guessed) and diffed against both the on-disk fixture and the
relevant git blob:

```
699ec193...  550 bytes    == db/fixtures/p5/p5_zoning_A.geojson        (identical)
70bf19c1...  115 bytes    == db/fixtures/p5/p5_permits_A.csv           (identical)
ea709a04...  817 bytes    == db/fixtures/p5/p5_zoning_B.geojson        (identical)
15b57694...  153 bytes    == db/fixtures/p5/p5_permits_B.csv           (identical)
b98138f0...  22,502 bytes == git blob 62cf90f:db/fixtures/phaseb/phaseb_A.geojson  (identical)
```

Every self-hash also verified (`sha256(bucket bytes) == the id's own digest`) — the objects
in MinIO are exactly what their own content-addressed ids claim, and exactly what the
checked-in fixture corpus (present or historical) claims.

**P4 — CONFIRMED as to mechanism, REFINED as to the actual sequence.**
`ingest_zoning_permits.py`'s `verified_snapshot_file()` resolves content from
`snapshot.object_uri` (S3, hash-verified against the registered `content_hash`/`byte_size`
before the caller ever touches the bytes) — it does **not** read `run_p5_acceptance.sh`'s
own `SCRATCHPAD_REAL` copy for the `--phase load` path. So the wave's `job_run` rows
genuinely reflect what was loaded, not a copy-paste mismatch between a `--snapshot-id`
argument and a scratchpad file. All five `job_run` rows in the window (2026-08-17
00:28:25–00:29:28) are real `--phase e`/`--phase load` invocations
(`rows_in`/`rows_out` populated — a load, per P55's own discriminator, not a bare fetch),
naming exactly the wave's own snapshot ids. **But the observed sequence does not match a
full, completed run of `run_p5_acceptance.sh`.** That script's own linear flow loads zoning
A, then B, then A again, then A again (same-snapshot re-run), then B again (source-scope
step) — five distinct zoning loads, two of them against the B fixture. What actually
happened: zoning A loaded twice (00:28:40, rows_out=522; 00:29:22, rows_out=443) and
permits A loaded twice; **the B fixtures (`ea709a04`, `15b57694`) were never loaded at
all** — their own snapshot rows exist (P1) but carry zero `job_run` rows, confirmed by
direct query. This reads as a partial or interrupted invocation — someone running the
script's own early commands by hand, or the script starting and stopping before reaching
its own "ZONING B / PERMITS B" step, retried once — not a single clean end-to-end run. One
detail is left open, not solved here because it is tangential to P1–P4 and this is a design
pass, not a forensic one: re-loading the identical `699ec193` snapshot a second time, against
a database already carrying the first load's own writes, produced a different `rows_out`
(522 → 443) even though the input bytes were provably unchanged. The most likely explanation
is that the second pass's own reconciliation read a database state the first pass had
already altered (e.g. `parcel_exception` rows already open from pass one changing how pass
two's own candidate set resolves) — plausible, not confirmed, and not required to close this
design.

### 2.4 — The blast-radius query, and the finding it surfaced that nothing anticipated

Queried every database on this Postgres instance (70, excluding `template0`/`template1`/
`postgres`/`template_postgis`) for `snapshot` rows with `request='{}'::jsonb` under a real
`ca_san_jose.{parcels,zoning_districts,building_permits_active}` source id:

```
49 of 70 databases (70%) carry at least one such row.
```

Broken down by writer signature (`byte_size=1, media_type='application/json'` — a
literal — versus everything else):

```
"golden" signature   (scripts/check_golden.py):     20 databases
"wave" signature      (_p5_setup.py / _phaseb_setup.py):  31 databases
(2 databases carry both)
```

**`scripts/check_golden.py:507-517` is a third writer with the identical defect shape**,
independent of #53's `_p5_setup.py`/`_phaseb_setup.py` and independent of #50's
`db/tests/invariants.sql`:

```python
cur.execute(
    """
    INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size,
                           request, http_status, fetched_at, licence_observed_id)
    VALUES (%s, %s, %s, %s, 'application/json', 1, '{}'::jsonb, 200, now(), %s)
    ON CONFLICT (id) DO NOTHING
    """,
    (ip.snapshot_id_for(digest), ip.SOURCE_ID, uri, digest, ip.LICENCE_ID),
)
```

`ip.SOURCE_ID` and `ip.JURISDICTION_ID` (imported directly from `ingest_parcels.py`) are the
real `ca_san_jose.parcels` / `ca_san_jose`. `make_fixture_parcel_and_fact()`, twenty lines
below, then writes a real `parcel` row under `jurisdiction_id='ca_san_jose'` and a `fact`
row under `licence_id=ip.LICENCE_ID` (the real, current production licence id — today,
`cc_by_4_0_api_2026_08`) citing that fake snapshot. No `job_run` row is ever written — this
INSERT bypasses `job_run` entirely, the same way `_p5_setup.py` does.

**This is not a hypothetical risk. It happened in this repo's own `ledgex_schema_check`
today**, during this session's Stage 7 gate (`make golden`, run against the freshly rebuilt,
exact-bar-verified database). Confirmed directly:

```
ledgex_schema_check: 3 "golden" rows (fetched_at 2026-08-23 22:17:21+00, TODAY)
                    + 3 "wave" rows (the b98138f0/699ec193/70bf19c1 kept for provenance, §12.18)
                    = 6 total, not the 3 the P55 close-out's own inventory assumed
```

`prompts/P55-scoped-unblock.md` §12.18 (written before this audit) states the fresh rebuild
is "clean by construction" for the wave and does not mention `check_golden.py` at all — it
was never checked against this specific question, because the P55 pass had no reason to ask
it. The P56 prompt's own closing question in §2.4 — "is the fresh `ledgex_schema_check`
clean by construction or clean by luck?" — has a direct, dated, self-implicating answer:
**neither. It was contaminated again, by a fourth known-good, multiply-reviewed writer
(`check_golden.py` — touched by P20, P25, and P34 per `docs/LEDGEX_SPEC.md` §6.6, all
without anyone noticing this), within hours of being pronounced clean.**

This finding is not yet in `prompts/README.md`. It belongs there — as its own numbered
finding, not folded into #53, since it is a different writer with a different (if
structurally identical) defect — but adding it is a `prompts/README.md` edit, which this
design-only pass does not make. **Flagged here for the owner to decide where it lands**
(§9.6).

### 2.5 — The mechanism, confirmed

`run_p5_acceptance.sh`/`run_phaseb_acceptance.sh` take whatever `DATABASE_URL` is already
in the caller's environment; neither refuses a non-scratch target. `make golden`
(`Makefile:382` area) reads the same `DATABASE_URL` as every other target — there is no
`GOLDEN_DATABASE_URL` or equivalent. Run by hand against the Makefile's own default
(`ledgex_schema_check`), any of the three writers lands on the live database with nothing
refusing, warning, or marking the rows as fixtures.

### 2.6 — Confirmed as read

`scripts/_p5_setup.py:49-58`'s own comment, cited verbatim in the prompt, is real and reads
exactly as quoted — the licence INSERT is defended against finding #50's own failure class
by name, twenty lines above a function that does the identical thing to `snapshot`. Now a
third instance exists (`check_golden.py`) that was never in a position to read that comment
at all, since it predates it. **The lesson generalizing from one table to the next has now
failed to generalize twice**, which is the argument §3 builds on.

---

## §3. Where the boundary belongs — ranked

Four candidates, as posed. Ranked with the evidence from §2, not from first principles
alone.

**Ranking: B3 primary, B2 co-primary (defense in depth against a writer B3 cannot cover),
B4 necessary for #50 specifically, B1 retired as a primary reliance.**

**Why B3 (dedicated harness databases) is primary.** It is the only one of the four that
stops the actual **damage**, not just the provenance signature. `#53`'s real cost was never
that two invented polygons existed — it was that `load_zoning()`'s own full reconciliation
treated a 2-feature file as a complete replacement for a 225,039-parcel real source, which
requires the load to run against a database that also holds the real source's own data. If
`run_p5_acceptance.sh` had been refused before its first snapshot INSERT — the way
`scripts/smoke_real.py`'s own `SMOKE_DATABASE_URL` pattern (`smoke_real.py:257-276`: a
dedicated variable, never falling back to `DATABASE_URL`, a refusal on a non-local host, an
explicit override for a deliberate operator) already refuses a non-local target — none of
finding #53 would have been possible, regardless of what the fixture bytes looked like. It
needs no migration, no schema change, and it is a proven, already-shipped pattern in this
exact codebase (P50). Its one real gap: it protects against a *harness pointed at the wrong
database*. It does nothing for a writer invoked with **no dedicated variable at all** —
which is exactly `check_golden.py`'s own shape (`make golden` reads plain `DATABASE_URL`,
same as everything else, and always has). Extending B3 to `check_golden.py` means giving
`make golden` its own dedicated database variable, the same shape P50 already proved for
smoke — real design work, not yet scoped by this pass (§9.2/§10).

**Why B2 (a schema-level provenance guard) is co-primary, not secondary.** It is the only
remedy that would catch a writer **nobody has written yet** — the thing B1's own repeated
failure (#50, then #53, then `check_golden.py`, independently, three separate times) proves
is not a hypothetical risk. Concretely: a `CHECK` constraint refusing the literal value
`request = '{}'::jsonb` on `snapshot`, added `NOT VALID` (so it validates nothing already on
disk — C2's own immutability constraint is honored exactly, no existing row is touched,
checked, or even read by the migration) and enforced only against future inserts. This
catches `_p5_setup.py`, `_phaseb_setup.py`, and `check_golden.py` identically — all three
write the exact same literal — without needing to define what a "legal fixture" looks like
in the schema (§4.1's own question, answered concretely: the legal way to be a fixture is to
supply *something* other than the empty object, e.g. `{"fixture": "p5_acceptance"}`, which
this constraint would accept without further schema change). It does **not** catch #50 —
`db/tests/invariants.sql`'s own snapshot rows already carry a real-looking `request`
payload (`{"url": "https://example.com", ...}`); #50's contamination is at the `parcel`
level, not the `snapshot` level, and B2 has nothing to say about it.

**Why B4 (namespace) is necessary but not sufficient, and does not generalize the way it
looks like it should.** It is #50's own already-argued remedy, and §5 below confirms it
would work exactly as proposed for `db/tests/invariants.sql`. But it does **not** address
#53's or `check_golden.py`'s real damage mechanism: `load_zoning()`'s reconciliation walks
every real parcel under the real `jurisdiction_id`/`source_id`, and that walk is what does
the damage — a fixture's own parcel/fact rows living under a different jurisdiction changes
nothing about what a full reconciliation against the *real* source id does when a tiny file
is loaded into it. B4 fixes the "stray parcel pollutes a real candidate count" shape (#50,
and the parcel-level half of `check_golden.py`'s own contamination); it does not fix the
"a fixture file gets treated as a complete replacement for a real bulk source" shape (#53's
actual damage). Both matter; they are not the same fix.

**Why B1 (per-writer discipline) is retired as a primary reliance, not abandoned as a
practice.** It has now failed independently three times, by three different authors, across
different time periods, in a codebase whose own conventions (`CLAUDE.md`) explicitly name
the precedent and were read by at least one of the three (`_p5_setup.py`'s own comment,
§2.6). A remedy that depends on every future author remembering this is not a boundary; it
is a hope. Still worth keeping as documented practice — the comment in `_p5_setup.py` is
good and should stay — but nothing in this design treats it as sufficient on its own again.

---

## §4. The candidate remedies — scored per finding

One row per remedy, one column per finding, answering only "would this have caught it,
before damage" — not "is this a good idea."

| Remedy | #50 (db-test parcels) | #52-corrected (fabricated `b98138f0`) | #53 (the wave) | `check_golden.py` (new, §2.4) | A genuine truncated fetch (#52's original scenario) |
|---|---|---|---|---|---|
| **R1** refuse/flag `request={}` | No — #50 never writes `request={}` | **Yes** | **Yes** | **Yes** | No — a real truncated fetch still builds a real `request` payload (§1) |
| **R2** content-shape validation | No | Plausible — `b98138f0`'s own 25 features share the real schema exactly (it *is* real San José data, §2.2/2.3), so a schema check alone would **not** have flagged it | Yes for zoning (`"zA-1"` FACILITYID, 3-property schema) — untested for permits' own CSV shape | Would need per-source schema rules `check_golden.py`'s fixture never claims to follow (it writes `parcel.apn` directly, not through a source-shaped file) — not a natural fit | No — genuine bytes, genuine schema, just incomplete |
| **R3** row-count/byte-size sanity vs. previous snapshot | No | **Yes** — 25 vs. 225,039 is exactly this check's own target case | **Yes** — 2/3 features vs. 225,039/13,691/17,499 | N/A — `check_golden.py` never writes a row-count-bearing source file | **Yes** — this is the literal scenario R3 was proposed for |
| **R4** dedicated harness databases (B3) | Partial — stops db-test's own snapshot/source writes from landing on a shared real database, but #50's actual parcels are written by `invariants.sql` run against whatever `DB_TEST_DATABASE_URL` already resolves to (already usually a scratch db per `db/README.md` — the *residual* risk here is exactly the "no override set" case `db/README.md`'s own history names, P14/P17) | **Yes** | **Yes** | **Yes, once extended to `make golden`** (not yet true — §3) | **Yes** — prevents nothing about truncation itself, but confines its blast radius to a disposable database |
| **R5** namespaced test jurisdiction/source (B4, generalized) | **Yes** (§5) | No — `phaseb_A.geojson`'s parcels are written under the real jurisdiction via the real `--phase e` path; namespacing the *fixture file* doesn't change what `--phase e` does with it once it's given the real `--snapshot-id` | No — same reasoning; `load_zoning` reconciles against the real source regardless of what jurisdiction any fixture-origin parcel ends up under | Would stop the *parcel/fact* half of the contamination (a namespaced `jurisdiction_id`) but not the snapshot-under-real-source-id half | No |
| **R6** shrinkage guard in reconciliation | No (not a reconciliation-shaped defect) | **Yes** | **Yes** | N/A | **Yes** — the one remedy that addresses the *original* #52 scenario and #53 identically, because it doesn't care why the file is small |

**4.1 — R1's legal-fixture answer, stated concretely, not deferred.** A `NOT VALID CHECK`
constraint refusing `request = '{}'::jsonb` costs every current writer of that literal
exactly one line: supply a non-empty JSON object naming what they are, e.g.
`'{"fixture": "p5_acceptance", "reason": "..."}'::jsonb`. No new column, no new table, no
enum of "fixture kinds" to maintain. It does not need to recognize a fixture as a fixture —
it only needs to refuse the one value that is structurally indistinguishable from "nobody
recorded what fetched this," which is the actual defect, not "this snapshot is synthetic"
in the abstract. Confirmed this breaks exactly the writers it should: `check_golden.py`
(§2.4), `_p5_setup.py`, `_phaseb_setup.py` (§2.2) all use the literal; the two real ingest
scripts never do (§1); `db/tests/invariants.sql`'s own snapshot rows already comply without
any change.

**4.2 — R6 is the only remedy that closes the ENTRY/DAMAGE gap for both threats at once,
and it is also the one remedy this pass cannot actually design.** `docs/LEDGEX_SPEC.md`
§6.1, item 16, read in full per this pass's own hygiene requirement: *"Invent a numeric
threshold. Plan 2.1.4 sets none and forbids manufacturing one. If a gate genuinely needs a
number, stop and ask."* R6, exactly as proposed ("refuse to supersede more than N% of a
source's live facts in one load"), **requires inventing N.** This is not a detail to work
out in Phase 2 implementation — it is a hard stop under this repo's own governing spec,
discovered by reading the spec this pass was required to read anyway. R6 cannot be
designed with a concrete number in this pass, or arguably in any pass, without the owner (or
Plan 2.1.4 itself) setting that number first, with evidence. What this pass *can* say: R6 is
the highest-value single item on this list if that precondition clears, because it is the
only remedy that also protects against a genuine truncated fetch (#52's original scenario,
which R1/R4/R5 all miss and R3 alone among the entry-side remedies actually covers).

**4.3 — R6's second precondition, independent of the threshold question.** `phase_e`'s own
disappeared-detection has been structurally inert against the real `ca_san_jose.parcels`
dataset since `0043_source_feature_identity.sql` shipped without a backfill (finding #51) —
nobody has seen it fire correctly against real production data. Building a shrinkage guard
on top of a detector that has never run in anger is designing against an unverified
foundation. **§9.3 escalates whether #51's backfill is therefore a hard precondition of R6**;
this section's own conclusion is that it should be treated as one — a guard added on top of
inert detection cannot be trusted to behave as designed until the detection underneath it
has been seen to work at least once against real data.

---

## §5. Finding #50's namespace — both halves

**Q5.1 — Is a namespaced test jurisdiction enough, or does something assume the real id?**
Checked directly, not guessed: `grep -rn "'ca_san_jose'" core/ scripts/ingest_parcels.py
scripts/ingest_zoning_permits.py` returns zero hits in `core/` and exactly the two expected
module-level constants in the ingest scripts (§1). Every reconciliation query in both
scripts scopes its own candidate pool by comparing `parcel.jurisdiction_id` against that
constant — meaning a row under any *other* jurisdiction id is already, structurally,
excluded from both scripts' own candidate pools today, with no further change needed on
the ingest side. **`db/tests/invariants.sql` already proves the fix mechanically, for a
different pair of rows**: `invariants.sql:252` inserts a second, genuinely distinct
jurisdiction (`test_other_jurisdiction`) via a plain `INSERT ... ON CONFLICT (id) DO
NOTHING`, with its own comment explaining why (0022's FK triple needs "a genuinely different
jurisdiction to disagree with"). The identical pattern, pointed at the file's own
parcel-creation call sites instead, is the whole fix. **Answer: yes, enough — nothing
downstream assumes the literal string `'ca_san_jose'`, only that a row's own
`jurisdiction_id` matches whatever the acting script's own constant says, and a namespaced
id trivially fails that match by construction.**

**Q5.2 — Both halves, stated in those words.** Fixing `invariants.sql` fixes every future
`db-test` run. It does nothing about the ~32 `TEST-`-prefixed parcels already permanent in
`ledgex_schema_check` and any other database `db-test` has ever run against —
fact-bearing parcels are permanent by `db/tests/teardown.sql`'s own documented policy
(0017/I4), and no migration can reach them without weakening an immutability trigger, which
C2 forbids outright. **Stated plainly, as instructed: those databases stay contaminated, and
every `ca_san_jose`-scoped `job_run` metric on them stays unreliable, permanently, unless
the specific database is rebuilt from a clean base the way P55's own Stage 6 rebuilt
`ledgex_schema_check`.** §2.4's own blast-radius count is the honest measure of how many
databases that describes today: at least 49 of 70, and — per §2.4's own new finding — the
freshly-rebuilt `ledgex_schema_check` is already back on that list, from a different cause.

**Q5.3 — Migration, seed, or `invariants.sql`-only?** `invariants.sql`-only, no migration,
no seed change. `jurisdiction`'s own schema (`\d jurisdiction`, checked directly) carries no
constraint that would refuse a new row beyond its existing `CHECK (kind = ANY (...))` and
its FK on `boundary_source_id` (nullable, and `invariants.sql`'s own existing
`test_other_jurisdiction` row already supplies neither, proving a minimal test jurisdiction
row needs neither). The exact working pattern already exists in the same file, twenty lines
from where it would need to be reused.

---

## §6. Forbidden shortcuts — refused, in writing

**6.1 — Deleting or updating the contaminated snapshot rows.** Refused. Every snapshot row
named in this document — the wave's five, `check_golden.py`'s rows in 20 databases, the
`_p5_setup.py`/`_phaseb_setup.py` rows in 31 — is immutable (0021) and stays exactly where
it is. No `DELETE`, no `UPDATE`, no `ON CONFLICT DO UPDATE` was written or run against any
of them in preparing this document. The only mechanism that would remove them is a rebuild,
which is not this pass.

**6.2 — Dropping any database.** Refused. `ledgex_schema_check_pre_p55_20260823` was queried
read-only throughout — no `INSERT`, `UPDATE`, or `DELETE` issued against it, confirmed by
this document's own audit trail above (every query shown against it is a bare `SELECT`).
Nothing was dropped, including the two disposable scratch databases this pass's own
verification queries touched (`ledgex_test`, referenced only for context, never written to
in this pass) and the 70-database blast-radius survey (read-only `SELECT count(*)` against
every one, nothing else).

**6.3 — Loosening `phase_e`/`load_zoning` reconciliation to make R6 easier.** Refused. §4's
own scoring treats the reconciliation as correct and the input as the defect (matching
`prompts/P55-scoped-unblock.md` §13's own already-established finding, restated not
re-litigated). No change to either function is proposed anywhere in this document.

**6.4 — Weakening any hook or guard.** Refused; none was encountered. `.claude/hooks/
test_guard_destructive.py` was not invoked adversarially in preparing this document — every
action taken was read-only against production-shaped data (§1's audit queries) or confined
to the two branches this pass is scoped to touch.

**6.5 — Editing an existing test to make a new guard pass.** Refused, and moot in this
pass — no guard was written. §7 names, in advance, every existing test this design's
eventual guards would be expected to break, so Phase 2 has no discretion to quietly edit one.

**6.6 — Retro-fitting `request` on old rows.** Refused. R1's own design (§4.1) is `NOT
VALID`, specifically so it never touches, validates, or even reads an existing row. No
historical `snapshot.request` value is proposed to change anywhere in this document.

---

## §7. The test list — specified, not written

Each test names its file, its assertion, and its RED condition. None of these exist yet.

**T1 — THE REPRODUCTION.** File: a new, throwaway-database script (not committed as a
permanent test; see T1's own note below). Run `_p5_setup.py` plus a real `ingest_zoning_
permits.py --phase load` against a database pre-loaded with real-shaped zoning facts (the
same shape `run_p5_acceptance.sh` itself sets up before its own B step), and show the
supersession happen — a real classification retired with no real successor, caused
entirely by a 2-3 feature fixture file. **RED condition: it fails to reproduce.** That
would refute §2 in a way this whole document depends on, and is worth more than everything
after it. (Reused, not duplicated: `run_p5_acceptance.sh` itself, run to completion against
a throwaway database that also carries a real-shaped baseline, is the reproduction — no new
harness needs writing for T1 specifically.)

**T2 — THE BOUNDARY REFUSES.** Whichever remedy Phase 2 selects from §3/§4 (most likely R1
+ R4, per this design's own ranking), the T1 sequence is refused before any damage occurs.
**RED: the guard is removed, or its condition inverted (e.g. `request != '{}'` instead of
`request = '{}'`).**

**T3 — NEGATIVE CONTROL: a real ingest still succeeds.** A genuine `--phase b` fetch →
snapshot → `--phase e`/`--phase load` sequence, against a live-network-shaped (or recorded
real-response) source, still writes real facts end to end. **RED: the guard's own condition
is widened** (e.g. changed to reject any `request` shorter than some byte count, which would
eventually catch a real minimal-but-genuine response too). This is the test that keeps R1
from becoming a production outage — named explicitly because C1 requires the boundary to
hold against the real writer without also holding against the real ingest path, and those
two paths differ only in exactly the field this remedy inspects.

**T4 — NEGATIVE CONTROL: every legitimate fixture writer still works.** Named individually,
not "the fixture writers" as a group — §2.4/§4's own writer inventory, all 17 files that
`INSERT INTO snapshot`:

```
db/tests/invariants.sql                          -- already compliant (§3), unaffected by R1
scripts/_p55_stage6_prep.py                       -- copies real, already-verified request payloads; unaffected
scripts/_p5_setup.py                              -- MUST be updated to satisfy R1 (§4.1) -- this is the point
scripts/_phaseb_setup.py                          -- MUST be updated, same reason
scripts/check_golden.py                           -- MUST be updated, same reason
scripts/ingest_parcels.py                         -- unaffected (real request payload, §1)
scripts/ingest_zoning_permits.py                  -- unaffected, same reason
scripts/seed_internal_test_licences.py            -- audit needed in Phase 2 (not checked for its own
                                                      request literal in this pass -- flagged, not assumed clean)
scripts/smoke_real.py                             -- audit needed, same flag
scripts/test_apn_canonicalization_invariant.py    -- audit needed, same flag
scripts/test_compose_election.py                  -- audit needed, same flag
scripts/test_compose_geometry_tier_used.py        -- audit needed, same flag
scripts/test_compose_l0_gate.py                   -- audit needed, same flag (read-only 'ca_san_jose'
                                                      references confirmed in this pass, §1; its OWN
                                                      snapshot-insert shape not separately checked)
scripts/test_refresh_failure_invariant.py         -- audit needed, same flag
scripts/test_zoning_ambiguity_invariant.py        -- audit needed, same flag
tests/core/test_fact_adoption_hazard.py           -- audit needed, same flag
tests/core/test_fact_provenance_equivalence.py    -- audit needed, same flag
```

**Stated honestly, not rounded up: this pass confirmed the `request` literal for 3 of 17
writers directly (the three that needed fixing) and confirmed 2 more (the real ingest
scripts) are unaffected. The remaining 11 were checked only for a `'ca_san_jose'` string
literal and a literal-`{}` grep, both zero — not the same as confirming their own snapshot
INSERTs are provenance-honest under R1's exact condition.** A full per-writer audit of the
remaining 11 is Phase 2 scope, not completed here — T4 cannot be marked "designed" as more
than a checklist until that audit runs. **RED: any of the 17 breaks under R1/R4 that this
design did not already name as "must be updated."**

**T5 — #50's NAMESPACE.** After the `invariants.sql` change (§5), no `parcel` row created by
`db-test` carries `jurisdiction_id='ca_san_jose'`. Permanent invariant, not a one-time
cleanup — belongs in `invariants.sql` itself as a self-check, not a separate file. **RED: a
future test is added that writes one anyway** (the exact failure this whole family is
named for, reproduced by omission).

**T6 — IMMUTABILITY INTACT.** `UPDATE`/`DELETE` on `snapshot`, `fact`, `licence`,
`licence_channel` still raise, after whichever migration Phase 2 lands. C2's own guard,
proving no trigger was loosened to make R1 easier to satisfy retroactively. **RED: any of
the four succeeds.**

**T7 — THE BLAST-RADIUS ASSERTION, made honest in CI.** A script (not wired into a make
target by this pass — Phase 2's call) that runs §2.4's own query against whatever database
it's pointed at and reports the count out loud, rather than silently passing. Against
`ledgex_ci_p5`/`ledgex_ci`/CI's own fresh databases, this should read zero — asserting that
is real coverage CI does not currently have. **RED: CI's own database returns nonzero**,
which would mean R1/R4 shipped without actually being wired into the paths CI itself
exercises.

**T8 — SCOPE-DRIFT SIGNAL**, per P52/P55's own convention. Enumerated now, before Phase 2:

*Expected to break, and the point of the change, not scope drift*: `scripts/_p5_setup.py`,
`scripts/_phaseb_setup.py`, `scripts/check_golden.py` — each currently writes the literal
`request='{}'` and each must change to satisfy R1. `scripts/check_golden.py`'s own
`payload_hash` fixtures do **not** need to change (the `request` column is not part of
`compose()`'s own output — confirmed by `check_golden.py`'s own normalization table,
`docs/LEDGEX_SPEC.md` §6.6, which does not name it); only the `snapshot` INSERT's own
literal argument changes.

*Expected to stay green*: `make db-test` (`invariants.sql` already compliant with R1 as
designed, and T5 turns its own compliance with R5 into a permanent check); `make
conformance`; `make check-boundary` (I1 unaffected — nothing in `core/` changes);
`.claude/hooks/test_guard_destructive.py` (no new destructive-shaped command is introduced).

*Needs Phase 2's own explicit check, not assumed either way*: `make smoke-real` (writes
under its own `SMOKE_DATABASE_URL`-guarded database already — likely already compliant with
R1's own condition, but its own snapshot INSERT was not individually audited in this pass);
the P5/phaseb acceptance suites themselves, post-fix (`check_p5_acceptance.py`'s own
assertions may depend on the exact `request` shape written, untested here); CI's `db.yml`
schema job, which runs `db/seeds/day4_sources.sql` between `make db-test` and `make golden`
(P36/#38) — confirmed this pass by reading the workflow file's own job structure directly,
not assumed; this job's own database is a fresh `ledgex_ci`, so §7's own T7 assertion should
read zero there today, before any Phase 2 change, and that baseline is worth confirming
before Phase 2 lands anything.

---

## §8. What this would not prove

1. **It would not clean a single already-contaminated database.** All 49 of the 70 surveyed
   remain exactly as contaminated after Phase 2 as before it — R1/R4/R5 are entry guards,
   not remediation. `ledgex_schema_check` itself, contaminated again today by
   `check_golden.py`, stays contaminated until someone runs `make golden` again after the
   fix ships and then separately decides what to do about the three rows already there.
2. **It would not tell anyone which historical `job_run` metrics are trustworthy.** #50's
   own finding already established this for `ca_san_jose`-scoped metrics generally; nothing
   in this design retroactively audits a single existing `job_run` row.
3. **It would not catch a writer that supplies a plausible, non-empty `request` payload on
   purpose or by accident** — R1's own condition is exactly `request = '{}'`, no more. A
   future fixture writer that copies `ingest_parcels.py`'s own real-looking payload shape
   (even with a fabricated URL) satisfies R1 while remaining exactly as contaminating as
   `_p5_setup.py` is today. R2 (content-shape validation) is the only partial defense here
   and this pass did not design it beyond naming it in §4.
4. **It would not prevent a deliberate, informed operator from writing a real-shaped fixture
   on purpose**, if that operator wants to. No guard proposed here is aimed at malice or even
   carelessness beyond the specific shape three real writers have already fallen into; a
   determined bypass (hand-crafting a `request` payload, or writing directly against a
   database B3/B4 would have refused via environment) remains possible.
5. **It would not resolve whether R6 (the shrinkage guard) is buildable at all** — that
   depends on an owner-set numeric threshold this pass is explicitly forbidden from inventing
   (§4.2, `docs/LEDGEX_SPEC.md` §6.1 item 16) and on #51's backfill landing first (§4.3, §9.3).
   Both are open after this document, not closed by it.
6. **It would not audit the 11 unconfirmed writers named in T4** to the same standard as the
   3 confirmed ones. A green T4 checklist item for those 11, if Phase 2 marks it green
   without running the audit, would be exactly the "quietly satisfied check" this repo's own
   conventions warn against.
7. **It would not tell anyone whether other jurisdictions' packs (if this repo ever adds a
   second) have their own version of this exact family.** Everything in this document is
   scoped to `ca_san_jose`, because that is the only real pack that exists; the boundary
   design in §3/§4 is jurisdiction-agnostic by construction (C3), but that has not been
   tested against a second real jurisdiction because none exists yet.
8. **It would not prove `scripts/check_golden.py`'s own fixture rows are otherwise
   harmless** beyond "no `load_zoning`-style reconciliation touched them" — this pass
   confirmed they exist and where they came from, not their full downstream effect on every
   query anywhere in this codebase that scopes by `jurisdiction_id='ca_san_jose'` without
   also filtering by a real source id or a real `job_run` lineage.

---

## §9. Open questions for the owner — presented, not resolved

**Q9.1 — Refuse or flag, for R1?** C7's own existing policy (`docs/LEDGEX_SPEC.md`,
snapshot-unconditionally-even-on-bad-fetch) chose flag-over-refuse for a bad HTTP status, on
the argument that a failed fetch is itself part of the provenance record worth keeping. A
`NOT VALID CHECK` refusing `request='{}'` outright is the opposite choice, for a different
kind of badness (no fetch happened at all, vs. a fetch happened and failed). Both readings
are defensible; presented, not decided here.

**Q9.2 — Does a schema change happen in this family at all?** B2 (R1) needs one, even if a
minimal `NOT VALID CHECK`. The alternative — B3 + B4 only (dedicated harness databases,
namespaced fixtures) — needs no migration and would have stopped #53 and (once extended to
`make golden`) `check_golden.py`'s own contamination, but leaves the row-level door open
forever for a writer nobody has designed a harness guard for yet. §3's own ranking puts
both in play; the owner may prefer one alone.

**Q9.3 — Is #51's backfill a precondition of R6?** §4.3 argues yes. If the owner agrees, R6
(the single highest-value remedy against a genuine truncated fetch, per §4's own scoring)
moves behind a queue item that has been open since P55 Phase 2, and P56's own scope grows
to include scheduling that dependency explicitly rather than treating R6 as parallel,
independent work.

**Q9.4 — What happens to the 49 already-contaminated databases, and does that number now
include `ledgex_schema_check` itself as a recurring condition, not a one-time event?**
Recorded, not resolved: `ledgex_schema_check` was contaminated by the wave (§53), rebuilt
clean, and contaminated again by `check_golden.py` within hours, before this design was
even finished. If the owner's answer to this question is "rebuild again once R1 ships," that
rebuild is itself a fourth Stage-6-shaped pass; if the answer is "accept the caveat," that
caveat needs to be as visible as `prompts/P55-scoped-unblock.md` §12.18's own database
inventory, updated to say the fresh rebuild's own "clean" status did not survive its own
close-out.

**Q9.5 — Does this change the spec?** Read `docs/LEDGEX_SPEC.md` §1, §5.3, §6.1-6.7, §7.2,
§9, §12 in full for this pass (§1's own hygiene requirement). No invariant (I1-I20) directly
governs snapshot provenance today; §7.3's own drift language (already flagged stale by P55
§13.1, unrelated to this family) is the nearest existing spec text and does not cover this
case either. If Phase 2 concludes new spec language is warranted — most likely a new
invariant or an addition to §5's runtime-workflow section describing what a "real" snapshot
must carry — that is a version bump and a §12 row (I17), reserved for the owner per
`CONVENTIONS.md`. **Left red here, reported, not bumped.**

**Q9.6 — Where does the `check_golden.py` finding land?** §2.4 found it; it belongs in
`prompts/README.md` as its own numbered finding (next available number, #54 as of this
writing, unconfirmed since this pass does not edit that file) — distinct from #53 because
it is a different writer, discovered independently, with a different (if structurally
identical) mechanism. The owner may prefer to fold it into #53 as an addendum instead
(matching how #52 itself was corrected in place rather than superseded by a new number).
Presented as a choice, not decided.

Vocabulary discipline, confirmed followed throughout this document: `permits_use` /
`permits_with_conditions` / `prohibits_use` / `unknown` for `rights_position`; `"allowed"`
used only for `licence_channel.allowed`, never as a `rights_position` value.

---

## §10. Rollback

**If R1 (the `NOT VALID CHECK`) lands and turns out to be wrong** — e.g. a real, legitimate
writer is found post-Phase-2 to use `request='{}'` for a reason this design didn't
anticipate — the failure is loud and immediate: every affected `INSERT` raises a constraint
violation at write time, in whatever process attempted it, with the constraint's own name
in the error text. No silent data loss, no partial write, nothing to detect after the fact.
Recovery is `ALTER TABLE snapshot DROP CONSTRAINT <name>`, a plain forward-only migration —
the constraint itself carries no data, so dropping it destroys nothing and re-adding a
corrected version later costs nothing already written.

**If R4 (dedicated harness database variables) lands and turns out to be wrong** — e.g. a
legitimate local workflow relied on the acceptance suites reading plain `DATABASE_URL` —
the failure is also loud: the harness refuses to start, printing the same kind of message
`local_up.py`'s own `check_remote_db_refusals()` already prints today (§3's own citation).
Recovery is unsetting the new dedicated variable's requirement in the script, a plain code
revert, no data involved at any point.

**If R5 (namespaced test jurisdiction) lands and turns out to break something §5's own
audit missed** (Q5.1's own answer, re-litigated) — the failure mode is a `db-test` suite
failure, caught by CI on the very next run, not a silent data issue. Recovery is a plain
revert of the `invariants.sql` change; no migration, so nothing to roll back at the schema
level.

**No remedy in this design touches an existing row of any kind.** Every rollback path above
ends at "revert the code/migration that added the guard," never "recover lost or damaged
data," because C2 and §6.1/§6.6 together mean nothing this design proposes is capable of
losing or damaging data in the first place — the worst case in every scenario is a legitimate
write refused loudly, not an illegitimate write silently accepted.

---

## Close-out — CONTAINMENT: `make golden` gets its own database

Single-phase, harness-only, 2026-08-23, same session and branch as the design above. No
migration, no seed change, no ingest change, no CHECK constraint, no new invariant, no
database dropped. Owner decisions D1-D4 (§0 of the containment prompt) followed exactly;
none relitigated.

### What shipped

- **`Makefile`**: `GOLDEN_DATABASE_URL ?= postgresql://localhost/ledgex_golden`, same block
  and style as `DB_TEST_DATABASE_URL`, with the one-time setup commands in the comment.
  `golden:`'s recipe now explicitly passes `GOLDEN_DATABASE_URL="$(GOLDEN_DATABASE_URL)"`
  into the subprocess environment — required, not cosmetic: verified directly (R2, below)
  that a Makefile `?=` default is **not** automatically inherited by a recipe that never
  references it, which is the exact mechanism that let this contamination happen in the
  first place.
- **`scripts/check_golden.py`**: new `golden_get_db()`, modelled directly on
  `scripts/smoke_real.py`'s `step_env()` (P50) and `scripts/local_up.py`'s
  `check_smoke_database()` (P51) — reads `GOLDEN_DATABASE_URL` only, never falls back to
  `DATABASE_URL` under any name; refuses a non-local host outright, no override flag (D3);
  refuses loudly, before any write, if the target database doesn't exist, isn't migrated, or
  isn't seeded, naming the exact three fixing commands in the error text every time. `main()`
  now prints the resolved DSN it's about to write to, unconditionally, at the top of every
  run. `run_composition()`'s single `get_db()` call site now calls `golden_get_db()` instead.
  `GOLDEN_ALLOW_RULE_SEED` is unchanged — kept deliberately (§2.4's own question, answered
  below).
- **`.github/workflows/db.yml`**: the `make golden` step now passes
  `GOLDEN_DATABASE_URL="$DATABASE_URL"` instead of `DATABASE_URL="$DATABASE_URL"` — the same
  shape the `db-test` step already uses for `DB_TEST_DATABASE_URL` two steps earlier in the
  same job. The stale comment claiming a bare local `make golden`'s risk was "Makefile's own
  `DATABASE_URL` default is `ledgex_schema_check`" is corrected in place (that claim was true
  before this change and is no longer accurate — see R2 below for what a bare invocation
  actually does now).
- **§2.5's setup path**: option (b), documented commands — not a new `make golden-db`
  target. Argued: `db-test` itself has no dedicated setup target either (`db/README.md`'s own
  three-command sequence is the precedent), a new target for one gate would be its own small
  inconsistency, and the refusal text in `golden_get_db()` already names the exact commands
  verbatim, so a developer who skips the docs and hits the refusal live is not left worse off
  than one who read the Makefile comment first.

### §2.4 — `GOLDEN_ALLOW_RULE_SEED`, argued, kept

**Still makes sense, and stays.** It protects a different axis than `GOLDEN_DATABASE_URL`
does. The new guard answers "is this the right database"; `GOLDEN_ALLOW_RULE_SEED` answers
"do you know this specific write can never be undone" — and `ledgex_golden` being
purpose-built and disposable-by-designation doesn't make the `rule` row it inserts (0013's
`rule_no_delete`) any less permanent once it lands. A first-time contributor running `make
golden` against a freshly-created `ledgex_golden` still deserves the same "this is
irreversible" warning a `ledgex_schema_check`-pointed run would have given them; removing the
gate because the database is now "safe" would conflate database-safety with
write-reversibility, which are not the same property. CI continues passing
`GOLDEN_ALLOW_RULE_SEED=1` unchanged, for the same reason it always did (`ledgex_ci` is torn
down with the runner regardless of what 0013 blocks).

### §4 (RED first) — R1, R2

**R1 — reproduced on purpose, on a throwaway database (`p56_golden_repro`, migrated, seeded,
never referenced by anything else this pass touches).** `check_golden.py` (pre-fix) PASSED
(0 failures) and planted exactly 3 contaminated snapshot rows —
`request='{}'`, `source_id='ca_san_jose.parcels'`, `licence_observed_id='cc_by_4_0_api_2026_08'`
— confirmed by direct query. Baseline captured for the T1 comparison below: refused=3
refusals, geometry-disabled=3 refusals, election-required=4 refusals, all three
`payload_hash` comparisons PASS.

**R2 — the resolved DSN, printed and checked, not inferred from `Makefile:32`. This is a
real correction to the containment prompt's own §1 claim, not a confirmation of it.** A truly
bare invocation (no shell-exported `DATABASE_URL`, no command-line override) does **not**
resolve to `ledgex_schema_check`. Verified directly, with zero shell exports:
`infra.env.env("DATABASE_URL")` resolves to the repo-root `.env`'s own value — in this
checkout, a **live remote Supabase host**, not the Makefile's local default at all, because
`golden:`'s pre-fix recipe (`$(PYTHON) scripts/check_golden.py`) never referenced
`$(DATABASE_URL)`, and the Makefile carries no blanket `export` — so the Makefile's own
`?=` default was never actually reachable by this specific target in the first place. What
*actually* stopped that from being catastrophic, both before and independent of this fix, is
`infra.env.get_db()`'s own pre-existing P39/finding-#43 guard: it refuses a non-local host
outright unless `LEDGEX_ALLOW_REMOTE_DB=1`. **The real, exploited vulnerability was never
"golden's true default is the shared local dev database" — it is "golden inherits whatever
local database a developer's shell already has `DATABASE_URL` pointed at for other work,"**
exactly the mechanism that contaminated `ledgex_schema_check` in this session's own Stage 7
run (`DATABASE_URL` was explicitly set to it, for legitimate unrelated reasons, and `make
golden` silently inherited that). This distinction doesn't change what the fix needed to be —
a dedicated, never-falling-back variable closes both paths identically — but it changes what
the fix's own *justification* should say, and the corrected comment in `db.yml` (above)
reflects this.

### §5 — the acceptance test and the stop condition

**T1 — PASSED, exact match, stop condition not triggered.** `make golden` (via
`GOLDEN_DATABASE_URL`) against a freshly created, migrated, seeded `ledgex_golden`: refused=3,
geometry-disabled=3, election-required=4, all three `payload_hash` comparisons PASS, 0
failures — identical to R1's own baseline, to the digit. `--bless` was never run.

**T2 — confirmed, `ledgex_schema_check` untouched.** No command in this containment pass ever
set `GOLDEN_DATABASE_URL` or `DATABASE_URL` to name it. Cross-checked directly, not only
asserted from the command history: its own `request='{}'` contamination count under the real
`ca_san_jose.*` source ids — 6, exactly matching Phase 1's own §2.4 finding (3 golden + 3
wave) — is unchanged after every fix-and-test action in this pass, including after the full
T5 gate run below. Fact/snapshot/parcel counts (1,118,855 / 22 / 225,053) were re-checked
identically before and after T5; no literal timestamped snapshot was captured at the very
start of this turn (an honest gap, not papered over), but the contamination-count invariant
and the command-history audit together are conclusive: nothing in this pass wrote to it.

**T3 — PASSED.** `GOLDEN_DATABASE_URL` naming a non-local host: refused, exit 1, error names
the resolved host and the reason, no override flag exists to bypass it.

**T4 — PASSED.** A nonexistent `GOLDEN_DATABASE_URL` target: refused, exit 1, error names the
exact three setup commands verbatim.

**T5 — every other gate unmoved, real numbers, nothing edited to pass:**

```
make db-test        123 PASS (matches the 122/123-shape baseline), exit 0
make conformance     PASSED, 0 failures, exit 0
make check-boundary  import-linter 5/5 kept, name-grep PASS, qa_check PASS, exit 0
make test            61 passed, 107 skipped, exit 0
make viewer-test      all assertions PASS, exit 0
make smoke-real       PASS -- 14/15 steps, 1 correctly SKIPPED, exit 0
.claude/hooks/test_guard_destructive.py   38/38, exit 0
make migrate-verify   MATCH, 56/56 (run at this pass's own start, per hygiene)
```

No test needed editing. No guard was weakened, widened, or routed around.

**T6 — CI reasoned through step by step, `.github/workflows/db.yml`'s schema job:**

```
CREATE DATABASE ledgex_ci                          -- unaffected
make schema DATABASE_URL=ledgex_ci                 -- unaffected
make migrate-verify DATABASE_URL=ledgex_ci          -- unaffected
make db-test DB_TEST_DATABASE_URL=ledgex_ci          -- unaffected (already its own variable)
psql ledgex_ci -f db/seeds/day4_sources.sql          -- unaffected, unchanged order
make golden GOLDEN_DATABASE_URL=ledgex_ci PYTHON=python3 GOLDEN_ALLOW_RULE_SEED=1
                                                      -- BEFORE: DATABASE_URL=ledgex_ci, read by
                                                         get_db() directly.
                                                         AFTER: GOLDEN_DATABASE_URL=ledgex_ci,
                                                         read by golden_get_db() -- same value,
                                                         same host (localhost, passes the local
                                                         check trivially), same already-migrated
                                                         and already-seeded database, same result.
                                                         GOLDEN_ALLOW_RULE_SEED=1 unaffected --
                                                         still auto-exported by Make's own
                                                         command-line-variable behaviour,
                                                         untouched by this recipe edit.
make schema-dump DATABASE_URL=ledgex_ci              -- unaffected, runs after golden as before
(remaining steps: P25/P34 regression checks, viewer-test, make test, make conformance)
                                                      -- unaffected, none reference
                                                         GOLDEN_DATABASE_URL or the changed
                                                         code path
```

**CI behaviour is unchanged: same database, same seeding order, same result.**

### §3 — confirmed untouched, per the containment prompt's own list

- `_p5_setup.py`/`_phaseb_setup.py` still write `request='{}'` under production source ids,
  unmodified. Phase 2's problem, not this pass's.
- No already-contaminated database was cleaned. `ledgex_schema_check` still carries its own 6
  contaminated rows (3 golden, from Stage 7; 3 wave, kept for provenance per P55 §12.18) —
  confirmed unchanged, not merely unclaimed.
- `ledgex_schema_check_pre_p55_20260823`: not connected to, not queried, not referenced by
  any command in this pass at all. Read-only guarantee trivially holds — nothing in a
  golden-database containment change had any reason to touch it, and nothing did.
- No database dropped. Two new databases exist that didn't before this pass:
  `ledgex_golden` (permanent — this is the whole point of the change) and
  `p56_golden_repro` (a throwaway R1 scratch database, left in place rather than dropped, per
  the instruction and matching this instance's own existing convention of leaving disposable
  scratch databases — `p22_scratch`, `p24_scratch`, etc. — rather than cleaning them up).
- Nothing merged, nothing pushed. Branch `p56-fixture-boundary`, one commit for the Phase 1
  design document, a separate commit for this containment change (below).

### The accepted risk, recorded in the owner's own terms (D2)

No row-level backstop exists after this change. B2's own argument — three independent
writers falling into the identical `request='{}'`-under-a-real-source-id trap predicts a
fourth — was not acted on here, by deliberate owner decision (D2), in favor of harness
discipline and namespacing alone. **This is a knowingly accepted trade, not an oversight.**
`_p5_setup.py` and `_phaseb_setup.py` remain exactly as exposed as they were before this
pass; only the writer that was *actively, currently* bleeding (`check_golden.py`, via `make
golden`'s own missing database scoping) is now contained. If a fifth writer with this same
shape is found later, **it is not a new finding — it is this decision's own known cost
arriving, exactly as named here in advance.**

### §9.6, proposed, not written

Per instruction, `prompts/README.md` is untouched. Proposed for the owner, next free number
as of this writing (#54, unconfirmed since the file wasn't checked again for intervening
edits):

> **#54** | `scripts/check_golden.py` writes real snapshot/parcel/fact rows under the real
> `ca_san_jose.parcels` source id and the real current licence id (`request='{}'`, no
> `job_run` row) every time `make golden` runs against a database that isn't its own dedicated
> target — the finding #53 signature, independently, in a fourth writer. Found live during
> P56 Phase 1's own blast-radius survey (`prompts/P56-fixture-contamination-boundary.md`
> §2.4), which found it in 20 of 70 surveyed databases, including this repo's own freshly
> P55-rebuilt `ledgex_schema_check`, contaminated hours after being certified clean.
> **Contained, not fixed at the source**, by giving `make golden` its own dedicated
> `GOLDEN_DATABASE_URL` (P56 containment close-out, same day) — the writer itself is
> unchanged; only its blast radius going forward is now bounded to `ledgex_golden`.
