## P39 — compose()'s transaction discipline and infra/env's default database binding

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Two findings recorded first
(#42, #43), then fixed; a third (#44) found while running this package's own gate set and
**reported, not absorbed**.

Baseline: `c52a266` (P38 close-out). Prompt as issued:
`PROMPT-P39-compose-transaction-and-db-binding.txt` (repo root, unmodified).

**Not committed.** Working tree only, per CONVENTIONS' "a delegated agent reports; it does
not commit or push to `main` on its own." Two source files changed:
`scripts/compose_property_file.py` (+117 lines, 0 removed) and `infra/env.py`.

**CI precondition, checked on the real runner, not locally:** `gh run list --workflow=db.yml`
and `--workflow=docs.yml` at commit `c52a266` both show `completed success`, run `32314117415`
(db) and `32314117407` (docs), both "P38 close-out: report on program state, finding #41
closed", `2026-08-19T23:38:44Z`. Confirmed via `gh`, not inferred. (`liveness.yml` is
`schedule:`/`workflow_dispatch`-only and out of scope for this precondition per CONVENTIONS'
own carve-out — not checked, deliberately, not overlooked.)

**Every transcript below in this revision was produced fresh, in this session, against a
real database — not carried over from an earlier draft.** An earlier working-tree draft of
this report cited `/tmp/p39_RED.txt` and `/tmp/pg.log`; neither file exists on this machine.
Rather than trust those citations, every probe, every gate-set step and every Fix 3 case was
re-run from scratch this session, against fresh databases, before this report was finalized.
The earlier draft's *numbers* turned out to be accurate wherever they can be checked against
this session's independent re-run — recorded here as a fact about this session's own
verification, not as reassurance about the missing files.

**Environment notes, disclosed rather than smoothed over:**
- No local PostgreSQL+PostGIS was running at session start. `brew`'s `postgresql@16` has no
  PostGIS build available for it locally (only for a separately-installed, unused
  `postgresql@17`) — confirmed by trying, not assumed: `CREATE EXTENSION postgis` against a
  fresh `postgresql@16` database fails with "extension postgis is not available." A
  from-scratch `postgresql@17`+PostGIS 3.6 instance was stood up to investigate this, and hit
  a real, reproducible-in-two-lines Postgres-17-specific defect (`CREATE MATERIALIZED VIEW …
  AS SELECT * FROM some_stable_sql_function()` raises "relation … does not exist during
  inlining" even when the relation and function both exist and are committed) — confirmed
  with a two-table, no-repo-code minimal reproduction, then abandoned as a dead end unrelated
  to this repo.
- **The actual database used for every real transcript below is `docker` container `ledgex`
  (`postgis/postgis:16-3.4`, Postgres 16.4, PostGIS 3.4.3), already running on this machine
  before this session started** — the same image `db.yml` itself uses, and an exact match for
  §11's "PostgreSQL 16 + PostGIS 3.4." All work below runs against fresh, throwaway databases
  created inside that container (`ledgex_p39v_*`) — the pre-existing `ledgex_schema_check` and
  `ledgex_test` databases were never read from or written to.
- Client tooling: `psql`/`pg_dump` 16.14 (Homebrew) against a 16.4 server — a minor-version
  gap, not the major-version gap CONVENTIONS' own precedent warns about; `make schema-dump`
  ran clean (no diff) against the committed `db/schema.sql` on both fresh gate-set runs below,
  which is itself evidence the gap doesn't matter here, not just an assumption that it
  wouldn't.
- Python: this session's venv is 3.14.7; §11 specifies 3.12; `db.yml` pins `3.11`. Not
  reconciled here — out of this package's scope — but stated rather than left implicit,
  since a version-sensitive stdlib/library behavior difference is exactly the kind of thing
  CONVENTIONS asks a session to disclose, not assume away.
- **Session-hygiene finding, not a code finding:** `.git/index.lock` existed, stale, at
  session start (0 bytes, dated hours before this session began — left by an earlier,
  presumably crashed process; no live `git` process was found holding it, `ps aux` checked
  before removal). It silently made every git write operation (`git stash`, `git add`, `git
  commit`) fail with exit code 1 and **no error text on stdout or stderr** — `git`'s own
  descriptive "Unable to create .git/index.lock: File exists" message only appeared once
  `git add` was tried directly outside of `git stash`. Removed after confirming no live
  process held it. Not one of this package's three findings (it's an artifact of this
  machine's state, not of the repository's code), but recorded because it would have silently
  blocked the RED/GREEN evidence this package's own instructions require, and because a
  future session hitting the same silent failure should not have to re-diagnose it.

---

### 1. What was actually wrong

#### Finding #42 — `compose()` had no transaction discipline, and one bad argument poisoned the connection

`compose()` opened a cursor and issued `SELECT`s immediately, which starts a transaction
(`infra.env.get_db` sets `autocommit = False`). It had three exits and only one of them
ended that transaction.

Measured directly against a real PostgreSQL 16.4 + PostGIS 3.4.3 database (docker container
`ledgex`, `postgis/postgis:16-3.4` -- the same image `db.yml` uses), built from
`db/migrations/` from empty (`make schema`, then `make migrate-verify` -> `MATCH -- 55
migration(s) verified`, before anything below was trusted). Predicted before running; every
prediction held. Real transcript, `scripts/compose_property_file.py` at `c52a266` (baseline
code restored via `git stash` for this run, popped back immediately after):

```
R1 -- compose(channel='not_a_real_channel')
  txn status before: 0
  raised: psycopg2.errors.InvalidTextRepresentation: invalid input value for enum output_channel: "not_a_real_channel"
  txn status after: 3
R2 -- compose(channel='paid_property_file') on that SAME connection
  raised: psycopg2.errors.InFailedSqlTransaction: current transaction is aborted, commands ignored until end of transaction block
  txn status after: 3
R3 -- PARCEL_REFERENCE_UNKNOWN (no parcel with that id)
  txn status before: 0
  returned: Result.refuse(Refusal(code='PARCEL_REFERENCE_UNKNOWN', ...))
  txn status after: 2
R4 -- NOTHING_COMPOSED (zero refusals; geometry gate stubbed, licence allowed)
  txn status before: 0
  returned: Result.ok(NOTHING_COMPOSED)
  txn status after: 2
R5 -- control: a real refused property_file row IS written (commit path)
  returned: Result.ok('07828b88-a900-49ce-a720-e20f9cbcc622')
  txn status after: 0
  server notices/warnings on this connection: (none)
```

(0=IDLE, 1=ACTIVE, 2=INTRANS, 3=INERROR. Harness: `p39_evidence_harness.py`, this session's
own scratchpad, run byte-identically against baseline and fixed code -- reproduced against a
fresh migrations-only database each time, shown in full in §3.)

**R2 is the finding, not R1.** R1 is an ugly error message. R2 is a *valid* request failing
for a reason that names nothing about the bad request that caused it — on a later call, to
a different parcel, potentially in a different user's session. It is invisible today (the
CLI runs one composition per process and closes the connection in a `finally`; every test
suite builds its own connection) and becomes live the moment `api/` reuses a connection
across requests. That is why this lands before `api/`, not with it.

`channel` was the trigger. It was the one caller-supplied value with no boundary check at
all: `election` has been validated against `KNOWN_ELECTIONS` since P34
(`compose_property_file.py`, pre-fix lines 294-300), and `parcel_id` became a typed refusal
in P37 (`PARCEL_REFERENCE_UNKNOWN`, finding #40). `channel` reached the `licence_channel`
query as a bare enum literal, after the transaction was already open and the parcel already
read.

**Reachability, stated honestly:** unreachable through today's five call sites, all of which
pass a literal. Recorded as a finding anyway, on P36's own precedent for finding #39 —
"unreachable through the only caller today" was explicitly rejected as a safety argument
there, citing `job_run.schema_drift`'s one writer becoming three before anyone checked.

#### Finding #43 — `infra.env` default-binds to a remote database

`env()` calls `load_dotenv(override=False)`, and `load_dotenv` searches **upward from the
current working directory**, so a script run from the repo root picks up the repo-root
`.env` — whose `DATABASE_URL` names a live remote Supabase instance.

Every `make` target is safe: each passes `DATABASE_URL` explicitly, defaulting to
`postgresql://localhost/ledgex_schema_check`. Running a script directly is not, and that is
the natural thing to do by hand:

```
python3 scripts/compose_property_file.py --parcel-apn 12345678   # writes property_file
python3 scripts/ingest_parcels.py                                # writes facts
python3 scripts/ingest_zoning_permits.py                         # writes facts
```

Those writes are permanent: `fact_no_delete` (0017), `fact_no_update` (0007/0040),
`licence`/`licence_channel` immutability (0027/0033), `rule_no_delete` (0013).

**Distinct from open finding #23**, which asks *what state that database is actually in and
nobody has checked*. This is *what an un-parameterised run connects to by default*, which is
answerable and fixable now, independently of #23. #23 stays open.

---

### 2. The three report-before-writing verdicts

Each was reasoned before any code was written, per the prompt's own instruction not to
silently pick.

**(a) `ValueError` for an unknown channel, not a new refusal code.** §9's refusal table has
no member for "the channel you named does not exist," and §9's own closing line puts this
class in the error taxonomy, verbatim from `docs/LEDGEX_SPEC.md:2025`:

> Errors (application/problem+json): schema-drift (502), source-timeout (504),
> **invalid-request (400)**, not-found (404), conflict (409), internal (500).

A refusal is a valid business answer *about a real channel* (`RIGHTS_BLOCKED` is one). An
unknown channel is a malformed request — a 400, not a 200 with `status: "refused"`. Adding a
refusal code would require a spec bump and a §12 row (I17), which CONVENTIONS says to stop
and report rather than absorb. So `ValueError`, matching `election` exactly, and `api/` maps
it to `invalid-request` (400) when `api/` exists.

This *is* a real grading difference from finding #40's treatment of `parcel_id`, and the
difference is deliberate: a `parcel_id` that does not resolve is a true statement about the
world (that parcel is not in our data), which is a refusal. A `channel` that is not in the
enum is a statement about the *request being malformed*, which is not.

**(b) `KNOWN_CHANNELS` is deliberately left undiffed by `qa_check.py`.** This is a fourth
Python copy of a database vocabulary, and refusal codes — which have three copies —
*are* diffed by `check_refusal_codes_match_spec()`. Not the same shape: refusal codes are
three hand-maintained prose/Python lists that can silently disagree; `output_channel` is a
Postgres ENUM. The failure a diff would prevent (a stale Python list quietly admitting a
value the database does not have) is impossible here, and the opposite drift (the enum gains
a member this tuple lacks) surfaces as a loud `ValueError` naming the channel, never as
silent wrong behavior. Recorded as a decision in the constant's own comment, not as an
omission.

**(c) `try/finally`, not `with conn:`; the guard in `get_db()`, not `env()`.**
psycopg2's connection context manager is a *transaction* manager that **commits** on clean
exit — wrong on both non-writing paths (neither wrote anything, and it would also silently
commit whatever a future edit added before those returns), and it would sit around
`_compose`'s own explicit `conn.commit()` leaving two things that both believe they own the
commit.

For #43, `env()` is a generic string accessor with no idea what any variable means; a
`DATABASE_URL`-specific rule there would apply that knowledge to every caller asking for
anything else. `get_db()` already knows it is building a database connection, and already
makes a connection *policy* decision one line down (`autocommit = False`, which nothing
forced on it either). Same category as that line.

On §2's "infra/ ... Zero business logic": the guard names no fact, licence, jurisdiction,
field key or channel — no domain concept at all. It is a property of the connection, which
is what the module exists to construct. Weighed rather than assumed; the alternative (a new
top-level module for one function) is worse.

---

### 3. The fixes, and the evidence

`compose()` is now a thin wrapper that owns the transaction boundary and validates
`channel`; the previous body is `_compose()`, unchanged apart from its name.

```python
    try:
        return _compose(conn, parcel_id, channel, election=election, as_of=as_of)
    finally:
        if conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            conn.rollback()
```

The status check, rather than an unconditional `rollback()`, is deliberate: after a
successful commit the connection is already IDLE, and issuing `ROLLBACK` there makes
Postgres emit `WARNING: there is no transaction in progress` on **every** successful
composition. Verified directly on psycopg2's own `conn.notices` (server NOTICE/WARNING
messages arrive there) after R5's commit-path call, GREEN run: `(none)` — not inferred from
absence of a log line, the actual notices list, empty.

**Precondition this wrapper cannot enforce, so it is stated in the docstring:** a caller must
commit its own fixture/setup writes *before* calling `compose()`, because the rollback ends
whatever transaction is open on `conn`. Verified true of all five real call sites by reading
each one, not assumed — `check_golden.run_composition` (both `seed_reference_rows` and
`make_fixture_parcel_and_fact` commit), `test_compose_election._seed`,
`test_compose_parcel_refusals` (both sites), `test_compose_geometry_tier_used._seed`.

#### RED → GREEN, same harness, same probes, two fresh databases (`ledgex_p39v_red`,
`ledgex_p39v_green`), both `MATCH`-verified by `make migrate-verify` before use

| Probe | RED (`c52a266`, restored via `git stash`) | GREEN (this working tree) |
|---|---|---|
| R1 unknown channel | `psycopg2.errors.InvalidTextRepresentation: invalid input value for enum output_channel: "not_a_real_channel"`; txn `0` → `3` | `ValueError: channel='not_a_real_channel' is not one of ('free_snapshot', 'paid_property_file', 'api', 'bulk_export', 'analytics', 'model_training')…`, raised before any query; txn `0` → `0` |
| R2 valid call, same connection | `psycopg2.errors.InFailedSqlTransaction: current transaction is aborted, commands ignored until end of transaction block`; txn stays `3` | `Result.ok('96b93493-b806-48af-b592-c88c176652c7')` — connection fully usable, real row written; txn `0` → `0` |
| R3 `PARCEL_REFERENCE_UNKNOWN` | `Result.refuse(Refusal(code='PARCEL_REFERENCE_UNKNOWN', …))`; txn `0` → `2` | identical refusal; txn `0` → `0` |
| R4 `NOTHING_COMPOSED` | `Result.ok(NOTHING_COMPOSED)`; txn `0` → `2` | identical; txn `0` → `0` |
| R5 control, row written | `Result.ok('07828b88-…')`; txn `0` → `0`; 0 server notices | `Result.ok('b0d01469-…')`; txn `0` → `0`; 0 server notices — unchanged |

Full raw stdout for both runs is reproducible verbatim by re-running
`p39_evidence_harness.py` (`P39_LABEL=RED|GREEN DATABASE_URL=<fresh db> python3
p39_evidence_harness.py`) against a fresh migrations-only database each time — the harness
itself is reproduced in full at the end of this report.

R4 required a fixture the repo has never had: `NOTHING_COMPOSED` is reachable only with zero
accumulated refusals, which needs both an `allowed=true` `licence_channel` row *and* a
geometry gate that does not fire. Those are mutually exclusive on real data —
`geometry_tier_enabled=false` always refuses `GEOMETRY_TIER_DISABLED`, and
`geometry_tier_enabled=true` raises `NotImplementedError` in `core/calc`. Reached by seeding
a `test.p39ev_*` licence with the channel allowed and stubbing
`evaluate_geometry_dependent_conclusion`, the same `mock.patch.object` precedent
`test_compose_geometry_tier_used.py` already established. **Worth noting on its own:** that
mutual exclusion means `NOTHING_COMPOSED` is unreachable in production today by any path.

#### Fix 3, all seven cases -- real connection attempts, not just the `_is_local` unit check

```
[remote, no opt-in]                 REFUSED by guard (SystemExit): "refusing to connect: DATABASE_URL points at
                                     host 'db.example-does-not-resolve.invalid', which is not local. Writes made
                                     through this connection can be PERMANENT and un-undoable ... re-run with
                                     LEDGEX_ALLOW_REMOTE_DB=1."
[remote, opt-in set]                guard ALLOWED, driver then failed for real:
                                     OperationalError: could not translate host name "db.example-does-not-resolve.invalid"
                                     to address: nodename nor servname provided, or not known
[local unix socket, ?host=/tmp]     CONNECTED for real: postgresql://dev@/ledgex_p39v_socket?host=/tmp ->
                                     ('ledgex_p39v_socket', None)   -- inet_client_addr() NULL confirms socket, not TCP
[local host name]                   CONNECTED for real: postgresql://postgres:x@localhost:5432/ledgex_p39v_green
                                     -> ('ledgex_p39v_green',)
[local loopback ip]                 CONNECTED for real: postgresql://postgres:x@127.0.0.1:5432/ledgex_p39v_green
                                     -> ('ledgex_p39v_green',)
[unparseable netloc]                REFUSED by guard: "...a host this guard could not parse, which is not local..."
[not a postgres scheme (mysql://)]  REFUSED by guard: "...a host this guard could not parse, which is not local..."
```

A dead, non-resolving remote host was used for cases 1–2 deliberately: the assertion is *the
guard fired before any connection was attempted*, which a non-resolving host proves just as
well and never touches the real database in `.env` (never read, never printed, in this
session). Cases 3–5 were run as REAL end-to-end connections against real local databases
(the unix-socket case against a throwaway `brew`-managed Postgres 16 instance, on a socket
directory chosen deliberately so the connection could only succeed if `host=` was actually
honoured — proven the negative way too, below). Unparseable is refused, not admitted — "I do
not know where this points" reads as refuse, not "probably fine."

`postgresql://postgres@/db?host=/tmp` is the shape that matters most and the one easiest to
get wrong: libpq honours a `host=` **query parameter** over the URL's netloc. `_resolved_host`
handles it explicitly.

#### Passing on real input, not just failing on planted input

Per CONVENTIONS ("proving a check can fail on planted input does not establish that it passes
on real input"), the new check was run against the real vocabulary once, for real:

```
live enum      : ('free_snapshot', 'paid_property_file', 'api', 'bulk_export', 'analytics', 'model_training')
KNOWN_CHANNELS : ('free_snapshot', 'paid_property_file', 'api', 'bulk_export', 'analytics', 'model_training')
AGREE          : True

free_snapshot        accepted -> refused-row written  (txn after: 0)
paid_property_file   accepted -> refused-row written  (txn after: 0)
api                  accepted -> refused-row written  (txn after: 0)
bulk_export          accepted -> refused-row written  (txn after: 0)
analytics            accepted -> refused-row written  (txn after: 0)
model_training       accepted -> refused-row written  (txn after: 0)
```

(All six ran against fresh `test_p39ev_chan_*` parcels on `ledgex_p39v_green`; every one wrote
a real refused `property_file` row via the normal L7/L8 refusal path, txn status `0` after
each. Full output in this session's transcript.)

#### Gate set, twice, each against its own fresh migrations-only database

Step order mirrors `db.yml`'s `schema` job.

```
=== ledgex_p39v_run1 (fresh, migrations-only) ===       === ledgex_p39v_run2 (fresh, migrations-only) ===
  PASS  make schema                                       PASS  make schema
  PASS  make migrate-verify (MATCH, 55 migrations)         PASS  make migrate-verify (MATCH, 55 migrations)
  PASS  make db-test                                       PASS  make db-test
  PASS  test_snapshot_race_invariant                       PASS  test_snapshot_race_invariant
  PASS  db/seeds/day4_sources.sql                          PASS  db/seeds/day4_sources.sql
  PASS  make golden (GOLDEN_ALLOW_RULE_SEED=1)              PASS  make golden (GOLDEN_ALLOW_RULE_SEED=1)
  PASS  test_compose_geometry_tier_used                    PASS  test_compose_geometry_tier_used
  PASS  test_compose_election                              PASS  test_compose_election
  PASS  test_compose_parcel_refusals                       PASS  test_compose_parcel_refusals
  PASS  make test                                          PASS  make test
  PASS  make conformance                                   PASS  make conformance
  PASS  make schema-dump (clean, no diff vs db/schema.sql)  PASS  make schema-dump (clean, no diff)
  PASS  lint-imports                                       PASS  lint-imports
  PASS  check_jurisdiction_names                           PASS  check_jurisdiction_names
  --> 14 passed, 0 failed                                  --> 14 passed, 0 failed
```

Both runs against the real `docker` `postgis/postgis:16-3.4` container (`ledgex`), each on its
own freshly-created, freshly-`CREATE EXTENSION postgis`'d database — `ledgex_p39v_run1`/
`ledgex_p39v_run2`, both distinct from each other and from every pre-existing database in that
container. `make schema-dump`'s clean diff on both runs is itself evidence that this session's
client `pg_dump` 16.14 against the container's server 16.4 doesn't introduce false drift (see
environment notes above). CLI smoke test, same `run1` database, after the full sequence:
`python3 scripts/compose_property_file.py --parcel-apn GOLDEN-REFUSED-FIXTURE --election
city` — real seeded parcel from `day4_sources.sql`, wrote a two-refusal
(`GEOMETRY_TIER_DISABLED`, `RIGHTS_BLOCKED`) `property_file` row, **exit code 0**.

Fix 2 changes the transaction boundary every compose-based suite runs inside, so the four
green `scripts/test_compose_*.py` runs and `make golden` are load-bearing here, not a
formality.

---

### 4. Finding #44 — reported, not absorbed

Found while running this package's own gate set, not looked for.

`scripts/migrate_baseline.py`'s `admin_connect()` (line 53) and `dump_schema()` (line 78)
both rebuild a connection from `urlparse` fields alone — `u.hostname`, `u.port`, `u.username`
— and **silently drop libpq's `host=` query parameter**. `scripts/migrate_verify.py` imports
and calls **these same two functions directly** (`from migrate_baseline import admin_connect,
dump_schema`, line 39) — to build its own disposable reference database (`admin_connect`) and
to dump both the reference's and the *target's own* schema (`dump_schema`, called on `target`
at line 99). **So `make migrate-verify` itself is broken against a unix-socket DSN, not only
`make migrate-baseline`** — confirmed by running `make migrate-verify` itself, not inferred
from `migrate_baseline.py` in isolation. Proven two ways, both for real:

```
# 1) make migrate-verify itself, against a unix-socket DSN, dies inside dump_schema()'s
#    subprocess call -- u.hostname is None (the URL has no netloc host, only a host= query
#    param), independent of which local default socket directory this machine happens to use:
$ make migrate-verify DATABASE_URL="postgresql://dev@/ledgex_p39v_socket?host=/tmp" PYTHON=python3
TypeError: expected str, bytes or os.PathLike object, not NoneType
make: *** [migrate-verify] Error 1

# 2) admin_connect() passes host=u.hostname (None here) straight to psycopg2.connect().
#    psycopg2/libpq then falls back to ITS OWN compiled-in default unix-socket directory --
#    which on this Homebrew-Postgres machine happens to also be /tmp, so a naive same-directory
#    test would (wrongly) look like it passed. Proven the other way instead: point host= at a
#    directory that holds NO socket file at all. If host= were honoured, this must fail --
#    it does not:
$ mkdir /private/tmp/.../no_socket_here   # confirmed empty, no .s.PGSQL.5432 in it
$ DATABASE_URL="postgresql://dev@/ledgex_p39v_socket?host=/private/tmp/.../no_socket_here" \
  python3 -c "import migrate_baseline as mb; mb.admin_connect('ledgex_p39v_socket')"
CONNECTED  # host= was silently ignored; libpq used its own default socket dir instead, not this one

$ make migrate-verify DATABASE_URL="postgresql://postgres:x@127.0.0.1:5432/ledgex_p39v_red"
MATCH -- ledgex_p39v_red's live schema is exactly what its ledger claims. 55 migration(s) verified.
```

Isolated to the DSN shape, not to P39's changes: neither function calls `get_db()`, and both
are untouched by this package. (This session's own default local unix-socket directory is
`/tmp` — Homebrew's convention, not Debian/CI's `/var/run/postgresql` — so the exact
`OperationalError` text a Debian-style environment would show for case 2 could not be
reproduced verbatim here; the empty-directory test above proves the same underlying claim,
environment-independently, rather than relying on one machine's default happening to differ
from the DSN's stated `host=`.)

**Why it matters more than it looks.** CONVENTIONS makes `make migrate-verify` mandatory
before citing any local database as evidence, precisely because CI cannot see ledger drift.
`db.yml` uses a TCP service DSN so this never fires there — meaning the one gate that exists
to catch drift on a *local* database is unrunnable on the local setup most likely to have it
(a unix-socket Postgres). Open finding #27 records that ledger drift has already happened
three times, all found incidentally.

It is also the **same root cause** Fix 3's `_resolved_host` had to handle: libpq honours
`host=` in the query string and `urlparse`-based code does not. Two independent instances of
one misunderstanding, which is usually a sign of a third.

Not fixed here — it is a different file, a different failure, and outside this package's
stated scope.

---

### 5. In plain terms

Findings #42 and #43 look similar and are not.

#42 was a door left unlatched in a room nobody walks through yet. `compose()` is called once
per process today and the process exits immediately, so neither the open transaction nor the
poisoned connection can currently produce a symptom. The moment a server calls it twice on
one connection, both become real — and the second is the nasty kind, where the failure shows
up on a *later, perfectly valid* request with an error that names nothing about the bad one.

#43 was live the whole time. The only thing between a typo and a permanent write to a
production database was that nobody had happened to run a script from the repo root without
exporting `DATABASE_URL` first. The repo already had the right pattern — `make golden`
refuses to plant its permanent rule row unless you say you meant it. That gate exists because
someone thought about an irreversible write before making one. This is the same thought, one
level lower.

#44 is the reminder that a rule you cannot run is not a rule. `make migrate-verify` is
mandatory by convention and unrunnable on a socket-based local Postgres, which is exactly
where the drift it looks for lives.

---

### 6. Evidence harness, verbatim

Not committed to the repo (throwaway evidence tooling, not a repo deliverable) — reproduced
here in full so the RED/GREEN transcripts above are independently re-runnable by anyone, not
just citable. Run as `P39_LABEL=RED|GREEN DATABASE_URL=<fresh, migrations-only db>
python3 p39_evidence_harness.py` against baseline and fixed `compose_property_file.py`
respectively.

```python
#!/usr/bin/env python3
"""P39 evidence harness -- RED/GREEN transaction-discipline probes (R1-R5).
Run byte-identically before and after the compose() fix, against a fresh
migrations-only database each time, so the two transcripts are directly
diffable. DATABASE_URL must already be set by the caller to a throwaway
local database -- this script never touches infra.env's own default.
"""
import datetime
import os
import sys
import uuid
from unittest import mock

REPO_ROOT = "/Users/dev/Desktop/ledgex-adu"
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import compose_property_file as cpf  # noqa: E402
from core.model import Result  # noqa: E402
from infra.env import get_db  # noqa: E402


def txn_status(conn):
    return conn.get_transaction_status()


def seed_bare_parcel(conn, suffix):
    jurisdiction_id = f"test_p39ev_{suffix}"
    apn = f"TEST-P39EV-{suffix}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, "
            "supported, geometry_tier_enabled) "
            "VALUES (%s, 'Test', 'city', 'CA', 'v1.0', true, false) ON CONFLICT (id) DO NOTHING",
            (jurisdiction_id,),
        )
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (jurisdiction_id, apn),
        )
        parcel_id = cur.fetchone()[0]
    conn.commit()
    return parcel_id


def seed_full_fixture(conn, suffix, channel):
    """jurisdiction + licence(channel allowed=true) + source + snapshot +
    field_definition + fact + rule -- everything needed to reach a zero-
    refusal composition (NOTHING_COMPOSED) under a mocked geometry gate."""
    jurisdiction_id = f"test_p39ev_full_{suffix}"
    licence_id = f"test.p39ev_licence_{suffix}"
    source_id = f"test.p39ev_source_{suffix}"
    field_key = f"test.p39ev_field_{suffix}"
    apn = f"TEST-P39EV-FULL-{suffix}"
    rule_id = f"test.p39ev_rule_{suffix}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jurisdiction (id, display_name, kind, state_code, pack_version, "
            "supported, geometry_tier_enabled) "
            "VALUES (%s, 'Test', 'city', 'CA', 'v1.0', true, true) ON CONFLICT (id) DO NOTHING",
            (jurisdiction_id,),
        )
        cur.execute(
            "INSERT INTO licence (id, display_name, restriction, commercial_use, redistribution, "
            "attribution_text, observed_at, cleared_by, cleared_at) "
            "VALUES (%s, 'Test', 'open', 'allowed', 'allowed', NULL, now(), 'test', now()) "
            "ON CONFLICT (id) DO NOTHING",
            (licence_id,),
        )
        cur.execute(
            "INSERT INTO licence_channel (licence_id, channel, allowed, rationale) "
            "VALUES (%s, %s, true, 'test fixture: allowed, P39 NOTHING_COMPOSED reachability') "
            "ON CONFLICT (licence_id, channel) DO NOTHING",
            (licence_id, channel),
        )
        cur.execute(
            "INSERT INTO source (id, jurisdiction_id, display_name, steward, method, phase_status, "
            "phase_status_reason, endpoint_url, licence_id, active) "
            "VALUES (%s, %s, 'Test Source', 'Test', 'bulk', 'active', 'test fixture', "
            "'https://example.com', %s, false) ON CONFLICT (id) DO NOTHING",
            (source_id, jurisdiction_id, licence_id),
        )
        digest = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars
        snapshot_id = f"{source_id}:sha256:{digest}"
        cur.execute(
            "INSERT INTO snapshot (id, source_id, object_uri, content_hash, media_type, byte_size, "
            "request, http_status, fetched_at, licence_observed_id) "
            "VALUES (%s, %s, 's3://test/fixture', %s, 'application/json', 1, '{}'::jsonb, 200, "
            "now(), %s) ON CONFLICT (id) DO NOTHING",
            (snapshot_id, source_id, digest, licence_id),
        )
        cur.execute(
            "INSERT INTO field_definition (field_key, display_name, claim, value_type, category, description) "
            "VALUES (%s, 'Test', 'public_record', 'string', 'parcel', 'test fixture') "
            "ON CONFLICT (field_key) DO NOTHING",
            (field_key,),
        )
        cur.execute(
            "INSERT INTO parcel (jurisdiction_id, apn) VALUES (%s, %s) RETURNING id",
            (jurisdiction_id, apn),
        )
        parcel_id = cur.fetchone()[0]
        now_ts = datetime.datetime.now(datetime.timezone.utc)
        cur.execute(
            "INSERT INTO fact (parcel_id, jurisdiction_id, field_key, value, method, "
            "source_id, snapshot_id, retrieved_at, source_url, licence_id, confidence, "
            "confidence_rule_id, effective_from, pack_version) "
            "VALUES (%s, %s, %s, '\"x\"'::jsonb, 'bulk', %s, %s, %s, 'https://example.com', "
            "%s, 'high', 'test.rule', %s, 'v1.0')",
            (parcel_id, jurisdiction_id, field_key, source_id, snapshot_id, now_ts, licence_id, now_ts),
        )
        cur.execute(
            "INSERT INTO rule (id, jurisdiction_id, rule_key, version, effective_from, effective_to, "
            "citation, source_text_uri, params, pack_version, authored_by, reviewed_by, review_mode, "
            "reviewed_at, attestation_uri) VALUES (%s, %s, 'adu.detached.max_height.city_standards', 1, "
            "'2020-01-01'::date, NULL, 'test citation', 'https://example.com/test', '{}'::jsonb, 'v1.0', "
            "'test@example.com', 'test@example.com', 'solo_founder_attestation', now(), "
            "'https://example.com/attest') ON CONFLICT (id) DO NOTHING",
            (rule_id, jurisdiction_id),
        )
    conn.commit()
    return parcel_id


def main():
    label = os.environ.get("P39_LABEL", "?")
    print(f"##### P39 evidence harness -- {label} #####")
    print(f"compose_property_file module: {cpf.__file__}")

    # --- R1 + R2: same connection, so R2 proves (or disproves) poisoning ---
    conn = get_db()
    p1 = seed_bare_parcel(conn, f"r1r2_{label}")
    print("\n=== R1: compose(channel='not_a_real_channel') ===")
    print(f"txn status before: {txn_status(conn)}")
    try:
        r1 = cpf.compose(conn, p1, "not_a_real_channel", election=None)
        print(f"UNEXPECTED: no exception raised, returned {r1}")
    except Exception as e:
        print(f"raised: {type(e).__module__}.{type(e).__name__}: {e}")
    print(f"txn status after: {txn_status(conn)}")

    print("\n=== R2: a VALID compose() call, SAME connection as R1 ===")
    try:
        r2 = cpf.compose(conn, p1, "paid_property_file", election=None)
        print(f"returned: {r2}")
    except Exception as e:
        print(f"raised: {type(e).__module__}.{type(e).__name__}: {e}")
    print(f"txn status after: {txn_status(conn)}")
    conn.close()

    # --- R3: PARCEL_REFERENCE_UNKNOWN, fresh connection ---
    conn = get_db()
    print("\n=== R3: PARCEL_REFERENCE_UNKNOWN (no parcel with that id) ===")
    fake_id = str(uuid.uuid4())
    print(f"txn status before: {txn_status(conn)}")
    r3 = cpf.compose(conn, fake_id, "paid_property_file", election=None)
    print(f"returned: {r3}")
    print(f"txn status after: {txn_status(conn)}")
    conn.close()

    # --- R4: NOTHING_COMPOSED, fresh connection ---
    conn = get_db()
    print("\n=== R4: NOTHING_COMPOSED (zero accumulated refusals; geometry gate stubbed) ===")
    p4 = seed_full_fixture(conn, f"r4_{label}", "paid_property_file")
    print(f"txn status before: {txn_status(conn)}")
    with mock.patch.object(cpf, "evaluate_geometry_dependent_conclusion", return_value=Result.ok("stub")):
        r4 = cpf.compose(conn, p4, "paid_property_file", election="city")
    print(f"returned: {r4}")
    print(f"txn status after: {txn_status(conn)}")
    conn.close()

    # --- R5: control -- a real refused row IS written (commit path) ---
    conn = get_db()
    print("\n=== R5: control -- a real refused property_file row IS written ===")
    p5 = seed_bare_parcel(conn, f"r5_{label}")
    print(f"txn status before: {txn_status(conn)}")
    r5 = cpf.compose(conn, p5, "paid_property_file", election=None)
    print(f"returned: {r5}")
    print(f"txn status after: {txn_status(conn)}")
    if conn.notices:
        print(f"server notices/warnings accumulated on this connection: {conn.notices}")
    else:
        print("server notices/warnings accumulated on this connection: (none)")
    conn.close()


if __name__ == "__main__":
    main()
```

---

### Review findings

*(empty — appended after review)*
