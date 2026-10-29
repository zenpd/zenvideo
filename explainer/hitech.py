"""
The Hi-tech style: the explainer's scenes (explainer.planner) and voice-over (explainer.voice.narrate) rendered by
HyperFrames (HeyGen's open-source HTML-to-video engine, Apache 2.0) - glowing kinetic motion graphics on one GSAP
timeline, with WebGL shader transitions between the scenes (@hyperframes/shader-transitions).

    render(work_dir, timeline, theme, log, progress, captions, music, logo, brand_name) -> final.mp4

The tooling is pinned in explainer/hyperframes/package.json (npm install there once). Everything runs on this
computer: GSAP and the shader library are copied into the project (no CDN), the voice is our own, the renderer's
telemetry and update checks are off, and it never publishes anything. It renders with the FFmpeg and headless Chrome
the rest of the pipeline already uses.
"""

import base64
import glob
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from demo import media
from demo.render import build_cues, write_ass, write_srt
from explainer import render as plain
from ppt.icons import ICONS

HERE = Path(__file__).resolve().parent
TOOLS = HERE / "hyperframes"
WEB = HERE / "web"
WORKERS = 4
# theme -> background, accent, second accent (a company's logo colours win: explainer.service.brand_colors)
PALETTES = {"midnight": ("#050816", "#22d3ee", "#a78bfa"), "daylight": ("#06122b", "#3b82f6", "#14b8a6"),
            "sunrise": ("#14060f", "#fb923c", "#f472b6"), "forest": ("#03120c", "#4ade80", "#facc15")}


class HyperFramesMissing(RuntimeError):
    pass


def _tool(*parts: str) -> Path:
    p = TOOLS / "node_modules" / Path(*parts)
    if not p.exists():
        raise HyperFramesMissing(f"HyperFrames is not installed - run `npm install` in {TOOLS}")
    return p


def _browser() -> str | None:
    """The headless Chrome Playwright already installed (newest), so HyperFrames needs no download of its own."""
    found = sorted(glob.glob(str(Path.home() / "AppData/Local/ms-playwright/chromium_headless_shell-*/"
                                 "chrome-headless-shell-win64/chrome-headless-shell.exe")))
    return found[-1] if found else None


def _env() -> dict:
    ffmpeg = Path(media.FFMPEG)
    env = {**os.environ, "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "HYPERFRAMES_NO_UPDATE_CHECK": "1",
           "HYPERFRAMES_NO_AUTO_INSTALL": "1", "HYPERFRAMES_SKIP_SKILLS": "1", "HYPERFRAMES_FFMPEG_PATH": str(ffmpeg),
           "PATH": str(ffmpeg.parent) + os.pathsep + os.environ.get("PATH", "")}
    if _browser():
        env["HYPERFRAMES_BROWSER_PATH"] = _browser()
    return env


def write_project(work_dir: Path, timeline: dict, theme: str = "midnight", logo: str | None = None,
                  brand: dict | None = None, brand_name: str = "") -> Path:
    """work_dir/hf/: index.html (the composition, with this video's data inlined), lib/ (GSAP, shader transitions),
    audio/mix.wav (voice and music)."""
    project = work_dir / "hf"
    (project / "lib").mkdir(parents=True, exist_ok=True)
    (project / "audio").mkdir(exist_ok=True)
    shutil.copyfile(_tool("gsap", "dist", "gsap.min.js"), project / "lib" / "gsap.min.js")
    shutil.copyfile(_tool("@hyperframes", "shader-transitions", "dist", "index.global.js"), project / "lib" / "shaders.js")
    shutil.copyfile(work_dir / "audio" / "mix.wav", project / "audio" / "mix.wav")
    bg, accent, accent2 = PALETTES.get(theme, PALETTES["midnight"])
    if brand:       # the company's colours: its dark colour deepened for the background, its vivid one as the accent
        accent = brand.get("accent") or accent
        accent2 = brand.get("accent2") or accent2
        if brand.get("primary"):
            bg = brand["primary"]
    data = {**timeline, "scenes": [{k: v for k, v in s.items() if k != "words"} for s in timeline["scenes"]],
            "icons": ICONS, "bg": bg, "accent": accent, "logo": logo, "brand_name": brand_name}
    d = round(timeline["duration"], 3)
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1920, height=1080" />
<title>{_esc(timeline.get("title") or "Explainer")}</title>
<script src="lib/gsap.min.js"></script>
<script src="lib/shaders.js"></script>
<style>{(WEB / "hitech.css").read_text(encoding="utf-8")}
:root {{ --bg: {bg}; --accent: {accent}; --accent2: {accent2}; }}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{d}" data-width="1920" data-height="1080">
  <audio id="voice" data-start="0" data-duration="{d}" data-volume="1" src="audio/mix.wav"></audio>
  <div id="driver" class="clip" data-start="0" data-duration="{d}" style="position:absolute;width:1px;height:1px;opacity:0"></div>
</div>
<script>window.VIDEO = {json.dumps(data, ensure_ascii=False).replace("</", "<\\/")};</script>
<script>{(WEB / "hitech.js").read_text(encoding="utf-8")}</script>
</body>
</html>
"""
    (project / "index.html").write_text(html, encoding="utf-8")
    return project


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(work_dir: Path, timeline: dict, theme: str = "midnight", log=print, progress=None, captions: str = "soft",
           music: bool = True, logo: Path | None = None, brand: dict | None = None, brand_name: str = "") -> Path:
    """final.mp4 (and final.srt, poster.jpg) through HyperFrames."""
    plain.mix_audio(work_dir, timeline["duration"], music)
    logo_url = "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode() if logo and logo.exists() else None
    project = write_project(work_dir, timeline, theme, logo_url, brand, brand_name)
    raw = work_dir / "hf_render.mp4"
    run(project, raw, timeline["duration"], log, progress, "shader transitions")
    return finish(work_dir, timeline, raw, captions, log)


def run(project: Path, raw: Path, duration: float, log=print, progress=None, what: str = "", gpu: bool = False,
        workers: int = WORKERS, ready_timeout_s: int = 45) -> None:
    """Render a HyperFrames project to raw (MP4 with its audio). gpu: draw WebGL with the graphics card (3D scenes);
    ready_timeout_s: how long a worker may take to load the page (3D models take a while)."""
    cmd = [str(_tool(".bin", "hyperframes.cmd" if os.name == "nt" else "hyperframes")), "render", str(project),
           "-o", str(raw), "-w", str(workers), "--quality", "standard",
           f"--player-ready-timeout={ready_timeout_s * 1000}"] + (["--browser-gpu"] if gpu else [])
    log(f"Rendering {duration:.1f}s with HyperFrames ({workers} workers{', ' + what if what else ''})")
    proc = subprocess.Popen(cmd, cwd=TOOLS, env=_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    tail: list[str] = []
    last = -1
    for line in proc.stdout:
        line = line.rstrip()
        tail = (tail + [line])[-25:]
        m = re.match(r"@hf-progress (\{.*\})", line)
        if m:
            try:
                p = json.loads(m[1]).get("pct", 0) / 100
            except json.JSONDecodeError:
                continue
            if progress:
                progress(min(0.99, p))
            if int(p * 10) != last:
                last = int(p * 10)
                log(f"  HyperFrames {round(p * 100)}%")
        elif "rendered in" in line or "Render complete" in line:
            log("  " + line.strip(" ◇█░"))
    if proc.wait() != 0 or not raw.exists():
        detail = "\n".join(t for t in tail if t.strip() and not t.startswith("[INFO]"))[-1500:]
        raise media.MediaError(f"HyperFrames could not render the video:\n{detail}")



def finish(work_dir: Path, timeline: dict, raw: Path, captions: str = "soft", log=print) -> Path:
    """final.mp4 from HyperFrames' render: captions (a switchable track, or burned in) and a poster frame."""
    segs = [{"index": i, "start": 0.0, "narration_end": sc["voice_end"]} for i, sc in enumerate(timeline["scenes"])]
    words = {"segments": [{"index": i, "words": sc.get("words") or []} for i, sc in enumerate(timeline["scenes"])]}
    cues = build_cues(words, segs, 0.0)
    write_srt(cues, work_dir / "final.srt")
    out = work_dir / "final.mp4"
    args = ["-i", raw]
    maps = ["-map", "0:v", "-map", "0:a?"]
    video = ["-c:v", "copy"]
    if captions == "burned" and cues:
        write_ass(cues, work_dir / "final.ass", 1920, 1080, True)
        video = ["-vf", "ass=final.ass", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
    if captions == "soft" and cues:
        args += ["-i", work_dir / "final.srt"]
        maps += ["-map", "1:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-disposition:s:0", "0"]
    media.run_ffmpeg([*args, *maps, *video, "-c:a", "aac", "-b:a", "192k", "-metadata", f"title={timeline['title']}",
                      "-movflags", "+faststart", out.name], cwd=work_dir)
    raw.unlink(missing_ok=True)
    second = timeline["scenes"][1] if len(timeline["scenes"]) > 1 else timeline["scenes"][0]
    at = max(second["start"] + 1.5, second["end"] - 1.2)
    media.run_ffmpeg(["-ss", f"{at:.2f}", "-i", out, "-frames:v", 1, "-vf", "scale=640:-2", "-q:v", 3, "poster.jpg"],
                     cwd=work_dir)
    log(f"Video ready: {out.name} ({timeline['duration']:.1f}s, {out.stat().st_size / 1e6:.1f} MB)")
    return out
