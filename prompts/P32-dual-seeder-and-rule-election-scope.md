## P32 — Close the dual-seeder before it drifts, then scope finding #35

Standard hard rules apply ([CONVENTIONS.md](CONVENTIONS.md)). Step 3 reports only — nothing
is built for it.

---

### 1. Finding #36 — the rule row had two independent `DO NOTHING` seeders

Confirmed directly, not assumed from the prompt's own citation: `db/seeds/
day4_sources.sql`'s rule `INSERT` and `scripts/check_golden.py`'s own copy both ended in
`ON CONFLICT (id) DO NOTHING` — finding #32's exact shape (two independent seeders, same
primary key, `DO NOTHING`), reintroduced by P31 one package after #32 was fixed for
`source`. Byte-identical today; nothing enforced that. A citation or `pack_version` edit to
one seeder alone would pass `make golden` silently — `ruleset_version` is only
`rule_key@version`, so the gate that would otherwise catch drift cannot see it.

**Verified the trigger interaction before relying on it, not on faith, per instruction.**
`db/migrations/0013_rule_triggers.sql`'s `rule_no_destructive_update()` has two guards:
guard 1 fires only when `NEW.effective_to IS DISTINCT FROM OLD.effective_to AND
OLD.effective_to IS NOT NULL` — our row's `effective_to` is `NULL` on both sides of a
same-value `DO UPDATE`, so `NULL IS DISTINCT FROM NULL` is `false`, guard 1 short-circuits.
Guard 2 ORs fourteen `IS DISTINCT FROM` comparisons across every other column — identical
`EXCLUDED` values make every comparison `false`, the OR-chain is `false`, guard 2 doesn't
fire either. Read this way first, then run for real: a full `ON CONFLICT (id) DO UPDATE SET`
covering all fourteen columns, identical `EXCLUDED` values, against the real seeded row on a
scratch database — `INSERT 0 1`, exit code `0`, no exception. Then the other half, for real:
the identical statement with one column drifted (`citation` replaced with a planted string)
raised immediately:
```
ERROR:  I18 violated: rule ca_san_jose.adu_detached_max_height_city_standards.v1 is
immutable. Only effective_to may be set (NULL -> a date, once). A correction is a new
rule row at version + 1, never an UPDATE.
```
`DO UPDATE` does not fire on identical values (confirmed, not the STOP-and-report branch)
— fixed at the source, `scripts/check_golden.py`'s `INSERT INTO rule` now ends `ON CONFLICT
(id) DO UPDATE SET` naming all fourteen non-key columns, the same remedy P26 applied to
`check_conformance.py` for finding #32.

**This is a strictly stronger guarantee than #32's own remedy could get, and the finding
says so rather than "fixed like #32."** `source` (finding #32) has no immutability trigger
— `DO UPDATE` there just makes the second seeder's values win, silently, same as before,
only order-independent now. `rule` has `0013`'s real trigger: `DO UPDATE` here does not
merely resolve ordering, it makes any FUTURE drift between the two seeders **impossible to
land silently** — the moment either copy is edited without the other, the very next
`make golden` run raises `I18 violated` by name, loudly, correctly attributing the row.
Silent drift became a loud, correctly-named exception, not just a fixed race.

**Verified against a fresh database, both orderings, after the fix**: `make schema` → fresh
insert via `check_golden.py`'s own seed → `PASSED`; re-run on the same database (the `DO
UPDATE` path with identical values) → `PASSED`, no exception. Separately: `db/seeds/
day4_sources.sql` applied first, then `check_golden.py`'s seed on top → `PASSED`, no
exception, confirming the two seeders are now safely commutative in either order.

---

### 2. Finding #37 — `make golden` performs an irreversible write

`0013`'s `rule_no_delete` raises unconditionally — no principal, no migration, no
superuser can ever remove a `rule` row once inserted. `make golden` now inserts one
(`check_golden.py`'s own seed, extended by P31). Every database `make golden` is run
against therefore now carries this row **permanently**. Idempotent, one known id, small
blast radius — but this is finding #28's exact class (a routine check performing an
irreversible write), and #28 was found the hard way, on a real WORM bucket, after real
fixture traffic had already accumulated 302 object versions. Found this time by reading
the trigger before it happened somewhere less recoverable, not after.

**Checked per-database, not assumed**: `ledgex_schema_check` — `make migrate-verify` run
first (required before citing it as evidence, per `CONVENTIONS.md`): 51 migrations,
`MATCH`. Then queried directly: `SELECT count(*) FROM rule WHERE id=
'ca_san_jose.adu_detached_max_height_city_standards.v1'` → `0`. **Does not currently carry
the row** — `make golden` has only ever been run against disposable scratch databases and
CI's own ephemeral containers during P31/P32's authoring, never against this one.
`ledgex_test` (`make test`'s own disposable default) does not exist locally at all right
now — nothing to check.

**The real, live risk, not a hypothetical one**: `Makefile`'s own `DATABASE_URL ?=
postgresql://localhost/ledgex_schema_check` is the bare default for every target,
including `golden`. A developer running `make golden` locally with no override — the
ordinary, unthinking way to run it — plants this row into the shared dev database on the
very next invocation, permanently, with no confirmation prompt. CI's own ephemeral
`ledgex_ci`/`ledgex_ci_p5`/`ledgex_ci_phaseb` databases are not a comparable risk: they are
destroyed with the runner at the end of every job regardless of what any trigger blocks,
the same property that already makes every other CI-only side effect in this project safe.

**Whether `make golden` should be doing this at all — the argument, not a decision.**
Every other row `check_golden.py`/`check_conformance.py` self-seed — `licence`,
`jurisdiction`, `source`, `field_definition` — is either free of any immutability trigger
or already idempotency-safe by construction (source, since #32/#36). `rule` is
categorically different since `0013`: irreversible, not merely re-correctable. A target
whose name is `check` permanently marking every database it ever touches is architecturally
surprising for a verification gate, independent of blast radius. Two real shapes, neither
built here:

- **(a) `make golden` refuses to run, loudly, when the rule row is absent** — requiring
  `db/seeds/day4_sources.sql` (the actual seed layer this row belongs to) to have run
  first. Correct in spirit — a check should verify, not create irreversible state as a
  side effect — but reopens the exact "CI never runs `db/seeds/`" gap this project already
  built a specific, working exception around (`check_golden.py`'s/`check_conformance.py`'s
  own self-seeding, for precisely the reference rows this option would now require `db/
  seeds/` to supply instead). Would need its own CI wiring decision, not a drop-in change.
- **(b) Keep `check_golden.py` as the seeder, but stop treating it as routine.** Document
  explicitly, in the target's own name or a loud one-time confirmation, that running `make
  golden` against a database for the first time is a one-way bootstrap action for this one
  row, not merely a check — closer to how `db/seeds/`'s own scripts are already understood
  by anyone who reads `db/README.md` first.

**No change made in this package** — reported for a decision, per instruction; recording
the current, real state (which databases already carry the row, and why the default
`DATABASE_URL` makes this a live risk rather than a theoretical one) is this section's own
job, not picking between (a) and (b).

---
