#!/usr/bin/env python3
"""Document QA — the drift gate.

Spec v1.16 sec 0.2: "Document QA fails if any invariant body or enforcement cell
differs." This script is that check. Wire it into `make check-boundary`.

It asserts:
  1. Every invariant in ledgex_source.INVARIANTS appears verbatim in BOTH
     docs/LEDGEX_SPEC.md and docs/LEDGEX_RULES.md.
  2. Every make target appears verbatim in both.
  3. Neither markdown file contains a second, differing copy of an invariant ID
     row (a copied table).
  4. The generated markdown is current — regenerating produces no diff.
  5. website/spec.html and website/rules.html are current — regenerating via
     build_website.py produces no diff. Added after website/rules.html was
     found publishing two-week-stale, pre-fix content (mangled invariant
     prose, a duplicate make-targets table) that this gate never saw because
     it only read docs/*.md. Requires pandoc; see build/build_website.py.
  6. Every "Engineering Reference Spec vX.Y" / "Implementation Rules vX.Y"
     string in ANY website/*.html — not just the two check 5 regenerates —
     matches ledgex_source.SPEC_VERSION / RULES_VERSION. Added after
     website/index.html (hand-authored, not covered by check 5) was found
     still reading "v1.7" after the spec bumped to v1.8: the same
     one-layer-out blind spot as check 5 closed, one layer further out.
  7. Every db/migrations/*.sql file is named at least once in
     docs/LEDGEX_SPEC.md, and every migration filename the spec names exists
     on disk. Added when §3 stopped restating DDL (v1.9): §3 used to carry a
     full copy of each migration's SQL, which had drifted from the real
     migrations in six places and was invisible to this gate, because it
     only ever checked regeneration fidelity against the source .txt, never
     parity against db/migrations. A text-diff parity check was rejected —
     §3's SQL was pdftotext-mangled prose, and diffing that against real
     migrations would be unmaintainable noise. This is the cheap structural
     replacement: it can't verify DDL content matches, but it can catch a
     migration added without a spec pointer, or a spec pointer to a file
     that was renamed or never written.

Exit code 0 = pass, 1 = fail.
"""
import pathlib, re, sys, subprocess

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ledgex_source as S
import build_website as W

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


def _prefix(text, n):
    """First n whitespace-normalized words of text."""
    return " ".join(norm(text).split(" ")[:n])


def check_no_mangled_invariant_prose():
    """The corrupted-appendix bug: a prose-format duplicate of an invariant or
    make-target row (its ID/name immediately followed by its own body/surface
    text, outside the canonical '| **ID** | ... |' markdown table) leaking
    into a generated doc because a convert() call's drop_before anchor didn't
    cut far enough. check_no_duplicate_table() only sees the pipe-table
    format and would count each row once, missing this second copy entirely.

    v1 of this check fingerprinted on the FULL verbatim body text, which is
    fragile: pdftotext -layout column-wraps long cells, so the tail of a
    duplicated row's text often doesn't match the canonical string
    byte-for-byte even though the row is clearly the same duplicate (an
    audit against real fixtures found this missed most real instances — the
    full-text needle almost never survives layout wrapping intact). The
    words immediately after the ID/name are far more stable than the tail,
    so we fingerprint on a short prefix instead:
      - invariants: "<ID> <first 6 words of body>"
      - make targets: "<target> <first N words of execution surface>" for
        N in 3..7 — targets have only 6 rows and a narrower table, so a
        single fixed N is more likely to land mid-wrap; sweeping a small
        range costs nothing and catches it regardless of exactly where that
        row's wrap point fell.

    Neither needle can occur in the canonical row: it renders as
    "**ID** | body" / "**target** | surface", with "** | " between the two
    fields, never a single space — but both occur verbatim in the mangled
    prose form.
    """
    for path in (SPEC, RULES):
        if not path.exists():
            continue
        flat = norm(path.read_text(encoding="utf-8"))

        for iid, body, enf in S.INVARIANTS:
            needle = f"{iid} {_prefix(body, 6)}"
            if needle in flat:
                failures.append(
                    f"{path.name}: prose-mangled duplicate of {iid} found "
                    f"outside the canonical table — a drop_before anchor is "
                    f"not cutting the corrupted appendix source block")

        for tgt, surface, cond in S.MAKE_TARGETS:
            if any(f"{tgt} {_prefix(surface, n)}" in flat for n in range(3, 8)):
                failures.append(
                    f"{path.name}: prose-mangled duplicate of '{tgt}' found "
                    f"outside the canonical table — a drop_before anchor is "
                    f"not cutting the corrupted appendix source block")


def check_regenerates_clean():
    """Rebuild into memory and compare. Catches hand-edited markdown."""
    import importlib
    for mod_name, path in (("build_spec_v1_16", SPEC), ("build_rules_v1_4", RULES)):
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


def check_website_current():
    """website/*.html must match what build_website.render_page() produces
    from the current docs/*.md right now. Same shape as
    check_regenerates_clean, one layer further out: that check catches
    hand-edited or stale markdown; this one catches a website that fell out
    of sync with markdown that WAS correctly regenerated, because nothing
    rebuilt the HTML. No date line to strip here — render_page() doesn't
    call datetime.today() itself, it only passes through whatever
    "Generated {date}" text is already baked into the source markdown, so a
    genuine byte-for-byte comparison is correct, not just close enough.

    Fails loudly, not silently, if pandoc is missing: an unverifiable
    website is not the same as a verified-current one, and this check
    exists specifically so staleness can't sit unnoticed.
    """
    import shutil
    if not shutil.which("pandoc"):
        failures.append(
            "website/*.html: cannot verify -- pandoc not found. Install "
            "pandoc; this check does not pass silently without it.")
        return
    for md_name, html_name, title in W.JOBS:
        html_path = ROOT / "website" / html_name
        if not html_path.exists():
            failures.append(f"MISSING ARTIFACT: website/{html_name}")
            continue
        try:
            fresh = W.render_page(md_name, title)
        except Exception as e:  # pragma: no cover
            failures.append(f"website/{html_name}: build_website failed ({e})")
            continue
        on_disk = html_path.read_text(encoding="utf-8")
        if fresh != on_disk:
            failures.append(
                f"website/{html_name}: on-disk file differs from "
                f"build_website.py output -- stale or hand-edited. Run "
                f"`make site`.")


SPEC_TITLE_RE = re.compile(r"Engineering Reference Spec v(\d+\.\d+)")
RULES_TITLE_RE = re.compile(r"Implementation Rules v(\d+\.\d+)")


def check_website_version_strings():
    """Every 'Engineering Reference Spec vX.Y' / 'Implementation Rules vX.Y'
    string in ANY website/*.html must match ledgex_source.SPEC_VERSION /
    RULES_VERSION -- not just spec.html/rules.html, which check_website_current
    already regenerates byte-for-byte. index.html is hand-authored, so
    check_website_current can't see it; this check reads every website/*.html
    file directly and doesn't care whether a page has a generator, closing
    that blind spot one layer further out than check_website_current closed
    the docs/*.md one.
    """
    website_dir = ROOT / "website"
    for html_path in sorted(website_dir.glob("*.html")):
        text = html_path.read_text(encoding="utf-8")
        for m in SPEC_TITLE_RE.finditer(text):
            found = m.group(1)
            if found != S.SPEC_VERSION:
                failures.append(
                    f"{html_path.relative_to(ROOT)}: says 'Engineering "
                    f"Reference Spec v{found}', current SPEC_VERSION is "
                    f"v{S.SPEC_VERSION}")
        for m in RULES_TITLE_RE.finditer(text):
            found = m.group(1)
            if found != S.RULES_VERSION:
                failures.append(
                    f"{html_path.relative_to(ROOT)}: says 'Implementation "
                    f"Rules v{found}', current RULES_VERSION is "
                    f"v{S.RULES_VERSION}")


MIGRATIONS_DIR = ROOT / "db" / "migrations"
MIGRATION_NAME_RE = re.compile(r"\b(\d{4}_[A-Za-z0-9_]+\.sql)\b")


def check_spec_references_migrations():
    """§3 no longer restates DDL (v1.9) -- replaces that deleted duplication
    with something cheap instead of a text-diff parity check against
    db/migrations, which would be unmaintainable noise against §3's
    pdftotext-mangled prose:
      - every db/migrations/*.sql file must be named at least once in
        docs/LEDGEX_SPEC.md
      - every migration filename the spec names must exist on disk
    Can't verify DDL content matches -- only that the pointer exists and
    resolves. Catches a migration added without a spec pointer, and a spec
    pointer to a file that was renamed or never written.
    """
    if not SPEC.exists():
        return  # already reported by check_presence

    on_disk = {p.name for p in MIGRATIONS_DIR.glob("*.sql")}
    spec_text = SPEC.read_text(encoding="utf-8")
    mentioned = set(MIGRATION_NAME_RE.findall(spec_text))

    missing_from_spec = sorted(on_disk - mentioned)
    if missing_from_spec:
        failures.append(
            f"LEDGEX_SPEC.md: migration(s) on disk but never referenced in "
            f"the spec: {', '.join(missing_from_spec)}")

    phantom_in_spec = sorted(mentioned - on_disk)
    if phantom_in_spec:
        failures.append(
            f"LEDGEX_SPEC.md: spec references migration file(s) that do not "
            f"exist on disk: {', '.join(phantom_in_spec)}")


if __name__ == "__main__":
    check_presence()
    check_no_duplicate_table()
    check_no_mangled_invariant_prose()
    check_regenerates_clean()
    check_website_current()
    check_website_version_strings()
    check_spec_references_migrations()
    if failures:
        print("DOCUMENT QA FAILED\n")
        for f in failures:
            print("  x " + f)
        sys.exit(1)
    print(f"DOCUMENT QA PASSED — {len(S.INVARIANTS)} invariants and "
          f"{len(S.MAKE_TARGETS)} make targets verbatim in both artifacts; "
          f"no copied tables; markdown current; website/*.html current; "
          f"no stale version strings anywhere in website/*.html; every "
          f"migration referenced and resolvable.")
