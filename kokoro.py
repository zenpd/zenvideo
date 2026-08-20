import os
import re
import time
import numpy as np
import static_ffmpeg
static_ffmpeg.add_paths()
from pydub import AudioSegment
import soundfile as sf

from kokoro_onnx import Kokoro
kokoro = Kokoro("kokoro-v0_19.onnx", "voices.bin")
print("Kokoro loaded!\n")

# ── Helpers ──────────────────────────────────────────────────────────────────
def is_timestamp(s):
    return bool(re.match(r'^\d{2}:\d{2}:\d{2}$', s))

def time_to_ms(t):
    h, m, s = map(int, t.split(':'))
    return (h * 3600 + m * 60 + s) * 1000

# ── Parse transcript ─────────────────────────────────────────────────────────
with open("transcript.txt", "r", encoding="utf-8") as f:
    lines = [line.strip() for line in f.readlines() if line.strip()]

entries = []
i = 0
while i < len(lines):
    if is_timestamp(lines[i]):
        timestamp = lines[i]
        text_parts = []
        i += 1
        while i < len(lines) and not is_timestamp(lines[i]):
            text_parts.append(lines[i])
            i += 1
        if text_parts:
            entries.append((timestamp, " ".join(text_parts)))
    else:
        i += 1

print(f"Total segments: {len(entries)}")

# ── Generate TTS (Sequential, no per-segment export) ──────────────────────────
GAP_MS = 1000   # 1 sec gap after each segment
SAMPLE_RATE = 24000

print("Generating audio segments...")
start_time = time.time()

# Build audio in memory without exporting each segment
audio_parts = []
gap_audio = np.zeros(int((GAP_MS / 1000) * SAMPLE_RATE), dtype=np.float32)

for idx, (time_line, text_line) in enumerate(entries):
    clean_text = text_line.replace("—", ", ").replace("–", ", ").replace("'", "'").replace("'", "'")
    print(f"[{idx+1}/{len(entries)}] {time_line[:15]}... ", end="", flush=True)

    try:
        samples, sample_rate = kokoro.create(
            clean_text,
            voice="af_sky",
            speed=1.1,
            lang="en-us"
        )
        
        # Keep samples as numpy arrays (no WAV export)
        samples = np.array(samples, dtype=np.float32)
        audio_parts.append(samples)
        audio_parts.append(gap_audio)
        
        elapsed = time.time() - start_time
        print(f"✅ ({elapsed:.1f}s total)")

    except Exception as e:
        print(f"❌ FAILED: {e}")
        audio_parts.append(gap_audio)

# Combine all audio at once
print("\nCombining audio...")
if audio_parts:
    final_audio = np.concatenate(audio_parts[:-1])  # Remove last gap
    final_audio = np.clip(final_audio, -1.0, 1.0)
    
    # Export once as WAV then convert to MP3
    print("Exporting to MP3...")
    sf.write("final_audio.wav", final_audio, SAMPLE_RATE)
    
    # Convert WAV to MP3
    wav_audio = AudioSegment.from_wav("final_audio.wav")
    wav_audio.export("final_audio.mp3", format="mp3", bitrate="128k")
    os.remove("final_audio.wav")
    
    total_time = time.time() - start_time
    duration_sec = len(final_audio) / SAMPLE_RATE
    mins = int(duration_sec) // 60
    secs = int(duration_sec) % 60
    print(f"\n✅ Done! final_audio.mp3 — {mins}:{secs:02d}")
    print(f"Total time: {total_time:.1f}s")
