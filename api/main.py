"""
FastAPI backend — TTS Audio/Video Pipeline
Each stage is fully independent; any stage can be triggered without running others first.

Run from project root:
  uvicorn api.main:app --reload --port 8000

Or from api/ directory:
  cd api && uvicorn main:app --reload --port 8000
"""

import sys
import os
import uuid
import json
import asyncio
import threading
from pathlib import Path
from queue import Queue, Empty

from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
import uvicorn

# ── Bootstrap: ensure pipeline modules are importable ────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from config import (
    RAW_TRANSCRIPT, TRANSCRIPT, FINAL_AUDIO, OUTPUT_VIDEO,
    VIDEO_FILE, KOKORO_MODEL, VOICES_BIN, SEGMENTS_DIR,
    WPM, GAP_SEC, GAP_MS,
    TTS_VOICE, TTS_SPEED, TTS_LANG,
    AUDIO_BITRATE, SAMPLE_RATE,
    VIDEO_PRESET, VIDEO_CRF,
)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="TTS Pipeline API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory job registry ────────────────────────────────────────────────────
# job_id -> {status: "running"|"done"|"error", queue: Queue, result: Any}
_jobs: dict[str, dict] = {}


def _run_job(job_id: str, func, kwargs: dict) -> None:
    """Execute a pipeline function in a background thread, piping logs to the job queue."""
    q = _jobs[job_id]["queue"]

    def log(msg: str) -> None:
        q.put({"type": "log", "msg": str(msg)})

    try:
        result = func(log=log, **kwargs)
        q.put({"type": "done", "msg": str(result) if result else "OK"})
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["result"] = result
    except Exception as exc:
        q.put({"type": "error", "msg": str(exc)})
        _jobs[job_id]["status"] = "error"


def _start_job(func, kwargs: dict) -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "queue": Queue(), "result": None}
    threading.Thread(target=_run_job, args=(job_id, func, kwargs), daemon=True).start()
    return job_id


# ── SSE log stream ────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request):
    """Server-Sent Events: yields log lines while the job runs, then closes."""

    async def generator():
        while True:
            if await request.is_disconnected():
                break
            job = _jobs.get(job_id)
            if not job:
                yield {"data": json.dumps({"type": "error", "msg": "Job not found"})}
                break
            try:
                event = job["queue"].get_nowait()
                yield {"data": json.dumps(event)}
                if event["type"] in ("done", "error"):
                    break
            except Empty:
                await asyncio.sleep(0.05)

    return EventSourceResponse(generator())


@app.get("/api/jobs/{job_id}/status")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {"job_id": job_id, "status": job["status"], "result": job["result"]}


# ── Pipeline file status ──────────────────────────────────────────────────────

@app.get("/api/status")
def pipeline_status():
    """Return existence + size for every file the pipeline uses."""
    files = {
        "raw_transcript": RAW_TRANSCRIPT,
        "transcript":     TRANSCRIPT,
        "final_audio":    FINAL_AUDIO,
        "video_file":     VIDEO_FILE,
        "output_video":   OUTPUT_VIDEO,
        "kokoro_model":   KOKORO_MODEL,
        "voices_bin":     VOICES_BIN,
    }
    result = {}
    for key, path in files.items():
        p = Path(path)
        result[key] = {
            "path":   str(path),
            "exists": p.exists(),
            "size":   p.stat().st_size if p.exists() else 0,
        }

    # count segment files
    seg_dir = Path(SEGMENTS_DIR)
    result["segments"] = {
        "path":   str(SEGMENTS_DIR),
        "exists": seg_dir.exists(),
        "count":  len(list(seg_dir.glob("*.mp3"))) if seg_dir.exists() else 0,
    }
    return result


# ── File browser (used by the FilePicker UI component) ───────────────────────

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist", "build"}

@app.get("/api/files")
def list_files(exts: str = ""):
    """List files under the project root, optionally filtered by extension."""
    ext_list = [e if e.startswith(".") else f".{e}" for e in
                (e.strip().lower() for e in exts.split(",")) if e]

    results = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if ext_list and fpath.suffix.lower() not in ext_list:
                continue
            try:
                size = fpath.stat().st_size
            except OSError:
                continue
            results.append({
                "name": str(fpath.relative_to(ROOT)),
                "ext":  fpath.suffix.lower(),
                "size": size,
            })

    results.sort(key=lambda f: f["name"])
    return results[:500]


# ── File upload / download ────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    safe_name = Path(file.filename).name
    if not safe_name:
        raise HTTPException(400, "Invalid filename")
    dest = ROOT / safe_name
    contents = await file.read()
    dest.write_bytes(contents)
    return {"filename": safe_name, "size": len(contents)}


@app.get("/api/download/{filename}")
def download_file(filename: str):
    safe_name = Path(filename).name
    p = ROOT / safe_name
    if not p.exists():
        raise HTTPException(404, f"File not found: {safe_name}")
    return FileResponse(str(p), filename=safe_name)


# ── Transcript helpers ────────────────────────────────────────────────────────

@app.get("/api/transcript/raw")
def get_raw_transcript():
    p = Path(RAW_TRANSCRIPT)
    return {"content": p.read_text(encoding="utf-8") if p.exists() else "", "exists": p.exists()}


class TranscriptBody(BaseModel):
    content: str

@app.post("/api/transcript/raw")
def save_raw_transcript(body: TranscriptBody):
    Path(RAW_TRANSCRIPT).write_text(body.content, encoding="utf-8")
    return {"saved": True}


# ── Stage 0: WebM → MP4 ───────────────────────────────────────────────────────

class Stage0Config(BaseModel):
    webm_path:   str
    output_path: str | None = None
    preset:      str = VIDEO_PRESET
    crf:         str = VIDEO_CRF

@app.post("/api/stage/0/run")
def run_stage0(body: Stage0Config):
    from convert_webm_to_mp4 import convert_webm
    return {"job_id": _start_job(convert_webm, {
        "webm_path":   body.webm_path,
        "output_path": body.output_path,
        "preset":      body.preset,
        "crf":         body.crf,
    })}


# ── Stage 1: Format transcript ────────────────────────────────────────────────

class Stage1Config(BaseModel):
    raw_path: str = RAW_TRANSCRIPT
    out_path: str = TRANSCRIPT
    wpm:      int = WPM
    gap_sec:  int = GAP_SEC

@app.post("/api/stage/1/run")
def run_stage1(body: Stage1Config):
    from format_transcript import format_transcript
    return {"job_id": _start_job(format_transcript, body.model_dump())}


# ── Stage 2: Generate TTS ─────────────────────────────────────────────────────

class Stage2Config(BaseModel):
    transcript_path:  str   = TRANSCRIPT
    model_path:       str   = KOKORO_MODEL
    voices_path:      str   = VOICES_BIN
    voice:            str   = TTS_VOICE
    speed:            float = TTS_SPEED
    lang:             str   = TTS_LANG
    segments_dir:     str   = SEGMENTS_DIR
    final_audio_path: str   = FINAL_AUDIO
    gap_ms:           int   = GAP_MS

@app.post("/api/stage/2/run")
def run_stage2(body: Stage2Config):
    from tts_generator import generate_audio
    return {"job_id": _start_job(generate_audio, body.model_dump())}



@app.get("/api/tts/preview/{voice}")
def preview_voice(
    voice: str,
    speed: float = TTS_SPEED,
    lang: str = TTS_LANG,
):
    from io import BytesIO
    import soundfile as sf
    from tts_generator import _load_kokoro

    # Load the Kokoro model
    kokoro = _load_kokoro(KOKORO_MODEL, VOICES_BIN)

    # Validate the requested voice
    available_voices = kokoro.get_voices()

    if voice not in available_voices:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice '{voice}'. Available voices: {available_voices}",
        )

    # Short sentence used for voice preview
    preview_text = "Hello, I am your voice assistant."

    # Generate speech
    samples, sample_rate = kokoro.create(
        preview_text,
        voice=voice,
        speed=speed,
        lang=lang,
    )

    # Convert WAV to memory
    audio_buffer = BytesIO()

    sf.write(
        audio_buffer,
        samples,
        sample_rate,
        format="WAV",
    )

    return Response(
        content=audio_buffer.getvalue(),
        media_type="audio/wav",
    )


# ── Stage 3: Sync & Merge ─────────────────────────────────────────────────────

class Stage3Config(BaseModel):
    video_path:    str   = VIDEO_FILE
    audio_path:    str   = FINAL_AUDIO
    output_path:   str   = OUTPUT_VIDEO
    audio_bitrate: str   = AUDIO_BITRATE
    sample_rate:   int   = SAMPLE_RATE
    tolerance:     float = 0.10

@app.post("/api/stage/3/run")
def run_stage3(body: Stage3Config):
    from sync_and_merge import sync_and_merge
    return {"job_id": _start_job(sync_and_merge, body.model_dump())}


# ── Stage 4: Browser Recording ───────────────────────────────────────────────

class Stage4Config(BaseModel):
    url: str
    transcript_path: str = RAW_TRANSCRIPT
    output_path: str = "video-recordings/recording.webm"


@app.post("/api/stage/4/run")
def run_stage4(body: Stage4Config):
    from generate_recording import generate_recording

    return {
        "job_id": _start_job(generate_recording, {
            "url": body.url,
            "transcript_path": body.transcript_path,
            "output_path": body.output_path,
        })
    }


# ── Stage 5: Screen Recorder ──────────────────────────────────────────────────

class Stage5StartConfig(BaseModel):
    output_path:   str = "recording.webm"
    video_idx:     str = "1"
    audio_idx:     str = "0"
    framerate:     int = 30
    audio_bitrate: str = AUDIO_BITRATE


@app.get("/api/stage/5/devices")
def stage5_devices():
    from screen_recorder import list_devices
    return list_devices()


@app.get("/api/stage/5/status")
def stage5_status():
    from screen_recorder import recording_status
    return recording_status()


@app.post("/api/stage/5/start")
def stage5_start(body: Stage5StartConfig):
    from screen_recorder import start_recording
    result = start_recording(**body.model_dump())
    if "error" in result:
        raise HTTPException(409, result["error"])
    return result


@app.post("/api/stage/5/stop")
def stage5_stop():
    from screen_recorder import stop_recording
    result = stop_recording()
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ── Stage 6: WebM + Transcript → Synced MP4 (one-shot) ───────────────────────

class Stage6Config(BaseModel):
    webm_path:        str
    transcript_path:  str   = RAW_TRANSCRIPT
    output_path:      str   = "output_synced.mp4"
    voice:            str   = TTS_VOICE
    speed:            float = TTS_SPEED
    lang:             str   = TTS_LANG
    wpm:              int   = WPM
    gap_sec:          int   = GAP_SEC
    audio_bitrate:    str   = AUDIO_BITRATE
    sample_rate:      int   = SAMPLE_RATE
    video_preset:     str   = VIDEO_PRESET
    video_crf:        str   = VIDEO_CRF

@app.post("/api/stage/6/run")
def run_stage6(body: Stage6Config):
    from webm_transcript_pipeline import webm_to_mp4
    return {"job_id": _start_job(webm_to_mp4, body.model_dump())}


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
