"""
Stage 3: render. Video frames (via the frame map) + effects + narration clips at their segment starts
-> final.mp4 + final.srt.

Nothing here guesses timing: segment starts come from timeline.json / the retime plan, word times from words.json,
zoom and ripples from events.jsonl. Frames are composed in Python (sub-pixel crop, no zoompan jitter) and piped to
ffmpeg; the data contracts stay the same so a Remotion renderer could replace this later.
"""

import datetime
import json
import math
import os
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image

from demo import effects, media, retime
from demo.script import ISO639_2, Demo

INTRO_S = 2.4
OUTRO_S = 2.6
XFADE_S = 0.6
ENCODE_PRESET = os.environ.get("DEMO_PRESET", "medium")
SUB_MAX_CHARS = 48
SUB_MIN_SECONDS = 0.8
HIGHLIGHT = "&H004AD5FF&"
WHITE = "&H00FFFFFF&"


def _load(out_dir: Path, name: str) -> dict:
    path = out_dir / name
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run the earlier stages first")
    return json.loads(path.read_text(encoding="utf-8"))


def build_narration(out_dir: Path, durations: dict, segments: list[dict], trim_start: float, length: float,
                    music: dict | None) -> np.ndarray:
    rate = media.SAMPLE_RATE
    buf = np.zeros(int(round(length * rate)), dtype=np.float32)
    files = {d["index"]: out_dir / d["file"] for d in durations["segments"] if d["file"]}
    for s in segments:
        if s["index"] not in files:
            continue
        clip, clip_rate = sf.read(files[s["index"]], dtype="float32")
        if clip_rate != rate:
            raise ValueError(f"{files[s['index']]} is {clip_rate} Hz, expected {rate}")
        pos = int(round((s["start"] - trim_start) * rate))
        if pos < 0 or pos + len(clip) > len(buf):
            raise ValueError(f"segment {s['index']} narration does not fit inside the cut (pos {pos / rate:.2f}s)")
        buf[pos:pos + len(clip)] += clip

    if music:
        bed = media.decode_audio(Path(music["file"]), rate)
        if bed.size:
            bed = np.tile(bed, int(math.ceil(len(buf) / len(bed))))[: len(buf)] * (10 ** (music["volume_db"] / 20))
            n_in, n_out = min(rate, len(bed)), min(2 * rate, len(bed))
            bed[:n_in] *= np.linspace(0, 1, n_in, dtype=np.float32)
            bed[-n_out:] *= np.linspace(1, 0, n_out, dtype=np.float32)
            buf += bed

    peak = float(np.abs(buf).max()) if buf.size else 0.0
    if peak > 0.99:
        buf *= 0.99 / peak
    return buf


def build_cues(words: dict, segments: list[dict], trim_start: float) -> list[dict]:
    by_index = {w["index"]: w["words"] for w in words["segments"]}
    cues: list[dict] = []
    for s in segments:
        offset = s["start"] - trim_start
        seg_words = [{"word": w["word"], "start": w["start"] + offset, "end": w["end"] + offset}
                     for w in by_index[s["index"]]]
        cur: list[dict] = []
        for w in seg_words:
            text_len = len(" ".join(x["word"] for x in cur + [w]))
            cur_len = len(" ".join(x["word"] for x in cur))
            sentence_break = cur and cur[-1]["word"][-1] in ".?!" and cur_len >= 15
            clause_break = cur and cur[-1]["word"][-1] in ",;:" and cur_len >= SUB_MAX_CHARS * 0.6
            pause = cur and w["start"] - cur[-1]["end"] > 0.8
            if cur and (text_len > SUB_MAX_CHARS or sentence_break or clause_break or pause):
                cues.append({"words": cur, "seg_end": s["narration_end"] - trim_start})
                cur = []
            cur.append(w)
        if cur:
            cues.append({"words": cur, "seg_end": s["narration_end"] - trim_start})

    for i, c in enumerate(cues):
        c["start"] = c["words"][0]["start"]
        end = max(c["words"][-1]["end"] + 0.3, c["start"] + SUB_MIN_SECONDS)
        end = min(end, c["seg_end"] + 0.5)
        if i + 1 < len(cues):
            end = min(end, cues[i + 1]["words"][0]["start"] - 0.05)
        c["end"] = max(end, c["words"][-1]["end"])
    return cues


def _srt_time(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _ass_time(cs: int) -> str:
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_escape(s: str) -> str:
    return s.replace("\\", "/").replace("{", "(").replace("}", ")")


def write_srt(cues: list[dict], path: Path) -> None:
    lines = []
    for i, c in enumerate(cues, start=1):
        lines += [str(i), f"{_srt_time(c['start'])} --> {_srt_time(c['end'])}", " ".join(w["word"] for w in c["words"]), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_ass(cues: list[dict], path: Path, width: int, height: int, highlight: bool) -> None:
    font_size = round(height * 0.043)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Box,Segoe UI,{font_size},&HFF000000,&HFF000000,&H48101418,&H48101418,1,0,0,0,100,100,0,0,3,{round(font_size * 0.3)},0,2,120,120,{round(height * 0.06)},1
Style: Text,Segoe UI,{font_size},&H00FFFFFF,&H00FFFFFF,&HFF000000,&HFF000000,1,0,0,0,100,100,0,0,1,0,0,2,120,120,{round(height * 0.06)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def cs(t: float) -> int:
        return int(round(t * 100))

    events = []
    for c in cues:
        ws = [_ass_escape(w["word"]) for w in c["words"]]
        start, end = cs(c["start"]), cs(c["end"])
        # Background box drawn once per cue (layer 0), so colour changes in the text can't split it.
        events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Box,,0,0,0,,{' '.join(ws)}")
        if not highlight:
            events.append(f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Text,,0,0,0,,{' '.join(ws)}")
            continue
        bounds = [cs(w["start"]) for w in c["words"]] + [end]
        bounds[0] = start
        for i in range(len(ws)):
            b0, b1 = bounds[i], max(bounds[i + 1], bounds[i])
            if b1 == b0:
                continue
            text = " ".join(f"{{\\c{HIGHLIGHT}}}{w}{{\\c{WHITE}}}" if j == i else w for j, w in enumerate(ws))
            events.append(f"Dialogue: 1,{_ass_time(b0)},{_ass_time(b1)},Text,,0,0,0,,{text}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")


class FrameReader:
    """Sequential decoder; frames must be requested in non-decreasing order (the frame map guarantees it)."""

    def __init__(self, video: Path, width: int, height: int):
        self.size = (width, height)
        self.nbytes = width * height * 3
        self.proc = subprocess.Popen(
            [media.FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(video), "-map", "0:v:0",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=self.nbytes * 2)
        self.index = -1
        self.data = b""

    def get(self, idx: int) -> tuple[bytes, bool]:
        """Returns (frame bytes, changed since the last call)."""
        changed = False
        while self.index < idx:
            chunk = self.proc.stdout.read(self.nbytes)
            if len(chunk) < self.nbytes:
                break
            self.data, self.index, changed = chunk, self.index + 1, True
        return self.data, changed

    def close(self) -> None:
        self.proc.stdout.close()
        self.proc.kill()
        self.proc.wait()


def run_render(demo: Demo, lang: str, log=print, progress=None) -> None:
    out_dir = demo.lang_dir(lang)
    tl = _load(out_dir, "timeline.json")
    durations = _load(out_dir, "durations.json")
    words = _load(out_dir, "words.json")
    events = [json.loads(line) for line in (out_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
    fps = tl["fps"]
    out_w, out_h = demo.resolution
    src_w, src_h = tl["video_size"]
    video = out_dir / tl["video"]
    style = demo.style
    source_mode = tl.get("mode") == "source"

    if source_mode:
        log("Retiming footage to the narration:")
        plan = retime.source_plan(demo, lang, tl, events, durations, words, retime.motion(video, out_dir / "motion"), log)
    else:
        plan = retime.live_plan(demo, tl, retime.motion(video, out_dir / "motion"), log, events)

    n_intro = round(INTRO_S * fps) if style["intro"] else 0
    n_outro = round(OUTRO_S * fps) if style["outro"] else 0
    n_xfade = round(XFADE_S * fps)
    n_content = len(plan.frames)
    n_frames = n_intro + n_content + n_outro
    offset = n_intro / fps
    length = n_frames / fps

    segs = [{**s, "start": s["start"] + offset, "narration_end": s["narration_end"] + offset} for s in plan.segments]
    narration = build_narration(out_dir, durations, segs, 0.0, length, demo.music)
    sf.write(out_dir / "narration.wav", narration, media.SAMPLE_RATE, subtype="PCM_16")
    cues = build_cues(words, segs, 0.0)
    write_srt(cues, out_dir / "final.srt")
    write_ass(cues, out_dir / "final.ass", out_w, out_h, demo.subtitles.get("highlight", True))

    # Events in content time (the camera works on the content timeline, before the intro offset).
    content_events = []
    for e in events:
        e = dict(e)
        e["t"] = plan.to_out(e["t"])
        if "t_end" in e:
            e["t_end"] = plan.to_out(e["t_end"])
        content_events.append(e)
    camera = effects.Camera(content_events, src_w, src_h, float(style["zoom_max"])) if style["zoom"] else None
    clicks = [e for e in content_events if source_mode and e["type"] == "click" and e.get("width")
              and e.get("ripple", True) is not False]
    comp = effects.Compositor(out_w, out_h, src_w, src_h, style)
    date = datetime.date.today().strftime("%B %Y")
    intro = effects.card(out_w, out_h, style, demo.title, style["intro_subtitle"], date)
    outro = effects.card(out_w, out_h, style, demo.title, style["outro_subtitle"], "")
    blank = effects.card(out_w, out_h, style, "", "", "")

    # With no narration there are no cues: an empty .srt/.ass makes ffmpeg exit at once, so leave subtitles out.
    has_subs = bool(cues)
    if not has_subs:
        log("No subtitle cues (no narration) - rendering without subtitles")
    vf = "format=yuv420p" + (",ass=final.ass" if has_subs and demo.subtitles.get("burn", True) else "")
    args = [media.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{out_w}x{out_h}", "-r", str(fps), "-i", "-",
            "-i", "narration.wav"]
    maps = ["-map", "0:v", "-map", "1:a"]
    if has_subs and demo.subtitles.get("soft", True):
        args += ["-i", "final.srt"]
        maps += ["-map", "2:s", "-c:s", "mov_text", "-metadata:s:s:0", f"language={ISO639_2.get(lang, 'und')}",
                 "-disposition:s:0", "0"]
    args += ["-vf", vf, *maps,
             "-c:v", "libx264", "-preset", ENCODE_PRESET, "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p",
             "-r", str(fps), "-fps_mode", "cfr", "-g", str(fps * 2),
             "-c:a", "aac", "-b:a", "192k", "-ar", str(media.SAMPLE_RATE), "-ac", "2",
             "-frames:v", str(n_frames), "-t", f"{length:.6f}",
             "-metadata", f"title={demo.title}", "-movflags", "+faststart", "final.mp4"]
    log(f"Rendering {length:.1f}s ({n_frames} frames) at {out_w}x{out_h}: {len(cues)} subtitle cues, "
        f"{len(camera.keyframes) if camera else 0} camera keyframes, {len(clicks)} click ripples")

    encoder = subprocess.Popen(args, cwd=out_dir, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    # Drain ffmpeg's stderr while frames are piped in, so a chatty encoder can't block and its real error is kept.
    err_chunks: list[bytes] = []
    drain = threading.Thread(target=lambda: err_chunks.extend(iter(lambda: encoder.stderr.read(4096), b"")), daemon=True)
    drain.start()

    def encoder_error(context: str) -> media.MediaError:
        try:
            encoder.wait(timeout=10)
        except subprocess.TimeoutExpired:
            encoder.kill()
        drain.join(timeout=5)
        err = b"".join(err_chunks).decode(errors="replace").strip()
        return media.MediaError(f"ffmpeg {context} (exit code {encoder.returncode}):\n"
                                f"{err[-3000:] or '(ffmpeg printed no error message)'}")

    reader = FrameReader(video, src_w, src_h)
    last_key, last_bytes = None, b""
    t0 = time.perf_counter()
    try:
        for k in range(n_frames):
            j = k - n_intro
            if j < 0:
                fade = min(1.0, k / (0.8 * fps))
                key = ("intro", round(fade, 3))
                if key != last_key:
                    last_bytes = Image.blend(blank, intro, fade).tobytes()
            elif j >= n_content:
                key = ("outro",)
                if key != last_key:
                    last_bytes = outro.tobytes()
            else:
                t = j / fps
                data, changed = reader.get(int(plan.frames[j]))
                crop = camera.crop(t) if camera else (0.0, 0.0, float(src_w), float(src_h))
                rip = effects.ripples_at(clicks, t)
                blend_in = j / n_xfade if n_intro and j < n_xfade else None
                blend_out = (n_content - j) / n_xfade if n_outro and j >= n_content - n_xfade else None
                key = (plan.frames[j], tuple(round(c, 2) for c in crop), tuple(rip), blend_in, blend_out)
                if key != last_key or changed:
                    img = comp.compose(Image.frombuffer("RGB", (src_w, src_h), data), crop, rip)
                    if blend_in is not None:
                        img = Image.blend(intro, img, blend_in)
                    if blend_out is not None:
                        img = Image.blend(outro, img, blend_out)
                    last_bytes = img.tobytes()
            last_key = key
            try:
                encoder.stdin.write(last_bytes)
            except OSError as e:   # BrokenPipeError, or EINVAL on Windows: ffmpeg has already exited
                raise encoder_error(f"stopped while receiving frame {k} of {n_frames}") from e
            if progress and k % fps == 0:
                progress(k / n_frames)
            if k and k % (fps * 20) == 0:
                rate = k / (time.perf_counter() - t0)
                log(f"  {k / fps:6.1f}s / {length:.1f}s  ({rate:.1f} fps, ~{(n_frames - k) / rate:.0f}s left)")
        try:
            encoder.stdin.close()
        except OSError as e:
            raise encoder_error("failed while finishing the file") from e
        if encoder.wait() != 0:
            raise encoder_error("failed")
    finally:
        reader.close()
        if encoder.poll() is None:
            encoder.kill()

    render_info = {
        "mode": tl.get("mode", "live"),
        "frames": n_frames,
        "duration": length,
        "fps": fps,
        "intro_s": offset,
        "aligner": words.get("aligner"),
        "segments": [{"index": s["index"], "id": s["id"], "start": round(s["start"], 4),
                      "narration_end": round(s["narration_end"], 4)} for s in segs],
        "late_actions": plan.late,
        "camera_keyframes": [[round(t, 3), [round(v, 1) for v in s[:2]] + [round(s[2], 3)]]
                             for t, s in (camera.keyframes if camera else [])],
        "cues": len(cues),
    }
    (out_dir / "render.json").write_text(json.dumps(render_info, indent=2), encoding="utf-8")
    log(f"Done in {time.perf_counter() - t0:.0f}s: {out_dir / 'final.mp4'} and final.srt")
