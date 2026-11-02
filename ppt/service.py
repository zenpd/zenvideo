"""
The PPT skill's one entry point: material in, deck out.

    generate(work_dir, template, narration=..., title=..., url=...) -> (deck path, token usage or None)
    revise(work_dir, template, comments, narration=..., title=..., url=...) -> (deck path, changes, token usage)
    preview(work_dir, template) -> slide picture names (work_dir/preview/<template>/NN.png)
    report(work_dir, template, narration=..., title=..., url=...) -> (Word report path, token usage or None)

work_dir keeps everything a deck needs to be regenerated for free: narration.txt (the material), pages/ and pages.json
(the app explored page by page, only when a link was given - once), deck.json (the story), revisions/ (each review
round's comments, the model's report and the story before it). Switching design reuses the story, so it costs no
tokens; rewrite asks Azure for a new story; recapture explores the app again; revise asks Azure to change the story as
the reviewer's comments say (one call), keeping the same fact checks.

The material is the narration, the uploaded documents (work_dir/docs/: Word, PDF, Excel - read once into docs.json by
ppt.documents) and/or the app tour (each screen's text and how it was reached); any one of them is enough. With
documents, each slide cites its sources (in its speaker notes, and in sources.json for the review) and what the brief
asks for that the material doesn't cover is reported as "gaps". The Word report (report.json, report*.docx) is written
from the same material in a second call, only when asked for; switching design rebuilds it for free.
"""

import datetime
import json
from pathlib import Path

from ppt import documents as docs_mod
from ppt import preview as previews
from ppt import report as reports
from ppt import source
from ppt.capture import capture_app
from ppt.designs import deck_file, design
from ppt.quality import polish
from ppt.writer import StoryError, add_usage, clean_brief, normalize, revise_story, write_story

STORY_VERSION = 2      # deck.json written by an older version of the writer is rewritten, not reused


def story_is_fresh(work_dir: Path, brief: dict | None = None) -> bool:
    """deck.json was written by this writer version, for this brief (when given), after the material it is based on,
    so it can be reused."""
    story = work_dir / "deck.json"
    if not story.exists():
        return False
    try:
        saved = json.loads(story.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    # both sides cleaned: a brief saved before a field existed still matches
    if saved.get("version") != STORY_VERSION or (brief is not None and
                                                 clean_brief(saved.get("brief")) != clean_brief(brief)):
        return False
    return all(story.stat().st_mtime >= p.stat().st_mtime for p in _inputs(work_dir))


def _inputs(work_dir: Path) -> list[Path]:
    """The files the material comes from: a story or report older than any of them is written again."""
    docs = sorted((work_dir / "docs").iterdir()) if (work_dir / "docs").exists() else []
    return [p for p in (work_dir / "narration.txt", work_dir / "pages.json", *docs) if p.exists()]


class Material:
    """Everything a deck or report is written from, and what its facts are checked against."""

    def __init__(self, work_dir: Path, narration: str, url: str, log=print):
        self.pages = _pages(work_dir) if url else []
        self.parts = source.clean(narration) if narration else []
        self.tour = _tour(self.pages)
        self.docs = docs_mod.load(work_dir, log)
        self.documents = docs_mod.for_writer(self.docs, log)      # what the AI reads
        self.doc_texts = docs_mod.texts(self.docs)
        self.refs = docs_mod.refs(self.docs)
        # facts are checked against all of it; figures against the narration and the documents (not the app's demo data)
        self.text = _material(self.pages, self.parts + self.doc_texts, self.tour)
        self.figures = "\n".join(self.parts + self.doc_texts)
        self.notes_from = self.parts + [x["text"] for x in (self.docs or {}).get("sections", [])]
        self.screen_ids = [p["id"] for p in self.pages]

    def empty(self) -> bool:
        return not (self.parts or self.tour or self.documents)

    def files(self) -> list[str]:
        return [f["name"] for f in docs_mod.summary(self.docs)]


def _pages(work_dir: Path) -> list[dict]:
    f = work_dir / "pages.json"
    pages = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    return [p for p in pages if (work_dir / "pages" / p["file"]).exists()]


def _tour(pages: list[dict]) -> list[dict]:
    """The app tour the story is written from: each screen's id, how it was reached and what it shows."""
    tour = [{"screen": p["id"], "kind": p.get("kind") or "page", "via": p.get("via") or p["label"],
             "text": p["text"][:1500 if p.get("kind") == "result" else 900]} for p in pages]
    if tour:     # where the app shows its own name: the browser tab's title and the frame around the pages
        tour[0].update(page_title=pages[0].get("title") or "", app_frame=pages[0].get("frame") or "")
    return tour


def _material(pages: list[dict], parts: list[str], tour: list[dict]) -> str:
    """What the facts are checked against: names and claims - the narration and everything the app's screens show
    (figures are checked against the narration alone: the screens' numbers are demo data, shown in the screenshots)."""
    return "\n".join(parts + [f"{t['via']}: {t['text']}" for t in tour] +
                     [f"{t.get('page_title', '')} {t.get('app_frame', '')}" for t in tour[:1]] +
                     [f"{p['label']}: {'; '.join(p['headings'])}" for p in pages])


def _finish(work_dir: Path, template: str, content: dict, pages: list[dict], parts: list[str], brief: dict,
            log=print, files: list[str] | None = None) -> Path:
    """The checked story saved as deck.json and built in the design: the talk track says where to show each screen in
    the app, the footer where the material came from."""
    via = {p["id"]: p.get("via") for p in pages}
    for sl in content["slides"]:
        if via.get(sl.get("screen") or "") and "In the app:" not in (sl.get("notes") or ""):
            sl["notes"] = "\n\n".join(x for x in (sl.get("notes"), f"In the app: {via[sl['screen']]}.") if x)
    _cite_charts(content, work_dir)
    for sl in content["slides"]:      # where its facts come from: in the notes, for whoever presents it
        if sl.get("sources") and "Sources:" not in (sl.get("notes") or ""):
            sl["notes"] = "\n\n".join(x for x in (sl.get("notes"), "Sources: " + "; ".join(sl["sources"])) if x)
    made_from = [x for x in ("uploaded documents" if files else "", "product narration" if parts else "",
                             "live app" if pages else "") if x]
    content["source"] = (" and ".join(made_from) if len(made_from) < 3 else "documents, narration and live app") or \
        "product narration"
    content["version"], content["brief"] = STORY_VERSION, brief
    (work_dir / "deck.json").write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    out = work_dir / deck_file(template)
    shots = {p["id"]: work_dir / "pages" / p["file"] for p in pages}
    n = design(template)(content, shots).save(out)
    log(f"Deck ready: {n} slides ({', '.join(s['type'] for s in content['slides'])}) -> {out.name}")
    _slide_sources(work_dir, template, content, out)
    return out


def _cite_charts(content: dict, work_dir: Path) -> None:
    """A chart slide that names no source cites the uploaded table its categories come from."""
    f = work_dir / "docs.json"
    if not f.exists():
        return
    tables = json.loads(f.read_text(encoding="utf-8")).get("tables", [])
    for sl in content["slides"]:
        if sl["type"] == "chart" and not sl.get("sources"):
            for t in tables:
                cells = {c.strip().lower() for r in t["rows"] for c in r}
                if all(c.strip().lower() in cells for c in sl["categories"]):
                    sl["sources"] = [t["ref"]]
                    break


def _slide_sources(work_dir: Path, template: str, content: dict, deck: Path) -> None:
    """sources.json: for each slide of the built deck (as the preview numbers them - designs add a cover and an agenda),
    the references its facts come from, matched by its headline."""
    f = work_dir / "sources.json"
    saved = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    if not any(sl.get("sources") for sl in content["slides"]):
        saved.pop(template, None)
    else:
        from pptx import Presentation
        heads = [(" ".join(str(sl.get("title") or sl.get("text") or "").split()), sl.get("sources") or [])
                 for sl in content["slides"]]
        per = []
        for slide in Presentation(deck).slides:
            text = " ".join(" ".join(sh.text_frame.text.split()) for sh in slide.shapes if sh.has_text_frame)
            per.append(next((src for h, src in heads if h and h in text), []))
        saved[template] = per
    f.write_text(json.dumps(saved, indent=1, ensure_ascii=False), encoding="utf-8")


def generate(work_dir: Path, template: str, narration: str = "", title: str = "", url: str = "",
             rewrite: bool = False, recapture: bool = False, log=print, brief: dict | None = None,
             try_forms: bool = False) -> tuple[Path, dict | None]:
    """Build the deck in the chosen design; returns its path and the story's token usage (None: story reused).
    brief: who the deck is for, how long, what to emphasise (ppt.writer.AUDIENCES / LENGTHS); a story written for
    another brief is rewritten. try_forms: while exploring, also submit forms that are already filled in."""
    brief = clean_brief(brief)
    work_dir.mkdir(parents=True, exist_ok=True)
    if url and (recapture or not (work_dir / "pages.json").exists()):
        log("Exploring the app page by page" + (" - forms already filled in are submitted" if try_forms else
                                                " (read-only)"))
        capture_app(url, work_dir, log, try_forms=try_forms)
    elif url:
        log("Reusing the explored screens")
    m = Material(work_dir, narration, url, log)
    pages, parts, tour, material, screen_ids = m.pages, m.parts, m.tour, m.text, m.screen_ids
    if m.empty():
        raise StoryError("nothing to build the deck from - give a narration of at least a few sentences, a document "
                         "with text, or an app link whose pages could be opened")
    story = work_dir / "deck.json"
    usage = None
    if not rewrite and story_is_fresh(work_dir, brief):
        log("Reusing the deck's story (deck.json) - no tokens spent")
        saved = json.loads(story.read_text(encoding="utf-8"))
        content = normalize(saved, material, screen_ids, title, "detailed" if saved.get("revised") else brief["length"],
                            brief["instructions"] + saved.get("review_notes", ""), figures=m.figures +
                            saved.get("review_notes", ""), refs=m.refs)
        content, _ = polish(content, material.split("\n"), log, repair=False, notes_from=m.notes_from)
        content.update({k: saved[k] for k in ("revised", "review_notes") if k in saved})
    else:
        focus = f", focus: {brief['focus']}" if brief["focus"] else ""
        log(f"Material: {len(parts)} narration part(s), {len(m.files())} document(s), {len(tour)} app screen(s), "
            f"{len(material.split()):,} words; for {brief['audience']}, {brief['length']} length{focus}")
        raw, usage = write_story(parts, title, tour or None, log, brief, m.documents or None)
        content = normalize(raw, material, screen_ids, title, brief["length"], brief["instructions"],
                            figures=m.figures, refs=m.refs)
        content, fix = polish(content, material.split("\n"), log, repair=True, notes_from=m.notes_from)
        usage = add_usage(usage, fix)
        for old in (work_dir / "revisions").glob("*.json") if (work_dir / "revisions").exists() else []:
            old.unlink()      # a new story: the review starts again
    return _finish(work_dir, template, content, pages, parts, brief, log, m.files()), usage


def revise(work_dir: Path, template: str, comments: list[dict], narration: str = "", title: str = "", url: str = "",
           log=print, brief: dict | None = None) -> tuple[Path, list[dict], dict]:
    """The story changed as the reviewer's comments say ([{"slide": number as shown, or None, "comment": text}]) in one
    Azure call, checked like a new story (facts from the material and the comments only), rebuilt in the design.
    Returns the deck's path, the model's report of each change, and the call's usage."""
    brief = clean_brief(brief)
    story = work_dir / "deck.json"
    if not story.exists():
        raise StoryError("there is no deck to revise yet - generate it first")
    comments = [{"slide": c.get("slide") if isinstance(c.get("slide"), int) else None,
                 "comment": str(c.get("comment") or "").strip()[:600]} for c in comments if str(c.get("comment") or "").strip()]
    if not comments:
        raise StoryError("write at least one comment")
    current = json.loads(story.read_text(encoding="utf-8"))
    built = work_dir / deck_file(template)
    if built.exists():      # what each commented slide shows: designs add slides (an agenda), so numbers alone mislead
        from pptx import Presentation
        shown = [" | ".join(" ".join(sh.text_frame.text.split()) for sh in s.shapes
                            if sh.has_text_frame and sh.text_frame.text.strip()) for s in Presentation(built).slides]
        heads = [" ".join(str(s.get("title") or s.get("text") or "").split()) for s in current["slides"]]
        for c in comments:
            if not c["slide"] or not 1 <= c["slide"] <= len(shown):
                continue
            text = shown[c["slide"] - 1]
            match = [i for i, h in enumerate(heads) if h and h in text]
            c["about"] = ("title slide" if c["slide"] == 1 else f"slides[{match[0] + 1}]" if match else
                          "agenda" if c["slide"] == 2 else f"the slide showing: {text[:300]}")
    m = Material(work_dir, narration, url, log)
    pages, parts, tour, material = m.pages, m.parts, m.tour, m.text
    notes = current.get("review_notes", "") + "\n" + "\n".join(c["comment"] for c in comments)
    log(f"Revising the deck from {len(comments)} comment(s)")
    raw, changes, usage = revise_story(current, comments, parts, tour or None, title, log, m.documents or None)
    # the comments are material too (a figure the reviewer gives may be used); a revised deck may grow to 15 slides
    content = normalize(raw, material + "\n" + notes, m.screen_ids, title, "detailed",
                        brief["instructions"] + notes, figures=m.figures + notes, refs=m.refs)
    content, fix = polish(content, (material + "\n" + notes).split("\n"), log, repair=True, notes_from=m.notes_from)
    usage = add_usage(usage, fix)
    content.update(revised=True, review_notes=notes)
    rounds = work_dir / "revisions"
    rounds.mkdir(exist_ok=True)
    n = len(list(rounds.glob("*.json"))) + 1
    (rounds / f"{n:02d}.json").write_text(json.dumps({
        "round": n, "at": datetime.datetime.now().isoformat(timespec="seconds"), "comments": comments,
        "changes": changes, "usage": usage, "before": current}, indent=2, ensure_ascii=False), encoding="utf-8")
    done = sum(1 for c in changes if c["status"] == "done")
    log(f"Review round {n}: {done} of {len(changes) or len(comments)} change(s) made")
    return _finish(work_dir, template, content, pages, parts, brief, log, m.files()), changes, usage


def report(work_dir: Path, template: str, narration: str = "", title: str = "", url: str = "", log=print,
           brief: dict | None = None, rewrite: bool = False, fmt: str = "docx") -> tuple[Path, dict | None]:
    """The report in the design's look (report.docx / report-<design>.docx, and with fmt "pdf" report*.pdf too):
    written from the material in one Azure call (saved as report.json, reused while the material and brief are
    unchanged), then built for free. Returns the file in fmt."""
    brief = clean_brief(brief)
    saved = work_dir / "report.json"
    m = Material(work_dir, narration, url, log)
    usage = None
    rep = None
    if saved.exists() and not rewrite:
        rep = json.loads(saved.read_text(encoding="utf-8"))
        fresh = (rep.get("version") == reports.REPORT_VERSION and clean_brief(rep.get("brief")) == brief and
                 all(saved.stat().st_mtime >= p.stat().st_mtime for p in _inputs(work_dir)))
        if fresh:
            log("Reusing the report's text (report.json) - no tokens spent")
        else:
            rep = None
    if rep is None:
        if m.empty():
            raise StoryError("nothing to write the report from")
        raw, usage = reports.write(m.parts, m.documents, m.tour or None, title, brief, log)
        try:
            rep = reports.check(raw, m.text, m.figures, m.docs, m.refs, title, brief["instructions"])
        except ValueError as e:
            raise StoryError(str(e)) from e
        rep["brief"] = brief
        saved.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    story = work_dir / "deck.json"
    subject = title or (json.loads(story.read_text(encoding="utf-8")).get("app_name") if story.exists() else "") or ""
    from ppt.writer import AUDIENCES
    audience = AUDIENCES[brief["audience"]][0] if brief["audience"] not in ("auto", "custom") else ""
    out = reports.build(rep, m.docs, template, work_dir / reports.report_file(template), subject, audience, m.files())
    charts, tables = sum(1 for x in rep["sections"] if x["chart"]), sum(1 for x in rep["sections"] if x["table"])
    log(f"Word report ready: {len(rep['sections'])} sections, {tables} table(s), {charts} chart(s) -> {out.name}")
    if fmt == "pdf":
        out = reports.pdf(rep, m.docs, template, work_dir / reports.report_file(template, "pdf"), subject, audience,
                          m.files())
        log(f"PDF ready -> {out.name}")
    return out, usage


def preview(work_dir: Path, template: str, log=print) -> list[str]:
    """Pictures of every slide of the built deck, for the review (work_dir/preview/<template>/NN.png)."""
    deck = work_dir / deck_file(template)
    if not deck.exists():
        return []
    names = previews.render(deck, work_dir / "preview" / template)
    log(f"Preview: {len(names)} slide pictures")
    return names


def revisions(work_dir: Path) -> list[dict]:
    """Every review round so far: when, the comments and what the model did with each (without the old story)."""
    rounds = work_dir / "revisions"
    out = []
    for f in sorted(rounds.glob("*.json")) if rounds.exists() else []:
        r = json.loads(f.read_text(encoding="utf-8"))
        out.append({k: r.get(k) for k in ("round", "at", "comments", "changes", "usage")})
    return out
