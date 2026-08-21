#!/usr/bin/env python3
"""P50 -- proof that guard_destructive.py blocks what it claims to block.

A guardrail nobody tested is a guardrail nobody knows the shape of. This
runs the hook as a real subprocess, feeding it the same JSON payload Claude
Code sends, and checks the exit code for two tables: commands that MUST be
blocked (exit 2) and commands that MUST get through (exit 0).

The second table is the one that earns its keep. A guard that blocks
everything is trivially "safe" and completely useless, and the ordinary work
of this repo -- `docker compose down` with no -v, a psql against localhost,
`grep -n "DROP DATABASE" db/migrations/`, `rm -rf dist` -- has to keep
working or the guard gets switched off within a day.

Run: python3 .claude/hooks/test_guard_destructive.py
Exit 0 = every case behaved as declared.
"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard_destructive.py")

MUST_BLOCK = [
    "sudo systemctl restart postgresql",
    "docker volume rm ledgex_pgdata",
    "docker volume prune -f",
    "docker compose down -v",
    "docker compose down --volumes",
    "bash -lc 'docker compose down --volumes'",
    "docker system prune -af",
    'psql "$DATABASE_URL" -c "DROP DATABASE ledgex_smoke"',
    'psql -c "drop schema public cascade"',
    "dropdb ledgex_test",
    "python3 scripts/ingest_parcels.py --phase e --snapshot-id ca_san_jose.parcels:sha256:ab",
    "LEDGEX_ALLOW_REMOTE_DB=1 python3 scripts/compose_property_file.py --parcel-apn 123",
    "psql postgresql://postgres:pw@db.example.supabase.co:5432/postgres -c \"select 1\"",
    "env DATABASE_URL=postgresql://user:pw@prod.example.com/ledgex make migrate",
    "git push --force origin main",
    "git push -f origin main",
    "rm -rf /",
    "rm -rf ~",
]

MUST_ALLOW = [
    "docker ps",
    "docker info",
    "docker compose down",
    "docker compose up -d",
    "make smoke-real",
    "make smoke-real SMOKE_PYTHON=.venv-ingest/bin/python3",
    'psql postgresql://localhost/ledgex_smoke -c "select count(*) from parcel"',
    'psql "postgresql://postgres@/ledgex_test?host=/tmp" -c "select 1"',
    'psql "postgresql://postgres:postgres@127.0.0.1:55445/clean_check" -f db/tests/invariants.sql',
    'grep -n "DROP DATABASE" db/migrations/0001_init.sql',
    'rg "drop database" db/',
    "python3 scripts/ingest_parcels.py --phase d --snapshot-id ca_san_jose.parcels:sha256:ab",
    "curl -sI --max-time 15 https://data.sanjoseca.gov/dataset/x/download/y.csv",
    "git push origin p50-local-smoke",
    "git log --oneline -5",
    "rm -rf dist",
    "rm -rf build/__pycache__",
    "make db-test",
    "createdb ledgex_smoke",
]


def run(command):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    p = subprocess.Popen([sys.executable, HOOK], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _out, err = p.communicate(payload.encode("utf-8"))
    return p.returncode, err.decode("utf-8", "replace")


def main():
    bad = 0
    print("MUST BLOCK (expect exit 2)")
    for cmd in MUST_BLOCK:
        rc, err = run(cmd)
        ok = rc == 2
        rule = err.split(" -- ", 1)[1].split("\n", 1)[0] if (ok and " -- " in err) else ""
        print("  %-6s %s%s" % ("ok" if ok else "MISS", cmd[:66],
                               ("   [%s]" % rule) if rule else ""))
        bad += 0 if ok else 1

    print("\nMUST ALLOW (expect exit 0)")
    for cmd in MUST_ALLOW:
        rc, _err = run(cmd)
        ok = rc == 0
        print("  %-6s %s" % ("ok" if ok else "FALSE+", cmd[:66]))
        bad += 0 if ok else 1

    print("\nFAIL-CLOSED on an unparseable payload (expect exit 2)")
    p = subprocess.Popen([sys.executable, HOOK], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.communicate(b"not json")
    ok = p.returncode == 2
    print("  %-6s malformed stdin -> exit %d" % ("ok" if ok else "MISS", p.returncode))
    bad += 0 if ok else 1

    total = len(MUST_BLOCK) + len(MUST_ALLOW) + 1
    print("\n%d/%d cases behaved as declared." % (total - bad, total))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
