"""
The output frame map: which video frame is shown on each output frame.

Live recordings already follow the audio, so their map is just the trimmed range. For source videos the map is
built per segment so that audio drives the timeline:
  - narration longer than the footage -> play at 1x, then hold the last frame (before an anchored action, the
    hold happens just before it, so the click lands on its word)
  - footage longer than the narration -> drop frames where nothing moves first (loading, "Thinking..."), then
    speed up evenly, at most MAX_SPEEDUP; if that still is not enough the next segment simply starts later.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from demo import media
from demo.script import Demo
from demo.text import find_phrase

STATIC_THRESHOLD = 0.5  # mean abs pixel change between 96x54 thumbnails
KEEP_STATIC_S = 0.35
MAX_SPEEDUP = 2.0


@dataclass
class Plan:
    frames: np.ndarray
    fps: int
    segments: list[dict]
    late: list[dict] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return len(self.frames) / self.fps

    def to_out(self, t_video: float) -> float:
        """Output time at which the given video time first appears."""
        k = int(np.searchsorted(self.frames, int(round(t_video * self.fps)), side="left"))
        return min(k, len(self.frames) - 1) / self.fps


def motion(video: Path, cache: Path) -> np.ndarray:
    """Per-frame change score of the video, cached next to the build."""
    meta = {"video": str(video), "size": video.stat().st_size, "mtime": video.stat().st_mtime}
    meta_file, data_file = cache.with_suffix(".json"), cache.with_suffix(".npy")
    if meta_file.exists() and data_file.exists() and json.loads(meta_file.read_text()) == meta:
        return np.load(data_file)
    th = media.decode_video_thumbs(video, 96, 54).astype(np.int16)
    score = np.concatenate([[0.0], np.abs(np.diff(th, axis=0)).mean(axis=(1, 2, 3))])
    np.save(data_file, score)
    meta_file.write_text(json.dumps(meta))
    return score


def _compress(idx: np.ndarray, want: int, static: np.ndarray, fps: int) -> np.ndarray:
    n = len(idx)
    need = n - want
    keep_run = int(KEEP_STATIC_S * fps)
    runs, start = [], None
    for i, f in enumerate(idx):
        if static[f] and start is None:
            start = i
        elif not static[f] and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, n))
    removable = [max(0, (b - a) - keep_run) for a, b in runs]
    total = sum(removable)
    drop = np.zeros(n, dtype=bool)
    if total:
        take = min(need, total)
        alloc = [take * r // total for r in removable]
        for k in sorted(range(len(runs)), key=lambda k: -removable[k])[: take - sum(alloc)]:
            alloc[k] += 1
        for (a, b), cut in zip(runs, alloc):
            if cut:
                s = a + ((b - a) - cut) // 2
                drop[s:s + cut] = True
    kept = idx[~drop]
    if len(kept) > want:
        target = max(want, math.ceil(len(kept) / MAX_SPEEDUP), 1)
        kept = kept[np.round(np.linspace(0, len(kept) - 1, target)).astype(int)]
    return kept


def _emit(fa: int, fb: int, want: int, static: np.ndarray, fps: int) -> np.ndarray:
    """Source frames [fa, fb) squeezed or stretched into `want` output frames (as close as allowed)."""
    n = fb - fa
    if n <= 0:
        return np.full(max(0, want), max(0, fa - 1) if n < 0 else fa, dtype=np.int64)
    idx = np.arange(fa, fb, dtype=np.int64)
    if want >= n:
        return np.concatenate([idx, np.full(want - n, fb - 1, dtype=np.int64)])
    return _compress(idx, want, static, fps)


def source_plan(demo: Demo, lang: str, timeline: dict, events: list[dict], durations: dict, words: dict,
                motion_score: np.ndarray, log=print) -> Plan:
    fps = timeline["fps"]
    static = motion_score < STATIC_THRESHOLD
    frame = lambda t: min(int(round(t * fps)), len(static))  # noqa: E731
    p = demo.pacing
    dur = {d["index"]: d["duration"] for d in durations["segments"]}
    wmap = {w["index"]: w["words"] for w in words["segments"]}

    parts = [np.full(int(round(p["lead_in"] * fps)), frame(demo.segments[0].span[0]), dtype=np.int64)]
    length = len(parts[0])
    segments, late = [], []

    def add(chunk: np.ndarray) -> None:
        nonlocal length
        parts.append(chunk)
        length += len(chunk)

    for seg in demo.segments:
        out_start = length / fps
        narr = dur[seg.index]
        anchors = sorted(
            (e["t"], wmap[seg.index][find_phrase(seg.tokens(lang), e["at_word"])]["start"], e)
            for e in events if e["segment"] == seg.index and e.get("at_word")
        )
        cur = seg.span[0]
        for src_t, word_t, e in anchors:
            target = out_start + word_t
            add(_emit(frame(cur), frame(src_t), max(0, round((target - length / fps) * fps)), static, fps))
            lateness = length / fps - target
            if lateness > 0.1:
                late.append({"action": e["action"], "word": e["at_word"], "late_s": round(lateness, 3)})
                log(f"    WARNING: {e['action']} lands {lateness:.2f}s after '{e['at_word']}' "
                    f"(footage before it can't be shortened enough)")
            cur = src_t
        end_target = out_start + narr + p["gap"] + seg.hold
        add(_emit(frame(cur), frame(seg.span[1]), max(0, round((end_target - length / fps) * fps)), static, fps))
        seg_end = length / fps
        segments.append({"index": seg.index, "id": seg.id, "start": round(out_start, 4),
                         "narration_end": round(out_start + narr, 4), "end": round(seg_end, 4),
                         "span": list(seg.span), "overrun_s": round(max(0.0, seg_end - end_target), 3)})
        src_len = seg.span[1] - seg.span[0]
        log(f"  [{seg.index:03d}] {seg.id:<18} footage {src_len:5.1f}s -> {seg_end - out_start:5.1f}s "
            f"(narration {narr:5.2f}s)")

    tail = np.full(int(round(p["tail"] * fps)), parts[-1][-1] if len(parts[-1]) else 0, dtype=np.int64)
    add(tail)
    frames = np.minimum(np.concatenate(parts), len(static) - 1)
    if np.any(np.diff(frames) < 0):
        raise AssertionError("frame map must never go backwards")
    return Plan(frames=frames, fps=fps, segments=segments, late=late)


LIVE_KEEP_IDLE_S = 0.6
NARRATION_GUARD_S = 0.3
# Recorded actions are never dead time, however little they change the picture (typing a few letters barely moves
# the motion score). Waiting (wait_for) is not protected - that is exactly what the trimmer is for.
ACTION_EVENTS = {"move", "click", "type", "hover", "scroll", "press", "navigate"}
ACTION_GUARD_S = 0.25


def live_plan(demo: Demo, timeline: dict, motion_score: np.ndarray, log=print, events: list[dict] | None = None) -> Plan:
    """Trimmed recording with dead time removed: frames where nothing moves, no narration plays and no action runs
    (e.g. waiting for an LLM reply) are cut down to a short beat. Narration and actions are never touched."""
    fps = timeline["fps"]
    segs = timeline["segments"]
    first = math.ceil(max(timeline["usable"][0], segs[0]["start"] - demo.pacing["lead_in"]) * fps)
    last = math.floor(timeline["usable"][1] * fps)
    if segs[-1]["narration_end"] > timeline["usable"][1]:
        raise ValueError("last narration runs past the end of the recording")

    n = len(motion_score)
    protect = np.zeros(n, dtype=bool)
    protect[: math.ceil(segs[0]["start"] * fps)] = True
    protect[int(max(s["narration_end"] for s in segs) * fps):] = True
    for s in segs:
        if s["narration_end"] > s["start"]:
            protect[max(0, int((s["start"] - NARRATION_GUARD_S) * fps)): math.ceil((s["narration_end"] + NARRATION_GUARD_S) * fps)] = True
    for e in events or []:
        if e.get("type") in ACTION_EVENTS:
            a, b = e["t"] - ACTION_GUARD_S, e.get("t_end", e["t"]) + ACTION_GUARD_S
            protect[max(0, int(a * fps)): max(0, math.ceil(b * fps))] = True
    idle = (motion_score < STATIC_THRESHOLD) & ~protect

    keep = np.ones(last - first, dtype=bool)
    keep_run = int(LIVE_KEEP_IDLE_S * fps)
    cut_total, i = 0, first
    while i < last:
        if not idle[i]:
            i += 1
            continue
        j = i
        while j < last and idle[j]:
            j += 1
        if j - i > keep_run:
            half = keep_run // 2
            keep[i - first + half: j - first - (keep_run - half)] = False
            cut_total += (j - i) - keep_run
        i = j
    frames = np.arange(first, last, dtype=np.int64)[keep]
    if cut_total:
        log(f"Trimmed {cut_total / fps:.1f}s of dead time (static screen, no narration)")

    plan = Plan(frames=frames, fps=fps, segments=[], late=[a for s in segs for a in s.get("late_actions", [])])
    plan.segments = [{"index": s["index"], "id": s["id"], "start": round(plan.to_out(s["start"]), 4),
                      "narration_end": round(plan.to_out(s["start"]) + (s["narration_end"] - s["start"]), 4),
                      "end": round(plan.to_out(s["end"]), 4)} for s in segs]
    return plan
