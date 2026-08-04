#!/usr/bin/env python3
"""Document QA — the drift gate.

Spec v1.7 sec 0.2: "Document QA fails if any invariant body or enforcement cell
differs." This script is that check. Wire it into `make check-boundary`.

It asserts:
  1. Every invariant in ledgex_source.INVARIANTS appears verbatim in BOTH
     docs/LEDGEX_SPEC.md and docs/LEDGEX_RULES.md.
  2. Every make target appears verbatim in both.
  3. Neither markdown file contains a second, differing copy of an invariant ID
     row (a copied table).
  4. The generated markdown is current — regenerating produces no diff.

Exit code 0 = pass, 1 = fail.
"""
import pathlib, re, sys, subprocess

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ledgex_source as S

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "LEDGEX_SPEC.md"
RULES = ROOT / "docs" / "LEDGEX_RULES.md"

failures = []


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def check_presence():
    for path in (SPEC, RULES):
        if not path.exists():
            failures.append(f"MISSING ARTIFACT: {path.relative_to(ROOT)}")
            continue
        body = norm(path.read_text(encoding="utf-8"))
        for iid, text, enf in S.INVARIANTS:
            if norm(text) not in body:
                failures.append(f"{path.name}: {iid} body text not found verbatim")
            if norm(enf) not in body:
                failures.append(f"{path.name}: {iid} enforcement cell not found verbatim")
        for tgt, surface, cond in S.MAKE_TARGETS:
            if norm(cond) not in body:
                failures.append(f"{path.name}: '{tgt}' pass condition not found verbatim")


def check_no_duplicate_table():
    """A second row for the same invariant ID means someone copied the table."""
    row = re.compile(r"^\|\s*\*\*(I\d+)\*\*\s*\|", re.M)
    for path in (SPEC, RULES):
        if not path.exists():
            continue
        seen = {}
        for m in row.finditer(path.read_text(encoding="utf-8")):
            seen[m.group(1)] = seen.get(m.group(1), 0) + 1
        dupes = sorted(k for k, v in seen.items() if v > 1)
        if dupes:
            failures.append(
                f"{path.name}: duplicated invariant rows {dupes} — copied table, "
                f"prohibited by sec 0.2")


def check_regenerates_clean():
    """Rebuild into memory and compare. Catches hand-edited markdown."""
    import importlib
    for mod_name, path in (("build_spec_v1_7", SPEC), ("build_rules_v1_4", RULES)):
        try:
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)
        except Exception as e:  # pragma: no cover
            failures.append(f"{mod_name}: builder failed to import ({e})")
            continue
        if not path.exists():
            continue
        fresh = mod.render_md()
        on_disk = path.read_text(encoding="utf-8")
        # ignore the generated-on date line
        strip = lambda t: re.sub(r"\*Generated \d{4}-\d{2}-\d{2}.*", "", t).strip()
        if strip(fresh) != strip(on_disk):
            failures.append(
                f"{path.name}: on-disk file differs from builder output — "
                f"hand-edited or stale. Run `make docs`.")


if __name__ == "__main__":
    check_presence()
    check_no_duplicate_table()
    check_regenerates_clean()
    if failures:
        print("DOCUMENT QA FAILED\n")
        for f in failures:
            print("  x " + f)
        sys.exit(1)
    print(f"DOCUMENT QA PASSED — {len(S.INVARIANTS)} invariants and "
          f"{len(S.MAKE_TARGETS)} make targets verbatim in both artifacts; "
          f"no copied tables; markdown current.")
