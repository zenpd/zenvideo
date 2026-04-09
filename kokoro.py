import os
import re
import time
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

# ── Generate TTS ─────────────────────────────────────────────────────────────
GAP_MS = 1000   # 1 sec gap after each segment

os.makedirs("segments", exist_ok=True)

final_audio = AudioSegment.silent(duration=0)

for idx, (time_line, text_line) in enumerate(entries):
    clean_text = text_line.replace("—", ", ").replace("–", ", ").replace("'", "'").replace("'", "'")
    print(f"\n[{idx+1}/{len(entries)}] {time_line}")
    print(f"  Text: {clean_text[:70]}...")

    try:
        samples, sample_rate = kokoro.create(
            clean_text,
            voice="af_sky",
            speed=1.1,
            lang="en-us"
        )

        wav_file = f"temp_seg_{idx}.wav"
        sf.write(wav_file, samples, sample_rate)
        seg = AudioSegment.from_wav(wav_file)
        os.remove(wav_file)

        print(f"  TTS: {len(seg)/1000:.1f}s")

        seg.export(f"segments/seg_{idx+1:02d}_{time_line.replace(':', '-')}.mp3", format="mp3")

        final_audio += seg
        if idx < len(entries) - 1:
            final_audio += AudioSegment.silent(duration=GAP_MS)

        print(f"  Total so far: {len(final_audio)/1000:.1f}s ✅")

    except Exception as e:
        print(f"  FAILED: {e}")
        final_audio += AudioSegment.silent(duration=GAP_MS)

    time.sleep(0.2)

final_audio.export("final_audio.mp3", format="mp3")
mins = len(final_audio) // 60000
secs = (len(final_audio) % 60000) // 1000
print(f"\n✅ Done! final_audio.mp3 — {mins}:{secs:02d}")
