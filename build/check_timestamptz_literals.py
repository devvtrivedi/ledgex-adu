#!/usr/bin/env python3
"""P60-4(d)/(e): static check for the timezone class -- a bare
'YYYY-MM-DD'::timestamptz (or 'YYYY-MM-DD HH:MM:SS'::timestamptz with no
explicit UTC offset) literal in db/seeds/ or db/migrations/. Postgres
resolves such a literal at the CONNECTING SESSION's local midnight, not a
fixed UTC instant -- the same real instant renders/compares differently
depending on the applying session's own TimeZone. Three confirmed
instances before this check existed: C7 (rule.effective_from/to), AD1
(scripts/check_golden.py's own golden seed), and db/seeds/day4_sources.sql
(P60-4(a), fixed in the same pass that added this check). Modelled
directly on build/check_jurisdiction_names.py's own shape (WORD_SEQUENCES
-> a single regex; GRANDFATHERED -> the same exact-site, staleness-checked
exemption mechanism; same print-every-run-pass-or-fail discipline) -- not
a new pattern, reuse of an already-established one.

Scope: db/seeds/**/*.sql and db/migrations/**/*.sql only -- the two
places a literal actually gets applied to a real database. Application
code (scripts/*.py) constructs timestamps in Python, not as bare SQL
literals, and is out of this check's scope.

The fix (day4_sources.sql, P60-4(a)) is to give every such literal an
explicit UTC offset (e.g. 'YYYY-MM-DDT00:00:00+00'::timestamptz) --
unambiguous regardless of the connecting session's TimeZone. This check
flags any literal that does NOT already carry one.

WHAT THIS CANNOT CATCH, STATED HONESTLY (same discipline
check_jurisdiction_names.py's own module docstring uses): a timestamp
value built by string concatenation or passed as a bind parameter from
Python is invisible to this line-by-line static grep -- it only sees a
literal `'...'::timestamptz` cast written directly in a .sql file. Also
does not flag bare `timestamp` (no time zone) or `date` literals with no
`::timestamptz` cast at all -- those have their own, different (and
already-correct-by-construction, since they carry no zone to begin with)
semantics, out of this check's own stated scope.

Exit code 0 = PASS (green). Exit code 1 = FAIL (red).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN_DIRS = (ROOT / "db" / "seeds", ROOT / "db" / "migrations")

# Matches the literal content of a '...'::timestamptz cast (single-quoted,
# no embedded quote -- true of every real literal in this codebase; a
# literal SQL-escaped '' inside the string would need a different capture,
# not present anywhere in db/seeds/ or db/migrations/ today).
LITERAL_CAST = re.compile(r"'([^']*)'::timestamptz")

# A literal is SAFE (has an explicit UTC offset) if, after the date and
# optional time-of-day, it ends in Z or a signed HH[:MM] offset. Anything
# else -- bare date, or date+time with no offset -- is the bug shape.
HAS_EXPLICIT_OFFSET = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?"
    r"(?:Z|[+-]\d{2}(?::?\d{2})?)$"
)

# 'infinity'/'-infinity'::timestamptz are Postgres's own special sentinel
# values ("later than every other timestamp"/"earlier than every other
# timestamp") -- not a date at all, and not session-timezone-dependent by
# construction (found live: db/migrations/0041_licence_channel_created_at_
# not_null.sql's own three uses, a real false positive against the naive
# check before this exemption was added).
SPECIAL_SENTINELS = {"infinity", "-infinity"}


def _sql_files():
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        yield from sorted(d.rglob("*.sql"))


def check():
    failures = []
    grandfathered_seen = set()

    for path in _sql_files():
        relpath = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            # A `--` line comment is prose, not applied SQL -- this check's
            # job is real literals a database will actually evaluate, same
            # "not a P59B-style implied guarantee beyond its actual scope"
            # discipline check_jurisdiction_names.py's own docstring states
            # for its own gaps. A line-comment-only check (not a full SQL
            # tokenizer) is enough: no real timestamptz literal in this
            # codebase today shares a line with a trailing `--` comment.
            if line.lstrip().startswith("--"):
                continue
            for m in LITERAL_CAST.finditer(line):
                literal = m.group(1)
                if literal.lower() in SPECIAL_SENTINELS:
                    continue  # not a date -- see SPECIAL_SENTINELS' own comment
                if HAS_EXPLICIT_OFFSET.match(literal):
                    continue  # unambiguous -- not the bug shape
                key = (relpath, lineno, literal)
                if key in GRANDFATHERED:
                    grandfathered_seen.add(key)
                    continue
                failures.append(
                    f"{relpath}:{lineno}: bare timestamptz literal "
                    f"'{literal}'::timestamptz has no explicit UTC offset -- "
                    f"resolves at the applying session's local midnight, not "
                    f"a fixed instant. Use 'YYYY-MM-DDT00:00:00+00'::"
                    f"timestamptz (or equivalent) instead.")

    stale = GRANDFATHERED - grandfathered_seen
    for relpath, lineno, literal in sorted(stale):
        failures.append(
            f"{relpath}:{lineno}: STALE GRANDFATHER ENTRY -- "
            f"'{literal}'::timestamptz no longer matches at this line. "
            f"Either the violation was fixed (remove this entry from "
            f"GRANDFATHERED) or it moved (update the line number) -- an "
            f"exemption must never outlive what it exempts.")

    return failures, grandfathered_seen


# GRANDFATHERED (P60-4(d)/(e)): exact (relative_path, line, literal)
# triples for the two landed, forward-only migrations already known to
# carry this defect -- see db/README.md's own "Known timezone-literal
# defects in landed migrations" section (P60-4(c)) for the full record of
# each, including current remediation status. NOT a directory or pattern
# exemption -- exact sites only; any NEW bare-literal site, in these files
# or any other, still fails. A migration body can never be hand-edited
# (forward-only, §3.13), so these two sites can only ever be resolved by
# a later correcting migration (mutable tables) or a rebuild (immutable
# tables) -- never by editing this list's own target lines.
GRANDFATHERED = {
    ("db/migrations/0023_correct_seeded_endpoint_urls.sql", 41, "2026-08-06"),
    ("db/migrations/0023_correct_seeded_endpoint_urls.sql", 49, "2026-08-06"),
    ("db/migrations/0056_l0_gate_boundary_source.sql", 135, "2026-08-22"),
}


if __name__ == "__main__":
    failures, grandfathered_seen = check()

    print(f"GRANDFATHERED (pre-existing, exact-site only) -- {len(GRANDFATHERED)} entr"
          f"{'y' if len(GRANDFATHERED) == 1 else 'ies'}:")
    for relpath, lineno, literal in sorted(GRANDFATHERED):
        seen_mark = "OK" if (relpath, lineno, literal) in grandfathered_seen else "STALE"
        print(f"  [{seen_mark}] {relpath}:{lineno} '{literal}'::timestamptz")
    print()

    if failures:
        print("TIMESTAMPTZ-LITERAL GREP FAILED\n")
        for f in failures:
            print("  x " + f)
        sys.exit(1)
    files_checked = len(list(_sql_files()))
    print(f"TIMESTAMPTZ-LITERAL GREP PASSED -- {files_checked} file(s) under "
          f"db/seeds/ and db/migrations/ scanned, no bare timestamptz literal "
          f"found outside the {len(GRANDFATHERED)} grandfathered site(s) above.")
