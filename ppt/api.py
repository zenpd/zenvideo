"""
PPT skill API (/api/ppt): pitch decks from a narration, call transcript or notes, uploaded documents (Word, PDF,
Excel - ppt.documents) and/or an app's link - the app is explored page by page (ppt.capture) and its screens become
material and screenshots. With "report", a Word report is written from the same material too (ppt.report).
"output" picks what is made: "pptx" (the deck, as above), or "docx" / "pdf" - only the document (the report, in
DOC_DESIGN's look), without slides; it is ready ("done") as soon as it is written. Independent of the video skill: a deck "from a video" is simply a deck whose narration the UI took from
that video (source_video records which one, for linking back).

Each deck lives in build/decks/<id>/ (job.json, job.log, narration.txt, and from ppt.service: pages/, pages.json,
deck.json - the story - deck*.pptx, preview/<design>/ - a picture of every slide - and revisions/; with documents
docs/ - the uploaded files - docs.json and sources.json; with a report report.json and report*.docx), so the list
survives restarts.

Review before it is final: a generated deck is "review" - the studio shows every slide; the user comments on slides or
the whole deck and "revise" has Azure change the story accordingly (one call, same fact checks), rebuilt and shown
again, as often as needed; "approve" makes it final ("done"). Switching design keeps an approved story approved. Switching design reuses the story (no tokens);
'rewrite' asks Azure for a new story, 'recapture' visits the app again. Every Azure call's tokens and estimated cost
are added up in job["usage"].
"""

import base64
import binascii
import datetime
import hashlib
import json
import re
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from ppt import documents
from ppt.designs import DEFAULT, DESIGNS, catalog, deck_file
from ppt.report import report_file
from ppt.writer import AUDIENCES, LENGTHS, add_usage, clean_brief

ROOT = Path(__file__).resolve().parent.parent
DECKS_DIR = ROOT / "build" / "decks"

router = APIRouter(prefix="/api/ppt")
OUTPUTS = ("pptx", "docx", "pdf")
DOC_DESIGN = "consulting"        # the look of a Word or PDF document made without a deck: navy and teal, Arial
_lock = threading.RLock()
_jobs: dict[str, dict] = {}
_logs: dict[str, list[str]] = {}


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _dir(deck_id: str) -> Path:
    return DECKS_DIR / deck_id


def _save(job: dict) -> None:
    job["updated"] = _now()
    (_dir(job["id"]) / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")


def _update(deck_id: str, **fields) -> dict:
    with _lock:
        job = _jobs[deck_id]
        job.update(fields)
        _save(job)
        return job


def _log(deck_id: str, msg: str) -> None:
    line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
    with _lock:
        _logs.setdefault(deck_id, []).append(line)
    with open(_dir(deck_id) / "job.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load() -> None:
    DECKS_DIR.mkdir(parents=True, exist_ok=True)
    for f in DECKS_DIR.glob("*/job.json"):
        job = json.loads(f.read_text(encoding="utf-8"))
        if job["status"] == "running":
            job.update(status="failed", error="Interrupted: the server was restarted.")
            _save(job)
        _jobs[job["id"]] = job
        log = f.parent / "job.log"
        _logs[job["id"]] = log.read_text(encoding="utf-8").splitlines() if log.exists() else []


_load()


def _get(deck_id: str) -> dict:
    with _lock:
        if deck_id not in _jobs:
            raise HTTPException(404, "No such deck")
        return _jobs[deck_id]


def _pages(deck_id: str) -> list[dict]:
    f = _dir(deck_id) / "pages.json"
    pages = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    return [{"id": p["id"], "label": p["label"], "file": p["file"], "via": p.get("via") or "",
             "kind": p.get("kind") or "page"} for p in pages
            if (_dir(deck_id) / "pages" / p["file"]).exists()]


def _view(deck_id: str, logs: int = 40) -> dict:
    from ppt.service import story_is_fresh

    job = dict(_get(deck_id))
    d = _dir(deck_id)
    job["files"] = {deck_file(t): (d / deck_file(t)).exists() for t in DESIGNS}
    job["output"] = job.get("output") or "pptx"
    job["report_files"] = {t: (d / report_file(t)).exists() for t in DESIGNS}
    job["pdf_files"] = {t: (d / report_file(t, "pdf")).exists() for t in DESIGNS}
    job["documents"], job["document_notes"] = [], []
    if (d / "docs.json").exists():
        docs = json.loads((d / "docs.json").read_text(encoding="utf-8"))
        job["documents"], job["document_notes"] = documents.summary(docs), docs.get("warnings") or []
    elif (d / "docs").exists():      # uploaded, not read yet
        job["documents"] = [{"name": f.name, "kind": documents.KINDS.get(f.suffix.lower(), ""), "sections": 0,
                             "tables": 0, "words": 0} for f in sorted((d / "docs").iterdir())]
    job["gaps"], job["report"], job["slide_sources"] = [], None, []
    try:
        story = json.loads((d / "deck.json").read_text(encoding="utf-8"))
        job["gaps"] = story.get("gaps") or []
    except (OSError, json.JSONDecodeError):
        pass
    try:
        rep = json.loads((d / "report.json").read_text(encoding="utf-8"))
        job["report"] = {"title": rep["title"], "sections": len(rep["sections"]),
                         "tables": sum(1 for x in rep["sections"] if x["table"]),
                         "charts": sum(1 for x in rep["sections"] if x["chart"]), "gaps": rep.get("gaps") or []}
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    try:
        job["slide_sources"] = json.loads((d / "sources.json").read_text(encoding="utf-8")).get(job.get("template") or "", [])
    except (OSError, json.JSONDecodeError):
        pass
    job["pages"] = _pages(deck_id)
    job["brief"] = clean_brief(job.get("brief"))
    job["story"] = story_is_fresh(d, job["brief"])
    narration = d / "narration.txt"
    job["narration"] = narration.read_text(encoding="utf-8") if narration.exists() else ""
    try:   # how each of the user's requests turned out (Custom brief)
        job["requests"] = json.loads((d / "deck.json").read_text(encoding="utf-8")).get("requests") or []
    except (OSError, json.JSONDecodeError):
        job["requests"] = []
    from ppt.service import revisions
    shown = d / "preview" / (job.get("template") or "")
    job["preview"] = sorted(p.name for p in shown.glob("[0-9][0-9].png")) if job.get("template") and shown.exists() else []
    job["revisions"] = revisions(d)
    with _lock:
        job["logs"] = _logs.get(deck_id, [])[-logs:]
    return job


def _story_hash(deck_id: str) -> str:
    """A fingerprint of the deck's story - what the user approves (the design can change without a new review)."""
    try:
        story = json.loads((_dir(deck_id) / "deck.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    keep = {k: story.get(k) for k in ("app_name", "tagline", "pitch", "slides")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:16]


def _worker(deck_id: str, template: str, rewrite: bool, recapture: bool, comments: list | None = None,
            report_only: bool = False) -> None:
    job = _get(deck_id)
    try:
        from pptx import Presentation

        from ppt.service import generate, preview, report, revise
        narration = _dir(deck_id) / "narration.txt"
        common = dict(narration=narration.read_text(encoding="utf-8") if narration.exists() else "",
                      title=job.get("custom_title") or "", url=job.get("url") or "", log=lambda m: _log(deck_id, m),
                      brief=job.get("brief"))
        calls, usage = 0, None
        output = job.get("output") or "pptx"
        report_only = report_only or output != "pptx"
        if not report_only:
            if comments:
                out, changes, usage = revise(_dir(deck_id), template, comments, **common)
            else:
                out, usage = generate(_dir(deck_id), template, rewrite=rewrite, recapture=recapture,
                                      try_forms=bool(job.get("try_forms")), **common)
            calls += 1 if usage else 0
            preview(_dir(deck_id), template, log=lambda m: _log(deck_id, m))
        if job.get("report") and not comments:      # the report follows the material, not the review comments
            _, used = report(_dir(deck_id), template, rewrite=rewrite, fmt="pdf" if output == "pdf" else "docx", **common)
            if used:
                calls += 1
                usage = add_usage(usage, used)
        if output != "pptx":                          # a document alone: ready as soon as it is written
            with _lock:
                total = dict(_jobs[deck_id].get("usage") or {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                                             "cost_usd": 0})
            if usage:
                total = {"calls": total["calls"] + calls, "input_tokens": total["input_tokens"] + usage["input_tokens"],
                         "output_tokens": total["output_tokens"] + usage["output_tokens"],
                         "cost_usd": round(total["cost_usd"] + usage["cost_usd"], 6), "model": usage["model"]}
            written = json.loads((_dir(deck_id) / "report.json").read_text(encoding="utf-8"))
            _update(deck_id, status="done", error=None, usage=total, last_usage=usage or job.get("last_usage"),
                    title=job.get("custom_title") or written.get("title") or job["title"])
            return
        out = _dir(deck_id) / deck_file(template)
        if not out.exists():
            raise RuntimeError("The deck isn't generated in this design yet")
        slides = len(Presentation(out).slides)
        story = json.loads((_dir(deck_id) / "deck.json").read_text(encoding="utf-8"))
        with _lock:
            decks = {**(_jobs[deck_id].get("decks") or {}), template: {"slides": slides, "created": _now()}}
            total = dict(_jobs[deck_id].get("usage") or {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                                         "cost_usd": 0})
        if usage:
            total = {"calls": total["calls"] + max(calls, 1), "input_tokens": total["input_tokens"] + usage["input_tokens"],
                     "output_tokens": total["output_tokens"] + usage["output_tokens"],
                     "cost_usd": round(total["cost_usd"] + usage["cost_usd"], 6), "model": usage["model"]}
        # a story the user has not approved yet waits for their review; an approved one stays approved
        approved = bool(job.get("approved")) and job.get("approved") == _story_hash(deck_id)
        _update(deck_id, status="done" if approved else "review", error=None, slides=slides, decks=decks, usage=total,
                last_usage=usage or job.get("last_usage"), title=job.get("custom_title") or story.get("app_name") or job["title"])
    except Exception as e:  # noqa: BLE001 - shown on the deck's page
        _log(deck_id, f"ERROR: {e}")
        _update(deck_id, status="failed", error=str(e).splitlines()[0][:300])


def _start(deck_id: str, template: str, rewrite: bool = False, recapture: bool = False,
           comments: list | None = None, report_only: bool = False) -> None:
    _update(deck_id, status="running", template=template, error=None)
    kind = {"docx": "Word document", "pdf": "PDF document"}.get(_jobs[deck_id].get("output") or "", "")
    _log(deck_id, f"Revising the pitch deck ({DESIGNS[template].name})..." if comments else
         f"Writing the {kind}..." if kind else
         f"Writing the Word report ({DESIGNS[template].name} design)..." if report_only else
         f"Generating the pitch deck ({DESIGNS[template].name})...")
    threading.Thread(target=_worker, args=(deck_id, template, rewrite, recapture, comments, report_only),
                     daemon=True).start()


def _check_template(template: str) -> None:
    if template not in DESIGNS:
        raise HTTPException(422, f"Unknown deck design '{template}'")


class Upload(BaseModel):
    name: str                  # the file's name (.docx, .pdf or .xlsx)
    data: str                  # its content, base64 (a data: URL is fine)


class NewDeck(BaseModel):
    narration: str = ""        # narration, call transcript or notes
    files: list[Upload] = []   # documents: Word, PDF, Excel (ppt.documents)
    report: bool = False       # also write a Word report from the same material
    output: str = "pptx"       # pptx: the deck; docx or pdf: only the document (the report), no slides
    url: str = ""              # the app's link: explored page by page (narration and/or url)
    try_forms: bool = False    # while exploring, submit forms that are already filled in (demo/test apps only)
    title: str = ""
    template: str = DEFAULT
    source_video: str = ""     # the video this narration came from (for linking back)
    source_title: str = ""
    audience: str = "auto"     # who the deck is for (ppt.writer.AUDIENCES)
    length: str = "standard"   # short / standard / detailed
    focus: str = ""            # what to emphasise
    instructions: str = ""     # audience "custom": the user's own requests (charts, slide order, ...)


class Build(BaseModel):
    template: str = DEFAULT
    rewrite: bool = False      # ask Azure for a new story
    recapture: bool = False    # visit the app again for fresh screens (implies a new story)
    audience: str | None = None    # a changed brief (any of these) means a new story
    length: str | None = None
    focus: str | None = None
    instructions: str | None = None


@router.get("/brief-options")
def brief_options():
    """The choices for a deck's brief: who it is for, and how long."""
    return {"audiences": [{"id": k, "label": v[0], "hint": v[1]} for k, v in AUDIENCES.items()],  # v[2]: for the AI
            "lengths": [{"id": k, "label": v[0], "slides": f"{v[1]}-{v[2]}"} for k, v in LENGTHS.items()]}


@router.get("/templates")
def templates():
    """Designs a deck can be generated in (the first is the default)."""
    return catalog()


@router.get("/templates/{template}/sample")
def template_sample(template: str):
    """The sample deck a design is based on, to look at in PowerPoint."""
    design = DESIGNS.get(template)
    if not design or not (design.sample and design.sample.exists()):
        raise HTTPException(404, "No sample deck for this design")
    return FileResponse(design.sample, filename=f"Sample - {design.name}.pptx")


@router.get("/decks")
def list_decks(video: str = ""):
    with _lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["created"], reverse=True)
    if video:
        jobs = [j for j in jobs if j.get("source_video") == video]
    return [{**j, "pages": len(_pages(j["id"])),
             "documents": len(list((_dir(j["id"]) / "docs").iterdir())) if (_dir(j["id"]) / "docs").exists() else 0}
            for j in jobs]


def _uploads(files: list[Upload]) -> list[tuple[str, bytes]]:
    """The uploaded documents, checked: Word, PDF or Excel, at most MAX_FILES, each within MAX_BYTES."""
    if len(files) > documents.MAX_FILES:
        raise HTTPException(422, f"Upload at most {documents.MAX_FILES} documents")
    out, seen = [], set()
    for f in files:
        name = re.sub(r"[^\w\-. ()]+", "_", Path(f.name).name).strip(" .") or "document"
        if Path(name).suffix.lower() not in documents.KINDS:
            raise HTTPException(422, f"“{f.name}” isn't a Word (.docx), PDF or Excel (.xlsx) file")
        try:
            data = base64.b64decode(f.data.split(",", 1)[1] if f.data.startswith("data:") else f.data, validate=True)
        except (binascii.Error, ValueError, IndexError):
            raise HTTPException(422, f"“{f.name}” couldn't be uploaded - try again") from None
        if not data:
            raise HTTPException(422, f"“{f.name}” is empty")
        if len(data) > documents.MAX_BYTES:
            raise HTTPException(422, f"“{f.name}” is over {documents.MAX_BYTES // 2**20} MB")
        while name.lower() in seen:          # two files with one name: keep both
            name = f"{Path(name).stem} (2){Path(name).suffix}"
        seen.add(name.lower())
        out.append((name, data))
    return out


@router.post("/decks")
def create_deck(body: NewDeck):
    url, narration = body.url.strip(), body.narration.strip()
    if url and not re.match(r"^https?://", url):
        raise HTTPException(422, "The app link must start with http:// or https://")
    uploads = _uploads(body.files)
    output = body.output if body.output in OUTPUTS else "pptx"
    template = body.template if output == "pptx" else DOC_DESIGN
    if len(narration.split()) < 20 and not url and not uploads:
        raise HTTPException(422, "Upload a document, give your app's link, or write a narration, transcript or notes "
                                 "of at least a few sentences")
    _check_template(template)
    deck_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    _dir(deck_id).mkdir(parents=True)
    if narration:
        (_dir(deck_id) / "narration.txt").write_text(narration, encoding="utf-8")
    if uploads:
        (_dir(deck_id) / "docs").mkdir()
        for name, data in uploads:
            (_dir(deck_id) / "docs" / name).write_bytes(data)
    title = body.title.strip()
    fallback = body.source_title.strip() or (re.sub(r"^www\.", "", url.split("/")[2]) if url else
                                             Path(uploads[0][0]).stem.replace("_", " ") if uploads else "Untitled deck")
    job = {"id": deck_id, "url": url, "title": title or fallback, "custom_title": title, "created": _now(),
           "status": "running", "template": template, "error": None, "decks": {}, "output": output,
           "source_video": body.source_video.strip(), "source_title": body.source_title.strip(),
           "try_forms": bool(url and body.try_forms), "report": bool(body.report) or output != "pptx",
           "brief": clean_brief({"audience": body.audience, "length": body.length, "focus": body.focus,
                                 "instructions": body.instructions})}
    with _lock:
        _jobs[deck_id] = job
        _logs[deck_id] = []
        _save(job)
    origin = (f"the video '{job['source_title']}'" if job["source_video"] else
              f"{len(uploads)} document(s)" + (" and the narration" if narration else "") if uploads else
              "the narration" if narration else "the app")
    made = {"docx": "Word document", "pdf": "PDF document"}.get(output, "Deck")
    _log(deck_id, f"{made} created from {origin}" + (f", exploring {url}" if url else "") +
         (" - with a Word report" if body.report and output == "pptx" else ""))
    _start(deck_id, template)
    return _view(deck_id)


@router.get("/decks/{deck_id}")
def get_deck(deck_id: str):
    return _view(deck_id)


@router.post("/decks/{deck_id}/build")
def build_deck(deck_id: str, body: Build):
    job = _get(deck_id)
    _check_template(body.template)
    if job["status"] == "running":
        raise HTTPException(409, "A deck is already being generated")
    if body.recapture and not job.get("url"):
        raise HTTPException(409, "This deck has no app link to capture")
    if any(v is not None for v in (body.audience, body.length, body.focus, body.instructions)):
        old = clean_brief(job.get("brief"))
        _update(deck_id, brief=clean_brief({
            "audience": old["audience"] if body.audience is None else body.audience,
            "length": old["length"] if body.length is None else body.length,
            "focus": old["focus"] if body.focus is None else body.focus,
            "instructions": old["instructions"] if body.instructions is None else body.instructions}))
    _start(deck_id, body.template, rewrite=body.rewrite or body.recapture, recapture=body.recapture)
    return _view(deck_id)


class Comment(BaseModel):
    slide: int | None = None   # the slide's number as the preview shows it (1: the title slide); None: the whole deck
    comment: str


class Revise(BaseModel):
    template: str = DEFAULT
    comments: list[Comment]


@router.post("/decks/{deck_id}/revise")
def revise_deck(deck_id: str, body: Revise):
    """Change the deck as the review comments say (one Azure call), rebuild it and its preview; it stays in review."""
    job = _get(deck_id)
    _check_template(body.template)
    if job["status"] == "running":
        raise HTTPException(409, "The deck is being generated")
    comments = [c.model_dump() for c in body.comments if c.comment.strip()]
    if not comments:
        raise HTTPException(422, "Write at least one comment")
    if len(comments) > 30:
        raise HTTPException(422, "At most 30 comments at a time")
    _update(deck_id, approved=None)
    _start(deck_id, body.template, comments=comments)
    return _view(deck_id)


@router.post("/decks/{deck_id}/approve")
def approve_deck(deck_id: str):
    """The user is happy with the deck: it is final (and stays so when another design is generated)."""
    job = _get(deck_id)
    if job["status"] == "running":
        raise HTTPException(409, "The deck is being generated")
    if not (_dir(deck_id) / deck_file(job["template"])).exists():
        raise HTTPException(409, "There is no deck to approve yet")
    _update(deck_id, status="done", approved=_story_hash(deck_id), approved_at=_now())
    _log(deck_id, "Deck approved")
    return _view(deck_id)


class ReportBody(BaseModel):
    template: str = DEFAULT
    rewrite: bool = False      # write the report's text again (one AI call); otherwise only a missing one is written
    audience: str | None = None    # a changed brief (any of these) is saved first, and means new text
    length: str | None = None
    focus: str | None = None
    instructions: str | None = None


@router.post("/decks/{deck_id}/report")
def write_report(deck_id: str, body: ReportBody):
    """Write the Word report from the deck's material (one AI call), or rebuild it in this design (free); from now on
    it follows the deck (a new story or design builds it too)."""
    job = _get(deck_id)
    _check_template(body.template)
    if job["status"] == "running":
        raise HTTPException(409, "The deck is being generated")
    rewrite = body.rewrite
    if any(v is not None for v in (body.audience, body.length, body.focus, body.instructions)):
        old = clean_brief(job.get("brief"))
        new = clean_brief({"audience": old["audience"] if body.audience is None else body.audience,
                           "length": old["length"] if body.length is None else body.length,
                           "focus": old["focus"] if body.focus is None else body.focus,
                           "instructions": old["instructions"] if body.instructions is None else body.instructions})
        rewrite = rewrite or new != old
        _update(deck_id, brief=new)
    template = body.template if (job.get("output") or "pptx") == "pptx" else job["template"]
    _update(deck_id, report=True)
    _start(deck_id, template, rewrite=rewrite, report_only=True)
    return _view(deck_id)


@router.get("/decks/{deck_id}/report/preview", response_class=HTMLResponse)
def report_preview(deck_id: str, template: str = DEFAULT):
    """The Word report as a web page, to read before downloading it."""
    from ppt.report import html
    from ppt.writer import AUDIENCES

    job = _get(deck_id)
    _check_template(template)
    d = _dir(deck_id)
    if not (d / "report.json").exists():
        raise HTTPException(404, "No report written yet")
    rep = json.loads((d / "report.json").read_text(encoding="utf-8"))
    docs = json.loads((d / "docs.json").read_text(encoding="utf-8")) if (d / "docs.json").exists() else None
    brief = clean_brief(job.get("brief"))
    story = json.loads((d / "deck.json").read_text(encoding="utf-8")) if (d / "deck.json").exists() else {}
    page = html(rep, docs, template, job.get("custom_title") or story.get("app_name") or "",
                AUDIENCES[brief["audience"]][0] if brief["audience"] not in ("auto", "custom") else "",
                [f["name"] for f in documents.summary(docs)])
    return HTMLResponse(page, headers={"Cache-Control": "no-cache"})


@router.get("/decks/{deck_id}/preview/{template}/{file}")
def preview_picture(deck_id: str, template: str, file: str):
    _get(deck_id)
    _check_template(template)
    path = _dir(deck_id) / "preview" / template / file
    if not re.fullmatch(r"\d{2}(\.thumb\.jpg|\.png)", file) or not path.exists():
        raise HTTPException(404, "No such slide picture")
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


@router.get("/decks/{deck_id}/pages/{file}")
def page_shot(deck_id: str, file: str):
    _get(deck_id)
    if not re.fullmatch(r"\d{2}\.png", file) or not (_dir(deck_id) / "pages" / file).exists():
        raise HTTPException(404, "No such screenshot")
    return FileResponse(_dir(deck_id) / "pages" / file)


@router.get("/decks/{deck_id}/files/{name}")
def deck_download(deck_id: str, name: str):
    job = _get(deck_id)
    safe = re.sub(r"[^\w\- ]+", "", job["title"]).strip() or "Pitch deck"
    reports = {report_file(t, fmt): (t, fmt) for t in DESIGNS for fmt in ("docx", "pdf")}
    if name in reports and (_dir(deck_id) / name).exists():
        t, fmt = reports[name]
        label = f" - Report ({DESIGNS[t].name})" if (job.get("output") or "pptx") == "pptx" else ""
        return FileResponse(_dir(deck_id) / name, filename=f"{safe}{label}.{fmt}")
    if name not in {deck_file(t) for t in DESIGNS} or not (_dir(deck_id) / name).exists():
        raise HTTPException(404, "Not generated yet")
    return FileResponse(_dir(deck_id) / name, filename=f"{safe} - {DESIGNS[next(t for t in DESIGNS if deck_file(t) == name)].name}.pptx")


@router.delete("/decks/{deck_id}")
def delete_deck(deck_id: str):
    job = _get(deck_id)
    if job["status"] == "running":
        raise HTTPException(409, "This deck is still being generated")
    with _lock:
        _jobs.pop(deck_id, None)
        _logs.pop(deck_id, None)
    shutil.rmtree(_dir(deck_id), ignore_errors=True)
    return {"deleted": deck_id}
