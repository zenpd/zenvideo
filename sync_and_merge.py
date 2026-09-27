"""Stage 3 — Sync & Merge
Merges TTS audio with a video file, auto-adjusting audio tempo
so both tracks have the same duration.
 
CLI usage:
  python sync_and_merge.py
 
Imported usage:
  from sync_and_merge import sync_and_merge
  sync_and_merge(log=my_log_fn)
"""
 
import os
import subprocess
import static_ffmpeg
static_ffmpeg.add_paths()
 
from pydub import AudioSegment
from config import (
    VIDEO_FILE, FINAL_AUDIO, OUTPUT_VIDEO,
    AUDIO_BITRATE, SAMPLE_RATE,
)
 
# ── Background music options (for Streamlit dropdown) ────────────────────────
BG_MUSIC_OPTIONS = {
    "None"              : None,
    "Corporate"         : "music/corporate.mp3",
    "Upbeat Corporate"  : "music/kornevmusic-upbeat-happy-corporate-487426.mp3",
    "Soft Background"   : "music/sigmamusicart-soft-background-music-468495.mp3",
    "Inspiring"         : "music/background.mp3",
}
BG_VOLUME = -28  # dB reduction (more negative = quieter)
 
 
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
    bg_music: str = None,
    log=print,
) -> str | None:
    """
    Merge audio into video, stretching/compressing audio to match video length.
 
    Args:
        tolerance: fractional difference below which tempo adjustment is skipped
                   (default 0.10 = 10 %).
    Returns:
        output_path on success, None on failure.
    """
    video_path    = video_path    or VIDEO_FILE
    audio_path    = audio_path    or FINAL_AUDIO
    output_path   = output_path   or OUTPUT_VIDEO
    audio_bitrate = audio_bitrate or AUDIO_BITRATE
    sample_rate   = sample_rate   if sample_rate is not None else SAMPLE_RATE
 
    # ── Mix background music if provided ─────────────────────────────────────
    temp_audio = None
    if bg_music and not os.path.exists(bg_music):
        log(f"WARNING: background music file not found, skipping: {bg_music}")
    if bg_music and os.path.exists(bg_music):
        log(f"Mixing background music: {bg_music}")
        tts = AudioSegment.from_mp3(audio_path)
        bg  = AudioSegment.from_mp3(bg_music) - abs(BG_VOLUME)
        if len(bg) < len(tts):
            loops = len(tts) // len(bg) + 1
            bg = bg * loops
        bg = bg[:len(tts)]
        mixed = tts.overlay(bg)
        temp_audio = audio_path.replace(".mp3", "_with_music.mp3")
        mixed.export(temp_audio, format="mp3")
        audio_path = temp_audio
        log("Background music mixed.")
 
    log("Getting file durations...")
    video_dur = get_duration(video_path)
    audio_dur = get_duration(audio_path)
 
    if not video_dur or not audio_dur:
        log("ERROR: Could not detect file durations.")
        return None
 
    log(f"  Video: {video_dur:.2f}s  ({int(video_dur//60)}m {int(video_dur%60)}s)")
    log(f"  Audio: {audio_dur:.2f}s  ({int(audio_dur//60)}m {int(audio_dur%60)}s)")
 
    speed_ratio = video_dur / audio_dur
    log(f"  Speed ratio: {speed_ratio:.4f}x")
 
    low  = 1.0 - tolerance
    high = 1.0 + tolerance
    if low < speed_ratio < high:
        log("  Durations are similar — standard merge (no tempo change).\n")
        af = f"aformat=sample_rates={sample_rate}"
    else:
        direction = "up" if speed_ratio > 1 else "down"
        log(f"  Significant difference — speeding audio {direction} to match video.\n")
        af = f"atempo={speed_ratio:.6f},aformat=sample_rates={sample_rate}"
 
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-filter:a", af,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-y",
        output_path,
    ]
 
    log("Merging audio and video...\n")
    result = subprocess.run(cmd, text=True, capture_output=True)
 
    if result.returncode == 0:
        log(f"Done! Created: {output_path}")
        return output_path
    else:
        log(f"ERROR (ffmpeg exited {result.returncode}):\n{result.stderr[-800:]}")
        return None
 
 
if __name__ == "__main__":
    sync_and_merge()