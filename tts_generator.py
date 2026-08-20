"""
Stage 2 — Generate TTS Audio
Loads Kokoro ONNX model and generates audio from a formatted transcript.
Exports individual segment MP3s and a combined final_audio.mp3.

CLI usage:
  python tts_generator.py

Imported usage:
  from tts_generator import generate_audio
  generate_audio(log=my_log_fn)
"""

import os
import re
import time
import subprocess
import static_ffmpeg
static_ffmpeg.add_paths()

import numpy as np
import soundfile as sf
from pydub import AudioSegment

from config import (
    TRANSCRIPT, KOKORO_MODEL, VOICES_BIN,
    TTS_VOICE, TTS_SPEED, TTS_LANG,
    SEGMENTS_DIR, FINAL_AUDIO, GAP_MS,
)

# ── Kokoro singleton (avoid reloading the model on every call) ────────────────
_kokoro = None

def _load_kokoro(model_path: str, voices_path: str):
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(model_path, voices_path)
    return _kokoro


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_timestamp(s: str) -> bool:
    return bool(re.match(r'^\d{2}:\d{2}:\d{2}$', s))


def _parse_transcript(path: str) -> list[tuple[str, str]]:
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    entries, i = [], 0
    while i < len(lines):
        if _is_timestamp(lines[i]):
            timestamp  = lines[i]
            text_parts = []
            i += 1
            while i < len(lines) and not _is_timestamp(lines[i]):
                text_parts.append(lines[i])
                i += 1
            if text_parts:
                entries.append((timestamp, " ".join(text_parts)))
        else:
            i += 1
    return entries


def _clean_text(text: str) -> str:
    return (
        text.replace("\u2014", ", ")   # em dash
            .replace("\u2013", ", ")   # en dash
            .replace("\u2019", "'")    # right single quote
            .replace("\u2018", "'")    # left single quote
    )


def _atempo_chain(ratio: float) -> str:
    """Build an ffmpeg atempo filter chain for an arbitrary ratio (atempo only supports 0.5-2.0 per stage)."""
    filters = []
    while ratio > 2.0:
        filters.append("atempo=2.0")
        ratio /= 2.0
    while ratio < 0.5:
        filters.append("atempo=0.5")
        ratio /= 0.5
    filters.append(f"atempo={ratio:.6f}")
    return ",".join(filters)


def parse_duration(value: str) -> float:
    """Parse a duration given as seconds ("149") or "MM:SS" / "H:MM:SS" into seconds."""
    if ":" in value:
        parts = [float(p) for p in value.split(":")]
        seconds = 0.0
        for p in parts:
            seconds = seconds * 60 + p
        return seconds
    return float(value)


# ── Main function ─────────────────────────────────────────────────────────────

def generate_audio(
    transcript_path: str = None,
    model_path: str = None,
    voices_path: str = None,
    voice: str = None,
    speed: float = None,
    lang: str = None,
    segments_dir: str = None,
    final_audio_path: str = None,
    gap_ms: int = None,
    target_duration_sec: float = None,
    log=print,
) -> str:
    """
    Generate TTS audio from transcript.

    Returns:
        Path to the final combined audio file.
    """
    transcript_path  = transcript_path  or TRANSCRIPT
    model_path       = model_path       or KOKORO_MODEL
    voices_path      = voices_path      or VOICES_BIN
    voice            = voice            or TTS_VOICE
    speed            = speed            if speed is not None else TTS_SPEED
    lang             = lang             or TTS_LANG
    segments_dir     = segments_dir     or SEGMENTS_DIR
    final_audio_path = final_audio_path or FINAL_AUDIO
    gap_ms           = gap_ms           if gap_ms is not None else GAP_MS

    kokoro = _load_kokoro(model_path, voices_path)
    log("Kokoro model loaded.\n")

    entries = _parse_transcript(transcript_path)
    log(f"Total segments: {len(entries)}")

    # Generate audio in memory without per-segment export
    log("Generating audio segments...")
    start_time = time.time()
    
    audio_parts = []
    sample_rate = 24000  # Kokoro default
    gap_samples = int((gap_ms / 1000.0) * sample_rate)
    gap_audio = np.zeros(gap_samples, dtype=np.float32)

    for idx, (time_line, text_line) in enumerate(entries):
        clean = _clean_text(text_line)
        log(f"[{idx+1}/{len(entries)}] {time_line[:15]}... ", end="", flush=True)

        try:
            samples, sample_rate = kokoro.create(clean, voice=voice, speed=speed, lang=lang)
            
            # Keep samples as numpy arrays (no WAV export per segment)
            samples = np.array(samples, dtype=np.float32)
            audio_parts.append(samples)
            audio_parts.append(gap_audio)
            
            elapsed = time.time() - start_time
            log(f"✅ ({elapsed:.1f}s total)")

        except Exception as e:
            log(f"❌ FAILED: {e}")
            audio_parts.append(gap_audio)

    # Combine all audio at once
    log("\nCombining audio...")
    if audio_parts:
        final_samples = np.concatenate(audio_parts[:-1])  # Remove last gap
        final_samples = np.clip(final_samples, -1.0, 1.0)

        # Export once as WAV then convert to MP3
        log("Exporting to MP3...")
        wav_temp = final_audio_path.replace(".mp3", "_temp.wav")
        sf.write(wav_temp, final_samples, sample_rate)

        current_dur = len(final_samples) / sample_rate

        if target_duration_sec and current_dur > 0:
            ratio = current_dur / target_duration_sec
            log(f"Current duration {current_dur:.2f}s -> stretching to target {target_duration_sec:.2f}s (ratio={ratio:.4f})")
            cmd = [
                "ffmpeg", "-y", "-i", wav_temp,
                "-filter:a", _atempo_chain(ratio),
                "-b:a", "128k",
                final_audio_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            os.remove(wav_temp)
            if result.returncode != 0:
                log(f"❌ ffmpeg stretch failed: {result.stderr[-800:]}")
        else:
            # Convert WAV to MP3
            wav_audio = AudioSegment.from_wav(wav_temp)
            wav_audio.export(final_audio_path, format="mp3", bitrate="128k")
            os.remove(wav_temp)

        total_time = time.time() - start_time
        final_dur = target_duration_sec if target_duration_sec else current_dur
        mins = int(final_dur) // 60
        secs = int(final_dur) % 60
        log(f"\n✅ Done! {final_audio_path} — {mins}:{secs:02d}")
        log(f"Total time: {total_time:.1f}s")

    return final_audio_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target-duration", type=str, default=None,
        help="Exact target duration for final_audio.mp3, e.g. 149 or 2:29",
    )
    cli_args = parser.parse_args()

    target = parse_duration(cli_args.target_duration) if cli_args.target_duration else None
    generate_audio(target_duration_sec=target)
