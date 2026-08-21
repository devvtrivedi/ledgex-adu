# P47 — the two standing findings (#45 and #44)

**Baseline.** `main` at `e6cdf64`. Neither P45 nor P46 has merged into `main` —
both exist only on their own unmerged branches, per each package's own
explicit boundary ("`main` is not touched," merge decision left to the
dispatching session). Part A2 of this package (the rights-gate extraction)
directly touches `api/main.py` and `scripts/compose_property_file.py`, the
same two files P46 already modified — so this branch,
`p47-tooling-and-sockets`, is cut from `p46-boundary-validation`'s own tip
(`991a14d`), not from bare `main`, to avoid a content conflict with P46's
still-unmerged Fix 1/Fix 3 changes in those files. `p46-boundary-validation`
itself was cut from `main` at `e6cdf64` and does not include P45's changes
(P45 touches only the ingest scripts, untouched by this package). If the
dispatching session merges these branches in some other order, this branch's
own base will need rebasing — flagged here for the same reason P46 flagged
its own finding-number collision risk.

**How long each finding sat open, and through how many packages** (the
number the 2026-08-21 review's own re-discovery makes worth recording):

- **#44**: found during P39's own gate run. Open across 6 further packages
  (P40, P41, P42, P43, P45, P46) before this one closed it.
- **#45**: found while checking P40's own D3. Open across 6 further packages
  (P41, P42, P43, P45, P46, and independently re-found by the 2026-08-21
  review in the interim) before this one closed it.

Neither is a High. Both are "apply a correctness pattern this repo already
wrote down somewhere else" — which is exactly why they were safe to defer
for six packages each, and exactly why deferring them that long let a
reviewer who didn't know they were known spend real attention re-finding
them.

## Part A — finding #45, the import-linter contract

### A0. Decisions, reported before writing

**Doing both A1 and A2, not just one.** They are separable, and the prompt
asks which. A1 (repair the contract) is valuable on its own — a stale
blacklist that silently stops enforcing an allowlist is a real, standing
gap regardless of what else happens. A2 (the extraction) is valuable only
IF A1 lands first: A2's own precondition, stated explicitly in P40 §0 D3 at
the time it was deferred, is that the import-linter contract meant to gate
a new `core/` submodule can actually do so. Doing A1 alone and stopping
would leave A2 deferred a fifth time for no new reason — the blocking
condition would be gone and nobody would know to revisit it. Doing both,
in that order, in the same package, closes the finding completely rather
than partially.

**A1: allowed-only formulation, not a longer blacklist.** Read live, not
transcribed: `ls core/` → `__init__.py`, `calc.py`, `exceptions.py`,
`model.py`, `rules.py`, `store.py` (five real submodules, confirmed this
session, not assumed from the finding's own prose). Two shapes considered:

- **Forbidden-modules list naming every current non-allowed submodule**
  (`core.store`, `core.exceptions`, `core.calc`, `core.rules`) — rejected.
  This is exactly the shape that already failed: the OLD contract
  (`forbidden_modules = core.store` alone) was a faithful proxy for §2's
  allowlist only as long as `core/` held nothing else, and stopped being
  faithful the moment a second submodule landed, silently, with nobody
  revisiting it for three packages. A longer list with the same shape
  breaks the identical way the next time a sixth submodule is added — the
  failure mode being fixed here, which the prompt itself names as a strong
  argument against repeating it, and it is.
- **Allowed-only formulation** — chosen. Import-linter's `forbidden`
  contract type has no native allowlist mode, but its `forbidden_modules`
  field accepts a wildcard (`core.*`, matching every direct submodule of
  `core/`) and its `ignore_imports` field can carve specific edges back out
  of a contract that would otherwise be broken by them. `forbidden_modules
  = core.*` + `ignore_imports = commerce.** -> core.model` (and
  `core.compose`, pre-emptively, though it does not exist as a file yet —
  confirmed this does not error, see A1 evidence) is a genuine allowlist:
  "forbid everything, then un-forbid exactly what §2 permits." A future
  seventh core/ submodule is forbidden by construction, not by someone
  remembering to add it to a list.

`unmatched_ignore_imports_alerting = none` was required, not optional:
`commerce/` is still an empty scaffold (`ls commerce/` → `__init__.py`
only, confirmed this session), so `commerce.** -> core.model` matches
nothing in today's import graph, and import-linter's default alerting
level (`error`) refuses to run at all when an `ignore_imports` expression
matches nothing — confirmed live (see A1 evidence, "No matches for ignored
import"). Without this setting, the fix would not merely be incomplete, it
would be un-runnable today.

The separate `core-commerce-layers-above-infra` contract needed the
identical `ignore_imports` carve-out for the identical reason, discovered
while testing A1: declaring `core | commerce` as co-equal layer siblings
(the shape that states the infra-layering rule in one contract) has the
side effect of forbidding ANY import between them, which is stricter than
§2's real rule and was itself part of finding #45's own already-recorded
evidence (a planted `commerce -> core.model` import made this contract go
`BROKEN` before this package, contradicting §2's own text). Fixed in place
rather than by restructuring the layers contract: that contract's real job
is the infra-layering rule, which `core | commerce`-as-siblings is a side
effect of, not the point — the commerce/core relationship itself is now
fully and correctly governed by the new A1 contract, so the layers
contract only needs to stop contradicting it.

**A2: exactly one function, exactly two call sites, no exceptions.** The
prompt's hard requirement. `evaluate_rights_gate` is a pure function (a
cursor, a list of tuples, a channel string in; two dicts out) with zero
dependency on anything else in `compose_property_file.py`'s own module
state — trivially extractable, no adapter, no wrapper needed. `KNOWN_CHANNELS`
had to move alongside it: `api/main.py` used both symbols from the SAME
import (`cpf.KNOWN_CHANNELS`, `cpf.evaluate_rights_gate`), and leaving
`KNOWN_CHANNELS` behind would leave `api/` still importing
`scripts/compose_property_file.py` for one symbol — the exact edge this
extraction exists to remove, just relocated to a different name. This is a
necessary consequence of the extraction's own stated purpose, not scope
creep: without it, A2 does not actually close anything.

### A1 evidence

Read live: `core/` submodules today are `calc`, `exceptions`, `model`,
`rules`, `store` (via `ls core/`, not transcribed).

**RED — old contract, real planted violation:**
```
$ cat > commerce/_p47_probe.py <<'EOF'
from core.exceptions import insert_exceptions
EOF
$ lint-imports   # real .importlinter, unmodified
...
I15: commerce may import core.model and core.compose only, never core.store KEPT
...
api above core/commerce above infra (finding #29, extended P40 D4) BROKEN
commerce is not allowed to import core:
- commerce._p47_probe -> core.exceptions (l.1)
```
The named contract (`i15-commerce-no-core-store`) stayed `KEPT` — proof the
finding's own headline claim is real, not argued. Only the SEPARATE layers
contract caught it, by accident, as a side effect of its own over-strictness
bug (see next).

**RED — old layers contract, the over-strictness half:** already recorded
directly in finding #45's own prior text (`commerce -> core.model` made
`core-commerce-layers-above-infra` go `BROKEN` before this package);
re-confirmed live this session before fixing it.

**Attempted fix, first pass — the `unmatched_ignore_imports_alerting`
requirement, found empirically, not anticipated:**
```
$ lint-imports --config test_allowlist.ini   # forbidden_modules=core.*, ignore_imports=commerce.**->core.model, no alerting override
No matches for ignored import commerce.** -> core.model.
```
Failed outright — `commerce/` has no real code, so the ignore expression
matches no edge in the graph, and the default alerting level treats that as
an error. Added `unmatched_ignore_imports_alerting = none`; re-ran; `KEPT`.

**GREEN — new contracts, same planted violation:**
```
$ lint-imports   # .importlinter as edited
I15: commerce may import core.model and core.compose only BROKEN
commerce is not allowed to import core.exceptions:
- commerce._p47_probe -> core.exceptions (l.1)
api above core/commerce above infra (finding #29, extended P40 D4) BROKEN
commerce is not allowed to import core:
- commerce._p47_probe -> core.exceptions (l.1)
```
Both contracts now name the real violation directly, by module.

**GREEN — the legitimate case stays legitimate:**
```
$ cat > commerce/_p47_probe.py <<'EOF'
from core.model import Fact
EOF
$ lint-imports
Contracts: 5 kept, 0 broken.
```
A real, direct `commerce -> core.model` import — spec-permitted — passes
cleanly under both fixed contracts. This is the exact case the OLD layers
contract got wrong; it is right now.

Probe file removed; `lint-imports` re-confirmed clean (`5 kept, 0 broken`)
before proceeding to A2.

### A2 evidence

**Grep proof — exactly one definition, exactly two call sites:**
```
$ grep -rn "^def evaluate_rights_gate" --include="*.py" .
core/rights.py:85:def evaluate_rights_gate(cur, touched, channel):

$ grep -rn "evaluate_rights_gate(" --include="*.py" . | grep -v "^\./core/rights.py:.*def "
scripts/compose_property_file.py:564:        allowed_by_licence, blocked_by_licence = evaluate_rights_gate(cur, touched, channel)
api/main.py:391:        allowed_by_licence, blocked_by_licence = evaluate_rights_gate(

$ grep -rn "^KNOWN_CHANNELS = " --include="*.py" .
core/rights.py:75:KNOWN_CHANNELS = (
```
Every other hit for either name across the repo is prose (docstrings,
comments) naming the new location, not a call.

**`make check-boundary`, full pipeline, after the move:**
```
I1: core must not import jurisdictions, api, pipelines, geo, or commerce KEPT
I15: commerce may import core.model and core.compose only KEPT
I15: core must never import commerce (reverse direction) KEPT
infra must import only stdlib/third-party -- not even core.model KEPT
api above core/commerce above infra (finding #29, extended P40 D4) KEPT
Contracts: 5 kept, 0 broken.
JURISDICTION-NAME GREP PASSED -- 7 file(s) under core/ scanned, no blocklisted token found.
DOCUMENT QA PASSED — ...
EXIT: 0
```
(7 files under `core/`, not 6 — `core/rights.py` was scanned too.)

**`make viewer-test`, twice on independent fresh databases, once against
migrations-only with no seed:**
```
run 1 (fresh db): All assertions passed, VIEWER-TEST EXIT: 0
run 2 (fresh db): All assertions passed, VIEWER-TEST EXIT: 0
migrations-only, no seed: No seeded parcel found (jurisdiction_id='internal_test.viewer_demo', ...).
  This test reads scripts/seed_internal_test_licences.py's own output -- it does not create it.
  Run it first: SEED_INTERNAL_TEST_LICENCES=1 python3 scripts/seed_internal_test_licences.py
  make: *** [viewer-test] Error 1
```
The migrations-only run refuses loudly and correctly, naming the exact
remediation command — the documented behavior, not a regression.

**`make test`:** `168 passed` (against a properly migrated database — a
first run against an unmigrated one gave 106 errors from `UndefinedTable`,
my own setup mistake, not a regression; corrected and re-run clean).

**Compose test suite, unmodified, against the extracted gate:**
```
test_compose_collision_invariant.py  -> PASS
test_compose_election.py             -> All assertions passed
test_compose_geometry_tier_used.py   -> All assertions passed
test_compose_parcel_refusals.py      -> All assertions passed
```

## Part B — finding #44, Unix-socket URLs

### B0. Decision, reported before writing

**Reuse, not reimplementation** — `infra.env._resolved_host` (P39) already
solves exactly this: honouring libpq's `host=` query parameter over the
netloc host, refusing (returning `None`) rather than admitting an
unparseable URL. Renamed to the public `resolved_host` (dropping the
leading underscore) since it now has a second real caller outside
`infra/env.py`'s own module; both its existing internal call sites
(`_is_local`, `get_db`'s own error message) updated in the same edit — a
pure rename, zero behavior change to `get_db()` itself.

**How Part A and Part B interact — the prompt's own explicit question.**
They don't collide, and the reason is structural, not coincidental:
`scripts/` is not one of import-linter's four declared `root_packages`
(`core`, `commerce`, `infra`, `api` — read directly from `.importlinter`'s
own `[importlinter]` section). No contract of any kind can see an import
originating in `scripts/`, before this package or after it. Part A repairs
the commerce/core contract and the layers contract; neither contract, in
either its old or new form, mentions or constrains `scripts/` at all.
`scripts/migrate_baseline.py` importing `infra.env.resolved_host` is not a
new edge for import-linter to reason about — it is the identical shape
every other file in `scripts/` already uses (`from infra.env import env,
get_db`, verbatim, in every ingest script and in
`compose_property_file.py`). Considered and rejected: adding `scripts/` to
`root_packages` so import-linter could see it, which would be redefining
§2's module boundaries (§2 says nothing about what `scripts/` may or may
not import), not enforcing them — explicitly out of this package's own
boundary #2 ("§2's module boundaries are being ENFORCED here, not
redefined").

### B evidence

A real, throwaway, native Postgres instance was started for this evidence,
listening ONLY on a Unix socket (`-h ''`, TCP disabled entirely) at
`/tmp/p47sock`, port 5433 (5432 already held by this session's Docker
Postgres) — never the Docker container itself, which exposes no host-side
socket (confirmed: `docker inspect` shows no socket volume mount). Stopped
and its data directory removed at the end of this session.

**Prediction, before running anything:** `admin_connect()` connects to the
WRONG socket path (libpq's own default directory on this machine, not the
one the DSN names) or fails outright; `dump_schema()`'s real `pg_dump`
subprocess call receives `None` where a host string belongs and raises
`TypeError` before `pg_dump` itself ever runs.

**RED — real, unfixed code, DATABASE_URL =
`postgresql://postgres@:5433/ledgex_p47_socket_test?host=/tmp/p47sock`:**
```
--- admin_connect('postgres') ---
FAILED: OperationalError: connection to server on socket "/tmp/.s.PGSQL.5433" failed: No such file or directory

--- dump_schema(target) ---
FAILED: TypeError: expected str, bytes or os.PathLike object, not NoneType
```
`admin_connect` reached `/tmp/.s.PGSQL.5433` — libpq's bare default socket
directory (`/tmp`, this machine's own Homebrew convention, already
recorded in finding #44's own text) — not `/tmp/p47sock`, the directory
the DSN actually named. `dump_schema` matches the finding's own predicted
failure exactly, reproduced fresh.

**GREEN — fixed code, identical DSN:**
```
--- admin_connect('postgres') ---
CONNECTED: current_database='postgres', via_socket=True

--- dump_schema(target) ---
pg_dump SUCCEEDED: 419 bytes of schema-only dump for 'ledgex_p47_socket_test'
```
`via_socket=True` is not assumed — it is `inet_client_addr() IS NULL`,
queried server-side, true only for a genuine Unix-socket connection.
`dump_schema` shows the real `pg_dump` binary, invoked with the corrected
`-h`, succeeding against the real socket.

**TCP form re-confirmed unbroken** (the same two functions, TCP DSN against
the existing Docker Postgres):
```
--- admin_connect('postgres') ---
CONNECTED: current_database='postgres', via_socket=False

--- dump_schema(target) ---
pg_dump SUCCEEDED: 69894 bytes of schema-only dump for 'ledgex_schema_check'
```

**The real target, end to end, TCP form, after all four fixes below:**
```
$ make migrate-verify DATABASE_URL=postgresql://postgres:x@localhost:5432/ledgex_p47_migverify
building reference from exactly the 55 migration(s) ledgex_p47_migverify's own ledger claims are applied
MATCH -- ledgex_p47_migverify's live schema is exactly what its ledger claims. 55 migration(s) verified.
EXIT: 0
```
A full socket-form `make migrate-verify` run was NOT attempted: the
throwaway native Postgres instance has no PostGIS extension installed (not
present in this machine's Homebrew Postgres, confirmed:
`CREATE EXTENSION postgis` → `extension "postgis" is not available`), and
every real migration from `0001_extensions_and_enums.sql` onward depends
on it — installing PostGIS via Homebrew to enable this one run would be a
disproportionate, lasting system change for evidence the direct
function-level test already provides completely. The function-level proof
above (`admin_connect`, `dump_schema`, the exact two functions named by
this finding, run against a real socket, with a real `pg_dump` subprocess)
is what the "or the real target" alternative in the prompt's own phrasing
allows for.

### Two more occurrences, found closing the named two

While confirming `admin_connect()`/`dump_schema()` were the only two
call sites needing this fix, `grep -n "u\.hostname\|psycopg2\.connect("`
across both files found two more:

- **`migrate_baseline.py`'s own `main()`** (the reference-database
  connection, `ref_conn = psycopg2.connect(host=u.hostname, ...)`) — a
  third, independent copy of the exact same construction, not routed
  through `admin_connect()` at all.
- **`migrate_verify.py`'s own `main()`** — a fourth, structurally identical
  copy. This one matters most against what the finding itself already
  said: finding #44's own text states migrate_verify.py "imports and calls
  **the same two functions directly** ... so it inherits the same
  behavior" — true of `admin_connect`/`dump_schema`, but incomplete:
  `migrate_verify.py` has its OWN separate copy of `migrate_baseline.py`'s
  reference-connection logic, inherited by nothing, that the finding never
  anticipated.

Both fixed identically (`resolved_host(env("DATABASE_URL"))`, the same
reuse). Final sweep, both files:
```
$ grep -n "u\.hostname" scripts/migrate_verify.py scripts/migrate_baseline.py
scripts/migrate_verify.py:78:        # same host=u.hostname mistake -- NOT inherited via the imported
scripts/migrate_baseline.py:155:        # same host=u.hostname mistake admin_connect()/dump_schema() had --
```
Only the comments describing the fix remain; no live code path still
builds a connection this way in either file.

## Boundaries respected

No schema change, no migration, no spec bump — §2's module boundaries were
enforced (the import-linter contracts now match what §2's own prose already
said), not redefined; `scripts/` was deliberately NOT added to
import-linter's `root_packages` (see Part B's own B0 argument). No behavior
change to `compose()` or any route — `evaluate_rights_gate`/`KNOWN_CHANNELS`
moved byte-for-byte, only their import path changed; `admin_connect`/
`dump_schema`/both `main()`s now resolve the correct host but compute
nothing differently once connected. The rights gate stayed one function,
one call site each in `compose()` and `api/` (grep-proven above). `LEDGEX_
ALLOW_REMOTE_DB` was never set; every database used was local (the Docker
Postgres already running for this session, or a throwaway native instance
created and destroyed within it) or the throwaway socket instance itself.
`main` was not touched.

## Review findings

(none yet — filled in by review)
