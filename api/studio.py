"""
ZenVideo Studio API: app URL + transcript -> drafted script -> human review -> recorded, rendered, checked video.

Jobs live in build/studio/<id>/ (job.json, job.log, transcript.txt, demo.yaml, en/final.mp4 ...), so the dashboard
survives restarts. Only one recording runs at a time. Takes record a hidden browser by default (Settings ->
recording mode 'background'); 'screen' mode runs the app full screen and captures the monitor.
"""

import asyncio
import datetime
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from typing import Literal
import uuid
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from demo import media
from demo.draft import DraftError, azure_config, draft_script, scan_app
from demo.script import ScriptError, load
from demo.tts import timing_available, whisper_model_path

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "build" / "studio"
MUSIC_DIR = ROOT / "music"
STAGES = ["script", "review", "narration", "recording", "render", "check"]
FILES = {"final.mp4": "en/final.mp4", "final.srt": "en/final.srt", "poster.jpg": "poster.jpg", "demo.yaml": "demo.yaml"}

router = APIRouter(prefix="/api/studio")
_lock = threading.RLock()
_production = threading.Lock()
_jobs: dict[str, dict] = {}
_logs: dict[str, list[str]] = {}


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _save(job: dict) -> None:
    job["updated"] = _now()
    (_dir(job["id"]) / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")


def _update(job_id: str, **fields) -> dict:
    with _lock:
        job = _jobs[job_id]
        job.update(fields)
        _save(job)
        return job


def _stage(job_id: str, name: str, status: str) -> None:
    with _lock:
        job = _jobs[job_id]
        st = job["stages"][name]
        st["status"] = status
        st["started" if status == "running" else "ended"] = _now()
        if status == "running":
            job["stage"], job["progress"] = name, 0.0
        _save(job)


def _log(job_id: str, msg: str) -> None:
    line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
    with _lock:
        _logs.setdefault(job_id, []).append(line)
    with open(_dir(job_id) / "job.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_jobs() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    for f in JOBS_DIR.glob("*/job.json"):
        job = json.loads(f.read_text(encoding="utf-8"))
        if job["status"] in ("drafting", "queued", "producing"):
            job["status"], job["error"] = "failed", "Interrupted: the server was restarted while this job was running."
            for st in job["stages"].values():
                if st["status"] == "running":
                    st["status"] = "failed"
            _save(job)
        _jobs[job["id"]] = job
        log_file = f.parent / "job.log"
        _logs[job["id"]] = log_file.read_text(encoding="utf-8").splitlines() if log_file.exists() else []


_load_jobs()


# ── helpers ──────────────────────────────────────────────────────────────────

_voices: list[dict] | None = None


def _voice_list() -> list[dict]:
    global _voices
    if _voices is None:
        from demo.tts import _get_kokoro
        accents = {"a": "US", "b": "UK"}
        _voices = [{"id": v, "label": f"{v.split('_', 1)[1].title()} ({accents.get(v[0], v[0])}, "
                                      f"{'female' if v[1:2] == 'f' else 'male'})"}
                   for v in sorted(_get_kokoro().get_voices()) if "_" in v]
    return _voices


def _summary(job_id: str) -> dict:
    """Segments + actions of the current script for the review screen."""
    path = _dir(job_id) / "demo.yaml"
    if not path.exists():
        return {}
    try:
        with tempfile.TemporaryDirectory() as td:
            demo = load(path, build_dir=td)
    except ScriptError as e:
        return {"error": str(e)}
    segs, words = [], 0
    for s in demo.segments:
        text = s.say.get(demo.languages[0], "") if s.say else ""
        words += len(text.split())
        segs.append({
            "index": s.index, "id": s.id, "say": text, "silent": s.silent,
            "actions": [{"kind": a.kind, "label": a.describe(), "at_word": next(iter(a.at_word.values()), None),
                         "until_word": next(iter(a.until_word.values()), None)} for a in s.actions],
        })
    return {"segments": segs, "actions": sum(len(s["actions"]) for s in segs), "estimated_seconds": round(words / 150 * 60)}


def _poster(job_id: str) -> None:
    video = _dir(job_id) / "en" / "final.mp4"
    dur = media.duration(video)
    media.run_ffmpeg(["-ss", f"{min(dur * 0.3, dur - 1):.2f}", "-i", video, "-frames:v", "1", "-vf", "scale=640:-2",
                      "-q:v", "3", _dir(job_id) / "poster.jpg"])


def _fail(job_id: str, stage: str, exc: Exception) -> None:
    msg = str(exc).strip() or exc.__class__.__name__
    _log(job_id, f"ERROR: {msg}")
    _log(job_id, traceback.format_exc().strip().splitlines()[-1])
    _stage(job_id, stage, "failed")
    _update(job_id, status="failed", error=msg.splitlines()[0][:500])


# ── workers ──────────────────────────────────────────────────────────────────

def _draft_worker(job_id: str) -> None:
    job = _jobs[job_id]
    _stage(job_id, "script", "running")
    try:
        transcript = (_dir(job_id) / "transcript.txt").read_text(encoding="utf-8")
        draft_script(job["url"], transcript, job["options"], _dir(job_id) / "demo.yaml", lambda m: _log(job_id, m))
        _stage(job_id, "script", "done")
        _stage(job_id, "review", "running")
        _update(job_id, status="review", error=None)
        _log(job_id, "Waiting for review: check the steps, then start recording.")
    except Exception as e:
        _fail(job_id, "script", e)


def _production_worker(job_id: str) -> None:
    _update(job_id, status="queued")
    if not _production.acquire(blocking=False):
        _log(job_id, "Another video is recording - this one will start when it finishes.")
        _production.acquire()
    stage = "narration"
    try:
        _update(job_id, status="producing", error=None)
        demo = load(_dir(job_id) / "demo.yaml", build_dir=_dir(job_id))
        demo.capture = _settings()["recording_mode"]
        _update(job_id, recording_mode=demo.capture)
        lang = demo.languages[0]
        log = lambda m: _log(job_id, m)  # noqa: E731
        prog = lambda p: _update(job_id, progress=round(min(max(p, 0.0), 1.0), 3))  # noqa: E731

        from demo.check import run_check
        from demo.record import run_record
        from demo.render import run_render
        from demo.tts import run_tts
        for stage, fn in (("narration", run_tts), ("recording", run_record), ("render", run_render)):
            _stage(job_id, stage, "running")
            fn(demo, lang, log=log, progress=prog)
            _stage(job_id, stage, "done")

        stage = "check"
        _stage(job_id, stage, "running")
        passed = run_check(demo, lang, log=log)
        check = json.loads((demo.lang_dir(lang) / "check.json").read_text(encoding="utf-8"))
        _stage(job_id, stage, "done" if passed else "failed")
        _poster(job_id)
        render = json.loads((demo.lang_dir(lang) / "render.json").read_text(encoding="utf-8"))
        _update(job_id, status="done" if passed else "failed", check=check, duration=round(render["duration"], 1),
                progress=1.0, error=None if passed else "The sync check failed - see the results below.")
    except Exception as e:
        _fail(job_id, stage, e)
    finally:
        _production.release()


# ── API ──────────────────────────────────────────────────────────────────────

class CheckUrl(BaseModel):
    url: str


class NewJob(BaseModel):
    url: str
    transcript: str = Field(min_length=20)
    title: str = ""
    voice: str = "af_sky"
    speed: float = Field(1.1, ge=0.5, le=2.0)
    music: str = ""
    zoom: bool = True
    burn_subtitles: bool = True
    highlight_words: bool = True


class ScriptBody(BaseModel):
    yaml: str


SETTINGS_FILE = JOBS_DIR / "settings.json"
DEFAULT_SETTINGS = {"monthly_minutes_target": 30, "recording_mode": "background"}


class SettingsBody(BaseModel):
    monthly_minutes_target: int | None = Field(None, ge=1, le=10000)
    recording_mode: Literal["background", "screen"] | None = None


def _settings() -> dict:
    try:
        return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)


@router.get("/settings")
def get_settings():
    return _settings()


@router.put("/settings")
def put_settings(body: SettingsBody):
    data = {**_settings(), **body.model_dump(exclude_none=True)}
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


@router.get("/options")
def options():
    return {
        "voices": _voice_list(),
        "music": [{"id": p.name, "label": p.stem.replace("-", " ").replace("_", " ").title()}
                  for p in sorted(MUSIC_DIR.glob("*.mp3"))],
        "azure_configured": azure_config() is not None,
        "whisper_installed": whisper_model_path() is not None,
        "word_timing": "exact" if timing_available() else ("whisper" if whisper_model_path() else "estimated"),
        "sample_transcript": (ROOT / "demo" / "examples" / "p2p_transcript.txt").read_text(encoding="utf-8"),
        "defaults": NewJob(url="https://x", transcript="x" * 20).model_dump(exclude={"url", "transcript"}),
    }


@router.post("/check-url")
def check_url(body: CheckUrl):
    t0 = time.perf_counter()
    try:
        scan = scan_app(body.url.strip())
    except Exception as e:
        raise HTTPException(400, f"Could not open the app: {str(e).splitlines()[0]}")
    return {"title": scan.get("title"), "nav": scan["nav"], "pages": len(scan["pages"]),
            "seconds": round(time.perf_counter() - t0, 1)}


@router.get("/jobs")
def list_jobs():
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j["created"], reverse=True)


@router.post("/jobs")
def create_job(body: NewJob):
    url = body.url.strip()
    if not re.match(r"^https?://", url):
        raise HTTPException(422, "The app URL must start with http:// or https://")
    job_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    _dir(job_id).mkdir(parents=True)
    (_dir(job_id) / "transcript.txt").write_text(body.transcript, encoding="utf-8")
    opts = body.model_dump(exclude={"url", "transcript"})
    if opts["music"]:
        music = (MUSIC_DIR / opts["music"]).resolve()
        if music.parent != MUSIC_DIR.resolve() or not music.exists():
            raise HTTPException(422, "Unknown background music track")
        opts["music"] = str(music)
    job = {
        "id": job_id, "title": body.title.strip() or "Untitled video", "url": url, "created": _now(),
        "status": "drafting", "stage": "script", "progress": 0.0, "error": None, "options": opts,
        "stages": {s: {"status": "pending"} for s in STAGES}, "duration": None, "check": None,
        "transcript_words": len(body.transcript.split()),
    }
    with _lock:
        _jobs[job_id] = job
        _logs[job_id] = []
        _save(job)
    _log(job_id, f"Job created for {url}")
    threading.Thread(target=_draft_worker, args=(job_id,), daemon=True).start()
    return job


def _get(job_id: str) -> dict:
    with _lock:
        if job_id not in _jobs:
            raise HTTPException(404, "No such job")
        return _jobs[job_id]


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = dict(_get(job_id))
    path = _dir(job_id) / "demo.yaml"
    job["script"] = path.read_text(encoding="utf-8") if path.exists() else None
    job["summary"] = _summary(job_id)
    job["files"] = {name: (_dir(job_id) / rel).exists() for name, rel in FILES.items()}
    if job["status"] in ("review", "failed", "queued") or not job.get("recording_mode"):
        job["recording_mode"] = _settings()["recording_mode"]   # what the next take will use
    return job


@router.put("/jobs/{job_id}/script")
def save_script(job_id: str, body: ScriptBody):
    job = _get(job_id)
    if job["status"] != "review":
        raise HTTPException(409, "The script can only be edited while the job is waiting for review")
    try:
        yaml.safe_load(body.yaml)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "demo.yaml"
            tmp.write_text(body.yaml, encoding="utf-8")
            load(tmp, build_dir=td)
    except (yaml.YAMLError, ScriptError) as e:
        raise HTTPException(422, str(e))
    (_dir(job_id) / "demo.yaml").write_text(body.yaml, encoding="utf-8")
    _log(job_id, "Script edited during review")
    return get_job(job_id)


@router.post("/jobs/{job_id}/approve")
def approve(job_id: str):
    job = _get(job_id)
    if job["status"] != "review":
        raise HTTPException(409, "Only a job waiting for review can be started")
    _stage(job_id, "review", "done")
    for s in ("narration", "recording", "render", "check"):
        job["stages"][s] = {"status": "pending"}
    threading.Thread(target=_production_worker, args=(job_id,), daemon=True).start()
    return get_job(job_id)


@router.post("/jobs/{job_id}/retry")
def retry(job_id: str):
    job = _get(job_id)
    if job["status"] not in ("failed", "done"):
        raise HTTPException(409, "Only a finished or failed job can be recorded again")
    if job["stages"]["script"]["status"] != "done":
        for s in STAGES:
            job["stages"][s] = {"status": "pending"}
        _update(job_id, status="drafting", error=None)
        threading.Thread(target=_draft_worker, args=(job_id,), daemon=True).start()
    else:
        for s in ("review", "narration", "recording", "render", "check"):
            job["stages"][s] = {"status": "pending"}
        _stage(job_id, "review", "running")
        _update(job_id, status="review", error=None)
    return get_job(job_id)


@router.post("/jobs/{job_id}/redraft")
def redraft(job_id: str):
    job = _get(job_id)
    if job["status"] not in ("review", "failed"):
        raise HTTPException(409, "Only a job in review or a failed job can be redrafted")
    for s in STAGES:
        job["stages"][s] = {"status": "pending"}
    _update(job_id, status="drafting", error=None, check=None)
    _log(job_id, "Redrafting the script")
    threading.Thread(target=_draft_worker, args=(job_id,), daemon=True).start()
    return get_job(job_id)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    job = _get(job_id)
    if job["status"] in ("drafting", "queued", "producing"):
        raise HTTPException(409, "This job is still running")
    with _lock:
        _jobs.pop(job_id, None)
        _logs.pop(job_id, None)
    shutil.rmtree(_dir(job_id), ignore_errors=True)
    return {"deleted": job_id}


@router.get("/jobs/{job_id}/files/{name}")
def job_file(job_id: str, name: str):
    _get(job_id)
    if name not in FILES:
        raise HTTPException(404, "Unknown file")
    path = _dir(job_id) / FILES[name]
    if not path.exists():
        raise HTTPException(404, "Not generated yet")
    return FileResponse(path, filename=None if name == "poster.jpg" else f"{job_id}-{name}")


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    _get(job_id)

    async def stream():
        sent_logs, last = 0, None
        while not await request.is_disconnected():
            with _lock:
                job = json.dumps(_jobs.get(job_id))
                lines = _logs.get(job_id, [])[sent_logs:]
                sent_logs += len(lines)
            if job != last:
                last = job
                yield {"event": "job", "data": job}
            for line in lines:
                yield {"event": "log", "data": line}
            await asyncio.sleep(0.5)

    return EventSourceResponse(stream())
