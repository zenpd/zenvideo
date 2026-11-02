"""
The Word report that goes with a deck: the same material (uploaded documents, narration, app tour) written up in full -
a cover, an executive summary with key figures, sections in paragraphs with tables and charts, conclusions and next
steps, and an appendix of the data tables - styled with the deck's design (its fonts and colours).

    write(parts, documents, tour, title, brief, log) -> (raw report JSON, usage)      one Azure call
    check(raw, ...) -> the report, safe to build: figures the material doesn't state removed, tables and charts by id
    build(report, docs, template, out, ...) -> report.docx                         python-docx, charts drawn by matplotlib
    pdf(report, docs, template, out, ...) -> report.pdf          the same layout as html(), printed by headless Chromium

The AI never types a table's or chart's numbers: it names a table (and, for a chart, its label and value columns) and
the cells are copied from the file - so every figure in a table or chart is one the document states.
"""

import io
import re
from pathlib import Path

from ppt.designs import DEFAULT, design
from ppt.writer import (AUDIENCES, LENGTHS, _number, _numbers_in, _scrub, _stated, _text, _vocab, chat_json,
                        clean_brief, cite, gaps)

REPORT_VERSION = 1
# brief length -> (sections, paragraphs per section, pages - for the prompt)
SIZE = {"short": ("3-4", "1-2", "2-3"), "standard": ("5-7", "2-3", "4-8"), "detailed": ("8-12", "3-5", "9-15")}
TONE = {"auto": "clear, professional", "executive": "formal, concise", "investor": "confident, persuasive",
        "customer": "warm, persuasive", "technical": "precise, technical", "internal": "plain, informative",
        "custom": "clear, professional"}

PROMPT = """You write a clear, well-structured business report (a Word document) from the material below: uploaded
documents ("documents": text sections {"ref", "text"} and tables {"table": id, "ref", "title", "rows": the header
row, then one line per row, cells separated by " | "}), and/or a narration, transcript or notes ("sections"), and/or an
"app_tour" of a live app. Return one JSON object:
{
 "title": the report's title (max 12 words), "subtitle": max 20 words,
 "executive_summary": [1-2 paragraphs, 120-250 words in all: what this is about, the key facts or findings, and what
   is proposed or decided],
 "key_figures": [0-4 {"value": a figure exactly as the material writes it (max 12 characters), "label": what it
   measures (max 8 words), "source": its ref}] - the most important numbers; [] when the material has none,
 "sections": [[SECTIONS] sections in a logical order, each:
   {"heading": max 8 words, "paragraphs": [[PARAS] paragraphs of 50-130 words each],
    "bullets": [] or 3-6 parallel items (max 20 words each) - only for a real list,
    "table": {"id": a table's id from "documents", "caption": max 15 words} or null - when a table supports the section,
    "chart": {"table": a table's id, "label_column": the column naming the categories (e.g. "Quarter"),
       "value_columns": [1-3 columns holding numbers], "type": "bar" | "line" | "pie", "title": max 8 words,
       "caption": what it shows (max 18 words)} or null,
    "sources": [the ref of each section or table this section's facts come from, copied exactly]}],
 "conclusion": [1-2 paragraphs, 60-150 words in all],
 "next_steps": [0-5 concrete actions the material states or clearly proposes, max 20 words each],
 "appendix": [ids of data tables worth giving in full at the end, or []],
 "gaps": [{"topic": what the brief's focus or the instructions ask for that the material does not cover (max 8 words),
   "note": what the user could add (max 15 words)}] - [] when nothing is missing
}

Rules:
- Facts: use ONLY what the material states. Never invent numbers, names, dates, customers, prices or results, and never
  calculate new figures (no totals, averages, percentages, differences or growth rates the material does not state
  itself). Write each figure exactly as the material gives it, with its currency symbol or unit.
- Tables and charts come from the documents' tables by id and column names: you never type their numbers. A chart
  needs a table with a label column and number columns: line for values over time, bar to compare categories, pie
  only for parts of one whole with 6 slices or fewer. Use a table where it supports the text, each table once. When
  the documents have a table of numbers over time or by category, at least one section shows it as a chart.
- Structure: start where the reader needs to start (the context or problem), then what it is and how it works, the
  evidence and results, risks or considerations, costs and plan - each only when the material covers it. Headings are
  short and specific (no numbers: they are added). Every section adds something new; no repetition.
- Write full paragraphs in a [TONE] tone for this reader: [AUDIENCE]. Use bullets only for real lists. No marketing
  filler, no exclamation marks.
- When two documents disagree, use the most recent or most specific figure and say in the text that they differ.
- The brief's focus gets extra weight - its own section where the material supports it; never make anything up for it.
- "instructions" (when given) are the user's own requests: follow them unless they break the facts rule.
- Return only the JSON object."""


def write(parts: list[str], documents: list[dict], tour: list[dict] | None, title: str, brief: dict,
          log=print) -> tuple[dict, dict]:
    brief = clean_brief(brief)
    sections, paras, pages = SIZE[brief["length"]]
    prompt = (PROMPT.replace("[SECTIONS]", sections).replace("[PARAS]", paras)
              .replace("[TONE]", TONE.get(brief["audience"], TONE["auto"]))
              .replace("[AUDIENCE]", AUDIENCES[brief["audience"]][2]))
    payload = {"subject": title or None, "brief": {"pages": pages, "focus": brief["focus"] or None},
               "documents": documents or None, "sections": parts or None}
    if brief["instructions"]:
        payload["instructions"] = brief["instructions"]
    if tour:
        payload["app_tour"] = tour
    raw, usage = chat_json(prompt, payload, "Writing the Word report", log, temperature=0.3)
    log(f"Report written: {usage['input_tokens']:,} input + {usage['output_tokens']:,} output tokens "
        f"(about ${usage['cost_usd']:.4f})")
    return raw, usage


# ── checking ─────────────────────────────────────────────────────────────────

def _paras(v, numbers, vocab, most: int) -> list[str]:
    items = v if isinstance(v, list) else [v] if isinstance(v, str) else []
    out = [_scrub(_text(x), numbers, vocab) for x in items if isinstance(x, str)]
    return [x for x in out if len(x.split()) >= 4][:most]


def _table(tables: dict, tid) -> dict | None:
    return tables.get(str(tid or "").strip().upper())


def _col(t: dict, name) -> int | None:
    key = re.sub(r"\s+", " ", str(name or "")).strip().lower()
    cols = [re.sub(r"\s+", " ", c).strip().lower() for c in t["columns"]]
    return cols.index(key) if key in cols else None


def chart_data(t: dict, spec: dict) -> dict | None:
    """A chart's data copied from the table's cells: categories from the label column, one series per value column
    with numbers in (nearly) every row. None when the table can't make that chart."""
    li = _col(t, spec.get("label_column"))
    if li is None:
        return None
    rows = [r for r in t["rows"] if li < len(r) and r[li].strip()][:12]
    series = []
    for name in (spec.get("value_columns") or [])[:3]:
        vi = _col(t, name)
        if vi is None or vi == li:
            continue
        vals = [_number(r[vi]) if vi < len(r) and re.search(r"\d", r[vi]) else None for r in rows]
        if sum(v is not None for v in vals) >= max(2, len(rows) - 1):
            series.append({"name": t["columns"][vi], "values": vals, "shown": [r[vi] if vi < len(r) else "" for r in rows]})
    if not series or len(rows) < 2:
        return None
    # one axis: a series far smaller than the first (e.g. engineers next to requests) would be a flat line - left out
    top = max(abs(v) for v in series[0]["values"] if v is not None) or 1
    kept = [series[0]] + [x for x in series[1:] if 0.1 <= (max(abs(v) for v in x["values"] if v is not None) or 0) / top <= 10]
    dropped = len(kept) < len(series)
    series = kept
    kind = spec.get("type") if spec.get("type") in ("bar", "line", "pie") else "bar"
    if kind == "pie" and (len(series) > 1 or len(rows) > 6 or any((v or 0) <= 0 for v in series[0]["values"])):
        kind = "bar"
    unit = next((u for u in ("%", "£", "$", "€", "₹") if all(u in s for s in series[0]["shown"] if s)), "")
    return {"type": kind, "categories": [r[li] for r in rows], "series": series, "label": t["columns"][li], "unit": unit,
            "renamed": f"{' and '.join(x['name'] for x in series)} by {t['columns'][li].lower()}" if dropped else ""}


def check(raw: dict, material: str, figures: str, docs: dict | None, refs: list[str], title: str = "",
          instructions: str = "") -> dict:
    """The report safe to build: sentences with figures or names the material doesn't state are dropped, key figures
    must be stated, tables and charts must name real tables and columns, sources must be real refs."""
    numbers = _numbers_in(f"{figures}\n{instructions}")
    vocab = _vocab(material, instructions, title)
    tables = {t["id"]: t for t in (docs or {}).get("tables", [])}
    known = {re.sub(r"\s+", " ", r).strip().lower(): r for r in refs}
    head = lambda v, n=0: _scrub(_text(v, n), numbers, vocab, True)    # noqa: E731 - titles are Title Case
    rep = {"version": REPORT_VERSION, "title": head(raw.get("title")) or title or "Report",
           "subtitle": head(raw.get("subtitle")),
           "executive_summary": _paras(raw.get("executive_summary"), numbers, vocab, 2),
           "key_figures": [], "sections": [], "conclusion": _paras(raw.get("conclusion"), numbers, vocab, 2),
           "next_steps": [x for x in _paras(raw.get("next_steps"), numbers, vocab, 5)], "appendix": [],
           "gaps": gaps(raw.get("gaps"))}
    for k in raw.get("key_figures") or []:
        if isinstance(k, dict) and (v := _text(k.get("value"))[:14]) and re.search(r"\d", v) and _stated(v, numbers):
            rep["key_figures"].append({"value": v, "label": head(k.get("label"), 10),
                                       "source": (cite([k.get("source")], known) or [""])[0]})
    rep["key_figures"] = rep["key_figures"][:4]
    used_tables, used_charts = set(), set()
    for s in raw.get("sections") or []:
        if not isinstance(s, dict) or not head(s.get("heading")):
            continue
        sec = {"heading": head(s.get("heading"), 10), "paragraphs": _paras(s.get("paragraphs"), numbers, vocab, 5),
               "bullets": [_scrub(_text(b), numbers, vocab) for b in s.get("bullets") or [] if isinstance(b, str)],
               "table": None, "chart": None, "sources": cite(s.get("sources"), known, 4)}
        sec["bullets"] = [b for b in sec["bullets"] if b][:6]
        if len(sec["bullets"]) < 2:          # one item is not a list
            sec["paragraphs"] += sec["bullets"]
            sec["bullets"] = []
        tb = s.get("table") if isinstance(s.get("table"), dict) else None
        if tb and (t := _table(tables, tb.get("id"))) and t["id"] not in used_tables:
            sec["table"] = {"id": t["id"], "caption": _text(tb.get("caption"), 18) or t["title"]}
            used_tables.add(t["id"])
        ch = s.get("chart") if isinstance(s.get("chart"), dict) else None
        if ch and (t := _table(tables, ch.get("table"))) and t["id"] not in used_charts and (data := chart_data(t, ch)):
            sec["chart"] = {"table": t["id"], "title": data["renamed"] or head(ch.get("title"), 10) or t["title"],
                            "caption": data["renamed"] or _scrub(_text(ch.get("caption"), 22), numbers, vocab), **data}
            used_charts.add(t["id"])
        for x in (sec["table"], sec["chart"]):     # a table or chart cites its table
            if x and tables[x.get("id") or x.get("table")]["ref"] not in sec["sources"]:
                sec["sources"].append(tables[x.get("id") or x.get("table")]["ref"])
        if sec["paragraphs"] or sec["bullets"] or sec["table"] or sec["chart"]:
            rep["sections"].append(sec)
    # the appendix gives tables in full: those no section shows, or shows cut short (over 25 rows)
    rep["appendix"] = [t for t in dict.fromkeys(str(x).strip().upper() for x in raw.get("appendix") or [])
                       if t in tables and (t not in used_tables or len(tables[t]["rows"]) > 25)][:8]
    if not rep["sections"]:
        raise ValueError("the report came back without usable sections - try again or give more material")
    return rep


# ── building the Word file ───────────────────────────────────────────────────

def report_file(template: str, fmt: str = "docx") -> str:
    """report.docx (or .pdf) for the default design, report-<id>.docx otherwise."""
    return f"report.{fmt}" if template == DEFAULT else f"report-{template}.{fmt}"


def _lum(hex_: str) -> float:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _deepen(hex_: str, target: float = 0.42) -> str:
    """A colour dark enough for text on a white page."""
    h = hex_.lstrip("#")[:6].upper()
    while _lum(h) > target:
        h = "".join(f"{int(int(h[i:i + 2], 16) * 0.85):02X}" for i in (0, 2, 4))
    return h


def _tint(hex_: str, k: float = 0.9) -> str:
    """A pale version of a colour (table stripes, figure boxes)."""
    h = hex_.lstrip("#")[:6]
    return "".join(f"{int(int(h[i:i + 2], 16) + (255 - int(h[i:i + 2], 16)) * k):02X}" for i in (0, 2, 4))


def _palette(d) -> dict:
    accent = _deepen(d.STRONG or d.ACCENT)
    series = [_deepen(c, 0.6) for c in (d.ACCENTS or [])] or [accent]
    if accent not in series:
        series = [accent] + series
    return {"accent": accent, "series": series + ["64748B", "94A3B8", "CBD5E1"], "ink": "1F2937", "muted": "6B7280",
            "pale": _tint(accent, 0.9), "line": "D7DCE3", "head": d.HEAD, "body": d.BODY}


def _chart_png(c: dict, pal: dict) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": [pal["body"], "DejaVu Sans"], "font.size": 9})
    fig, ax = plt.subplots(figsize=(6.4, 3.3), dpi=200)
    colors = ["#" + x for x in pal["series"]]
    cats = c["categories"]
    if c["type"] == "pie":
        s = c["series"][0]
        ax.pie([v or 0 for v in s["values"]], labels=[f"{k}\n{t}" for k, t in zip(cats, s["shown"])], colors=colors,
               startangle=90, counterclock=False, wedgeprops={"width": 0.42, "edgecolor": "white"},
               textprops={"color": "#" + pal["ink"], "fontsize": 8.5})
        ax.axis("equal")
    else:
        n = len(c["series"])
        x = range(len(cats))
        w = 0.8 / n
        for k, s in enumerate(c["series"]):
            vals = [v if v is not None else float("nan") for v in s["values"]]
            if c["type"] == "line":
                ax.plot(list(x), vals, marker="o", lw=2.4, color=colors[k % len(colors)], label=s["name"])
                if n == 1:
                    for xi, v, t in zip(x, vals, s["shown"]):
                        ax.annotate(t, (xi, v), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8,
                                    color="#" + pal["ink"])
            else:
                pos = [xi - 0.4 + w * (k + 0.5) for xi in x]
                bars = ax.bar(pos, vals, width=w * 0.92, color=colors[k % len(colors)], label=s["name"])
                if n == 1 and len(cats) <= 8:
                    for b, t in zip(bars, s["shown"]):
                        ax.annotate(t, (b.get_x() + b.get_width() / 2, b.get_height()), textcoords="offset points",
                                    xytext=(0, 3), ha="center", fontsize=8, color="#" + pal["ink"])
        ax.set_xticks(list(x))
        ax.set_xticklabels(cats, fontsize=8.5, rotation=0 if max(len(k) for k in cats) * len(cats) < 70 else 25,
                           ha="center" if max(len(k) for k in cats) * len(cats) < 70 else "right")
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#" + pal["line"])
        ax.tick_params(axis="y", colors="#" + pal["muted"], length=0)
        ax.tick_params(axis="x", colors="#" + pal["ink"], length=0)
        ax.yaxis.grid(True, color="#" + pal["line"], lw=0.6)
        ax.set_axisbelow(True)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}" if abs(v) >= 10 else f"{v:g}"))
        if n > 1:
            ax.legend(frameon=False, fontsize=8.5, loc="upper left", ncol=n)
        else:
            ax.set_ylabel(c["series"][0]["name"], color="#" + pal["muted"], fontsize=8.5)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def build(rep: dict, docs: dict | None, template: str, out: Path, subject: str = "", audience: str = "",
          made_from: list[str] | None = None) -> Path:
    import datetime

    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Inches, Pt, RGBColor

    pal = _palette(design(template))
    tables = {t["id"]: t for t in (docs or {}).get("tables", [])}
    rgb = lambda h: RGBColor.from_string(h)  # noqa: E731
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.3)
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.2)

    def font(style, name, size=None, bold=None, color=None):
        f = style.font
        f.name = name
        rpr = style.element.get_or_add_rPr()
        fonts = rpr.find(qn("w:rFonts"))
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            rpr.append(fonts)
        for k in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            fonts.set(qn(k), name)
        if size:
            f.size = Pt(size)
        if bold is not None:
            f.bold = bold
        if color:
            f.color.rgb = rgb(color)

    normal = doc.styles["Normal"]
    font(normal, pal["body"], 10.5, color=pal["ink"])
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.18
    for name, size in (("Heading 1", 17), ("Heading 2", 12.5)):
        st = doc.styles[name]
        font(st, pal["head"], size, True, pal["accent"] if name == "Heading 1" else pal["ink"])
        st.paragraph_format.space_before = Pt(20 if name == "Heading 1" else 12)
        st.paragraph_format.space_after = Pt(8)
        st.paragraph_format.keep_with_next = True
    for name in ("List Bullet", "List Number"):
        font(doc.styles[name], pal["body"], 10.5, color=pal["ink"])
        doc.styles[name].paragraph_format.space_after = Pt(4)

    def para(text="", size=None, color=None, bold=False, italic=False, after=None, align=None, style=None):
        p = doc.add_paragraph(style=style)
        if text:
            r = p.add_run(text)
            r.bold, r.italic = bold, italic
            if size:
                r.font.size = Pt(size)
            if color:
                r.font.color.rgb = rgb(color)
        if after is not None:
            p.paragraph_format.space_after = Pt(after)
        if align:
            p.alignment = align
        return p

    def shade(cell, hex_):
        tcpr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_)
        tcpr.append(shd)

    def borders(table, color, outer=True):
        tblpr = table._tbl.tblPr
        b = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            e = OxmlElement(f"w:{edge}")
            on = edge in ("insideH",) or (outer and edge in ("top", "bottom"))
            e.set(qn("w:val"), "single" if on else "nil")
            e.set(qn("w:sz"), "4")
            e.set(qn("w:color"), color)
            b.append(e)
        tblpr.append(b)

    def rule(p, color, size=18):
        ppr = p._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for k, v in (("w:val", "single"), ("w:sz", str(size)), ("w:space", "6"), ("w:color", color)):
            bottom.set(qn(k), v)
        bdr.append(bottom)
        ppr.append(bdr)

    def field(p, code):
        r = p.add_run()
        for kind, text in (("begin", None), (None, code), ("end", None)):
            if kind:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
            else:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = text
            r._r.append(el)
        return r

    def source_line(refs, label="Source"):
        if refs:
            para(f"{label}{'s' if len(refs) > 1 else ''}: " + "; ".join(refs), 8.5, pal["muted"], italic=True, after=10)

    n_table = n_fig = 0

    def add_table(t, caption, cap_rows=None):
        nonlocal n_table
        n_table += 1
        rows = t["rows"][:cap_rows] if cap_rows else t["rows"]
        ncol = max(len(t["columns"]), *(len(r) for r in rows)) if rows else len(t["columns"])
        tb = doc.add_table(rows=1 + len(rows), cols=ncol)
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        borders(tb, pal["line"])
        numeric = [all(_number(r[i]) is not None for r in rows if i < len(r) and r[i]) and any(i < len(r) and r[i] for r in rows)
                   for i in range(ncol)]
        for i in range(ncol):
            cell = tb.rows[0].cells[i]
            shade(cell, pal["accent"])
            cell.paragraphs[0].text = ""
            run = cell.paragraphs[0].add_run(t["columns"][i] if i < len(t["columns"]) else "")
            run.bold, run.font.size, run.font.color.rgb = True, Pt(9), rgb("FFFFFF")
            if numeric[i] and i:
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for k, r in enumerate(rows, 1):
            for i in range(ncol):
                cell = tb.rows[k].cells[i]
                if k % 2 == 0:
                    shade(cell, "F5F7FA")
                cell.paragraphs[0].text = ""
                run = cell.paragraphs[0].add_run(r[i] if i < len(r) else "")
                run.font.size = Pt(9)
                if numeric[i] and i:
                    cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for row in tb.rows:
            for cell in row.cells:
                cell.paragraphs[0].paragraph_format.space_after = Pt(2)
                cell.paragraphs[0].paragraph_format.space_before = Pt(2)
        p = para(after=2)
        p.paragraph_format.space_before = Pt(6)
        r = p.add_run(f"Table {n_table}. ")
        r.bold, r.font.size, r.font.color.rgb = True, Pt(9), rgb(pal["ink"])
        r = p.add_run(caption + (f" (first {len(rows)} of {len(t['rows'])} rows)" if len(rows) < len(t["rows"]) else ""))
        r.font.size, r.font.color.rgb = Pt(9), rgb(pal["ink"])
        source_line([t["ref"]])

    def add_chart(c):
        nonlocal n_fig
        n_fig += 1
        doc.add_picture(io.BytesIO(_chart_png(c, pal)), width=Inches(6.2))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        p = para(after=2)
        r = p.add_run(f"Figure {n_fig}. ")
        r.bold, r.font.size = True, Pt(9)
        r = p.add_run(c["caption"] or c["title"])
        r.font.size = Pt(9)
        source_line([tables[c["table"]]["ref"]])

    # cover
    for _ in range(6):
        para(after=6)
    para((subject or "").upper(), 10, pal["accent"], bold=True, after=10)
    p = para(rep["title"], 30, pal["ink"], bold=True, after=8)
    p.runs[0].font.name = pal["head"]
    if rep["subtitle"]:
        para(rep["subtitle"], 14, pal["muted"], after=16)
    rule(para(after=18), pal["accent"], 24)
    meta = [("Prepared for", audience), ("Based on", ", ".join(made_from or [])),
            ("Date", datetime.date.today().strftime("%d %B %Y"))]
    for k, v in meta:
        if v:
            p = para(after=3)
            r = p.add_run(f"{k}:  ")
            r.bold, r.font.size, r.font.color.rgb = True, Pt(10), rgb(pal["muted"])
            r = p.add_run(v)
            r.font.size, r.font.color.rgb = Pt(10), rgb(pal["ink"])
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # contents
    doc.add_heading("Contents", 1)
    heads = ["Executive summary"] + [f"{i}. {s['heading']}" for i, s in enumerate(rep["sections"], 1)]
    if rep["conclusion"] or rep["next_steps"]:
        heads.append("Conclusions and next steps")
    if rep["appendix"]:
        heads.append("Appendix: data tables")
    for h in heads:
        para(h, 11, pal["ink"], after=5)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # executive summary and key figures
    doc.add_heading("Executive summary", 1)
    for x in rep["executive_summary"]:
        para(x)
    if rep["key_figures"]:
        k = rep["key_figures"]
        tb = doc.add_table(rows=2, cols=len(k))
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        borders(tb, "FFFFFF", outer=False)
        for i, f in enumerate(k):
            for row in (0, 1):
                shade(tb.rows[row].cells[i], pal["pale"])
            c = tb.rows[0].cells[i].paragraphs[0]
            r = c.add_run(f["value"])
            r.bold, r.font.size, r.font.color.rgb = True, Pt(22), rgb(pal["accent"])
            r.font.name = pal["head"]
            c.paragraph_format.space_before = Pt(8)
            c = tb.rows[1].cells[i].paragraphs[0]
            r = c.add_run(f["label"])
            r.font.size, r.font.color.rgb = Pt(9), rgb(pal["ink"])
            c.paragraph_format.space_after = Pt(8)
        para(after=4)
        source_line(list(dict.fromkeys(f["source"] for f in k if f["source"])))

    # the sections
    for i, s in enumerate(rep["sections"], 1):
        doc.add_heading(f"{i}. {s['heading']}", 1)
        for x in s["paragraphs"]:
            para(x)
        for b in s["bullets"]:
            para(b, style="List Bullet")
        if s["chart"]:
            add_chart(s["chart"])
        if s["table"]:
            add_table(tables[s["table"]["id"]], s["table"]["caption"], cap_rows=25)
        shown = {tables[s["table"]["id"]]["ref"] if s["table"] else "", tables[s["chart"]["table"]]["ref"] if s["chart"] else ""}
        source_line([r for r in s["sources"] if r not in shown])     # a table's or chart's own source is under it

    if rep["conclusion"] or rep["next_steps"]:
        doc.add_heading("Conclusions and next steps", 1)
        for x in rep["conclusion"]:
            para(x)
        if rep["next_steps"]:
            doc.add_heading("Next steps", 2)
            for x in rep["next_steps"]:
                para(x, style="List Number")

    if rep["appendix"]:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        doc.add_heading("Appendix: data tables", 1)
        for tid in rep["appendix"]:
            t = tables[tid]
            doc.add_heading(t["title"], 2)
            add_table(t, t["title"], cap_rows=200)

    # header and footer: the subject, and page numbers
    hp = sec.header.paragraphs[0]
    r = hp.add_run(f"{subject}  ·  {rep['title']}" if subject and subject.lower() not in rep["title"].lower() else rep["title"])
    r.font.size, r.font.color.rgb = Pt(8.5), rgb(pal["muted"])
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for part in ("Page ", "PAGE", " of ", "NUMPAGES"):
        r = field(fp, part) if part.isupper() else fp.add_run(part)
        r.font.size, r.font.color.rgb = Pt(8.5), rgb(pal["muted"])
    sec.different_first_page_header_footer = True
    doc.core_properties.title = rep["title"]
    doc.core_properties.subject = subject
    doc.save(str(out))
    return out


# ── the report as a web page: the studio's preview of the Word file ────────────

def html(rep: dict, docs: dict | None, template: str, subject: str = "", audience: str = "",
         made_from: list[str] | None = None) -> str:
    """The report laid out like the Word file (same order, numbering, tables and charts), for reading in the browser
    before downloading."""
    import base64
    import datetime
    from html import escape as e

    pal = _palette(design(template))
    tables = {t["id"]: t for t in (docs or {}).get("tables", [])}
    n = {"table": 0, "fig": 0}
    src = lambda refs, label="Source": (f'<p class="src">{label}{"s" if len(refs) > 1 else ""}: {e("; ".join(refs))}</p>'  # noqa: E731
                                        if refs else "")

    def table(t, caption, cap):
        n["table"] += 1
        rows = t["rows"][:cap]
        head = "".join(f"<th>{e(c)}</th>" for c in t["columns"])
        body = "".join("<tr>" + "".join(f'<td{" class=num" if i and _number(c) is not None else ""}>{e(c)}</td>'
                                        for i, c in enumerate(r)) + "</tr>" for r in rows)
        more = f" (first {len(rows)} of {len(t['rows'])} rows)" if len(rows) < len(t["rows"]) else ""
        return (f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
                f'<p class="cap"><b>Table {n["table"]}.</b> {e(caption)}{more}</p>{src([t["ref"]])}')

    def chart(c):
        n["fig"] += 1
        png = base64.b64encode(_chart_png(c, pal)).decode()
        return (f'<img class="chart" src="data:image/png;base64,{png}" alt="{e(c["title"])}">'
                f'<p class="cap"><b>Figure {n["fig"]}.</b> {e(c["caption"] or c["title"])}</p>{src([tables[c["table"]]["ref"]])}')

    out = [f'<section class="cover"><p class="kick">{e(subject.upper())}</p><h1 class="title">{e(rep["title"])}</h1>'
           f'<p class="sub">{e(rep["subtitle"])}</p><hr>']
    for k, v in (("Prepared for", audience), ("Based on", ", ".join(made_from or [])),
                 ("Date", datetime.date.today().strftime("%d %B %Y"))):
        if v:
            out.append(f'<p class="meta"><b>{k}:</b> {e(v)}</p>')
    heads = ["Executive summary"] + [f"{i}. {s['heading']}" for i, s in enumerate(rep["sections"], 1)]
    if rep["conclusion"] or rep["next_steps"]:
        heads.append("Conclusions and next steps")
    if rep["appendix"]:
        heads.append("Appendix: data tables")
    out.append('</section><section class="contents"><h2>Contents</h2><ol>' +
               "".join(f"<li>{e(h)}</li>" for h in heads) + "</ol></section>")
    out.append("<section><h2>Executive summary</h2>")
    out += [f"<p>{e(x)}</p>" for x in rep["executive_summary"]]
    if rep["key_figures"]:
        out.append('<div class="kf">' + "".join(f'<div><b>{e(f["value"])}</b><span>{e(f["label"])}</span></div>'
                                                for f in rep["key_figures"]) + "</div>")
        out.append(src(list(dict.fromkeys(f["source"] for f in rep["key_figures"] if f["source"]))))
    out.append("</section>")
    for i, s in enumerate(rep["sections"], 1):
        out.append(f'<section><h2>{i}. {e(s["heading"])}</h2>')
        out += [f"<p>{e(x)}</p>" for x in s["paragraphs"]]
        if s["bullets"]:
            out.append("<ul>" + "".join(f"<li>{e(b)}</li>" for b in s["bullets"]) + "</ul>")
        if s["chart"]:
            out.append(chart(s["chart"]))
        if s["table"]:
            out.append(table(tables[s["table"]["id"]], s["table"]["caption"], 25))
        shown = {tables[s["table"]["id"]]["ref"] if s["table"] else "", tables[s["chart"]["table"]]["ref"] if s["chart"] else ""}
        out.append(src([r for r in s["sources"] if r not in shown]) + "</section>")
    if rep["conclusion"] or rep["next_steps"]:
        out.append("<section><h2>Conclusions and next steps</h2>" + "".join(f"<p>{e(x)}</p>" for x in rep["conclusion"]))
        if rep["next_steps"]:
            out.append("<h3>Next steps</h3><ol>" + "".join(f"<li>{e(x)}</li>" for x in rep["next_steps"]) + "</ol>")
        out.append("</section>")
    if rep["appendix"]:
        out.append("<section><h2>Appendix: data tables</h2>")
        for tid in rep["appendix"]:
            out.append(f"<h3>{e(tables[tid]['title'])}</h3>" + table(tables[tid], tables[tid]["title"], 200))
        out.append("</section>")
    css = f"""
    :root {{ --accent: #{pal['accent']}; --ink: #{pal['ink']}; --muted: #{pal['muted']}; --pale: #{pal['pale']};
             --line: #{pal['line']}; }}
    * {{ box-sizing: border-box; }}
    html {{ background: #e9edf2; }}
    body {{ margin: 0; padding: 24px 12px; font: 15px/1.6 "{pal['body']}", "Segoe UI", system-ui, sans-serif; color: var(--ink); }}
    .page {{ max-width: 820px; margin: 0 auto; background: #fff; padding: 64px 72px; box-shadow: 0 2px 18px rgba(15,23,42,.12); }}
    h1, h2, h3 {{ font-family: "{pal['head']}", "Segoe UI", system-ui, sans-serif; }}
    .cover {{ padding: 80px 0 60px; border-bottom: 1px solid var(--line); margin-bottom: 24px; }}
    .kick {{ color: var(--accent); font-weight: 700; letter-spacing: .08em; font-size: 13px; margin: 0 0 12px; }}
    .title {{ font-size: 40px; line-height: 1.1; margin: 0 0 12px; }}
    .sub {{ color: var(--muted); font-size: 19px; margin: 0 0 22px; }}
    hr {{ border: 0; border-top: 4px solid var(--accent); margin: 0 0 22px; }}
    .meta {{ margin: 4px 0; font-size: 14px; }} .meta b {{ color: var(--muted); }}
    h2 {{ color: var(--accent); font-size: 23px; margin: 34px 0 10px; }}
    h3 {{ font-size: 17px; margin: 22px 0 8px; }}
    .kf {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 6px; margin: 18px 0 6px; }}
    .kf div {{ background: var(--pale); padding: 14px 16px; }}
    .kf b {{ display: block; color: var(--accent); font-size: 28px; line-height: 1.1; }}
    .kf span {{ font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin: 14px 0 4px; }}
    th {{ background: var(--accent); color: #fff; text-align: left; padding: 6px 8px; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid var(--line); }}
    tbody tr:nth-child(even) td {{ background: #f5f7fa; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .chart {{ display: block; width: 100%; margin: 14px 0 4px; }}
    .cap {{ font-size: 13px; margin: 6px 0 0; }}
    .src {{ font-size: 12px; color: var(--muted); font-style: italic; margin: 2px 0 14px; }}
    .contents ol {{ list-style: none; padding: 0; margin: 0; }}
    .contents li {{ padding: 6px 0; border-bottom: 1px solid var(--line); }}
    @media (max-width: 640px) {{ .page {{ padding: 28px 18px; }} .title {{ font-size: 30px; }} }}
    @page {{ size: A4; margin: 22mm 22mm 20mm; }}
    @media print {{
      html, body {{ background: #fff; padding: 0; font-size: 10.5pt; }}
      .page {{ max-width: none; padding: 0; box-shadow: none; }}
      .cover {{ min-height: 230mm; display: flex; flex-direction: column; justify-content: center; border: 0;
                padding: 0; margin: 0; break-after: page; }}
      .contents {{ break-after: page; }}
      h2, h3 {{ break-after: avoid; }}
      tr, .kf div, .chart, .cap {{ break-inside: avoid; }}
      .chart {{ max-height: 95mm; object-fit: contain; }}
      p {{ orphans: 3; widows: 3; }}
    }}"""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width, initial-scale=1"><title>{e(rep["title"])}</title><style>{css}</style></head>'
            f'<body><article class="page">{"".join(out)}</article></body></html>')


def pdf(rep: dict, docs: dict | None, template: str, out: Path, subject: str = "", audience: str = "",
        made_from: list[str] | None = None) -> Path:
    """The report as a PDF: the html() page printed on A4 by headless Chromium (Playwright), with the title and page
    numbers in the footer."""
    from html import escape as e

    from playwright.sync_api import sync_playwright

    page_html = html(rep, docs, template, subject, audience, made_from)
    pal = _palette(design(template))
    footer = (f'<div style="width:100%;font:8px Arial,sans-serif;color:#{pal["muted"]};padding:0 22mm;display:flex;'
              f'justify-content:space-between"><span>{e(rep["title"])}</span><span>Page <span class="pageNumber"></span> '
              f'of <span class="totalPages"></span></span></div>')
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(page_html, wait_until="load")
            page.emulate_media(media="print")
            page.pdf(path=str(out), format="A4", print_background=True, display_header_footer=True,
                     header_template="<span></span>", footer_template=footer,
                     margin={"top": "22mm", "bottom": "20mm", "left": "22mm", "right": "22mm"})
        finally:
            browser.close()
    return out
