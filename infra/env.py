"""Environment variable access and database connection construction.

First extraction slice out of scripts/*.py -- byte-identical across
ingest_parcels.py, ingest_zoning_permits.py, flag_invalid_geometry.py and
compose_property_file.py before this move. No behavior change, no
canonical-copy judgment call: there was only ever one copy to choose
between.

P39, README finding #43 -- THE DEFAULT BINDING. env() calls
load_dotenv(override=False), and load_dotenv searches UPWARD from the current
working directory, so a script run from the repo root picks up the repo-root
.env. That file's DATABASE_URL points at a live remote database. The Makefile
targets are all safe -- every one passes DATABASE_URL explicitly, defaulting to
postgresql://localhost/ledgex_schema_check -- but running a script directly is
not, and that is the natural thing to do by hand:

    python3 scripts/compose_property_file.py --parcel-apn 12345678
    python3 scripts/ingest_parcels.py
    python3 scripts/ingest_zoning_permits.py

Those writes cannot be undone. fact_no_delete (0017) and fact_no_update
(0007/0040) make a fact permanent; licence_no_delete/licence_no_update (0027)
and licence_channel_no_delete/_no_update (0033) do the same one level up;
rule_no_delete (0013) does it for rules. There is no "oops" for any of them.

So get_db() now REFUSES a non-local host unless LEDGEX_ALLOW_REMOTE_DB=1 is set
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
This is the same category as that line, not a new one. Every real caller reaches
a database through get_db(), so nothing is missed by scoping it here.

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


def get_db():
    database_url = env("DATABASE_URL")
    if not _is_local(database_url) and os.environ.get(_ALLOW_REMOTE_VAR) != "1":
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
            f"DATABASE_URL explicitly -- every Makefile target already does."
        )
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    return conn
