"""Environment variable access and database connection construction.

First extraction slice out of scripts/*.py -- byte-identical across
ingest_parcels.py, ingest_zoning_permits.py, flag_invalid_geometry.py and
compose_property_file.py before this move. No behavior change, no
canonical-copy judgment call: there was only ever one copy to choose
between.

P39, README finding #43 -- THE DEFAULT BINDING. env() calls
load_dotenv(override=False), and load_dotenv searches UPWARD from the current
working directory, so a script run from the repo root picks up the repo-root
.env. That file's DATABASE_URL points at a live remote database. Running a
script directly picks this up, and that is the natural thing to do by hand:

    python3 scripts/compose_property_file.py --parcel-apn 12345678
    python3 scripts/ingest_parcels.py
    python3 scripts/ingest_zoning_permits.py

Those writes cannot be undone. fact_no_delete (0017) and fact_no_update
(0007/0040) make a fact permanent; licence_no_delete/licence_no_update (0027)
and licence_channel_no_delete/_no_update (0033) do the same one level up;
rule_no_delete (0013) does it for rules. There is no "oops" for any of them.

**Corrected 2026-08-23 (P56a) -- "the Makefile targets are all safe" was
false, and stayed false through two separate incidents before it was
checked.** The Makefile carries no `export` directive, so a make variable
only reaches a recipe's own subprocess environment when that recipe names it
explicitly on the command line -- and roughly half of this repo's own
python-based targets never did (`make golden` until P56 containment,
301f312; `scripts/migrate.py`/`migrate_verify.py`/`migrate_baseline.py`
did not either, found live by P56a's own §2 test:
`DATABASE_URL=postgresql://nonexistent.invalid/x make migrate` reached a raw
`psycopg2.OperationalError`, not this file's own refusal, because all three
connected via env("DATABASE_URL") directly and never called get_db() at
all). D9 (P59): that TEST RESULT is no longer live -- P56a's own fix, the
same pass this paragraph documents, added an explicit `refuse_remote()`
call to each of the three scripts (see refuse_remote()'s own docstring
below); re-run today, the identical command correctly refuses, naming the
host, not a raw OperationalError (verified live before writing this
correction, not assumed). The "never call get_db()" clause remains
literally true -- refuse_remote() was extracted specifically so these
three could call it directly without also inheriting get_db()'s own
connection-policy choices (autocommit=False) that do not fit them. The
Makefile-passing-DATABASE_URL half is also fixed (all three recipes now
name it explicitly) -- verify any claim like this against the Makefile's
own recipe text, not this comment, the same discipline that was skipped
the first time.

So get_db() REFUSES a non-local host unless LEDGEX_ALLOW_REMOTE_DB=1 is set
explicitly. Modelled directly on scripts/check_golden.py's own
GOLDEN_ALLOW_RULE_SEED gate, which exists for the identical reason (an
irreversible INSERT nobody should be able to make by accident) -- same shape,
same refuse-by-default posture, same "name the target and say why" error text.
Deliberately NOT a new mechanism.

WHY IN get_db(), NOT IN env(): env() is a generic string accessor with no idea
what any variable means, and a DATABASE_URL-specific rule inside it would apply
that knowledge to every caller asking for anything else (OBJECT_STORE_URL,
OBJECT_STORE_SECRET_KEY). get_db() is the function that already knows it is
building a database connection -- and it already makes a connection POLICY
decision one line down (autocommit = False, which nothing forced on it either).
This is the same category as that line, not a new one.

**Corrected 2026-08-23 (P56a) -- "every real caller reaches a database
through get_db()" was also false.** scripts/migrate.py, migrate_verify.py and
migrate_baseline.py each call psycopg2.connect(env("DATABASE_URL")) (or
admin_connect(), which re-derives the same host) directly -- the exact three
scripts that apply DDL to a live database. refuse_remote() below is the same
refusal, extracted so an env()-level caller can opt into it explicitly at its
own connect site without going through get_db()'s own connection-policy
choices (autocommit=False) that do not fit every caller -- migrate.py already
sets that itself, migrate_verify.py/migrate_baseline.py connect to more than
one database per run (target plus a disposable admin/reference database on
the same host) and get_db()'s own single-connection shape does not fit them.
get_db() itself is unchanged in behavior; it now calls refuse_remote()
(defined below, after _is_local/resolved_host) instead of inlining the same
check, so there is one implementation, not two that could drift.

WHY THIS IS NOT "BUSINESS LOGIC" UNDER §2 ("infra/ ... Zero business logic"):
it names no fact, no licence, no jurisdiction, no field key, no channel -- no
domain concept at all. It is a property of the connection itself, which is
exactly what this module exists to construct. Weighed before writing rather than
assumed; the alternative, a new top-level module for one function, is worse.
"""
import os
from urllib.parse import parse_qs, urlparse

import psycopg2
from dotenv import load_dotenv

# A libpq host that means "this machine." The empty string covers a URL with no
# host at all (postgresql:///ledgex_test), which is a unix socket. A host= query
# parameter beginning with "/" is a unix socket DIRECTORY
# (postgresql://postgres@/db?host=/tmp) and is also local -- handled explicitly
# in _is_local rather than by adding "/tmp" and friends to this set.
_LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"})

_ALLOW_REMOTE_VAR = "LEDGEX_ALLOW_REMOTE_DB"


def env(name):
    load_dotenv(override=False)
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"missing required environment variable: {name}")
    return val


def resolved_host(database_url):
    """The host libpq will actually connect to, or None if this URL cannot be
    parsed into one.

    A `host=` QUERY PARAMETER WINS over the URL's own netloc host, because that
    is what libpq does -- and it is not a corner case here, it is the form this
    project's own local socket connections use
    (postgresql://postgres@/ledgex_test?host=/tmp). Getting that backwards would
    make the guard refuse the one shape it most needs to allow.

    Public (no leading underscore) since P47 (README finding #44, closed):
    scripts/migrate_baseline.py's admin_connect() and dump_schema() rebuilt a
    connection from urlparse fields alone and silently dropped this exact
    query parameter -- the identical mistake this function exists to prevent,
    written a second time nearby because the first fix was never reused.
    Both now call this function instead of re-deriving a host their own way.
    """
    try:
        parts = urlparse(database_url)
    except ValueError:
        return None
    if parts.scheme not in ("postgresql", "postgres"):
        return None
    query_host = parse_qs(parts.query).get("host", [None])[0]
    if query_host is not None:
        return query_host
    try:
        return parts.hostname or ""
    except ValueError:
        # urlparse defers some malformed-netloc errors (a bad bracketed IPv6
        # literal, a non-numeric port) until .hostname is actually read.
        return None


def _is_local(database_url):
    host = resolved_host(database_url)
    if host is None:
        # Unparseable is NOT treated as local. A URL this function cannot read
        # is a URL it cannot vouch for, and the safe reading of "I do not know
        # where this points" is refuse, not "probably fine."
        return False
    if host.startswith("/"):
        return True  # unix socket directory
    return host.lower() in _LOCAL_HOSTS


def refuse_remote(database_url):
    """Raise SystemExit if database_url points at a non-local host and
    LEDGEX_ALLOW_REMOTE_DB=1 is not set. No return value -- call it, then
    connect. Extracted from get_db() (P56a) so scripts/migrate.py,
    migrate_verify.py and migrate_baseline.py can call it once, before their
    own first connection (target or admin -- migrate_verify.py/
    migrate_baseline.py each also open a disposable reference/admin
    connection on the same host via admin_connect(), which re-derives that
    host from this same database_url, so one check here covers both without
    needing a second call at the admin connect site), rather than
    duplicating the host check or being forced to route through get_db()'s
    own connection-policy choices (autocommit=False, a single connection)
    that do not fit every caller. D3 (P56 Phase 2 owner decision): refuses,
    does not warn."""
    if _is_local(database_url) or os.environ.get(_ALLOW_REMOTE_VAR) == "1":
        return
    host = resolved_host(database_url)
    where = f"host {host!r}" if host else "a host this guard could not parse"
    raise SystemExit(
        f"refusing to connect: DATABASE_URL points at {where}, which is not "
        f"local. Writes made through this connection can be PERMANENT and "
        f"un-undoable -- fact_no_delete/fact_no_update (0017, 0007/0040), "
        f"licence and licence_channel immutability (0027, 0033), "
        f"rule_no_delete (0013). Refusing by default so that running a "
        f"script by hand from the repo root cannot silently write to a real "
        f"database just because .env happened to be found by load_dotenv "
        f"(README finding #43). If you genuinely intend this, re-run with "
        f"{_ALLOW_REMOTE_VAR}=1. If you meant a local database, set "
        f"DATABASE_URL explicitly on the command line -- the Makefile's own "
        f"default is local, but not every recipe passes it through yet "
        f"(P56a) -- check the specific recipe rather than assuming."
    )


def get_db():
    database_url = env("DATABASE_URL")
    refuse_remote(database_url)
    # C7 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): rule.effective_from/
    # effective_to are `date` columns (0009); core.rules.select_effective_rule
    # compares them to a `timestamptz` as_of. Postgres promotes a date to a
    # timestamptz at SESSION-LOCAL midnight -- with no pinned session
    # timezone, the same rule row and the same as_of instant can be
    # effective under one machine's default TimeZone and not effective
    # under another's (reproduced empirically: UTC vs America/Los_Angeles
    # disagree by up to 26 hours on the same comparison). Pinned here, per
    # C7's own acceptance criterion ("pin the session timezone at
    # connection time in ONE place, infra.env.get_db") --
    # scripts/compose_property_file.py's real runtime path imports and
    # uses get_db() for exactly this. NOT the only psycopg2.connect() call
    # site in this repo (grepped: check_golden.py, smoke_real.py,
    # migrate.py/migrate_verify.py/migrate_baseline.py and others each
    # open their own connection directly, a pre-existing pattern this fix
    # does not change) -- those are golden/migration/smoke infrastructure,
    # not the rule-effectivity comparison path C7 is about; out of this
    # fix's scope, not silently assumed unaffected. Pinned via the
    # connection's own startup `options`, NOT a `SET TIME ZONE` statement
    # after connecting: a SET is transactional and would be silently
    # undone by any caller's later conn.rollback() (a real, common path in
    # this codebase's own exception handlers), leaving the pin
    # inconsistently in effect depending on what happened earlier in the
    # same connection's lifetime. The `options` startup parameter is not
    # part of any transaction and holds for the connection's entire
    # session regardless of later commits/rollbacks.
    conn = psycopg2.connect(database_url, options="-c timezone=UTC")
    conn.autocommit = False
    return conn
