"""
Central config — reads from .env (falls back to defaults).
Import this in every module instead of hardcoding values.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Transcript formatting ─────────────────────────────────────────────────────
WPM     = int(os.getenv("WPM", 180))
GAP_SEC = int(os.getenv("GAP_SEC", 1))

# ── TTS generation ────────────────────────────────────────────────────────────
GAP_MS    = int(os.getenv("GAP_MS", 1000))
TTS_VOICE = os.getenv("TTS_VOICE", "af_sky")
TTS_SPEED = float(os.getenv("TTS_SPEED", 1.1))
TTS_LANG  = os.getenv("TTS_LANG", "en-us")

# ── Available Kokoro voices ───────────────────────────────────────────────────
AVAILABLE_VOICES = [
    # American Female voices
    "af_sky",
    "af_bella",
    "af_sarah",
    "af_nicole",
    # American Male voices
    "am_adam",
    "am_michael",
    # British Female voices
    "bf_emma",
    # British Male voices
    "bm_george",
]

# ── Model files ───────────────────────────────────────────────────────────────
KOKORO_MODEL = os.getenv("KOKORO_MODEL", "kokoro-v0_19.onnx")
VOICES_BIN   = os.getenv("VOICES_BIN", "voices.bin")

# ── File paths ────────────────────────────────────────────────────────────────
RAW_TRANSCRIPT = os.getenv("RAW_TRANSCRIPT", "raw_transcript.txt")
TRANSCRIPT     = os.getenv("TRANSCRIPT", "transcript.txt")
SEGMENTS_DIR   = os.getenv("SEGMENTS_DIR", "segments")
FINAL_AUDIO    = os.getenv("FINAL_AUDIO", "final_audio.mp3")
OUTPUT_VIDEO   = os.getenv("OUTPUT_VIDEO", "output.mp4")

# ── Input video ───────────────────────────────────────────────────────────────
VIDEO_FILE = os.getenv("VIDEO_FILE", "paycontrol_sb_trim2.mp4")

# ── Encoding settings ─────────────────────────────────────────────────────────
AUDIO_BITRATE = os.getenv("AUDIO_BITRATE", "128k")
SAMPLE_RATE   = int(os.getenv("SAMPLE_RATE", 48000))
VIDEO_PRESET  = os.getenv("VIDEO_PRESET", "medium")
VIDEO_CRF     = os.getenv("VIDEO_CRF", "23")
