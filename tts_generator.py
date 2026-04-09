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
import static_ffmpeg
static_ffmpeg.add_paths()

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

    os.makedirs(segments_dir, exist_ok=True)
    final_audio = AudioSegment.silent(duration=0)

    for idx, (time_line, text_line) in enumerate(entries):
        clean = _clean_text(text_line)
        log(f"\n[{idx+1}/{len(entries)}] {time_line}")
        log(f"  Text: {clean[:70]}...")

        try:
            samples, sample_rate = kokoro.create(clean, voice=voice, speed=speed, lang=lang)

            wav_tmp = f"_tmp_seg_{idx}.wav"
            sf.write(wav_tmp, samples, sample_rate)
            seg = AudioSegment.from_wav(wav_tmp)
            os.remove(wav_tmp)

            log(f"  TTS: {len(seg)/1000:.1f}s")

            seg_name = f"seg_{idx+1:02d}_{time_line.replace(':', '-')}.mp3"
            seg.export(os.path.join(segments_dir, seg_name), format="mp3")

            final_audio += seg
            if idx < len(entries) - 1:
                final_audio += AudioSegment.silent(duration=gap_ms)

            log(f"  Total so far: {len(final_audio)/1000:.1f}s")

        except Exception as e:
            log(f"  FAILED: {e}")
            final_audio += AudioSegment.silent(duration=gap_ms)

        time.sleep(0.2)

    final_audio.export(final_audio_path, format="mp3")
    mins = len(final_audio) // 60000
    secs = (len(final_audio) % 60000) // 1000
    log(f"\nDone! {final_audio_path} — {mins}:{secs:02d}")
    return final_audio_path


if __name__ == "__main__":
    generate_audio()
