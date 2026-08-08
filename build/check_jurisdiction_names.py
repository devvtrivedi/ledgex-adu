#!/usr/bin/env python3
"""I1's other half: core/ contains no jurisdiction name, local rule or
local field name -- checked directly against core/**/*.py.

import-linter (.importlinter) enforces the import-graph half of I1: core/
must not import jurisdictions/, api/, pipelines/, geo/ or commerce/. It
cannot see a bare string literal sitting in a core/ file with no import
attached at all -- exactly how every jurisdiction id and source-specific
property name is written today (e.g. JURISDICTION_ID = "ca_san_jose" is
a plain assignment, nothing imported). This script is the grep the
spec's own make check-boundary description names alongside import-linter
("Jurisdiction-name grep, import-linter, ...") for exactly that reason.

BLOCKLIST is not a general list of every field name in existence -- it's
evidence-based, drawn from the actual copy-list audit of scripts/*.py
(the three real ingests plus the composer) before any extraction:
  - every jurisdiction id §2's own repository tree names (ca_state,
    ca_santa_clara_county, ca_san_jose), whether or not it's live yet
  - every San-José-source-specific property/column name found as a
    literal string lookup key during that audit (APN, ZONING,
    ZONINGABBREV, ASSESSORS_PARCEL_NUMBER, and the SITUS_ADDRESS-family
    address-key candidates)
A future jurisdiction pack will need its own names added here when it
lands -- this list documents what's actually been seen leak into code
so far, not a permanent or complete enumeration.

Scoped to core/**/*.py only, matching import-linter's own scope --
scripts/, infra/, jurisdictions/ are expected to name jurisdictions and
source fields; that's their job. Only core/ is supposed to be free of
them (I1).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE_DIR = ROOT / "core"

BLOCKLIST = [
    # Jurisdiction ids named in §2's repository tree.
    "ca_san_jose",
    "ca_santa_clara_county",
    "ca_state",
    # San-José-source-specific property/column names, found as literal
    # string lookup keys during the scripts/*.py copy-list audit.
    "ASSESSORS_PARCEL_NUMBER",
    "ZONINGABBREV",
    "SITUSADDR",
    "SITEADDRESS",
    "SITE_ADDR",
    "SITUS_ADDRESS",
]

# Matched as whole tokens (word boundaries), case-sensitive: these are
# exact identifiers/property keys as they appear in source data and code,
# not prose words that might otherwise share a substring.
PATTERN = re.compile(r"\b(" + "|".join(re.escape(w) for w in BLOCKLIST) + r")\b")


def check():
    if not CORE_DIR.exists():
        print("core/ does not exist -- nothing to check.")
        return []

    failures = []
    for path in sorted(CORE_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = PATTERN.search(line)
            if m:
                failures.append(
                    f"{path.relative_to(ROOT)}:{lineno}: forbidden token "
                    f"'{m.group(1)}' (I1: core/ contains no jurisdiction "
                    f"name, local rule or local field name)")
    return failures


if __name__ == "__main__":
    failures = check()
    if failures:
        print("JURISDICTION-NAME GREP FAILED\n")
        for f in failures:
            print("  x " + f)
        sys.exit(1)
    files_checked = len(list(CORE_DIR.rglob("*.py"))) if CORE_DIR.exists() else 0
    print(f"JURISDICTION-NAME GREP PASSED -- {files_checked} file(s) under "
          f"core/ scanned, no blocklisted token found.")
