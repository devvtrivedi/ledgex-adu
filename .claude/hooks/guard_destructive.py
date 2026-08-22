#!/usr/bin/env python3
"""P50 -- PreToolUse guard. Blocks irreversible actions before they run.

WHY A HOOK AND NOT JUST A DENY LIST. .claude/settings.json carries the same
rules declaratively, and that file is where a human looks to find out what is
forbidden -- so both exist. But permission patterns match the SHAPE of a
command (its leading tokens), and the actions worth stopping here do not
always live at the front:

    psql "$URL" -c "DROP DATABASE ledgex_smoke"
    bash -lc 'docker compose down --volumes'
    env LEDGEX_ALLOW_REMOTE_DB=1 python3 scripts/ingest_parcels.py --phase e

Every one of those is destructive somewhere in the middle of a string a
prefix pattern reads as a harmless `psql`, `bash` or `env` invocation. This
hook reads the whole command text and matches against all of it.

CONTRACT. Claude Code sends the tool call as JSON on stdin. Exit 0 allows;
exit 2 BLOCKS the call and shows this script's stderr to the model, which is
why every reason below is written to be read by whoever hits it.

FAIL-CLOSED. If the payload cannot be parsed, this exits 2. A guard that
cannot see what it is guarding has no business waving it through. The cost
of that choice is that a malformed payload stops work loudly instead of
silently -- which is the correct trade for a file whose entire purpose is to
stand between an agent and an un-undoable act.

NO DEPENDENCIES. Standard library only, and no import from this repo. A hook
runs under whatever interpreter Claude Code has, which is not guaranteed to
be either virtualenv -- importing infra.env would pull in psycopg2 and
python-dotenv and fail on a bare python3. That forces the one duplication in
this file, _host_is_local() below, which is deliberately MORE conservative
than infra.env._is_local: anything it cannot confidently read as local, it
treats as remote and blocks.
"""
import json
import os
import re
import sys
import urllib.parse

# Commands that only read. A rule below may match text inside one of these
# (`grep -n "DROP DATABASE" db/migrations/*.sql` is a normal thing to do), so
# a command whose first token is here AND which contains no shell operator
# that could chain something else on is exempt.
READ_ONLY_HEADS = frozenset({
    "grep", "rg", "cat", "head", "tail", "wc", "ls", "find", "less", "file",
    "stat", "diff", "sort", "uniq", "column", "jq", "tree", "which", "type",
})
READ_ONLY_GIT = frozenset({"grep", "log", "show", "diff", "status", "blame", "branch"})
SHELL_OPERATORS = (";", "&&", "||", "|", ">", "<", "$(", "`", "\n")

_LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"})


def _host_is_local(url):
    """Conservative: unparseable or unrecognised means NOT local."""
    try:
        parts = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if parts.scheme not in ("postgresql", "postgres"):
        return False
    query_host = urllib.parse.parse_qs(parts.query).get("host", [None])[0]
    if query_host is not None:
        return query_host.startswith("/") or query_host.lower() in _LOCAL_HOSTS
    try:
        host = parts.hostname or ""
    except ValueError:
        return False
    if host.startswith("/"):
        return True
    return host.lower() in _LOCAL_HOSTS


def _remote_database_url(command):
    """Return the first non-local postgres URL literal in the command, if any."""
    for m in re.finditer(r"postgres(?:ql)?://[^\s\"'`;|&)]+", command):
        if not _host_is_local(m.group(0)):
            return m.group(0)
    return None


# (rule name, matcher, reason). A matcher is a compiled regex or a callable
# returning a truthy detail.
RULES = [
    (
        "sudo",
        re.compile(r"(?:^|[;&|(\s])(?:sudo|doas)\b"),
        "This session does not run privileged commands. Nothing in LedgeX's local\n"
        "setup needs root: Postgres, MinIO and the viewer all run as your user or\n"
        "inside Docker. If something genuinely requires sudo, run it yourself in a\n"
        "terminal so the decision is yours.",
    ),
    (
        "docker volume destruction",
        re.compile(r"docker\s+volume\s+(?:rm|prune)\b"
                   r"|docker\s+system\s+prune\b"
                   r"|docker\s+compose\s+down\b[^\n;&|]*(?:-v\b|--volumes\b)"
                   r"|docker\s+rm\b[^\n;&|]*(?:\s-v\b|--volumes\b)"),
        "This would delete Docker volumes -- the Postgres data directory and the\n"
        "MinIO object store live in them. Every snapshot this project has ever\n"
        "written locally is in that bucket, and fact/licence/snapshot rows are\n"
        "immutable by design precisely because they are not meant to be recreated\n"
        "casually. `docker compose down` WITHOUT -v is fine and is not blocked.",
    ),
    (
        "database destruction",
        re.compile(r"\bDROP\s+DATABASE\b|\bDROP\s+SCHEMA\b|\bdropdb\b"
                   r"|\bDROP\s+OWNED\b|\bDROP\s+TABLESPACE\b", re.IGNORECASE),
        "This drops a database or schema. CLAUDE.md records that a rebuild (drop,\n"
        "re-migrate, reseed) is sometimes the ONLY remedy for a contaminated\n"
        "database -- and also that it must never happen without the before-state\n"
        "being queried and recorded first, and without asking. Ask, show the query\n"
        "output that justifies it, and let the human run the drop.",
    ),
    (
        "full-scale ingest (--phase e)",
        re.compile(r"--phase[=\s]+e\b"),
        "--phase e is the full ~225k-parcel load, not the 20-parcel slice. It writes\n"
        "one parcel row per feature plus facts for every one of them, in a single\n"
        "transaction, and fact_no_delete/fact_no_update (0017, 0007/0040) mean none\n"
        "of it can be undone. `make smoke-real` deliberately runs --phase d instead.\n"
        "Running phase E is an explicit human decision, every time.",
    ),
    (
        "remote-database override",
        re.compile(r"LEDGEX_ALLOW_REMOTE_DB\s*=\s*1"),
        "LEDGEX_ALLOW_REMOTE_DB=1 disables infra.env.get_db()'s refusal to connect to\n"
        "a non-local database. That guard exists because the repo-root .env's\n"
        "DATABASE_URL points at a real hosted database and load_dotenv finds it from\n"
        "anywhere in the tree (P39, finding #43). Setting this flag is exactly the\n"
        "act it was written to prevent an agent from performing.",
    ),
    (
        "write to a non-local database",
        _remote_database_url,
        "This command names a postgres URL that is not localhost. Writes through it\n"
        "may be PERMANENT: fact rows cannot be deleted or updated (0017, 0007/0040),\n"
        "licence and licence_channel are immutable (0027, 0033), rules cannot be\n"
        "deleted (0013), snapshots cannot be changed (0021). There is no undo and no\n"
        "migration that can walk it back. Use a local database -- ledgex_smoke,\n"
        "ledgex_test or ledgex_schema_check.",
    ),
    (
        "force-push",
        re.compile(r"git\s+push\b[^\n;&|]*(?:--force(?!-with-lease)\b|(?:^|\s)-f\b)"),
        "A force-push rewrites published history. This repo's prompts/README.md\n"
        "records commit hashes per pass as its own audit trail, so a rewrite makes\n"
        "those rows point at nothing. Push normally, or let the human decide.",
    ),
    (
        "recursive delete outside the working tree",
        re.compile(r"\brm\s+(?:-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\s+"
                   r"(?:/(?!tmp/|private/tmp/|var/folders/)|~|\$HOME|\.\s*$|\*)"),
        "A recursive force-delete rooted outside a scratch directory. If this is\n"
        "meant to clear build output, name the specific path (`rm -rf dist`), which\n"
        "is not blocked.",
    ),
]


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except ValueError:
        sys.stderr.write(
            "guard_destructive.py could not parse the PreToolUse payload, so it\n"
            "cannot tell whether this call is safe. Failing closed -- see this\n"
            "script's own FAIL-CLOSED note.\n")
        return 2

    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command.strip():
        return 0

    # Read-only exemption -- see READ_ONLY_HEADS above.
    if not any(op in command for op in SHELL_OPERATORS):
        tokens = command.split()
        head = os.path.basename(tokens[0]) if tokens else ""
        if head in READ_ONLY_HEADS:
            return 0
        if head == "git" and len(tokens) > 1 and tokens[1] in READ_ONLY_GIT:
            return 0

    for name, matcher, reason in RULES:
        detail = matcher(command) if callable(matcher) else matcher.search(command)
        if not detail:
            continue
        shown = detail if isinstance(detail, str) else (
            detail.group(0) if hasattr(detail, "group") else str(detail))
        sys.stderr.write(
            "BLOCKED by .claude/hooks/guard_destructive.py -- %s\n\n"
            "  matched: %s\n\n"
            "%s\n\n"
            "This is a guardrail, not a puzzle to route around. Do not retry the same\n"
            "action through a different shell, script, heredoc or tool. If it is\n"
            "genuinely the right thing to do, say so plainly and let the human run it.\n"
            % (name, shown, reason))
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
