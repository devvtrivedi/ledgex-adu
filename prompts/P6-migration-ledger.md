## P6 — migration application has no ledger

Design reported, not built. Do not build from this file directly — it is the record of
the design, written when P5 needed to touch `ledgex_schema_check` and found it five
migrations behind. Turn it into a real package (with its own "before writing" checkpoint)
when it is actually scheduled.

### What is actually wrong

`make schema` applies `db/migrations/*.sql` in order with `ON_ERROR_STOP=1`. Every
migration is a plain forward-only `.sql` file — `CREATE TABLE`, `ALTER TABLE`, etc. — with
no ledger row of its own. There is no `schema_migrations` table anywhere in this repo.
Consequently:

- `make schema` only succeeds against an **empty** database — re-running it against a
  database that already has migration N applied fails immediately on N's own `CREATE
  TABLE` (`relation already exists`).
- There is no supported way to bring an already-partially-migrated database forward.
  Hand-applying the missing files, one at a time, by figuring out which ones are missing,
  is the *only* option today — which is exactly how `ledgex_schema_check` fell behind:
  loaded once against migrations 0001–~0038ish, never brought forward as 0039–0044
  landed, because nothing would have told anyone it needed to be.
- CI (`db.yml`) never notices, because CI always builds from an empty database. The gap
  is invisible exactly where you'd expect a migration runner to catch it.

### The design

**A ledger table**, added by its own forward-only migration (next number after whatever's
current when this is scheduled):

```sql
CREATE TABLE schema_migrations (
    version      text PRIMARY KEY,       -- e.g. '0045'
    file_sha256  text NOT NULL,          -- content hash of the migration file at apply time
    applied_at   timestamptz NOT NULL DEFAULT now()
);
```

`file_sha256` is not decoration: migrations are supposed to be immutable once merged
(CLAUDE.md, `prompts/README.md`'s own forward-only discipline). Recording the hash at
apply time means a later `make migrate` run can detect a merged migration that was
edited after landing — a real integrity check this repo doesn't have today, not just a
version counter.

**A runner, not a modified `make schema`.** `make schema`'s documented contract (Makefile
comment, spec §1.2) is "clean apply" — a from-scratch build sanity check, which is
exactly what CI wants and exactly why CI catches migrations that can't build cleanly.
Making it idempotent would quietly change what it proves: "the schema builds from
nothing" and "this specific database is caught up" are different guarantees, and
conflating them is the same kind of scope-widening this repo's own migrations argue
against elsewhere (0044's own header, arguing against widening scope to "fix" something
adjacent). `make schema` stays exactly as it is, empty-DB-only, CI's target, unchanged.

A **new `make migrate`** target:

1. Connects to `DATABASE_URL`.
2. If `schema_migrations` doesn't exist yet *and* no other repo table exists either —
   truly empty database — behaves like `make schema`: applies every migration in order,
   recording a ledger row after each one, all in that migration's own transaction (so a
   failure rolls back the migration *and* leaves no ledger row for it — atomic, not
   two separate steps that can disagree).
3. If `schema_migrations` exists — the normal case from here on — applies only migrations
   with a version greater than the highest recorded, in order, recording each as it goes.
   Safe to run repeatedly; a fully-caught-up database is a no-op.
4. If `schema_migrations` doesn't exist *but* other repo tables do — a pre-ledger
   database, exactly `ledgex_schema_check`'s situation — refuses and says so, rather than
   guessing. Bringing a pre-ledger database under the ledger for the first time is a
   one-time **baseline** operation (see below), not something `make migrate` should do
   silently as a side effect of its normal job.

**Baselining a pre-ledger database** (needed exactly once, for exactly this kind of
database): for each migration file, in order, check whether the object it defines already
exists (the same technique used by hand this session — `pg_dump --schema-only`, diffed
against `db/schema.sql`, is enough to find the boundary; a per-migration fingerprint isn't
worth maintaining permanently for something used once). Record a ledger row for each
already-applied migration without re-running its SQL; apply for real whatever isn't there
yet. This is manual/semi-automated, run once, and not part of the ongoing `make migrate`
path — once a database is baselined, it behaves like any other ledger-tracked database
from then on, and this logic is never needed again for it.

`db/schema.sql` is unaffected by any of this — it stays the `pg_dump` record of a clean,
empty-DB apply, produced by `make schema-dump` exactly as today. The ledger changes how a
non-empty database *reaches* that state; it doesn't change what the state is.

### Why this matters now, not later

P5 (and anything after it) keeps touching `ledgex_schema_check` directly. Without this,
the next gap is discovered the same way this one was — by accident, mid-task, requiring a
manual `pg_dump` diff to even locate it — rather than by `make migrate` refusing to run
against a database it doesn't recognize.
