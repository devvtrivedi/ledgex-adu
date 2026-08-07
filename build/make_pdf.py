#!/usr/bin/env python3
"""Render the presentation PDFs FROM the markdown files of record.

Chain:  ledgex_source.py  ->  docs/*.md  ->  dist/*.pdf

The PDF can no longer disagree with the markdown, because the PDF is made from
the markdown. This is what "one source" means in practice: there is exactly one
place to edit (ledgex_source.py for the invariant/target tables, text/*.txt for
the prose body), and everything downstream regenerates.

Requires pandoc. If pandoc is not installed the script says so and exits 0 —
the markdown is the file of record, so a missing PDF engine must never block
a build.
"""
import pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DIST = ROOT / "dist"

JOBS = [
    ("LEDGEX_SPEC.md", "LedgeX_Engineering_Reference_Spec_v1_11.pdf",
     "LedgeX / ADU.X — Engineering Reference Spec v1.11"),
    ("LEDGEX_RULES.md", "LedgeX_Implementation_Rules_v1_4.pdf",
     "LedgeX / ADU.X — Implementation Rules v1.4"),
]


def main():
    if not shutil.which("pandoc"):
        print("pandoc not found — skipping PDF render. "
              "The markdown in docs/ is the file of record and is complete.")
        return 0
    DIST.mkdir(exist_ok=True)
    for md_name, pdf_name, title in JOBS:
        src = DOCS / md_name
        if not src.exists():
            print(f"skip {md_name} — not built yet")
            continue
        dst = DIST / pdf_name
        # xelatex handles the box-drawing characters in the repository-layout
        # tree; pdflatex does not. Fall back only if xelatex is absent.
        engine = "xelatex" if shutil.which("xelatex") else "pdflatex"
        cmd = [
            "pandoc", str(src), "-o", str(dst),
            "--from", "gfm",
            f"--pdf-engine={engine}",
            "--metadata", f"title={title}",
            "--toc", "--toc-depth=2",
            "-V", "geometry:margin=2cm",
            "-V", "fontsize=9pt",
            "-V", "colorlinks=true",
            "-V", "monofont=DejaVu Sans Mono",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAILED {pdf_name}:\n{r.stderr[:800]}")
            return 1
        print(f"wrote dist/{pdf_name}  ({dst.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
