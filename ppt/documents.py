"""
Uploaded documents as material: Word (.docx), PDF and Excel (.xlsx) files read into text sections and tables, each
with a reference the deck and the report cite as their source, so every fact can be checked:

    Plan.docx > Market overview          a Word section (the text under a heading)
    Plan.docx > Table 2                  a Word table
    Results.pdf > page 3                 a PDF page (and "Results.pdf > page 3 > table 1")
    Metrics.xlsx > Adoption > A1:E9      a block of cells on an Excel sheet

    read_all(paths, log) -> {"files": [...], "sections": [...], "tables": [...], "warnings": [...]}   (docs.json)
    for_writer(docs) -> what the AI gets ("documents"), within a word budget
    texts(docs) -> the documents as plain text: what the facts are checked against

Tables keep the cells' values as the file shows them (Excel number formats: currency, percentages, thousands), so a
figure on a slide or in the report is a figure the file states. Scanned PDFs (pictures of pages, no text) are reported,
not guessed at - reading them would need OCR.
"""

import datetime
import json
import re
from pathlib import Path

KINDS = {".docx": "Word", ".pdf": "PDF", ".xlsx": "Excel"}
MAX_FILES = 5
MAX_BYTES = 15 * 1024 * 1024     # per file
MAX_WORDS = 15000                # what the AI reads of all the documents together (cost); the rest is noted
TABLE_ROWS = 40                  # rows of each table the AI reads (all rows stay for the report's appendix)
KEEP_ROWS = 500                  # rows kept of each table
MAX_COLS = 12


def _clean(text: str) -> str:
    return re.sub(r"[ \t ]+", " ", str(text or "")).strip()


def _words(text: str) -> int:
    return len(str(text).split())


# ── Word ──────────────────────────────────────────────────────────────────────

def _docx(path: Path, name: str) -> tuple[list[dict], list[dict], list[str]]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(str(path))
    sections, tables, warnings = [], [], []
    heading, buf, n_tables = "", [], 0

    def flush():
        text = "\n".join(buf).strip()
        if text:
            sections.append({"ref": f"{name} > {heading or 'Introduction'}", "heading": heading, "text": text})
        buf.clear()

    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            text = _clean(p.text)
            if not text:
                continue
            style = (p.style.name if p.style is not None else "") or ""
            if style.startswith("Heading") or style == "Title":
                flush()
                heading = text[:90]
            elif style.startswith("List"):
                buf.append(f"- {text}")
            else:
                buf.append(text)
        elif tag == "tbl":
            n_tables += 1
            rows = []
            for r in Table(child, doc).rows:
                cells, last = [], None
                for c in r.cells:            # merged cells repeat: keep each once
                    if c._tc is last:
                        continue
                    last = c._tc
                    cells.append(_clean(c.text))
                if any(cells):
                    rows.append(cells[:MAX_COLS])
            if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                tables.append({"ref": f"{name} > Table {n_tables}", "title": heading or f"Table {n_tables}",
                               "columns": rows[0], "rows": rows[1:KEEP_ROWS + 1]})
            elif rows:
                buf.extend(" | ".join(r) for r in rows)
    flush()
    if not sections and not tables:
        warnings.append(f"{name}: no text found")
    return sections, tables, warnings


# ── PDF ───────────────────────────────────────────────────────────────────────

def _pdf(path: Path, name: str) -> tuple[list[dict], list[dict], list[str]]:
    import pdfplumber

    sections, tables, warnings, empty = [], [], [], 0
    with pdfplumber.open(str(path)) as pdf:
        pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if len(text.strip()) < 20:
                empty += 1
            else:
                sections.append({"ref": f"{name} > page {i}", "heading": "", "text": text.strip()})
            for k, rows in enumerate(page.extract_tables() or [], 1):
                rows = [[_clean(c) for c in r][:MAX_COLS] for r in rows if r and any(_clean(c) for c in r)]
                if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                    tables.append({"ref": f"{name} > page {i} > table {k}", "title": f"Page {i}, table {k}",
                                   "columns": rows[0], "rows": rows[1:KEEP_ROWS + 1]})
    if pages and empty == pages:
        warnings.append(f"{name}: looks scanned (pictures of pages, no text) - it can't be read without OCR")
    elif empty:
        warnings.append(f"{name}: {empty} of {pages} pages have no text (scanned pages or images) and were skipped")
    return sections, tables, warnings


# ── Excel ─────────────────────────────────────────────────────────────────────

def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _value(cell) -> str:
    """A cell as the sheet shows it: £1,200 / 12.5% / 3,400 / 14 Mar 2025."""
    v = cell.value
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%d %b %Y")
    if isinstance(v, (int, float)):
        fmt = str(getattr(cell, "number_format", "") or "")
        if "%" in fmt:
            dec = len(fmt.split(".")[1].split("%")[0]) if "." in fmt else 0
            return f"{v * 100:.{dec}f}%"
        cur = next((s for s in "£$€₹¥" if s in fmt), "")
        if float(v).is_integer():
            num = f"{int(v):,}"
        else:
            dec = len(fmt.split(".")[1].rstrip(";)_-").split(";")[0].replace("#", "0")) if "." in fmt else 2
            num = f"{v:,.{min(max(dec, 0), 4)}f}"
        return f"-{cur}{num[1:]}" if cur and num.startswith("-") else cur + num
    return _clean(v)


def _xlsx(path: Path, name: str) -> tuple[list[dict], list[dict], list[str]]:
    import openpyxl

    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    sections, tables, warnings = [], [], []
    for ws in wb.worksheets:
        grid = []
        for r_i, row in enumerate(ws.iter_rows(), 1):
            vals = [(c.column if hasattr(c, "column") else k + 1, _value(c)) for k, c in enumerate(row)]
            grid.append((r_i, vals))
        # blocks of non-empty rows, split by empty rows
        blocks, cur = [], []
        for r_i, vals in grid:
            if any(v for _, v in vals):
                cur.append((r_i, vals))
            elif cur:
                blocks.append(cur)
                cur = []
        if cur:
            blocks.append(cur)
        notes = []
        for block in blocks:
            cols = sorted({c for _, vals in block for c, v in vals if v})
            if not cols:
                continue
            c0, c1 = cols[0], min(cols[-1], cols[0] + MAX_COLS - 1)
            rows = [[dict(vals).get(c, "") for c in range(c0, c1 + 1)] for _, vals in block]
            ref = f"{name} > {ws.title} > {_col(c0)}{block[0][0]}:{_col(c1)}{block[-1][0]}"
            filled = [sum(1 for v in r if v) for r in rows]
            if len(rows) >= 2 and max(filled) >= 2:
                title = notes[-1] if notes else ws.title
                tables.append({"ref": ref, "title": title[:90], "columns": rows[0], "rows": rows[1:KEEP_ROWS + 1]})
            else:
                notes.extend(" ".join(v for v in r if v) for r in rows)
        if notes:
            sections.append({"ref": f"{name} > {ws.title}", "heading": ws.title, "text": "\n".join(notes)})
    wb.close()
    if not tables and not sections:
        warnings.append(f"{name}: no data found")
    return sections, tables, warnings


READERS = {".docx": _docx, ".pdf": _pdf, ".xlsx": _xlsx}


def read_all(paths: list[Path], log=print) -> dict:
    """Every uploaded file read into sections and tables (tables numbered T1, T2, ... across all files)."""
    out = {"files": [], "sections": [], "tables": [], "warnings": []}
    for path in paths:
        name, ext = path.name, path.suffix.lower()
        if ext not in READERS:
            out["warnings"].append(f"{name}: not a Word, PDF or Excel file - skipped")
            continue
        try:
            sections, tables, warnings = READERS[ext](path, name)
        except Exception as e:  # noqa: BLE001 - a broken or protected file: say so, read the others
            sections, tables, warnings = [], [], [f"{name}: couldn't be read ({str(e).splitlines()[0][:120]})"]
        for t in tables:
            t["id"] = f"T{len(out['tables']) + 1}"
            out["tables"].append(t)
        out["sections"].extend(sections)
        out["warnings"].extend(warnings)
        words = sum(_words(s["text"]) for s in sections) + sum(_words(" ".join(sum(t["rows"], t["columns"]))) for t in tables)
        out["files"].append({"name": name, "kind": KINDS[ext], "sections": len(sections), "tables": len(tables),
                             "words": words})
        log(f"Read {name}: {len(sections)} section(s), {len(tables)} table(s), {words:,} words")
    for w in out["warnings"]:
        log(f"  note: {w}")
    return out


def load(work_dir: Path, log=print) -> dict | None:
    """docs.json (the uploaded files in work_dir/docs/, read once - again when a file is newer), or None."""
    folder, saved = work_dir / "docs", work_dir / "docs.json"
    files = sorted(p for p in folder.iterdir() if p.is_file()) if folder.exists() else []
    if not files:
        return None
    if saved.exists() and all(saved.stat().st_mtime >= p.stat().st_mtime for p in files):
        return json.loads(saved.read_text(encoding="utf-8"))
    log(f"Reading {len(files)} document(s)")
    docs = read_all(files, log)
    saved.write_text(json.dumps(docs, indent=1, ensure_ascii=False), encoding="utf-8")
    return docs


def _table_text(t: dict, rows: int = TABLE_ROWS) -> str:
    lines = [" | ".join(t["columns"])] + [" | ".join(r) for r in t["rows"][:rows]]
    more = len(t["rows"]) - rows
    return "\n".join(lines) + (f"\n(+{more} more rows)" if more > 0 else "")


def for_writer(docs: dict | None, log=print) -> list[dict]:
    """The documents as the AI reads them, in order, within MAX_WORDS: {"ref", "text"} sections and {"table", "ref",
    "title", "rows": "a | b | c" lines} tables."""
    if not docs:
        return []
    out, used, cut = [], 0, 0
    for s in docs["sections"]:
        n = _words(s["text"])
        if used + n > MAX_WORDS:
            room = MAX_WORDS - used
            if room > 60:
                out.append({"ref": s["ref"], "text": " ".join(s["text"].split()[:room]) + " ..."})
                used += room
            cut += n - max(room, 0)
            continue
        out.append({"ref": s["ref"], "text": s["text"]})
        used += n
    for t in docs["tables"]:
        text = _table_text(t)
        n = _words(text)
        if used + n > MAX_WORDS * 1.3:      # tables are dense: a little more room
            cut += n
            continue
        out.append({"table": t["id"], "ref": t["ref"], "title": t["title"], "rows": text})
        used += n
    if cut:
        log(f"The documents are long: about {cut:,} words beyond the first {MAX_WORDS:,} were not read by the AI")
    return out


def texts(docs: dict | None) -> list[str]:
    """The documents as plain text (sections, then tables, all rows): what facts and figures are checked against."""
    if not docs:
        return []
    return [s["text"] for s in docs["sections"]] + [f"{t['title']}\n{_table_text(t, KEEP_ROWS)}" for t in docs["tables"]]


def refs(docs: dict | None) -> list[str]:
    """Every reference a slide or report section may cite."""
    if not docs:
        return []
    return [s["ref"] for s in docs["sections"]] + [t["ref"] for t in docs["tables"]]


def summary(docs: dict | None) -> list[dict]:
    """For the studio: each file, what was read from it."""
    return (docs or {}).get("files") or []
