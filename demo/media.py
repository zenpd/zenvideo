import json
import subprocess
from pathlib import Path

import numpy as np
import static_ffmpeg.run

FFMPEG, FFPROBE = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()

SAMPLE_RATE = 48000


class MediaError(RuntimeError):
    pass


def run_ffmpeg(args: list, cwd: Path | None = None) -> None:
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *map(str, args)]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise MediaError(f"ffmpeg exited {r.returncode}\n  args: {' '.join(map(str, args))}\n{r.stderr[-3000:]}")


def probe(path: Path) -> dict:
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        raise MediaError(f"ffprobe failed on {path}: {r.stderr.strip()}")
    return json.loads(r.stdout)


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def stream(path: Path, kind: str) -> dict:
    for s in probe(path)["streams"]:
        if s["codec_type"] == kind:
            return s
    raise MediaError(f"{path} has no {kind} stream")


def stream_duration(path: Path, kind: str) -> float:
    s = stream(path, kind)
    if "duration" in s:
        return float(s["duration"])
    return duration(path)


def cfr_report(path: Path, fps: int) -> tuple[bool, str]:
    """True if every video frame is exactly 1/fps after the previous one."""
    s = stream(path, "video")
    num, den = map(int, s["time_base"].split("/"))
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    pts = sorted(int(x) for x in r.stdout.split() if x.strip().lstrip("-").isdigit())
    if len(pts) < 2:
        return False, "fewer than 2 frames"
    deltas = np.diff(pts) * num / den
    expected = 1 / fps
    bad = np.flatnonzero(np.abs(deltas - expected) > expected * 0.01)
    if bad.size:
        return False, f"{bad.size} of {len(deltas)} frame intervals differ from 1/{fps}s (first at frame {bad[0] + 1})"
    return True, f"{len(pts)} frames, all exactly 1/{fps}s apart"


def decode_audio(path: Path, rate: int = SAMPLE_RATE) -> np.ndarray:
    r = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-map", "0:a:0", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise MediaError(f"could not decode audio from {path}: {r.stderr.decode(errors='replace')[-1000:]}")
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def decode_video_thumbs(path: Path, width: int = 32, height: int = 18,
                        crop: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """Every frame (optionally cropped to w, h, x, y first), shrunk to width x height RGB. Shape (frames, h, w, 3)."""
    pre = f"crop={crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}," if crop else ""
    r = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-threads", "0", "-i", str(path),
         "-map", "0:v:0", "-vf", f"{pre}scale={width}:{height}:flags=area,format=rgb24",
         "-f", "rawvideo", "-"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise MediaError(f"could not decode video from {path}: {r.stderr.decode(errors='replace')[-1000:]}")
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(-1, height, width, 3)
