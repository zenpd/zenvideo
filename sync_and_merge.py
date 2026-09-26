"""
Stage 3 — Sync & Merge
Merges TTS audio with Playwright recording, using hyperframe metadata to dynamically
trim initial blank browser page load delays.

CLI usage:
  python sync_and_merge.py

Imported usage:
  from sync_and_merge import sync_and_merge
  sync_and_merge(log=my_log_fn)
"""

import os
import json
import subprocess
from pathlib import Path
import static_ffmpeg

static_ffmpeg.add_paths()

from config import (
    VIDEO_FILE, FINAL_AUDIO, OUTPUT_VIDEO,
    AUDIO_BITRATE, SAMPLE_RATE,
)


def get_duration(file_path: str) -> float | None:
    """Return duration of a media file in seconds (via ffmpeg)."""
    result = subprocess.run(
        ["ffmpeg", "-i", file_path, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    for line in result.stderr.split("\n"):
        if "Duration:" in line:
            ts = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = ts.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return None


def sync_and_merge(
    video_path: str = None,
    audio_path: str = None,
    output_path: str = None,
    audio_bitrate: str = None,
    sample_rate: int = None,
    tolerance: float = 0.10,
    log=print,
) -> str | None:
    video_path    = video_path    or VIDEO_FILE
    audio_path    = audio_path    or FINAL_AUDIO
    output_path   = output_path   or OUTPUT_VIDEO
    audio_bitrate = audio_bitrate or AUDIO_BITRATE
    sample_rate   = sample_rate   if sample_rate is not None else SAMPLE_RATE

    log("Getting file durations...")
    video_dur = get_duration(video_path)
    audio_dur = get_duration(audio_path)

    if not video_dur or not audio_dur:
        log("ERROR: Could not detect file durations.")
        return None

    log(f"  Raw Video: {video_dur:.2f}s  ({int(video_dur//60)}m {int(video_dur%60)}s)")
    log(f"  Raw Audio: {audio_dur:.2f}s  ({int(audio_dur//60)}m {int(audio_dur%60)}s)")

    # Read Hyperframe Metadata if present to detect initial page load delay
    trim_start = 0.0
    hyperframe_file = Path(video_path).parent / "hyperframes.json"
    if hyperframe_file.exists():
        try:
            with open(hyperframe_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    trim_start = float(data.get("initial_load_delay", 0.0))
                elif isinstance(data, list):
                    # Fallback for older hyperframes.json structure
                    trim_start = 0.0
            log(f"Dynamic page load delay detected: {trim_start:.2f}s. Trimming leading blank frames...")
        except Exception as e:
            log(f"Warning: Failed to parse hyperframes.json: {e}")

    # Build FFmpeg command with dynamic start offset (-ss)
    cmd = [
        "ffmpeg",
        "-ss", str(trim_start),  # Dynamically skip initial blank loading frames
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "libx264",      # Re-encode video slightly for precise keyframe cutting
        "-preset", "ultrafast",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-ar", str(sample_rate),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        "-y",
        output_path,
    ]

    log("Merging audio and video with dynamic trim & Hyperframe sync...\n")
    result = subprocess.run(cmd, text=True, capture_output=True)

    if result.returncode == 0:
        log(f"Done! Created final merged output: {output_path}")
        return output_path
    else:
        log(f"ERROR (ffmpeg exited {result.returncode}):\n{result.stderr[-800:]}")
        return None


if __name__ == "__main__":
    sync_and_merge()