"""
Stage 1 — Format Transcript
Reads raw_transcript.txt, converts numbers to words, adds timestamps,
and writes transcript.txt ready for TTS generation.

CLI usage:
  python format_transcript.py

Imported usage:
  from format_transcript import format_transcript
  result = format_transcript(log=my_log_fn)
"""

import re
from num2words import num2words
from config import WPM, GAP_SEC, RAW_TRANSCRIPT, TRANSCRIPT


def convert_numbers(text: str) -> str:
    # e.g. "3.5%" → "three point five percent"
    text = re.sub(
        r'(\d+\.\d+)%',
        lambda m: num2words(float(m.group(1))).replace(',', '') + ' percent',
        text,
    )
    # e.g. "50%" → "fifty percent"
    text = re.sub(
        r'(\d+)%',
        lambda m: num2words(int(m.group(1))) + ' percent',
        text,
    )
    # e.g. "3.5" → "three point five"
    text = re.sub(
        r'\b(\d+)\.(\d+)\b',
        lambda m: num2words(int(m.group(1))) + ' point ' + num2words(int(m.group(2))),
        text,
    )
    # remaining plain integers
    text = re.sub(r'\b(\d+)\b', lambda m: num2words(int(m.group(1))), text)
    return text


def format_transcript(
    raw_path: str = None,
    out_path: str = None,
    wpm: int = None,
    gap_sec: int = None,
    log=print,
) -> dict:
    """
    Format raw transcript into timed transcript.

    Returns:
        dict with keys: segments (list of dicts), total_duration_sec (int)
    """
    raw_path = raw_path or RAW_TRANSCRIPT
    out_path = out_path or TRANSCRIPT
    wpm      = wpm      if wpm      is not None else WPM
    gap_sec  = gap_sec  if gap_sec  is not None else GAP_SEC

    with open(raw_path, "r", encoding="utf-8") as f:
        content = f.read()

    raw_segments = [s.strip() for s in content.split("---") if s.strip()]
    log(f"Total segments found: {len(raw_segments)}\n")

    current_sec  = 0
    output_lines = []
    segments_meta = []

    for i, seg in enumerate(raw_segments):
        lines = seg.split("\n")
        if len(lines) > 1:
            log(f"  Skipping heading: {lines[0].strip()}")
            seg = "\n".join(lines[1:]).strip()

        seg = convert_numbers(seg)
        word_count   = len(seg.split())
        duration_sec = (word_count / wpm) * 60

        h = current_sec // 3600
        m = (current_sec % 3600) // 60
        s = current_sec % 60
        timestamp = f"{h:02d}:{m:02d}:{s:02d}"

        output_lines.extend([timestamp, seg, ""])

        log(f"[{i+1}] {timestamp} | {word_count} words | {duration_sec:.0f}s")
        segments_meta.append({"index": i + 1, "timestamp": timestamp,
                               "words": word_count, "duration_sec": duration_sec})

        current_sec += int(duration_sec) + gap_sec

    total_h = current_sec // 3600
    total_m = (current_sec % 3600) // 60
    total_s = current_sec % 60
    log(f"\nEstimated total duration: {total_h:02d}:{total_m:02d}:{total_s:02d}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    log(f"Done! {out_path} ready.")
    return {"segments": segments_meta, "total_duration_sec": current_sec}


if __name__ == "__main__":
    format_transcript()
