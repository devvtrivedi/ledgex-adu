# Running the coding agent locally, and `make smoke-real`

P50. Two things live here: how to start a coding agent on this machine so
that "localhost" means *this Mac*, and what the one end-to-end command it
should run first actually proves.

---

## 1. Why it has to run locally

Postgres on `localhost:5432`, MinIO on `localhost:9000`, the viewer on
`127.0.0.1:8420` and the Docker daemon are all on this machine. An agent
running in a hosted sandbox cannot reach any of them — not "slowly", not
"with a tunnel": there is no route. Anything it claims about `docker ps` or
a parcel query from there is unverifiable by construction.

So: start the agent from this repo directory, on this machine.

```bash
cd ~/Desktop/ledgex-adu
claude
```

Started that way it inherits the shell's environment, so no secret is ever
typed into a prompt. Nothing below asks you to paste a credential.

### The environment it inherits

| Variable | Read by | Notes |
|---|---|---|
| `DATABASE_URL` | `infra.env.get_db()` | From `.env` via `load_dotenv`, which searches **upward** from the cwd. Keep it local. |
| `OBJECT_STORE_URL` / `_BUCKET` / `_ACCESS_KEY` / `_SECRET_KEY` | ingest scripts, `smoke_real.py` | `.env`. See `.env.example`. |
| `SMOKE_DATABASE_URL` | `make smoke-real` only | Defaults to `postgresql://localhost/ledgex_smoke`. Never falls back to `DATABASE_URL`. |
| `LEDGEX_VIEWER_URL` | `smoke_real.py` | Defaults to `http://127.0.0.1:8420`. |

`.env` is gitignored. `.env.example` is the tracked template and contains no
values.

---

## 2. One-time setup

`make smoke-real` writes **permanent** rows — `fact` cannot be updated or
deleted (0017, 0007/0040), `snapshot` cannot be changed (0021). It therefore
binds to its own database and refuses to guess one, for the same reason
`make db-test` got `DB_TEST_DATABASE_URL` (P18, finding #25) and `make test`
got `TEST_DATABASE_URL` (P21).

```bash
createdb ledgex_smoke
make schema DATABASE_URL=postgresql://localhost/ledgex_smoke
psql postgresql://localhost/ledgex_smoke -v ON_ERROR_STOP=1 -f db/seeds/day4_sources.sql
```

Then, **once**, fetch the parcels source so there is an immutable snapshot to
bind a load to. This is the full ArcGIS GeoJSON — the same file `--phase e`
reads — which is exactly why `make smoke-real` will not do it for you as a
side effect:

```bash
DATABASE_URL=postgresql://localhost/ledgex_smoke \
  .venv-ingest/bin/python3 scripts/ingest_parcels.py --phase b
```

Start the viewer **against the smoke database** (step 14 fails loudly and
tells you if it is bound elsewhere):

```bash
DATABASE_URL=postgresql://localhost/ledgex_smoke \
  .venv-api/bin/python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8420
```

`api/main.py` has no authentication by design. Do not bind it beyond
localhost.

---

## 3. `make local-up` / `make local-down`

P51. `make local-up` starts the internal viewer bound to `ledgex_smoke`, with
no credential ever typed or exported by hand -- it derives the Postgres
password itself (an already-set `PGPASSWORD`, else `docker inspect`'s
`Config.Env`, else trust auth) and never prints or logs the value, only its
source. `make local-down` stops only the one process it started, after
confirming that pid's command line still looks like our own uvicorn
invocation. Both are idempotent: a second `local-up` while it is already
healthy reports that and exits 0; a second `local-down` reports nothing to
stop and exits 0. Neither ever reads `DATABASE_URL`, and neither ever binds
anything but the local smoke database (`SMOKE_DATABASE_URL`, same default
and same refusal logic as `make smoke-real` above).

State: pidfile at `/tmp/ledgex-local/viewer.pid`, log at
`/tmp/ledgex-local/viewer.log` -- both printed on every run.

From another directory, `make` still needs a Makefile in the cwd, so
`make local-up` from `~` does not work. Either
`make -C ~/Desktop/ledgex-adu local-up`, or invoke the script directly by
absolute path -- it resolves its own repo root from its own file location
and re-execs itself under `.venv-api`'s interpreter, so this works from
anywhere:

```bash
python3 ~/Desktop/ledgex-adu/scripts/local_up.py
python3 ~/Desktop/ledgex-adu/scripts/local_up.py --down
```

---

## 4. `make smoke-real`

```bash
make smoke-real
# or, if the default python3 lacks scripts/requirements.txt:
make smoke-real SMOKE_PYTHON=.venv-ingest/bin/python3
```

Fifteen steps, each printing PASS / FAIL / SKIP, then one overall verdict.

| # | Step | What a PASS means |
|---|---|---|
| 1–2 | tooling, environment binding | The interpreter can import `psycopg2`/`requests`/`boto3`; `SMOKE_DATABASE_URL` resolves to a local host; `LEDGEX_ALLOW_REMOTE_DB` is not set; object-store config is present (never printed). |
| 3 | Docker daemon | `docker info` answers. Running containers are listed, not asserted — this repo ships no compose file to assert against. |
| 4 | PostgreSQL + PostGIS | Real connection to the smoke database; server and PostGIS versions reported. |
| 5 | object store | `head_bucket` succeeds on the configured bucket. |
| 6 | viewer | `GET /v1/rights` → 200 on `:8420`. |
| 7 | network | The **exact** permits URL `ingest_zoning_permits.py` will fetch is reachable — imported from that module, never retyped. |
| 8 | schema + seed | `schema_migrations` is not behind `db/migrations/`, and both sources are seeded. |
| 9 | real fetch | Delegates to `ingest_zoning_permits.py --source permits --phase b`: fetch, hash, upload, snapshot, `job_run`. |
| 10 | **independent SHA-256** | The stored object is re-downloaded and re-hashed *here*, and checked against `snapshot.content_hash`, `snapshot.byte_size` **and** the content-addressed key. Step 9's own claim that it verified the upload is not the proof. |
| 11–12 | 20-parcel ingest | `--phase d` bound to the immutable parcels snapshot. Skipped with a note when parcels are already loaded — `--phase d` is not idempotent. |
| 13–14 | query one back | Once in SQL, once over HTTP. Step 14 is also the only thing that proves the viewer process is bound to the same database this run wrote to. |
| 15 | **I6 rights gate** | D1 (P59): both-outcomes proof since P55 Phase 2 Stage 4, not refusal-only. A deterministic, self-seeded blocked fact must land under `omitted_for_rights`, never under `facts`, with its **value absent from the response bytes** — not merely from a parsed dict; a fact whose licence is NOT blocked must land under `facts`, with its value present. Neither side may SKIP (the old refusal-only version skipped silently if the loaded parcel carried no `cc_by_4_0` fact — closed, see this repo's own §11 argument against a silent-skip shape). |

### What a PASS does not mean

Printed on every run, pass or fail, in the same coverage-honesty style
`make test`, `make golden` and `make viewer-test` already use:

- It does not run `make db-test`, `make conformance`, `make golden`,
  `make test` or `make viewer-test`, and stands in for none of them.
- **It never proves the gate PERMITS anything.** No permitted fixture exists
  here by construction: the only permitted data comes from
  `scripts/seed_internal_test_licences.py`, whose `SEED_INTERNAL_TEST_LICENCES=1`
  opt-in guards a permanent, un-deletable `licence`/`licence_channel` write.
  `make smoke-real` will not trigger that for you, for exactly the reason
  `make viewer-test` does not. Run the seed deliberately, then
  `make viewer-test`, for the both-outcomes proof.
- `--phase e` never runs.
- Only one JSON route is called. Nothing is proved about the HTML viewer.

---

## 5. Guardrails

Two layers, because they fail differently.

**`.claude/settings.json`** — declarative, and the place a human looks to
find out what is forbidden. `deny` beats `ask` beats `allow`, and a `deny`
here beats any `allow` in the gitignored `settings.local.json`.

**`.claude/hooks/guard_destructive.py`** — a `PreToolUse` hook that reads the
*whole* command string. Permission patterns match a command's leading tokens,
and the actions worth stopping do not always live at the front:

```
psql "$URL" -c "DROP DATABASE ledgex_smoke"
bash -lc 'docker compose down --volumes'
env LEDGEX_ALLOW_REMOTE_DB=1 python3 scripts/ingest_parcels.py --phase e
```

A prefix pattern reads those as a harmless `psql`, `bash` and `env`.

### Blocked outright (exit 2, with a reason)

| Rule | Covers |
|---|---|
| `sudo` | `sudo`, `doas`, anywhere in the command |
| docker volume destruction | `docker volume rm/prune`, `docker system prune`, `docker compose down -v/--volumes`, `docker rm -v`. Plain `docker compose down` is **not** blocked. |
| database destruction | `DROP DATABASE`, `DROP SCHEMA`, `DROP OWNED`, `dropdb` |
| full-scale ingest | `--phase e` |
| remote-database override | `LEDGEX_ALLOW_REMOTE_DB=1` |
| non-local database | any `postgres://`/`postgresql://` literal whose host is not localhost / `127.0.0.1` / `::1` / a unix socket |
| force-push | `git push --force`, `git push -f` (`--force-with-lease` allowed) |
| recursive delete | `rm -rf` rooted at `/`, `~`, `$HOME` or `*`. `rm -rf dist` is fine. |

A command whose first token is a pure reader (`grep`, `rg`, `cat`, `git log`,
…) with no shell operators is exempt, so `grep -n "DROP DATABASE"
db/migrations/*.sql` still works.

Unparseable payload → **exit 2**. A guard that cannot see what it is guarding
does not wave it through.

### Requires your approval (`ask`)

`docker compose down`, `docker stop/rm`, `createdb`, `make schema`,
`make migrate`, `make migrate-baseline`, `SEED_INTERNAL_TEST_LICENCES=1`,
`GOLDEN_ALLOW_RULE_SEED=1`, `git push`, `git reset --hard`, `git clean`,
`brew/pip install`, and reading `.env`.

Editing or writing `.env` is denied outright.

### Verify the guard, don't trust it

```bash
python3 .claude/hooks/test_guard_destructive.py
```

38 cases: 18 that must be blocked, 19 that must get through, and the
fail-closed check. The must-get-through table is the half that matters — a
guard that blocks everything is trivially safe and gets switched off within
a day.

---

## 6. One security finding, from writing this

`.env` currently holds a live hosted Postgres URL **with its password in
plaintext**, pointing at a real database — not a local one.

Checked, and good news on the worst case:

- `.env` has **never** been committed (`git log --all -- .env` is empty).
- Neither the password nor the hostname appears in any tracked file. The host
  is named once in `prompts/README.md` row #23 as a known-unverified finding;
  the credential is not.

Still worth acting on:

1. **Rotate that password.** It has been sitting in a plaintext file inside a
   directory that gets handed to coding agents. Rotation is cheap; assuming
   it was never read is not.
2. **Point `.env`'s `DATABASE_URL` at a local database.** Pass the hosted URL
   explicitly on the command line for the one command that needs it. As
   written, `load_dotenv` hands that URL to any script run from anywhere in
   the tree, which is the entire reason `infra.env.get_db()`'s refusal exists.
3. `prompts/README.md` row #23 is still open — whether that database carries
   the `cleared_by='test'` licence contamination. It needs one `SELECT` from a
   machine with network access, and it is the least rebuildable database in
   the project. The guardrails above block writes to it; they deliberately do
   not block a read you run yourself.
