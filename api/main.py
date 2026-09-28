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


# ── File upload / download ────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    dest = ROOT / file.filename
    contents = await file.read()
    dest.write_bytes(contents)
    return {"filename": file.filename, "size": len(contents)}


@app.get("/api/download/{filename}")
def download_file(filename: str):
    p = ROOT / filename
    if not p.exists():
        raise HTTPException(404, f"File not found: {filename}")
    return FileResponse(str(p), filename=filename)


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


# ── ZenVideo Studio (API + built web app) ────────────────────────────────────

from api.studio import router as studio_router  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

app.include_router(studio_router)
_studio_dist = ROOT / "studio" / "dist"
if _studio_dist.exists():
    app.mount("/", StaticFiles(directory=_studio_dist, html=True), name="studio")

# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
