"""
Explainer skill API (/api/explainer): animated videos from a narration - motion graphics ("explainer"), two people
talking in an office ("conversation") or two presenters in a branded studio ("presenters", with the company's logo).
Independent of the demo-video and PPT skills. Videos made with the command line (python -m explainer, into
build/explainers/<name>/) show here too, while they are being made: the command line keeps its own job.json and
job.log up to date (read from disk on every request); a folder without them is shown from the files it holds.

Each video lives in build/explainers/<id>/ (job.json, job.log, and from explainer.service: narration.txt, plan.json -
the scenes - timeline.json, audio/, player.html, final.mp4, final.srt), so the list survives restarts. Changing the
theme, voice or captions reuses the plan (no tokens); 'replan' asks Azure for new scenes. Every Azure call's tokens
and estimated cost are added up in job["usage"].
"""

import base64
import binascii
import datetime
import io
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from explainer.dialogue import CAST, DEFAULT_CAST, DEFAULT_STUDIO, STUDIO_CAST, presets_for
from explainer.planner import MODES
from explainer.render import THEMES
from explainer.service import STYLES

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT / "build" / "explainers"
CAPTIONS = ("soft", "burned", "none")

router = APIRouter(prefix="/api/explainer")
_lock = threading.RLock()
_jobs: dict[str, dict] = {}
_logs: dict[str, list[str]] = {}


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _dir(video_id: str) -> Path:
    return VIDEOS_DIR / video_id


def _save(job: dict) -> None:
    job["updated"] = _now()
    (_dir(job["id"]) / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")


def _update(video_id: str, **fields) -> dict:
    with _lock:
        job = _jobs[video_id]
        job.update(fields)
        _save(job)
        return job


def _log(video_id: str, msg: str) -> None:
    line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
    with _lock:
        _logs.setdefault(video_id, []).append(line)
    with open(_dir(video_id) / "job.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load() -> None:
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    for f in VIDEOS_DIR.glob("*/job.json"):
        job = json.loads(f.read_text(encoding="utf-8"))
        if job["status"] == "running" and job.get("source") != "command line":
            job.update(status="failed", error="Interrupted: the server was restarted.")
            _save(job)
        _jobs[job["id"]] = job
        log = f.parent / "job.log"
        _logs[job["id"]] = log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _adopt(d: Path) -> None:
    """A job for a video made with the command line, from what its folder holds (the plan, the timeline)."""
    try:
        plan = json.loads((d / "plan.json").read_text(encoding="utf-8"))
        tl = json.loads((d / "timeline.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    made = plan.get("made_for") or {}
    style = plan.get("style") if plan.get("style") in ("conversation", "presenters") else "explainer"
    cast = [c.get("id") for c in plan.get("cast") or []] or list(DEFAULT_STUDIO if style == "presenters" else DEFAULT_CAST)
    stamp = datetime.datetime.fromtimestamp((d / "final.mp4").stat().st_mtime).isoformat(timespec="seconds")
    job = {"id": d.name, "title": plan.get("app_name") or plan.get("title") or d.name, "custom_title": made.get("title", ""),
           "created": stamp, "built": stamp, "status": "done", "error": None, "progress": 1, "style": style, "cast": cast,
           "voices": ["", ""], "theme": "midnight", "voice": tl.get("voice") or "af_sky", "speed": 1.0,
           "mode": made.get("mode", plan.get("mode", "as_written")), "seconds": made.get("seconds", 120),
           "captions": "soft", "music": True, "brand_name": tl.get("brand_name", ""),
           "duration": round(tl.get("duration", 0), 1), "scenes_count": len(plan.get("scenes") or plan.get("lines") or []),
           "source": "command line"}
    _jobs[job["id"]] = job
    _logs[job["id"]] = []
    _save(job)


STALE = 900      # a command-line run whose files have not changed for 15 minutes has stopped


def _newest(d: Path) -> float:
    return max((p.stat().st_mtime for p in d.rglob("*") if p.is_file()), default=0.0)


def _in_progress(d: Path) -> dict | None:
    """A command-line run that started without a job record, still going: its stage from the files written so far."""
    if not (d / "narration.txt").exists() or (d / "final.mp4").exists() or time.time() - _newest(d) > STALE:
        return None
    plan = tl = {}
    try:
        plan = json.loads((d / "plan.json").read_text(encoding="utf-8"))
        tl = json.loads((d / "timeline.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    stage, progress = "Writing the script", 0.0
    if plan:
        stage = "Voicing the script"
    if tl and (d / "player.html").exists():      # frames: about 13 a second in 4 browsers
        took = time.time() - (d / "player.html").stat().st_mtime
        progress = round(min(0.97, took / max(30.0, tl["duration"] * 30 / 13)), 3)
        stage = f"Animating · about {round(progress * 100)}%"
    started = datetime.datetime.fromtimestamp((d / "narration.txt").stat().st_mtime).isoformat(timespec="seconds")
    style = plan.get("style") if plan.get("style") in ("conversation", "presenters") else "explainer"
    return {"id": d.name, "title": plan.get("app_name") or plan.get("title") or d.name, "custom_title": "",
            "created": started, "status": "running", "error": None, "progress": progress, "stage": stage,
            "style": style, "cast": [c.get("id") for c in plan.get("cast") or []] or list(DEFAULT_CAST),
            "voices": ["", ""], "theme": "midnight", "voice": "af_sky", "speed": 1.0, "mode": "as_written",
            "seconds": (plan.get("made_for") or {}).get("seconds", 120), "captions": "soft", "music": True,
            "brand_name": "", "source": "command line", "external": True}


def _adopt_all() -> None:
    """Bring in what the command line is doing or has done: its own job records (re-read every time, it keeps them
    up to date), finished videos without a record, and runs still going without one."""
    for d in VIDEOS_DIR.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        rec = d / "job.json"
        if rec.exists():
            known = _jobs.get(d.name)
            if known is None or known.get("source") == "command line":
                try:
                    job = json.loads(rec.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue        # being written right now
                if job.get("status") == "running" and time.time() - _newest(d) > STALE:
                    job.update(status="failed", error="The command-line run stopped.")
                _jobs[d.name] = job
                log = d / "job.log"
                _logs[d.name] = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        elif (d / "final.mp4").exists():
            if d.name not in _jobs or _jobs[d.name].get("external"):
                _jobs.pop(d.name, None)
                _adopt(d)
        else:
            job = _in_progress(d)
            if job:
                _jobs[d.name] = job
                _logs[d.name] = [f"[{datetime.datetime.now():%H:%M:%S}] {job['stage']} (started from the command line)"]
            elif _jobs.get(d.name, {}).get("external"):
                _jobs.pop(d.name, None)


_load()
_adopt_all()


def _get(video_id: str) -> dict:
    with _lock:
        if video_id not in _jobs:
            raise HTTPException(404, "No such video")
        return _jobs[video_id]


def _view(video_id: str, logs: int = 40) -> dict:
    job = dict(_get(video_id))
    d = _dir(video_id)
    narration = d / "narration.txt"
    job["narration"] = narration.read_text(encoding="utf-8") if narration.exists() else ""
    try:   # what each scene shows and says, for the scene list
        tl = json.loads((d / "timeline.json").read_text(encoding="utf-8"))
        if tl.get("style") in ("conversation", "presenters"):    # one entry per line: who says it, the screen
            names = [c["name"] for c in tl["cast"]]
            job["scenes"] = [{"type": "line", "speaker": names[ln["speaker"]], "start": ln["start"], "end": ln["end"],
                              "say": ln["say"], "title": (ln.get("screen") or {}).get("title") or ""} for ln in tl["lines"]]
        else:
            job["scenes"] = [{"type": s["type"], "start": s["start"], "end": s["end"], "say": s["say"],
                              "title": s.get("title") or s.get("text") or ""} for s in tl["scenes"]]
    except (OSError, json.JSONDecodeError, KeyError):
        job["scenes"] = []
    job["files"] = {n: (d / n).exists() for n in ("final.mp4", "final.srt", "player.html", "poster.jpg", "logo.png")}
    with _lock:
        job["logs"] = _logs.get(video_id, [])[-logs:]
    return job


def _settings(job: dict) -> dict:
    return {"style": "explainer", "cast": list(DEFAULT_CAST), "voices": ["", ""], "brand_name": "",   # older videos
            **{k: job[k] for k in ("theme", "voice", "speed", "mode", "seconds", "captions", "music", "style", "cast",
                                   "voices", "brand_name") if k in job}}


def _worker(video_id: str, replan: bool) -> None:
    job = _get(video_id)
    last = [0.0]

    def progress(p: float) -> None:     # saved at most every 2%
        if p - last[0] >= 0.02 or p >= 1:
            last[0] = p
            _update(video_id, progress=round(p, 3), stage=f"Animating · {round(p * 100)}%")

    try:
        from demo import media
        from explainer.service import generate, stage_of
        s = _settings(job)
        out, usage = generate(_dir(video_id), "", title=job.get("custom_title") or "", theme=s["theme"],
                              voice=s["voice"], speed=s["speed"], mode=s["mode"], target_seconds=s["seconds"],
                              captions=s["captions"], music=s["music"], replan=replan,
                              log=lambda m: (_log(video_id, m), (st := stage_of(m)) and _update(video_id, stage=st)),
                              progress=progress, style=s["style"],
                              cast=tuple(s["cast"]), voices=tuple(s["voices"]), brand_name=s["brand_name"],
                              logo=_dir(video_id) / "logo.png" if (_dir(video_id) / "logo.png").exists() else None)
        plan = json.loads((_dir(video_id) / "plan.json").read_text(encoding="utf-8"))
        with _lock:
            total = dict(_jobs[video_id].get("usage") or {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                                          "cost_usd": 0})
        if usage:
            total = {"calls": total["calls"] + 1, "input_tokens": total["input_tokens"] + usage["input_tokens"],
                     "output_tokens": total["output_tokens"] + usage["output_tokens"],
                     "cost_usd": round(total["cost_usd"] + usage["cost_usd"], 6), "model": usage["model"]}
        _update(video_id, status="done", error=None, progress=1, stage="", usage=total, last_usage=usage,
                duration=round(media.duration(out), 1), scenes_count=len(plan.get("scenes") or plan.get("lines") or []),
                built=_now(),
                title=job.get("custom_title") or plan.get("app_name") or plan.get("title") or job["title"])
    except Exception as e:  # noqa: BLE001 - shown on the video's page
        _log(video_id, f"ERROR: {e}")
        _update(video_id, status="failed", error=str(e).splitlines()[0][:300])


def _start(video_id: str, replan: bool = False) -> None:
    _update(video_id, status="running", error=None, progress=0, stage="Starting")
    _log(video_id, "Making the animated video...")
    threading.Thread(target=_worker, args=(video_id, replan), daemon=True).start()


class Look(BaseModel):
    style: str = "explainer"   # explainer (motion graphics) or conversation (two people in an office)
    cast: list[str] = list(DEFAULT_CAST)   # conversation: who asks, who explains (explainer.dialogue.CAST);
                                           # presenters: the two presenters (STUDIO_CAST)
    brand_name: str = ""                   # presenters: the company's name (shown when there is no logo)
    voices: list[str] = ["", ""]           # conversation: their voices ("" = the person's own)
    theme: str = "midnight"
    voice: str = "af_sky"
    speed: float = 1.0
    mode: str = "as_written"   # as_written: the narration word for word; tighten: the AI rewrites it to `seconds`
    seconds: int = 120
    captions: str = "soft"     # soft (a track players can switch on), burned (always on screen), none
    music: bool = True


class NewVideo(Look):
    narration: str
    title: str = ""
    logo: str = ""             # presenters: the company's logo as a data: URL (PNG, JPG or WebP)


class Build(BaseModel):
    style: str | None = None
    cast: list[str] | None = None
    brand_name: str | None = None
    logo: str | None = None    # a new logo (data: URL); "" leaves it as it is
    voices: list[str] | None = None
    theme: str | None = None
    voice: str | None = None
    speed: float | None = None
    captions: str | None = None
    music: bool | None = None
    mode: str | None = None
    seconds: int | None = None
    replan: bool = False       # ask Azure for new scenes (or a new conversation)


def _check(look: dict) -> dict:
    if look["theme"] not in THEMES:
        raise HTTPException(422, f"Unknown theme '{look['theme']}'")
    if look["mode"] not in MODES:
        raise HTTPException(422, f"Unknown script mode '{look['mode']}'")
    if look["captions"] not in CAPTIONS:
        raise HTTPException(422, f"Captions must be one of {', '.join(CAPTIONS)}")
    if look["style"] not in STYLES:
        raise HTTPException(422, f"Unknown style '{look['style']}'")
    presets, default = presets_for(look["style"] if look["style"] in ("presenters", "conversation3d") else "conversation")
    if not all(c in presets for c in look["cast"]):
        look["cast"] = list(default)
    if len(look["cast"]) != 2 or any(c not in presets for c in look["cast"]) or look["cast"][0] == look["cast"][1]:
        raise HTTPException(422, "Pick two different people")
    look["brand_name"] = (look.get("brand_name") or "").strip()[:60]
    look["voices"] = (list(look["voices"]) + ["", ""])[:2]
    from api.studio import _voice_list
    known = {v["id"] for v in _voice_list()}
    for v in [look["voice"], *[x for x in look["voices"] if x]]:
        if v not in known:
            raise HTTPException(422, f"Unknown voice '{v}'")
    look["speed"] = min(1.3, max(0.8, float(look["speed"])))
    look["seconds"] = min(300, max(30, int(look["seconds"])))
    return look


@router.get("/options")
def options():
    from api.studio import _voice_list
    return {"themes": [{"id": k, "label": v} for k, v in THEMES.items()], "voices": _voice_list(),
            "modes": [{"id": "as_written", "label": "Word for word"}, {"id": "tighten", "label": "AI tightens it"}],
            "captions": [{"id": "soft", "label": "Switchable"}, {"id": "burned", "label": "Always on"},
                         {"id": "none", "label": "None"}],
            "styles": [{"id": "explainer", "label": "Explainer", "hint": "Motion graphics: points, steps and numbers animate in as they are said"},
                       {"id": "conversation", "label": "Conversation", "hint": "Two colleagues talk it through in an office"},
                       {"id": "presenters", "label": "Presenters", "hint": "Two presenters in a branded studio, your logo behind them"},
                       {"id": "hitech", "label": "Hi-tech", "hint": "Glowing motion graphics with shader transitions, rendered by HyperFrames"},
                       {"id": "conversation3d", "label": "3D conversation", "hint": "Two realistic 3D office people talk it through (Microsoft Rocketbox)"}],
            "cast": [{"id": k, **{x: c[x] for x in ("name", "voice", "skin", "hair", "hair_style", "top", "top2", "glasses", "beard")}}
                     for k, c in CAST.items()],
            "studio_cast": [{"id": k, "name": c["name"], "voice": c["voice"], "skin": c["skin"], "hair": c["hair"],
                             "hair_style": "long" if c["hair_style"] == "shoulder" else c["hair_style"], "top": c["suit"],
                             "glasses": False, "beard": False} for k, c in STUDIO_CAST.items()],
            "cast3d": [{"id": k, "name": a["name"], "voice": a["voice"], "hair_style": "long" if a["set"] == "f" else "short",
                        "skin": "#e6bc9c", "hair": "#2e221b", "top": "#2d3036", "glasses": False, "beard": False}
                       for k, a in presets_for("conversation3d")[0].items()],
            "default_cast": list(DEFAULT_CAST), "default_studio": list(DEFAULT_STUDIO),
            "default_3d": list(presets_for("conversation3d")[1])}


@router.get("/videos")
def list_videos():
    with _lock:
        _adopt_all()      # videos made with the command line since the server started
        return sorted(_jobs.values(), key=lambda j: j["created"], reverse=True)


@router.post("/videos")
def create_video(body: NewVideo):
    narration = body.narration.strip()
    if len(narration.split()) < 20:
        raise HTTPException(422, "Give a narration of at least a few sentences")
    look = _check(body.model_dump(exclude={"narration", "title", "logo"}))
    logo = _logo_png(body.logo) if body.logo else None
    video_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    _dir(video_id).mkdir(parents=True)
    (_dir(video_id) / "narration.txt").write_text(narration, encoding="utf-8")
    if logo:
        (_dir(video_id) / "logo.png").write_bytes(logo)
    title = body.title.strip()
    job = {"id": video_id, "title": title or " ".join(narration.split()[:6]) + "...", "custom_title": title,
           "created": _now(), "status": "running", "error": None, "progress": 0, **look}
    with _lock:
        _jobs[video_id] = job
        _logs[video_id] = []
        _save(job)
    _log(video_id, f"Animated video created from the narration ({len(narration.split()):,} words)")
    _start(video_id)
    return _view(video_id)


@router.get("/videos/{video_id}")
def get_video(video_id: str):
    if _jobs.get(video_id, {}).get("source") == "command line" or video_id not in _jobs:
        with _lock:
            _adopt_all()
    return _view(video_id)


@router.post("/videos/{video_id}/build")
def build_video(video_id: str, body: Build):
    job = _get(video_id)
    if job["status"] == "running":
        raise HTTPException(409, "This video is already being made")
    look = _check({**_settings(job), **{k: v for k, v in body.model_dump(exclude={"replan", "logo"}).items()
                                        if v is not None}})
    if body.logo:
        (_dir(video_id) / "logo.png").write_bytes(_logo_png(body.logo))
    _update(video_id, **look)
    _start(video_id, replan=body.replan)
    return _view(video_id)


FILES = {"final.mp4", "final.srt", "player.html", "audio/mix.wav", "poster.jpg", "logo.png"}


def _logo_png(data_url: str) -> bytes:
    """The uploaded logo (a data: URL) as PNG bytes, at most 1600 px wide."""
    from PIL import Image, UnidentifiedImageError
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url, validate=False)
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (IndexError, binascii.Error, UnidentifiedImageError, OSError) as e:
        raise HTTPException(422, "The logo must be a PNG, JPG or WebP image") from e
    if len(raw) > 8_000_000:
        raise HTTPException(422, "The logo is too large (8 MB at most)")
    img = img.convert("RGBA")
    if img.width > 1600:
        img = img.resize((1600, round(img.height * 1600 / img.width)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


@router.get("/videos/{video_id}/files/{name:path}")
def video_file(video_id: str, name: str, download: bool = False):
    """The video, its captions, and the animated player (with the voice-over it plays along to)."""
    job = _get(video_id)
    path = _dir(video_id) / name
    if name not in FILES or not path.exists():
        raise HTTPException(404, "Not made yet")
    if download:
        safe = re.sub(r"[^\w\- ]+", "", job["title"]).strip() or "Explainer"
        return FileResponse(path, filename=f"{safe}{path.suffix}")
    return FileResponse(path)


@router.delete("/videos/{video_id}")
def delete_video(video_id: str):
    job = _get(video_id)
    if job["status"] == "running":
        raise HTTPException(409, "This video is still being made")
    with _lock:
        _jobs.pop(video_id, None)
        _logs.pop(video_id, None)
    shutil.rmtree(_dir(video_id), ignore_errors=True)
    return {"deleted": video_id}
