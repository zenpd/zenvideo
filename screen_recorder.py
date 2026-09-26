"""
Stage 5 — Screen Recorder
Uses FFmpeg avfoundation (macOS) to capture screen + microphone.
Outputs a .webm or .mp4 file ready to feed into Stage 4.

CLI:
  python screen_recorder.py list              # list devices
  python screen_recorder.py start [output]    # start recording
  python screen_recorder.py stop              # stop (sends 'q' to running process)

Imported / API usage:
  from screen_recorder import list_devices, start_recording, stop_recording
"""

import os
import re
import sys
import json
import time
import signal
import subprocess
import tempfile
from pathlib import Path

import static_ffmpeg
static_ffmpeg.add_paths()

from config import VIDEO_PRESET, VIDEO_CRF, AUDIO_BITRATE, SAMPLE_RATE

# ── PID file to track the running ffmpeg process ──────────────────────────────
_PID_FILE = Path(tempfile.gettempdir()) / "zenvideo_recorder.pid"
_LOG_FILE = Path(tempfile.gettempdir()) / "zenvideo_recorder.log"

# How long to wait for ffmpeg to exit after each escalating stop signal.
_STOP_GRACE_SECONDS = 3.0
_STOP_TERM_SECONDS  = 2.0


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _wait_for_exit(pid: int, timeout: float) -> bool:
    """Poll until the process exits or the timeout elapses. Returns True if it exited."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.1)
    return not _pid_alive(pid)

# ── Device discovery ──────────────────────────────────────────────────────────

def list_devices(log=print) -> dict:
    """
    Return available avfoundation video and audio devices.
    Returns: { "video": [{"idx": "0", "name": "..."}, ...],
               "audio": [{"idx": "0", "name": "..."}, ...] }
    """
    result = subprocess.run(
        ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True, text=True,
    )
    output = result.stderr

    video, audio = [], []
    section = None
    for line in output.splitlines():
        if "AVFoundation video devices" in line:
            section = "video"
        elif "AVFoundation audio devices" in line:
            section = "audio"
        else:
            m = re.search(r'\[(\d+)\]\s+(.+)', line)
            if m and section:
                entry = {"idx": m.group(1), "name": m.group(2).strip()}
                (video if section == "video" else audio).append(entry)

    log(f"Video devices: {[d['name'] for d in video]}")
    log(f"Audio devices: {[d['name'] for d in audio]}")
    return {"video": video, "audio": audio}


# ── Start recording ───────────────────────────────────────────────────────────

def start_recording(
    output_path:    str   = "recording.webm",
    video_idx:      str   = "1",        # "1" = Capture screen 0
    audio_idx:      str   = "0",        # "0" = MacBook Pro Microphone
    framerate:      int   = 30,
    video_preset:   str   = None,
    video_crf:      str   = None,
    audio_bitrate:  str   = None,
    sample_rate:    int   = None,
    log=print,
) -> dict:
    """
    Start a background screen recording via FFmpeg avfoundation.
    Returns { "pid": int, "output_path": str } on success.
    """
    video_preset  = video_preset  or VIDEO_PRESET
    video_crf     = str(video_crf) if video_crf is not None else VIDEO_CRF
    audio_bitrate = audio_bitrate or AUDIO_BITRATE
    sample_rate   = sample_rate   if sample_rate is not None else SAMPLE_RATE

    if _PID_FILE.exists():
        try:
            pid = int(_PID_FILE.read_text().strip())
            os.kill(pid, 0)   # check if still alive
            log(f"ERROR: A recording is already running (PID {pid}). Stop it first.")
            return {"error": f"Already recording (PID {pid})"}
        except (ProcessLookupError, ValueError):
            _PID_FILE.unlink(missing_ok=True)

    # avfoundation input: "video_idx:audio_idx"
    av_input = f"{video_idx}:{audio_idx}"

    # Choose codec based on output extension
    ext = Path(output_path).suffix.lower()
    if ext == ".webm":
        vcodec = ["libvpx-vp9", "-crf", video_crf, "-b:v", "0", "-deadline", "realtime", "-cpu-used", "8"]
        acodec = ["libopus", "-b:a", audio_bitrate]
    else:
        # Default to H.264 MP4
        vcodec = ["libx264", "-preset", video_preset, "-crf", video_crf]
        acodec = ["aac", "-b:a", audio_bitrate]

    cmd = [
        "ffmpeg",
        "-f", "avfoundation",
        "-framerate", str(framerate),
        "-capture_cursor", "1",
        "-i", av_input,
        "-ar", str(sample_rate),
        "-c:v", *vcodec,
        "-c:a", *acodec,
        "-y", output_path,
    ]

    log(f"Starting recording: {' '.join(cmd[:8])}…")
    log(f"Output: {output_path}")

    log_fh = open(_LOG_FILE, "w")
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=log_fh,
        stderr=log_fh,
    )

    # Give ffmpeg a moment to fail fast (bad device index, missing binary, ...)
    # before we report success — avfoundation errors surface almost immediately.
    time.sleep(0.6)
    if proc.poll() is not None:
        log_fh.close()
        tail = _LOG_FILE.read_text(errors="replace")[-800:] if _LOG_FILE.exists() else ""
        log(f"ERROR: ffmpeg exited immediately (code {proc.returncode}).\n{tail}")
        return {"error": f"ffmpeg exited immediately (code {proc.returncode}): {tail[-300:]}"}

    _PID_FILE.write_text(str(proc.pid))
    log(f"Recording started. PID: {proc.pid}")
    log(f"Call stop_recording() or POST /api/stage/5/stop to finish.")
    return {"pid": proc.pid, "output_path": output_path}


# ── Stop recording ────────────────────────────────────────────────────────────

def stop_recording(log=print) -> dict:
    """
    Stop the running FFmpeg recording, escalating from a graceful SIGINT
    (lets ffmpeg finalise the container) up to SIGKILL if it won't die.
    Returns { "stopped": True, "pid": int, "note"?: str } or { "error": str }.
    """
    if not _PID_FILE.exists():
        log("No active recording found.")
        return {"error": "No active recording"}

    try:
        pid = int(_PID_FILE.read_text().strip())
    except ValueError:
        _PID_FILE.unlink(missing_ok=True)
        return {"error": "Invalid PID file"}

    if not _pid_alive(pid):
        _PID_FILE.unlink(missing_ok=True)
        log("Process was already stopped.")
        return {"stopped": True, "pid": pid, "note": "already stopped"}

    os.kill(pid, signal.SIGINT)
    log(f"Sent SIGINT to PID {pid} — finalising file…")
    if _wait_for_exit(pid, _STOP_GRACE_SECONDS):
        _PID_FILE.unlink(missing_ok=True)
        return {"stopped": True, "pid": pid}

    log(f"PID {pid} did not exit after SIGINT — sending SIGTERM…")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _PID_FILE.unlink(missing_ok=True)
        return {"stopped": True, "pid": pid}
    if _wait_for_exit(pid, _STOP_TERM_SECONDS):
        _PID_FILE.unlink(missing_ok=True)
        return {"stopped": True, "pid": pid, "note": "force-terminated (SIGTERM) — output file may be corrupt"}

    log(f"PID {pid} still alive — sending SIGKILL…")
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    _wait_for_exit(pid, 2.0)
    _PID_FILE.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid, "note": "force-killed (SIGKILL) — output file is likely corrupt/unplayable"}


def recording_status() -> dict:
    """Check if a recording is currently active."""
    if not _PID_FILE.exists():
        return {"active": False}
    try:
        pid = int(_PID_FILE.read_text().strip())
    except ValueError:
        _PID_FILE.unlink(missing_ok=True)
        return {"active": False}
    if _pid_alive(pid):
        return {"active": True, "pid": pid}
    _PID_FILE.unlink(missing_ok=True)
    return {"active": False}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        devices = list_devices()
        print(json.dumps(devices, indent=2))
    elif cmd == "start":
        out = sys.argv[2] if len(sys.argv) > 2 else "recording.webm"
        result = start_recording(output_path=out)
        print(json.dumps(result, indent=2))
        print("Press Ctrl+C or run: python screen_recorder.py stop")
        try:
            signal.pause()
        except KeyboardInterrupt:
            stop_recording()
    elif cmd == "stop":
        result = stop_recording()
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python screen_recorder.py [list|start [output.webm]|stop]")
