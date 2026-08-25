#!/usr/bin/env python3
"""Regression test for A-N6 (P59C): build/check_jurisdiction_names.py's
widened blocklist missed the accented forms "San José"/"SAN JOSÉ" -- the
literal ASCII words in WORD_SEQUENCES never matched an accented "é"
(a different character from plain "e", not a case difference IGNORECASE
folds), while the module's own docstring claimed the accented name was
covered. Fixed by NFKD-decomposing and stripping combining marks from
each line before matching (_strip_diacritics), not by hand-listing an
accented variant -- this test protects THAT mechanism, which nothing
exercised before this pass (the widening itself, C6/P59, was proven RED-
then-GREEN on planted input at the time but never run against the real
tree afterward until P59B caught it -- CONVENTIONS.md's own "proving a
check can fail on planted input does not establish it passes on real
input" incident, recurring).

Plants a temporary core/-shaped file (never touches the real core/) via
build.check_jurisdiction_names.check(), monkeypatching CORE_DIR --
imported, not reimplemented, so this test tracks the real check()
function, not a copy of it. Also runs check() against the REAL core/
tree, unpatched, and asserts the accented-form fix does not itself
introduce a false positive there (the real tree has no accented
jurisdiction name to begin with, so this is a green-stays-green check,
not a second RED proof).

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "build")
import check_jurisdiction_names as CJN  # noqa: E402 -- module under test


def run():
    failures = []

    with tempfile.TemporaryDirectory() as tmp:
        fake_core = pathlib.Path(tmp) / "core"
        fake_core.mkdir()
        (fake_core / "fixture.py").write_text(
            "# comment naming the city in prose\n"
            "CITY_1 = 'San José'\n"
            "CITY_2 = 'SAN JOSÉ'\n"
            "CITY_3 = 'a harmless line with no jurisdiction name'\n",
            encoding="utf-8",
        )

        original_core_dir, original_root = CJN.CORE_DIR, CJN.ROOT
        try:
            CJN.CORE_DIR = fake_core
            CJN.ROOT = pathlib.Path(tmp)  # check()'s own relpath is relative to ROOT, not CORE_DIR
            planted_failures, _ = CJN.check()
        finally:
            CJN.CORE_DIR = original_core_dir
            CJN.ROOT = original_root

    # "core/fixture.py:" (relpath is relative to the patched ROOT, i.e.
    # tmp, so it includes the "core/" prefix). Excludes STALE GRANDFATHER
    # entries -- expected noise here: scanning only the fake core/ means
    # none of the real GRANDFATHERED sites (core/exceptions.py etc.) were
    # ever "seen," so check()'s own stale-detection correctly reports all
    # of them stale for THIS scan; irrelevant to what this test checks.
    matched_lines = {
        int(f.split(":")[1]) for f in planted_failures
        if f.startswith("core/fixture.py:") and "forbidden token" in f
    }
    if 2 not in matched_lines:
        failures.append(f"'San José' (mixed case) was NOT caught -- planted_failures={planted_failures!r}")
    if 3 not in matched_lines:
        failures.append(f"'SAN JOSÉ' (upper case) was NOT caught -- planted_failures={planted_failures!r}")
    if 4 in matched_lines:
        failures.append("the harmless line was flagged -- false positive")

    # Real-tree check (CONVENTIONS.md's own requirement: planted-input proof
    # alone is insufficient). Not a RED proof -- the real tree has no
    # accented jurisdiction name, so this asserts the fix doesn't create a
    # NEW false positive there, and that the tree is otherwise still clean
    # modulo the existing, unrelated GRANDFATHERED entries.
    real_failures, _ = CJN.check()
    unexpected_real_failures = [f for f in real_failures if "STALE GRANDFATHER" not in f]
    if unexpected_real_failures:
        failures.append(
            f"real core/ tree is NOT clean under the accent-stripping fix: {unexpected_real_failures!r}"
        )

    if failures:
        print("[test] FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("[test] PASS: 'San José' and 'SAN JOSÉ' both caught on planted input; "
          "no false positive on a harmless line; real core/ tree stays clean.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
