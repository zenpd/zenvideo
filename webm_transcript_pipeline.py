"""
Stage 4 — WebM + Transcript → Synced MP4  (one-shot pipeline)

Sync strategy: timestamp-based placement (adelay + amix).
Each TTS segment is placed at its exact transcript timestamp in the audio
timeline — no uniform tempo-stretching of the whole audio.

Steps:
  1. Convert WebM → intermediate MP4 (H.264)
  2. Parse transcript (raw or pre-formatted)
  3. Generate TTS for every segment via Kokoro ONNX
  4. Place each segment at its transcript timestamp using FFmpeg adelay
  5. Mix all positioned clips into one audio track (amix)
  6. Merge positioned audio with video → output.mp4

CLI usage:
  python webm_transcript_pipeline.py input.webm raw_transcript.txt output.mp4

Imported usage:
  from webm_transcript_pipeline import webm_to_mp4
  webm_to_mp4(webm_path="rec.webm", transcript_path="raw_transcript.txt", log=print)
"""

import os
import re
import sys
import time
import tempfile
import subprocess
import static_ffmpeg
static_ffmpeg.add_paths()

import soundfile as sf
from pydub import AudioSegment

from config import (
    KOKORO_MODEL, VOICES_BIN,
    TTS_VOICE, TTS_SPEED, TTS_LANG,
    WPM, GAP_SEC,
    AUDIO_BITRATE, SAMPLE_RATE,
    VIDEO_PRESET, VIDEO_CRF,
)
from format_transcript import convert_numbers

# ── Kokoro singleton ──────────────────────────────────────────────────────────
_kokoro = None

def _load_kokoro(model_path, voices_path):
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(model_path, voices_path)
    return _kokoro


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_duration(path: str) -> float:
    """Return media duration in seconds via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        # fallback via ffmpeg stderr
        r2 = subprocess.run(["ffmpeg", "-i", path, "-f", "null", "-"],
                            capture_output=True, text=True)
        for line in r2.stderr.split("\n"):
            if "Duration:" in line:
                ts = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = ts.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def _clean_text(text: str) -> str:
    return (
        text.replace("\u2014", ", ")
            .replace("\u2013", ", ")
            .replace("\u2019", "'")
            .replace("\u2018", "'")
    )


def _ts_to_ms(ts: str) -> int:
    """HH:MM:SS → milliseconds."""
    h, m, s = map(int, ts.split(":"))
    return (h * 3600 + m * 60 + s) * 1000


def _parse_raw_transcript(raw_path: str, wpm: int, gap_sec: int) -> list[dict]:
    """
    Parse raw_transcript.txt (--- separated) into a list of:
      { timestamp_ms, text }
    Timestamps are auto-calculated from WPM, same as format_transcript.py.
    """
    with open(raw_path, "r", encoding="utf-8") as f:
        content = f.read()

    segments = [s.strip() for s in content.split("---") if s.strip()]
    current_sec = 0
    result = []

    for seg in segments:
        lines = seg.split("\n")
        if len(lines) > 1:
            seg = "\n".join(lines[1:]).strip()
        seg = convert_numbers(seg)
        word_count  = len(seg.split())
        duration_sec = (word_count / wpm) * 60
        result.append({"timestamp_ms": current_sec * 1000, "text": seg})
        current_sec += int(duration_sec) + gap_sec

    return result


def _parse_formatted_transcript(path: str) -> list[dict]:
    """
    Parse transcript.txt (timestamp + text blocks) into list of:
      { timestamp_ms, text }
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    ts_re = re.compile(r'^\d{2}:\d{2}:\d{2}$')
    entries, i = [], 0
    while i < len(lines):
        if ts_re.match(lines[i]):
            ts   = lines[i]
            parts = []
            i += 1
            while i < len(lines) and not ts_re.match(lines[i]):
                parts.append(lines[i])
                i += 1
            if parts:
                entries.append({
                    "timestamp_ms": _ts_to_ms(ts),
                    "text": " ".join(parts),
                })
        else:
            i += 1
    return entries


# ── Stage 4 main function ─────────────────────────────────────────────────────

def webm_to_mp4(
    webm_path:        str,
    transcript_path:  str,
    output_path:      str   = "output_synced.mp4",
    model_path:       str   = None,
    voices_path:      str   = None,
    voice:            str   = None,
    speed:            float = None,
    lang:             str   = None,
    wpm:              int   = None,
    gap_sec:          int   = None,
    audio_bitrate:    str   = None,
    sample_rate:      int   = None,
    video_preset:     str   = None,
    video_crf:        str   = None,
    log=print,
) -> str | None:
    """
    Full one-shot pipeline: WebM + transcript → synced MP4.

    Sync method: each TTS segment is placed at its transcript timestamp
    using FFmpeg adelay — no uniform audio stretching.

    Returns output path on success, None on failure.
    """
    model_path    = model_path    or KOKORO_MODEL
    voices_path   = voices_path   or VOICES_BIN
    voice         = voice         or TTS_VOICE
    speed         = speed         if speed    is not None else TTS_SPEED
    lang          = lang          or TTS_LANG
    wpm           = wpm           if wpm      is not None else WPM
    gap_sec       = gap_sec       if gap_sec  is not None else GAP_SEC
    audio_bitrate = audio_bitrate or AUDIO_BITRATE
    sample_rate   = sample_rate   if sample_rate is not None else SAMPLE_RATE
    video_preset  = video_preset  or VIDEO_PRESET
    video_crf     = str(video_crf) if video_crf is not None else VIDEO_CRF

    # ── Validate inputs ────────────────────────────────────────────────────
    for label, path in [("WebM", webm_path), ("Transcript", transcript_path),
                         ("Kokoro model", model_path), ("Voices", voices_path)]:
        if not os.path.exists(path):
            log(f"ERROR: {label} file not found: {path}")
            return None

    # ── Determine transcript format ────────────────────────────────────────
    with open(transcript_path, "r", encoding="utf-8") as f:
        first_lines = [l.strip() for l in f.readlines()[:5] if l.strip()]
    has_timestamps = any(re.match(r'^\d{2}:\d{2}:\d{2}$', l) for l in first_lines)

    if has_timestamps:
        log("Detected pre-formatted transcript (with timestamps).")
        segments = _parse_formatted_transcript(transcript_path)
    else:
        log("Detected raw transcript — computing timestamps from WPM.")
        segments = _parse_raw_transcript(transcript_path, wpm, gap_sec)

    log(f"Segments parsed: {len(segments)}")

    # ── Step 1: Convert WebM → temp MP4 ───────────────────────────────────
    with tempfile.TemporaryDirectory() as tmpdir:
        log("\nStep 1/4 — Converting WebM to MP4…")
        video_mp4 = os.path.join(tmpdir, "video.mp4")
        r = subprocess.run([
            "ffmpeg", "-i", webm_path,
            "-c:v", "libx264", "-preset", video_preset, "-crf", video_crf,
            "-an",           # strip original audio
            "-y", video_mp4,
        ], capture_output=True, text=True)
        if r.returncode != 0:
            log(f"ERROR converting WebM:\n{r.stderr[-400:]}")
            return None
        video_dur = _get_duration(video_mp4)
        log(f"  Video duration: {video_dur:.2f}s")

        # ── Step 2: Generate TTS for each segment ──────────────────────────
        log("\nStep 2/4 — Generating TTS audio…")
        kokoro = _load_kokoro(model_path, voices_path)
        log("  Kokoro model loaded.")

        seg_wavs = []   # list of (timestamp_ms, wav_path, duration_ms)
        for idx, seg in enumerate(segments):
            text  = _clean_text(seg["text"])
            ts_ms = seg["timestamp_ms"]
            log(f"  [{idx+1}/{len(segments)}] @{ts_ms}ms — {text[:60]}…")

            try:
                samples, sr = kokoro.create(text, voice=voice, speed=speed, lang=lang)
                wav_path = os.path.join(tmpdir, f"seg_{idx:03d}.wav")
                sf.write(wav_path, samples, sr)
                dur_ms = int(len(AudioSegment.from_wav(wav_path)))
                seg_wavs.append((ts_ms, wav_path, dur_ms))
                log(f"    TTS: {dur_ms/1000:.1f}s")
                time.sleep(0.1)
            except Exception as e:
                log(f"    WARN: TTS failed for segment {idx+1}: {e} — skipping")

        if not seg_wavs:
            log("ERROR: No segments generated.")
            return None

        # ── Step 3: Build timestamp-positioned audio mix ───────────────────
        log("\nStep 3/4 — Positioning audio segments by timestamp (adelay)…")

        # Check if last segment overruns video — warn but don't fail
        last_ts, _, last_dur = seg_wavs[-1]
        projected_end = (last_ts + last_dur) / 1000
        if projected_end > video_dur + 2:
            log(f"  WARN: Audio ends at {projected_end:.1f}s but video is {video_dur:.1f}s")
            log(f"  Consider increasing WPM or reducing transcript length.")

        # Build ffmpeg command with one -i per segment + adelay + amix
        cmd = ["ffmpeg"]
        for _, wav_path, _ in seg_wavs:
            cmd += ["-i", wav_path]

        # filter_complex: each input gets adelay, then all are amixed
        filter_parts = []
        for i, (ts_ms, _, _) in enumerate(seg_wavs):
            filter_parts.append(
                f"[{i}]adelay={ts_ms}|{ts_ms},aresample={sample_rate}[a{i}]"
            )

        mix_inputs = "".join(f"[a{i}]" for i in range(len(seg_wavs)))
        filter_parts.append(
            f"{mix_inputs}amix=inputs={len(seg_wavs)}:duration=longest:dropout_transition=0[mix]"
        )

        filter_complex = ";".join(filter_parts)

        mixed_wav = os.path.join(tmpdir, "mixed.wav")
        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[mix]",
            "-y", mixed_wav,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            log(f"ERROR building audio mix:\n{r.stderr[-600:]}")
            return None

        mix_dur = _get_duration(mixed_wav)
        log(f"  Mixed audio duration: {mix_dur:.2f}s")

        # ── Step 4: Merge positioned audio with video ──────────────────────
        log("\nStep 4/4 — Merging audio with video…")

        # If audio is shorter than video, pad it with silence to the video's length, then
        # -shortest trims any pad overshoot back down to exactly that length. If audio is
        # longer, video is copy-only (no re-encode) so it can't be extended to match — the
        # best we can do without re-encoding is let the narration play in full rather than
        # silently cutting it off; -shortest must NOT be passed in that case, or it truncates
        # the audio to the shorter video length regardless of this branch (the bug this
        # replaces: -shortest was previously hard-coded unconditionally below).
        if mix_dur < video_dur - 0.5:
            log(f"  Audio ({mix_dur:.1f}s) shorter than video ({video_dur:.1f}s) — padding silence to video length.")
            # apad extends audio to match video
            audio_filter = f"apad,aformat=sample_rates={sample_rate}"
            shortest_flag = ["-shortest"]
        else:
            if mix_dur > video_dur + 0.5:
                log(f"  WARN: audio ({mix_dur:.1f}s) is longer than video ({video_dur:.1f}s); video has no more "
                    f"frames after {video_dur:.1f}s but narration will keep playing to the end.")
            audio_filter = f"aformat=sample_rates={sample_rate}"
            shortest_flag = []

        r = subprocess.run([
            "ffmpeg",
            "-i", video_mp4,
            "-i", mixed_wav,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", audio_bitrate,
            "-filter:a", audio_filter,
            "-map", "0:v:0",
            "-map", "1:a:0",
            *shortest_flag,
            "-y", output_path,
        ], capture_output=True, text=True)

        if r.returncode != 0:
            log(f"ERROR merging:\n{r.stderr[-600:]}")
            return None

    out_size = os.path.getsize(output_path) / 1_048_576
    log(f"\nDone! {output_path} ({out_size:.1f} MB)")
    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python webm_transcript_pipeline.py <input.webm> <transcript.txt> [output.mp4]")
        sys.exit(1)
    webm_to_mp4(
        webm_path=sys.argv[1],
        transcript_path=sys.argv[2],
        output_path=sys.argv[3] if len(sys.argv) > 3 else "output_synced.mp4",
    )
