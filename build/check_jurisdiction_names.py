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
  - the human-readable city name (San Jose, San José), since I1's own
    text ("no jurisdiction name") is not limited to identifier-shaped
    tokens -- a docstring or comment naming the city in prose leaks the
    same information a literal "ca_san_jose" does, and grep for the
    identifier alone would miss it
A future jurisdiction pack will need its own names added here when it
lands -- this list documents what's actually been seen leak into code
so far, not a permanent or complete enumeration.

CORRECTED, not written correctly the first time: this module's own
docstring already claimed "APN, ZONING" were in BLOCKLIST below when
they were not -- only the compound forms (ASSESSORS_PARCEL_NUMBER,
ZONINGABBREV) were ever actually in the list, and San Jose/San José in
either script were never in it at all. Confirmed directly, not assumed,
before writing the fix: all four -- bare APN, bare ZONING, "San Jose",
"San José" -- ran against the list as it stood and matched nothing.
Proven capable of catching each individually (planted, confirmed RED,
reverted) before trusting this comment to describe the list again.

Scoped to core/**/*.py only, matching import-linter's own scope --
scripts/, infra/, jurisdictions/ are expected to name jurisdictions and
source fields; that's their job. Only core/ is supposed to be free of
them (I1).
"""
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE_DIR = ROOT / "core"

# C6 (P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): each entry is a WORD
# SEQUENCE, not a literal string -- _pattern_for() below joins the words
# with a flexible, optional separator ([\s_-]*, case-insensitive) so
# "ca_san_jose", "ca-san-jose", "ca san jose" and "caSanJose" all match the
# SAME compiled pattern (IGNORECASE makes the case transition inside
# "caSanJose" invisible to the matcher; the zero-width separator handles
# the no-separator camelCase/concatenated case). Single-word entries
# (APN, ZONING, ...) go through the identical builder for one consistent
# code path, not a special case.
WORD_SEQUENCES = [
    # Jurisdiction ids named in §2's repository tree, plus their bare
    # (no "ca_" prefix) city/county-name-only forms -- probed directly and
    # confirmed missing from the pre-fix blocklist (audit: "bare 'san_jose'
    # ... all pass").
    ("ca", "san", "jose"),
    ("san", "jose"),
    ("ca", "santa", "clara", "county"),
    ("santa", "clara"),
    ("ca", "state"),
    # The human-readable city name, in prose -- I1 forbids the
    # jurisdiction name, not just its identifier form. "san jose" above
    # already covers this under IGNORECASE + flexible separator (a plain
    # space IS one of the allowed separators) -- kept as an explicit
    # comment, not a redundant second entry, so a future reader does not
    # wonder where "San Jose" prose is caught.
    #
    # San-José-source-specific property/column names, found as literal
    # string lookup keys during the scripts/*.py copy-list audit.
    ("apn",),
    ("zoning",),
    ("assessors", "parcel", "number"),
    ("zoning", "abbrev"),
    ("situs", "addr"),
    ("site", "address"),
    ("site", "addr"),
    ("situs", "address"),
]


def _strip_diacritics(s):
    """A-N6 (P59C): the pattern builder's literal ASCII words ("jose") never
    matched an accented "José" -- the accent is a genuinely different
    character (U+00E9 vs 'e'), not a case difference IGNORECASE can fold,
    and the trailing \\b boundary compounded it (a \\b right after plain
    'e' asserts nothing useful once the actual next character is 'é').
    Rather than hand-list an accented variant per word (which only ever
    covers the specific accents someone thought to add), NFKD-decompose
    each character to base-letter + combining marks and drop every
    combining mark (Unicode category Mn) before matching -- "José" becomes
    "Jose" the same way "jose" already is, so the EXISTING ASCII-only
    WORD_SEQUENCES entries catch it with no separate accented entry
    needed, and any future accented name (not just this one) is covered
    the same way. Applied to the whole line before matching, not per-word,
    since NFKD decomposition can change a string's length (one accented
    character can become base + combining mark, two characters) -- a
    failure's reported token and its GRANDFATHERED key both come from the
    stripped line (a real match still names the actual forbidden word, in
    its unaccented ASCII form, and the file/line number pinpoint the
    accented source unambiguously -- reporting the exact accented glyph is
    not needed for a human to find and fix the violation)."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if unicodedata.category(c) != "Mn"
    )


def _pattern_for(words):
    # \b at the outer edges only -- internal boundaries between words are
    # the flexible separator itself, not \b, precisely so a zero-width
    # (camelCase/concatenated) join still matches.
    body = r"[\s_-]*".join(re.escape(w) for w in words)
    return re.compile(r"\b" + body + r"\b", re.IGNORECASE)


COMPILED = [(seq, _pattern_for(seq)) for seq in WORD_SEQUENCES]

# Data-file extensions scanned in addition to *.py (C6 acceptance (b)):
# a jurisdiction lookup table dropped as a non-.py file was invisible to
# both this grep and import-linter before this pass. Binary/generated
# artifacts are deliberately excluded (nothing under core/ is expected to
# be one; if that changes, this list is the place to extend, not a reason
# to widen the glob to "every file").
DATA_EXTENSIONS = (".json", ".yaml", ".yml", ".sql", ".txt")

# WHAT THIS STILL CANNOT CATCH, STATED HONESTLY (C6 acceptance (c), not an
# implied guarantee): runtime string construction -- e.g. "ca_" + "san_jose"
# as two separate literals concatenated at execution time -- produces no
# single line containing the forbidden compound, so this line-by-line
# static grep cannot see it, by construction. No case-insensitivity or
# separator-flexibility closes that gap; only a data-flow/taint analysis
# could, and this script is not one. I1's CI enforcement is therefore
# narrower than I1's own text ("a violation should be impossible") --
# recorded here, not left as an implied guarantee this script does not
# back.


# GRANDFATHERED (C6, P59, LEDGEX-P58-PRE-MAP-AUDIT-REPORT.md): exact
# (relative_path, line, matched_token) triples for pre-existing violations
# this widening pass caught for real, run against the real tree, per
# CONVENTIONS' own requirement -- not hidden by narrowing the pattern
# (CONVENTIONS forbids weakening a check to make something pass). This is
# NOT a directory or pattern exemption -- exact sites only, and a NEW
# occurrence of any of these tokens anywhere else still fails. Every entry
# below carries the new finding it belongs to (deliverable §f of the P59
# pass that discovered it, not yet a numbered register finding) and a
# one-line reason. A grandfathered site whose line no longer contains its
# recorded token is itself a failure (STALE ENTRY, printed as such) --
# an exemption that outlives its violation is exactly the kind of
# self-certifying claim this repo has already found rotting twice
# (teardown.sql's "confirmed directly", 0056's "TRUE no-op").
#
# core/model.py's Parcel.apn / Parcel.situs_address, and core/store.py's /
# core/exceptions.py's own docstring references to `.apn` -- a real,
# pre-existing I1 violation the case-sensitivity bug in this script was
# concealing (bare uppercase "APN" was already deliberately blocklisted;
# see this module's own "CORRECTED" docstring paragraph above). Whether
# "apn" is a local (San-José-specific) field name or portable US-assessor
# domain vocabulary for I1's purposes is an open question, put to the
# owner in this pass's own deliverable, not resolved here by removing the
# match. 0035_parcel_source_parcel_id_field.sql shows this repo already
# has a working precedent for a jurisdiction-neutral name at the schema
# layer (field_key "parcel.source_parcel_id", not "parcel.PARCELID") --
# renaming core/model.py's fields is a real, separate, cross-cutting
# refactor (touches core/, api/, scripts/, possibly the API wire
# contract), out of scope for this pass.
GRANDFATHERED = {
    # Line numbers updated (P59, later in the same pass): C24.4 shifted
    # core/exceptions.py, C24.8 shifted core/model.py -- caught by this
    # very staleness check when make check-boundary was run as part of
    # the D10/D18 spec-amendment sweep. Content re-verified unchanged at
    # the new positions before updating (same docstring/field-definition
    # sites, not new violations).
    ("core/exceptions.py", 210, "apn"),
    ("core/exceptions.py", 230, "apn"),
    # B1 (P59C): shifted from 541/542/556/557 -- core/model.py grew 31
    # lines earlier in the file (Refusal.detail's MappingProxyType fix).
    # Content re-verified unchanged at the new positions before updating
    # (same Parcel docstring / field declarations, not new violations) --
    # same discipline the P59 shift above this one already used.
    ("core/model.py", 572, "apn"),
    ("core/model.py", 573, "apn"),
    ("core/model.py", 587, "apn"),
    ("core/model.py", 588, "situs_address"),
    ("core/store.py", 12, "apn"),
    ("core/store.py", 19, "apn"),
}


def check():
    if not CORE_DIR.exists():
        print("core/ does not exist -- nothing to check.")
        return [], set()

    failures = []
    grandfathered_seen = set()
    paths = sorted(
        p for p in CORE_DIR.rglob("*")
        if p.is_file() and (p.suffix == ".py" or p.suffix in DATA_EXTENSIONS)
    )
    for path in paths:
        relpath = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            # A-N6: match against the diacritic-stripped line (see
            # _strip_diacritics' own docstring) -- "San José" and "San Jose"
            # both reach the same ASCII-only WORD_SEQUENCES patterns below.
            search_line = _strip_diacritics(line)
            for seq, pattern in COMPILED:
                m = pattern.search(search_line)
                if m:
                    key = (relpath, lineno, m.group(0).lower())
                    if key in GRANDFATHERED:
                        grandfathered_seen.add(key)
                        continue
                    failures.append(
                        f"{relpath}:{lineno}: forbidden token "
                        f"'{m.group(0)}' (matches word sequence {seq!r}; I1: "
                        f"core/ contains no jurisdiction name, local rule or "
                        f"local field name)")

    stale = GRANDFATHERED - grandfathered_seen
    for relpath, lineno, token in sorted(stale):
        failures.append(
            f"{relpath}:{lineno}: STALE GRANDFATHER ENTRY -- '{token}' no "
            f"longer matches at this line. Either the violation was fixed "
            f"(remove this entry from GRANDFATHERED) or it moved (update "
            f"the line number) -- an exemption must never outlive what it "
            f"exempts.")

    return failures, grandfathered_seen


if __name__ == "__main__":
    failures, grandfathered_seen = check()

    # Printed every run, pass or fail -- same coverage-honesty discipline
    # make test/make golden/make viewer-test already use: a grandfather
    # list nobody has to go looking for is a list that stays accurate.
    print(f"GRANDFATHERED (pre-existing, exact-site only) -- {len(GRANDFATHERED)} entr"
          f"{'y' if len(GRANDFATHERED) == 1 else 'ies'}:")
    for relpath, lineno, token in sorted(GRANDFATHERED):
        seen_mark = "OK" if (relpath, lineno, token) in grandfathered_seen else "STALE"
        print(f"  [{seen_mark}] {relpath}:{lineno} '{token}'")
    print()

    if failures:
        print("JURISDICTION-NAME GREP FAILED\n")
        for f in failures:
            print("  x " + f)
        sys.exit(1)
    files_checked = (
        len([p for p in CORE_DIR.rglob("*") if p.is_file() and (p.suffix == ".py" or p.suffix in DATA_EXTENSIONS)])
        if CORE_DIR.exists() else 0
    )
    print(f"JURISDICTION-NAME GREP PASSED -- {files_checked} file(s) under "
          f"core/ scanned (.py + {DATA_EXTENSIONS}), no blocklisted token found "
          f"outside the {len(GRANDFATHERED)} grandfathered site(s) above.")
