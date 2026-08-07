#!/usr/bin/env python3
"""Render website/spec.html and website/rules.html FROM the markdown files of
record.

Chain:  ledgex_source.py  ->  docs/*.md  ->  website/*.html

Before this script existed, website/spec.html and website/rules.html were a
pandoc run performed once by hand on 2026-08-03 and pasted into the site
shell, then never regenerated. docs/LEDGEX_RULES.md and docs/LEDGEX_SPEC.md
were both fixed on 2026-08-04/05 (mangled invariant prose, duplicate
make-targets table); the website pages kept publishing the pre-fix text for
two weeks because nothing rebuilt them and qa_check.py only ever read
docs/*.md. This script is the fix for the class, not just that instance:
website/*.html now has a reproducible source, `make site` regenerates it, and
qa_check.py's check_website_current (see build/qa_check.py) fails the gate if
the committed HTML doesn't match what this script produces from the current
docs.

Requires pandoc, and -- unlike build/make_pdf.py's PDF, which is an optional
presentation artifact -- does NOT no-op if pandoc is missing: a missing
website source of truth is not an acceptable steady state the way a missing
PDF is, so this fails loudly instead. Same operational consequence as
`make schema`/`schema-dump` requiring a reachable PostgreSQL 16 instance --
an environment dependency that must be present for this target (and for the
qa gate that checks it) to run at all.

The exact pandoc invocation (-f gfm -t html --wrap=none) was reverse-derived
from the committed HTML's own header-id slug scheme
(id="ledgex--adux--...", which only pandoc's gfm reader produces) and its
un-wrapped paragraph lines (max line length in the committed files is in the
thousands of characters, which only happens with --wrap=none) -- chosen to
match what was there, not invented fresh. Different pandoc versions are
known to change output byte-for-byte (header-id slugification in particular
has changed across pandoc releases); if `make site` and `make qa` disagree
about whether website/*.html is current, check `pandoc --version` first
before assuming the content actually changed.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
WEBSITE = ROOT / "website"

# (source markdown, output HTML, <title> text). Title is a literal, not
# parsed from the doc's own H1, matching build/make_pdf.py's JOBS convention
# -- bump it in the same commit that bumps the version in ledgex_source.py.
JOBS = [
    ("LEDGEX_SPEC.md", "spec.html", "Engineering Reference Spec v1.14"),
    ("LEDGEX_RULES.md", "rules.html", "Implementation Rules v1.4"),
]

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — LedgeX</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <nav class="navbar">
        <div class="container">
            <h1 class="logo">LedgeX</h1>
            <ul class="nav-links">
                <li><a href="index.html">Home</a></li>
                <li><a href="spec.html">Engineering Spec</a></li>
                <li><a href="rules.html">Implementation Rules</a></li>
            </ul>
        </div>
    </nav>

    <div class="doc-content">
{body}
    </div>

    <footer class="footer">
        <p>&copy; 2026 Veritas Land Consultants Inc. | <a href="mailto:hello@ledgexproperties.com">Contact</a></p>
    </footer>
</body>
</html>
"""


def render_fragment(md_path: pathlib.Path) -> str:
    cmd = ["pandoc", str(md_path), "-f", "gfm", "-t", "html", "--wrap=none"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"pandoc failed on {md_path.name}:\n{r.stderr}")
    return r.stdout.rstrip("\n")


def render_page(md_name: str, title: str) -> str:
    """Full HTML file content for one page, rendered fresh from docs/{md_name}.

    Imported by build/qa_check.py's check_website_current, the same way
    check_regenerates_clean imports build_spec_v1_14.render_md() -- one
    render function, called from both the writer and the gate, so they
    can never independently drift from each other.
    """
    src = DOCS / md_name
    body = render_fragment(src)
    return TEMPLATE.format(title=title, body=body)


def main() -> int:
    if not shutil.which("pandoc"):
        print("pandoc not found -- website/*.html NOT regenerated. "
              "Install pandoc; unlike the PDF, the website has no other "
              "source of truth to fall back to.", file=sys.stderr)
        return 1

    for md_name, html_name, title in JOBS:
        src = DOCS / md_name
        if not src.exists():
            print(f"FAILED: {src} does not exist", file=sys.stderr)
            return 1
        dst = WEBSITE / html_name
        dst.write_text(render_page(md_name, title), encoding="utf-8")
        print(f"wrote {dst.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
