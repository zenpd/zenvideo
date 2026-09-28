"""
Stage 4: sync acceptance check. Fails loudly; writes check.json.

  - raw.mp4 and final.mp4 are constant frame rate
  - final audio vs video duration within 100 ms
  - every narration segment starts in final.mp4 within +/-40 ms of the timeline (measured on decoded audio)
  - capture clock fit (flash residual) within 40 ms
"""

import json

import numpy as np
import soundfile as sf

from demo import media
from demo.script import Demo

DURATION_TOLERANCE = 0.100
ONSET_TOLERANCE = 0.040
CLOCK_TOLERANCE_MS = 40.0


def _onset(samples: np.ndarray, rate: int, threshold: float, start: int = 0) -> int | None:
    win = max(1, rate // 200)
    rms = np.sqrt(np.convolve(samples[start:].astype(np.float64) ** 2, np.ones(win) / win, mode="valid"))
    hits = np.flatnonzero(rms > threshold)
    return int(hits[0]) + start if hits.size else None


def _locate(audio: np.ndarray, snippet: np.ndarray, rate: int, expected: float, search: float = 0.3) -> float | None:
    """Where the snippet best matches the audio near `expected` (normalized cross-correlation), in seconds."""
    lo = max(0, int((expected - search) * rate))
    hi = min(len(audio), int((expected + search) * rate) + len(snippet))
    window = audio[lo:hi].astype(np.float64)
    snip = snippet.astype(np.float64)
    if len(window) < len(snip) or not snip.any():
        return None
    n = 1 << (len(window) + len(snip)).bit_length()
    corr = np.fft.irfft(np.fft.rfft(window, n) * np.conj(np.fft.rfft(snip, n)), n)[: len(window) - len(snip) + 1]
    energy = np.sqrt(np.convolve(window ** 2, np.ones(len(snip)), mode="valid"))
    score = corr / (energy * np.linalg.norm(snip) + 1e-9)
    return (lo + int(np.argmax(score))) / rate


def run_check(demo: Demo, lang: str, log=print) -> bool:
    out_dir = demo.lang_dir(lang)
    final = out_dir / "final.mp4"
    render = json.loads((out_dir / "render.json").read_text(encoding="utf-8"))
    timeline = json.loads((out_dir / "timeline.json").read_text(encoding="utf-8"))
    durations = {d["index"]: d for d in json.loads((out_dir / "durations.json").read_text(encoding="utf-8"))["segments"]}
    fps = render["fps"]
    results: list[dict] = []

    def add(name: str, ok: bool, detail: str, level: str = "fail") -> None:
        results.append({"check": name, "ok": ok, "level": level, "detail": detail})

    for path in (out_dir / timeline["video"], final):
        ok, detail = media.cfr_report(path, fps)
        add(f"{path.name} constant {fps} fps", ok, detail)
    frames = int(media.stream(final, "video").get("nb_frames", 0))
    add("final frame count", frames == render["frames"], f"{frames} frames, render planned {render['frames']}")

    v = media.stream(final, "video")
    add("final video format", v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p",
        f"{v['codec_name']} {v['pix_fmt']} {v['width']}x{v['height']}")

    vdur = media.stream_duration(final, "video")
    adur = media.stream_duration(final, "audio")
    add("audio/video duration", abs(vdur - adur) <= DURATION_TOLERANCE,
        f"video {vdur:.3f}s, audio {adur:.3f}s, diff {abs(vdur - adur) * 1000:.0f} ms")

    audio = media.decode_audio(final)
    rate = media.SAMPLE_RATE
    worst = 0.0
    for s in render["segments"]:
        if not durations[s["index"]]["file"]:
            continue
        clip, _ = sf.read(out_dir / durations[s["index"]]["file"], dtype="float32")
        clip_onset = _onset(clip, rate, 0.2 * float(np.abs(clip).max()))
        if clip_onset is None:
            add(f"segment {s['index']} ({s['id']}) start", False, "clip has no speech")
            continue
        expected = s["start"] + clip_onset / rate
        found = _locate(audio, clip[clip_onset: clip_onset + int(0.8 * rate)], rate, expected)
        if found is None:
            add(f"segment {s['index']} ({s['id']}) start", False, f"speech not found near {expected:.3f}s")
            continue
        err = found - expected
        worst = max(worst, abs(err))
        add(f"segment {s['index']} ({s['id']}) start", abs(err) <= ONSET_TOLERANCE,
            f"expected {expected:.3f}s, found {found:.3f}s ({err * 1000:+.0f} ms)")

    if "worst_residual_ms" in timeline["sync"]:
        res = timeline["sync"]["worst_residual_ms"]
        add("capture clock fit", res <= CLOCK_TOLERANCE_MS,
            f"worst flash residual {res:.1f} ms, drift {(timeline['sync']['b'] - 1) * 1e6:+.0f} ppm")

    late = render.get("late_actions", [])
    add("word-anchored actions on time", not late,
        "all on time" if not late else "; ".join(f"{a['action']} {a['late_s']:.2f}s late" for a in late), level="warn")
    add("word timings", render.get("aligner") != "estimate-v1",
        f"aligner: {render.get('aligner')}" + ("" if render.get("aligner") != "estimate-v1"
                                               else " (no Whisper model - word times estimated)"), level="warn")

    passed = all(r["ok"] for r in results if r["level"] == "fail")
    (out_dir / "check.json").write_text(json.dumps({"passed": passed, "results": results}, indent=2), encoding="utf-8")

    width = max(len(r["check"]) for r in results)
    for r in results:
        mark = "PASS" if r["ok"] else ("WARN" if r["level"] == "warn" else "FAIL")
        log(f"  {mark}  {r['check']:<{width}}  {r['detail']}")
    log(f"{'PASSED' if passed else 'FAILED'}: sync check for {final}")
    return passed
