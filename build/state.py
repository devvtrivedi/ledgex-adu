#!/usr/bin/env python3
"""`make state` -- everything a cold session needs to orient, in one
command instead of ten separate git/grep calls. Generated at call time
from the live repo; never cached to a committed file, because a stale
state file is worse than none (prompts/README.md's own session-hygiene
rule, applied to this tool too).

Prints in under 30 lines: HEAD sha + subject, origin/main sha, unpushed
commit count + subjects, migration count + highest, SPEC_VERSION,
RULES_VERSION, invariant test floor, working-tree cleanliness, and the
active package from prompts/README.md.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))


def sh(args):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def main():
    lines = []

    head = sh(["git", "log", "-1", "--format=%h %s"])
    lines.append(f"HEAD:          {head or '(no commits)'}")

    origin = sh(["git", "rev-parse", "--short", "origin/main"])
    lines.append(f"origin/main:   {origin or '(no origin/main -- never fetched?)'} "
                 f"(as of last fetch, not live)")

    unpushed = sh(["git", "log", "--oneline", "origin/main..HEAD"]) if origin else None
    if unpushed:
        n = len(unpushed.splitlines())
        lines.append(f"Unpushed:      {n} commit(s)")
        for l in unpushed.splitlines():
            lines.append(f"                 {l}")
    elif origin:
        lines.append("Unpushed:      none -- HEAD matches origin/main")

    migrations = sorted((ROOT / "db" / "migrations").glob("*.sql"))
    highest = migrations[-1].name if migrations else "(none)"
    lines.append(f"Migrations:    {len(migrations)} (highest: {highest})")

    try:
        import ledgex_source as S
        lines.append(f"SPEC_VERSION:  {S.SPEC_VERSION}")
        lines.append(f"RULES_VERSION: {S.RULES_VERSION}")
    except Exception as e:
        lines.append(f"SPEC/RULES version: FAILED to import ledgex_source ({e})")

    invariants_sql = ROOT / "db" / "tests" / "invariants.sql"
    floor_match = re.search(r"IF v_pass_count < (\d+) THEN", invariants_sql.read_text())
    lines.append(f"Invariant floor: {floor_match.group(1) if floor_match else '(not found)'}")

    status = sh(["git", "status", "--porcelain"])
    if status:
        n = len(status.splitlines())
        lines.append(f"Working tree:  DIRTY -- {n} file(s) changed/untracked")
    else:
        lines.append("Working tree:  clean")

    readme = ROOT / "prompts" / "README.md"
    active = None
    if readme.exists():
        for row in readme.read_text().splitlines():
            m = re.match(r"\|\s*(P\d+)\s*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^|]+)\|", row)
            if m and "done" not in m.group(4):
                active = f"{m.group(1)} — {m.group(2)} ({m.group(4).strip()}) -- prompts/{m.group(3)}"
                break
    lines.append(f"Active package: {active or '(none found -- check prompts/README.md)'}")

    print("\n".join(lines))
    if len(lines) > 30:
        print(f"\n[state.py: {len(lines)} lines, over the 30-line budget -- "
              f"tighten before trusting this in a script]", file=sys.stderr)


if __name__ == "__main__":
    main()
