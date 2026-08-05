"""Shared prose converter: cleaned pdftotext -layout body -> markdown.
Imported by both builders so the conversion rules have one source too."""
import re

SEC   = re.compile(r"^\s*Section\s+(\d+)\s*[-–—]\s*(.+?)\s*$")
NSEC  = re.compile(r"^\s*(\d+)\s*/\s*(.+?)\s*$")            # Rules style: "2 / Six make targets"
SUB   = re.compile(r"^\s*(\d+\.\d+(?:\.\d+)?)\s+(\S.*?)\s*$")
ASUB  = re.compile(r"^\s*(A-1\.\d+)\s+(\S.*?)\s*$")
CAPS  = re.compile(r"^\s{2,}([A-Z][A-Z0-9 ,§&/'\-\.]{9,})\s*$")
SQLST = re.compile(r"^\s*(--|CREATE |ALTER |INSERT |DROP |COMMENT |WITH |SELECT |BEGIN;|COMMIT;|CREATE OR REPLACE)")
TRIGST = re.compile(r"^\s*CREATE\s+(CONSTRAINT\s+)?TRIGGER\b")
SQLIN = re.compile(r"^\s{4,}\S")
BULL  = re.compile(r"^\s*[•·]\s*(.+?)\s*$")
TREE  = re.compile(r"[├└│─┌┐┘┬┴┼]")          # repository-layout tree drawing
YAMLK = re.compile(r"^\s{2,}[a-z_]+:\s")      # sources.yaml / licences.yaml blocks


def _flush(buf, out, kind):
    if not buf:
        return
    while buf and not buf[-1].strip():
        buf.pop()
    if not buf:
        return
    if kind == "sql":
        out.append("```sql")
        out.extend(buf)
        out.append("```")
    elif kind == "pre":
        out.append("```text")
        out.extend(buf)
        out.append("```")
    out.append("")


def convert(text, drop_before=None):
    lines = text.split("\n")
    if drop_before is not None:
        for i, ln in enumerate(lines):
            if drop_before in ln:
                lines = lines[i:]
                break
    out, buf, kind = [], [], None
    # Inside a dollar-quoted function body (CREATE [OR REPLACE] FUNCTION ...
    # AS $$ ... $$ LANGUAGE ...), pdftotext -layout output has no reliable
    # indentation or keyword prefix — DECLARE, BEGIN, END; and bare "$$
    # LANGUAGE plpgsql;" all sit flush-left. Treating the region between an
    # odd and the next even count of "$$" as opaque keeps the whole function
    # in one fenced block instead of splitting on every line the SQLIN/SQLST
    # heuristics don't recognize.
    in_dollar_quote = False
    # A CREATE [CONSTRAINT] TRIGGER statement's own continuation lines (FOR
    # EACH ROW, EXECUTE FUNCTION ...) sit at inconsistent indentation in the
    # pdftotext -layout output — sometimes 2 spaces, sometimes 7 — so SQLIN's
    # fixed threshold misses some of them. Once such a statement has opened,
    # keep swallowing lines until its terminating ";" regardless of indent.
    # Scoped to this one unambiguous DDL keyword, not "any unterminated line",
    # so it can't run away into unrelated prose the way a generic
    # doesn't-end-in-";" heuristic did (see git history for that regression).
    in_trigger_stmt = False
    for raw in lines:
        ln = raw.rstrip()
        s = ln.strip()

        if kind == "sql":
            if in_dollar_quote:
                buf.append(ln)
                if ln.count("$$") % 2 == 1:
                    in_dollar_quote = False
                continue
            if in_trigger_stmt:
                buf.append(ln)
                if s.endswith(";"):
                    in_trigger_stmt = False
                continue
            if s == "" or SQLIN.match(ln) or SQLST.match(ln) or s in (");", ")", "$$;") or "$$" in ln:
                buf.append(ln)
                if ln.count("$$") % 2 == 1:
                    in_dollar_quote = True
                if TRIGST.match(ln) and not s.endswith(";"):
                    in_trigger_stmt = True
                continue
            _flush(buf, out, kind); buf, kind = [], None

        # Repository-layout tree: keep it preformatted or the shape is lost,
        # and the box-drawing characters break naive PDF engines.
        if kind == "pre":
            if s == "" and buf and not buf[-1].strip():
                _flush(buf, out, kind); buf, kind = [], None
            elif TREE.search(ln) or s == "" or ln.startswith("  "):
                buf.append(ln)
                continue
            else:
                _flush(buf, out, kind); buf, kind = [], None
        if TREE.search(ln):
            _flush(buf, out, kind); buf, kind = [], "pre"
            buf.append(ln)
            continue

        m = SEC.match(ln) or NSEC.match(ln)
        if m and len(m.group(2)) < 90:
            _flush(buf, out, kind); buf, kind = [], None
            out += [f"## {m.group(1)}. {m.group(2)}", ""]
            continue
        m = ASUB.match(ln)
        if m:
            _flush(buf, out, kind); buf, kind = [], None
            out += [f"### {m.group(1)} {m.group(2)}", ""]
            continue
        m = SUB.match(ln)
        if m and len(m.group(2)) < 90 and not s.endswith(","):
            _flush(buf, out, kind); buf, kind = [], None
            out += [f"### {m.group(1)} {m.group(2)}", ""]
            continue
        m = CAPS.match(ln)
        if m:
            _flush(buf, out, kind); buf, kind = [], None
            out += [f"> **{m.group(1).strip()}**", ""]
            continue
        m = BULL.match(ln)
        if m:
            _flush(buf, out, kind); buf, kind = [], None
            out.append(f"- {m.group(1)}")
            continue
        if SQLST.match(ln):
            _flush(buf, out, kind); buf, kind = [], "sql"
            buf.append(ln)
            if ln.count("$$") % 2 == 1:
                in_dollar_quote = True
            if TRIGST.match(ln) and not s.endswith(";"):
                in_trigger_stmt = True
            continue
        if s == "":
            _flush(buf, out, kind); buf, kind = [], None
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(s)

    _flush(buf, out, kind)
    md = "\n".join(out)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"
