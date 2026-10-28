"""
PPT skill API (/api/ppt): pitch decks from a narration, call transcript or notes, and/or an app's link - the app is
explored page by page (ppt.capture) and its screens become material and screenshots. Independent of the video skill: a deck "from a video" is simply a deck whose narration the UI took from
that video (source_video records which one, for linking back).

Each deck lives in build/decks/<id>/ (job.json, job.log, narration.txt, and from ppt.service: pages/, pages.json,
deck.json - the story - and deck*.pptx), so the list survives restarts. Switching design reuses the story (no tokens);
'rewrite' asks Azure for a new story, 'recapture' visits the app again. Every Azure call's tokens and estimated cost
are added up in job["usage"].
"""

import datetime
import json
import re
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ppt.designs import DEFAULT, DESIGNS, catalog, deck_file
from ppt.writer import AUDIENCES, LENGTHS, clean_brief

ROOT = Path(__file__).resolve().parent.parent
DECKS_DIR = ROOT / "build" / "decks"

router = APIRouter(prefix="/api/ppt")
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
    job["pages"] = _pages(deck_id)
    job["brief"] = clean_brief(job.get("brief"))
    job["story"] = story_is_fresh(d, job["brief"])
    narration = d / "narration.txt"
    job["narration"] = narration.read_text(encoding="utf-8") if narration.exists() else ""
    try:   # how each of the user's requests turned out (Custom brief)
        job["requests"] = json.loads((d / "deck.json").read_text(encoding="utf-8")).get("requests") or []
    except (OSError, json.JSONDecodeError):
        job["requests"] = []
    with _lock:
        job["logs"] = _logs.get(deck_id, [])[-logs:]
    return job


def _worker(deck_id: str, template: str, rewrite: bool, recapture: bool) -> None:
    job = _get(deck_id)
    try:
        from pptx import Presentation

        from ppt.service import generate
        narration = _dir(deck_id) / "narration.txt"
        out, usage = generate(_dir(deck_id), template,
                              narration=narration.read_text(encoding="utf-8") if narration.exists() else "",
                              title=job.get("custom_title") or "", url=job.get("url") or "",
                              rewrite=rewrite, recapture=recapture, log=lambda m: _log(deck_id, m),
                              brief=job.get("brief"), try_forms=bool(job.get("try_forms")))
        slides = len(Presentation(out).slides)
        story = json.loads((_dir(deck_id) / "deck.json").read_text(encoding="utf-8"))
        with _lock:
            decks = {**(_jobs[deck_id].get("decks") or {}), template: {"slides": slides, "created": _now()}}
            total = dict(_jobs[deck_id].get("usage") or {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                                         "cost_usd": 0})
        if usage:
            total = {"calls": total["calls"] + 1, "input_tokens": total["input_tokens"] + usage["input_tokens"],
                     "output_tokens": total["output_tokens"] + usage["output_tokens"],
                     "cost_usd": round(total["cost_usd"] + usage["cost_usd"], 6), "model": usage["model"]}
        _update(deck_id, status="done", error=None, slides=slides, decks=decks, usage=total, last_usage=usage,
                title=job.get("custom_title") or story.get("app_name") or job["title"])
    except Exception as e:  # noqa: BLE001 - shown on the deck's page
        _log(deck_id, f"ERROR: {e}")
        _update(deck_id, status="failed", error=str(e).splitlines()[0][:300])


def _start(deck_id: str, template: str, rewrite: bool = False, recapture: bool = False) -> None:
    _update(deck_id, status="running", template=template, error=None)
    _log(deck_id, f"Generating the pitch deck ({DESIGNS[template].name})...")
    threading.Thread(target=_worker, args=(deck_id, template, rewrite, recapture), daemon=True).start()


def _check_template(template: str) -> None:
    if template not in DESIGNS:
        raise HTTPException(422, f"Unknown deck design '{template}'")


class NewDeck(BaseModel):
    narration: str = ""        # narration, call transcript or notes
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
    return [{**j, "pages": len(_pages(j["id"]))} for j in jobs]


@router.post("/decks")
def create_deck(body: NewDeck):
    url, narration = body.url.strip(), body.narration.strip()
    if url and not re.match(r"^https?://", url):
        raise HTTPException(422, "The app link must start with http:// or https://")
    if len(narration.split()) < 20 and not url:
        raise HTTPException(422, "Give your app's link, or a narration, transcript or notes of at least a few sentences")
    _check_template(body.template)
    deck_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    _dir(deck_id).mkdir(parents=True)
    if narration:
        (_dir(deck_id) / "narration.txt").write_text(narration, encoding="utf-8")
    title = body.title.strip()
    fallback = body.source_title.strip() or (re.sub(r"^www\.", "", url.split("/")[2]) if url else "Untitled deck")
    job = {"id": deck_id, "url": url, "title": title or fallback, "custom_title": title, "created": _now(),
           "status": "running", "template": body.template, "error": None, "decks": {},
           "source_video": body.source_video.strip(), "source_title": body.source_title.strip(),
           "try_forms": bool(url and body.try_forms),
           "brief": clean_brief({"audience": body.audience, "length": body.length, "focus": body.focus,
                                 "instructions": body.instructions})}
    with _lock:
        _jobs[deck_id] = job
        _logs[deck_id] = []
        _save(job)
    origin = f"the video '{job['source_title']}'" if job["source_video"] else "the narration" if narration else "the app"
    _log(deck_id, f"Deck created from {origin}" + (f", exploring {url}" if url else ""))
    _start(deck_id, body.template)
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


@router.get("/decks/{deck_id}/pages/{file}")
def page_shot(deck_id: str, file: str):
    _get(deck_id)
    if not re.fullmatch(r"\d{2}\.png", file) or not (_dir(deck_id) / "pages" / file).exists():
        raise HTTPException(404, "No such screenshot")
    return FileResponse(_dir(deck_id) / "pages" / file)


@router.get("/decks/{deck_id}/files/{name}")
def deck_download(deck_id: str, name: str):
    job = _get(deck_id)
    if name not in {deck_file(t) for t in DESIGNS} or not (_dir(deck_id) / name).exists():
        raise HTTPException(404, "Not generated yet")
    safe = re.sub(r"[^\w\- ]+", "", job["title"]).strip() or "Pitch deck"
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
