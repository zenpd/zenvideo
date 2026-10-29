"""
The explainer's picture and sound: the timeline as a self-contained HTML player (player.html), its frames taken one by
one in hidden browsers, and the final MP4 with the voice-over, a music bed and captions.

Frames are exact: the player's animations are all paused Web Animations, so seek(t) puts the page at second t and the
frame is captured - no screen recording, no dropped frames, and the same result on any machine. The frames are split
between a few browsers working in parallel; each writes a chunk, and the chunks are joined without re-encoding.

    write_player(work_dir, timeline, theme) -> player.html
    render(work_dir, timeline, log, progress, captions) -> final.mp4 (+ final.srt)
"""

import base64
import json
import math
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

from demo import media
from demo.render import build_cues, write_ass, write_srt
from ppt.icons import ICONS

WEB = Path(__file__).resolve().parent / "web"
REPO = Path(__file__).resolve().parent.parent
MUSIC = REPO / "music" / "corporate.mp3"
SIZE = (1920, 1080)
FPS = 30
THEMES = {"midnight": "Midnight", "daylight": "Daylight", "sunrise": "Sunrise", "forest": "Forest"}
MUSIC_DB = -24
WORKERS = max(1, min(4, (os.cpu_count() or 2) // 2))


def write_player(work_dir: Path, timeline: dict, theme: str = "midnight") -> Path:
    """player.html: the player with its CSS, script and this video's data inlined - opens from disk or the API."""
    data = {**timeline, "theme": theme if theme in THEMES else "midnight", "icons": ICONS, "audio": "audio/mix.wav",
            # the player needs scene and item times only, not every word
            "scenes": [{k: v for k, v in sc.items() if k != "words"} for sc in timeline["scenes"]]}
    page = {"conversation": "office", "presenters": "stage"}.get(timeline.get("style"), "player")   # which player draws it
    html = (WEB / f"{page}.html").read_text(encoding="utf-8")
    html = (html.replace("/*CSS*/", (WEB / f"{page}.css").read_text(encoding="utf-8"))
            .replace("/*DATA*/", "window.VIDEO = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + ";")
            .replace("/*JS*/", (WEB / f"{page}.js").read_text(encoding="utf-8")))
    out = work_dir / "player.html"
    out.write_text(html, encoding="utf-8")
    return out


def mix_audio(work_dir: Path, duration: float, music: bool = True) -> Path:
    """audio/mix.wav: the voice-over over a quiet music bed that fades in and out."""
    rate = media.SAMPLE_RATE
    voice, _ = sf.read(work_dir / "audio" / "voice.wav", dtype="float32")
    buf = np.zeros(int(round(duration * rate)), dtype=np.float32)
    buf[:min(len(buf), len(voice))] += voice[:len(buf)]
    if music and MUSIC.exists():
        bed = media.decode_audio(MUSIC, rate)
        if bed.size:
            bed = np.tile(bed, int(math.ceil(len(buf) / len(bed))))[:len(buf)] * (10 ** (MUSIC_DB / 20))
            n_in, n_out = min(rate, len(bed)), min(3 * rate, len(bed))
            bed[:n_in] *= np.linspace(0, 1, n_in, dtype=np.float32)
            bed[-n_out:] *= np.linspace(1, 0, n_out, dtype=np.float32)
            buf += bed
    peak = float(np.abs(buf).max()) if buf.size else 0.0
    if peak > 0.99:
        buf *= 0.99 / peak
    out = work_dir / "audio" / "mix.wav"
    sf.write(out, buf, rate, subtype="PCM_16")
    return out


def _render_chunk(player: Path, first: int, last: int, out: Path, fps: int, counter: list, lock) -> None:
    """Frames first..last-1 of the player into one video chunk, from its own hidden browser."""
    from playwright.sync_api import sync_playwright

    w, h = SIZE
    cmd = [media.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "pipe:0",
           "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-r", str(fps), "-g", str(fps * 2), str(out)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--force-color-profile=srgb", "--disable-lcd-text"])
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.add_init_script("window.RENDER = true")
            page.goto(player.as_uri())
            page.wait_for_function("window.READY === true", timeout=30000)
            cdp = page.context.new_cdp_session(page)
            for k in range(first, last):
                page.evaluate(f"window.seek({k / fps:.6f})")
                shot = cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 93, "optimizeForSpeed": True})
                enc.stdin.write(base64.b64decode(shot["data"]))
                with lock:
                    counter[0] += 1
            browser.close()
        enc.stdin.close()
        if enc.wait() != 0:
            raise media.MediaError(f"ffmpeg failed on {out.name}: {enc.stderr.read().decode(errors='replace')[-1500:]}")
    finally:
        if enc.poll() is None:
            enc.kill()


def render(work_dir: Path, timeline: dict, log=print, progress=None, captions: str = "soft",
           music: bool = True) -> Path:
    """final.mp4 from player.html and the voice-over. captions: "soft" (a track players can switch on), "burned"
    (always on screen) or "none"; final.srt is written either way."""
    fps, duration = FPS, timeline["duration"]
    n = int(math.ceil(duration * fps))
    player = work_dir / "player.html"
    mix = mix_audio(work_dir, duration, music)

    segs = [{"index": i, "start": 0.0, "narration_end": sc["voice_end"]} for i, sc in enumerate(timeline["scenes"])]
    words = {"segments": [{"index": i, "words": sc.get("words") or []} for i, sc in enumerate(timeline["scenes"])]}
    cues = build_cues(words, segs, 0.0)
    write_srt(cues, work_dir / "final.srt")

    chunks_dir = work_dir / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    for old in chunks_dir.glob("*.mp4"):
        old.unlink()
    workers = max(1, min(WORKERS, n // (fps * 10)))
    bounds = [round(n * i / workers) for i in range(workers + 1)]
    chunks = [chunks_dir / f"chunk_{i:02d}.mp4" for i in range(workers)]
    log(f"Rendering {duration:.1f}s ({n:,} frames at {SIZE[0]}x{SIZE[1]}, {fps} fps) in {workers} hidden browser(s)")
    counter, lock, t0 = [0], threading.Lock(), time.perf_counter()
    with ThreadPoolExecutor(workers) as pool:
        jobs = [pool.submit(_render_chunk, player, bounds[i], bounds[i + 1], chunks[i], fps, counter, lock)
                for i in range(workers)]
        last_log = 0.0
        while not all(j.done() for j in jobs):
            time.sleep(0.5)
            done = counter[0]
            if progress:
                progress(done / n)
            if time.perf_counter() - last_log > 15 and done:
                rate = done / (time.perf_counter() - t0)
                log(f"  {done:,} / {n:,} frames ({rate:.0f} fps, ~{(n - done) / rate:.0f}s left)")
                last_log = time.perf_counter()
        for j in jobs:
            j.result()
    log(f"Frames done in {time.perf_counter() - t0:.0f}s")

    (chunks_dir / "list.txt").write_text("".join(f"file '{c.name}'\n" for c in chunks), encoding="utf-8")
    out = work_dir / "final.mp4"
    args = ["-f", "concat", "-safe", "0", "-i", chunks_dir / "list.txt", "-i", mix]
    maps = ["-map", "0:v", "-map", "1:a"]
    if captions == "burned" and cues:
        write_ass(cues, work_dir / "final.ass", SIZE[0], SIZE[1], True)
        video = ["-vf", "ass=final.ass", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
    else:
        video = ["-c:v", "copy"]
    if captions == "soft" and cues:
        args += ["-i", work_dir / "final.srt"]
        maps += ["-map", "2:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-disposition:s:0", "0"]
    media.run_ffmpeg([*args, *maps, *video, "-c:a", "aac", "-b:a", "192k", "-ar", media.SAMPLE_RATE, "-ac", 2,
                      "-t", f"{n / fps:.6f}", "-metadata", f"title={timeline['title']}", "-movflags", "+faststart",
                      out.name], cwd=work_dir)
    for c in chunks:
        c.unlink(missing_ok=True)
    second = timeline["scenes"][1] if len(timeline["scenes"]) > 1 else timeline["scenes"][0]
    # explainer: near the end of the second scene, when all its items are on screen; conversation: the opening shot
    # of the office with the title
    at = 1.8 if timeline.get("style") in ("conversation", "presenters") else max(second["start"] + 1.5, second["end"] - 1.2)
    media.run_ffmpeg(["-ss", f"{at:.2f}", "-i", out, "-frames:v", 1,
                      "-vf", "scale=640:-2", "-q:v", 3, "poster.jpg"], cwd=work_dir)   # the list's thumbnail
    log(f"Video ready: {out.name} ({duration:.1f}s, {out.stat().st_size / 1e6:.1f} MB)")
    return out
