#!/usr/bin/env python3
"""Regression test for C16 (P59): build/qa_check.py's refusal-code sync
check (check_refusal_codes_match_spec) used letters-only regexes to pull
the refusal-code vocabulary out of docs/LEDGEX_SPEC.md §9, 0055's
REFUSAL_CODES_BEGIN/END block, and core/model.py's REFUSAL_CODES tuple.
A code containing a digit would fail to match on whichever side used that
regex, silently vanishing from that side's set instead of surfacing as a
mismatch -- two copies of a vocabulary can drift apart with the sync check
reporting "PASSED" the entire time, for exactly the class of code this
check exists to catch.

Not a live-corruption regression (no real refusal code has ever contained
a digit -- confirmed directly against docs/LEDGEX_SPEC.md, 0055, and
core/model.py before landing the fix), so this proves the mechanism on
synthetic text reproducing the real bug shape, not a real divergence
found in the tree.

Exit code 0 = PASS (green, current qa_check.py regexes). Exit code 1 =
FAIL (red -- reproduces the pre-fix behavior by using the old, letters-
only patterns inline, without editing qa_check.py itself).
"""
import re
import sys

sys.path.insert(0, "build")
import qa_check as QC  # noqa: E402 -- module under test, imported, not reimplemented

# The exact shape of the real bug: a digit-bearing code ("OAUTH2_TOKEN_
# EXPIRED") present in the spec prose and the model tuple, but silently
# missing from the migration's REFUSAL_CODES_BEGIN/END block -- a REAL
# drift the check must catch.
SPEC_PROSE = "OAUTH2_TOKEN_EXPIRED   L1   Some digit-bearing code for this test"
MIGRATION_BLOCK = "'JURISDICTION_UNRESOLVED',\n'PARCEL_NOT_FOUND'"  # OAUTH2_TOKEN_EXPIRED missing
MODEL_BLOCK = '"OAUTH2_TOKEN_EXPIRED",\n"JURISDICTION_UNRESOLVED",\n"PARCEL_NOT_FOUND"'

# The OLD (pre-C16) letters-only patterns, reproduced inline here (not by
# importing qa_check, since that module now carries the fix) so this test
# still demonstrates the pre-fix failure mode after the fix lands.
OLD_PROSE_RE = re.compile(r"\b[A-Z][A-Z]*(?:_[A-Z]+)+\b")
OLD_MIGRATION_RE = re.compile(r"'([A-Z][A-Z_]+)'")
OLD_MODEL_RE = re.compile(r'"([A-Z][A-Z_]+)"')


def run():
    failures = []

    # RED reproduction: with the OLD regexes, the digit-bearing code is
    # invisible on ALL THREE sides -- it never enters spec_codes,
    # migration_codes, or model_codes, so a diff between any pair reports
    # no mismatch even though the migration is genuinely missing it.
    old_spec = set(OLD_PROSE_RE.findall(SPEC_PROSE))
    old_migration = set(OLD_MIGRATION_RE.findall(MIGRATION_BLOCK))
    old_model = set(OLD_MODEL_RE.findall(MODEL_BLOCK))
    if "OAUTH2_TOKEN_EXPIRED" in old_spec or "OAUTH2_TOKEN_EXPIRED" in old_model:
        failures.append(
            "OLD regex unexpectedly captured the digit-bearing code -- "
            "the synthetic fixture no longer reproduces the pre-fix bug "
            "shape; this test needs updating, not qa_check.py")
    old_missing_from_migration_detected = "OAUTH2_TOKEN_EXPIRED" in (old_spec - old_migration)
    if old_missing_from_migration_detected:
        failures.append(
            "OLD regex unexpectedly DETECTED the real migration gap -- "
            "expected it to be blind (both sides missing the code, so no "
            "diff), proving the described blind spot doesn't actually "
            "reproduce with these fixtures")

    # GREEN: with the CURRENT (post-fix) qa_check.py regexes, the digit-
    # bearing code IS captured from spec prose and the model block, and
    # its real absence from the migration block is correctly detected.
    new_spec = set(QC.REFUSAL_CODE_IN_PROSE_RE.findall(SPEC_PROSE))
    new_migration = set(QC.REFUSAL_CODE_LITERAL_RE.findall(MIGRATION_BLOCK))
    new_model = set(QC.REFUSAL_CODE_MODEL_LITERAL_RE.findall(MODEL_BLOCK))
    if "OAUTH2_TOKEN_EXPIRED" not in new_spec:
        failures.append(f"current REFUSAL_CODE_IN_PROSE_RE failed to capture the digit-bearing code from prose: {new_spec}")
    if "OAUTH2_TOKEN_EXPIRED" not in new_model:
        failures.append(f"current REFUSAL_CODE_MODEL_LITERAL_RE failed to capture the digit-bearing code: {new_model}")
    if "OAUTH2_TOKEN_EXPIRED" in new_migration:
        failures.append("current REFUSAL_CODE_LITERAL_RE captured a code that isn't in MIGRATION_BLOCK -- fixture bug")
    missing_from_migration = new_spec - new_migration
    if "OAUTH2_TOKEN_EXPIRED" not in missing_from_migration:
        failures.append(
            "current regexes did NOT detect the real gap (code present in "
            f"spec prose/model, absent from migration block): spec={new_spec} migration={new_migration}")

    # Sanity: the ordinary, non-digit codes still work identically old vs
    # new (no regression on the common case).
    if old_migration - {"OAUTH2_TOKEN_EXPIRED"} != new_migration - {"OAUTH2_TOKEN_EXPIRED"}:
        failures.append("non-digit code extraction diverged between old and new patterns -- unexpected")

    if failures:
        print("[test] FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("[test] PASS: current qa_check.py regexes catch a digit-bearing "
          "refusal code missing from one source; the pre-fix letters-only "
          "regexes were blind to it on all three sides (reproduced inline).")
    return 0


if __name__ == "__main__":
    sys.exit(run())
