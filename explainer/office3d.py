"""
The 3D conversation: the conversation style's script and voices (explainer.dialogue, explainer.voice.narrate_dialogue)
played by two realistic 3D office people - Microsoft Rocketbox avatars (MIT licence) with motion-captured talking,
listening and idle animations and facial blendshapes for lip-sync - in a lit office with the company's logo and a
wall screen, rendered by HyperFrames with Three.js (explainer/web/office3d.js).

    render(work_dir, timeline, log, progress, captions, music, logo, brand, brand_name) -> final.mp4

Assets: build/rocketbox/<Avatar>/ (avatar.fbx with blendshapes, textures converted to JPG/PNG) and
build/rocketbox/anims/*.fbx - prepared from https://github.com/microsoft/Microsoft-Rocketbox (see AVATARS).
Tools: explainer/hyperframes (npm install there once): HyperFrames, GSAP and Three.js, copied into each project.
"""

import json
import shutil
from pathlib import Path

from explainer import hitech
from explainer import render as plain

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "build" / "rocketbox"

# Rocketbox avatars: folder, texture prefix, motion set; name and voice are the defaults the cast picker shows
AVATARS = {
    "business_female_04": {"name": "Sophie", "voice": "bf_emma", "folder": "Business_Female_04", "tex": "f020", "set": "f"},
    "business_male_03": {"name": "James", "voice": "bm_george", "folder": "Business_Male_03", "tex": "m020", "set": "m"},
}
DEFAULT_3D = ("business_female_04", "business_male_03")
MOTIONS = {
    "f": {"idle": ["f_idle_breathe_01.fbx"],
          "talk": ["f_gestic_talk_neutral_01.fbx", "f_gestic_talk_relaxed_01.fbx", "f_gestic_talk_neutral_02.fbx",
                   "f_gestic_talk_self-assured_01.fbx"],
          "listen": ["f_gestic_listen_neutral_01.fbx", "f_gestic_listen_accept_01.fbx"],
          "point": ["f_gestic_presentation_right_01.fbx"]},
    "m": {"idle": ["m_idle_breathe_01.fbx"],
          "talk": ["m_gestic_talk_neutral_01.fbx", "m_gestic_talk_relaxed_01.fbx", "m_gestic_talk_neutral_02.fbx"],
          "listen": ["m_gestic_listen_neutral_01.fbx", "m_gestic_listen_accept_01.fbx"],
          "point": ["m_gestic_presentation_left_01.fbx"]},
}
THREE_FILES = ["build/three.module.js", "examples/jsm/loaders/FBXLoader.js", "examples/jsm/libs/fflate.module.js",
               "examples/jsm/curves/NURBSCurve.js", "examples/jsm/curves/NURBSUtils.js",
               "examples/jsm/environments/RoomEnvironment.js"]


def write_project(work_dir: Path, timeline: dict, avatars: tuple[str, str], logo: str | None = None,
                  brand: dict | None = None, brand_name: str = "") -> Path:
    """work_dir/hf3d/: index.html, the 3D player, Three.js and GSAP, the two avatars, their motions, the audio."""
    project = work_dir / "hf3d"
    lib = project / "lib"
    (lib / "jsm").mkdir(parents=True, exist_ok=True)
    three = hitech._tool("three")
    for f in THREE_FILES:
        dst = lib / ("three.module.js" if f.startswith("build/") else Path("jsm", *Path(f).parts[2:]))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(three / f, dst)
    shutil.copyfile(hitech._tool("gsap", "dist", "gsap.min.js"), lib / "gsap.min.js")
    shutil.copyfile(HERE / "web" / "office3d.js", project / "office3d.js")
    (project / "audio").mkdir(exist_ok=True)
    shutil.copyfile(work_dir / "audio" / "mix.wav", project / "audio" / "mix.wav")
    cast = []
    for i, c in enumerate(timeline["cast"]):
        a = AVATARS[avatars[i]]
        src, dst = ASSETS / a["folder"], project / "assets" / "avatars" / a["folder"]
        if not (src / "avatar.fbx").exists():
            raise FileNotFoundError(f"Rocketbox avatar {a['folder']} is not prepared in {ASSETS}")
        shutil.copytree(src, dst, dirs_exist_ok=True)
        motions = MOTIONS[a["set"]]
        (project / "assets" / "anims").mkdir(parents=True, exist_ok=True)
        for files in motions.values():
            for f in files:
                shutil.copyfile(ASSETS / "anims" / f, project / "assets" / "anims" / f)
        t = a["tex"]
        cast.append({**c, "model": a["folder"], "anims": motions,
                     "textures": {"body": f"{t}_body_color.jpg", "bodyN": f"{t}_body_normal.jpg",
                                  "head": f"{t}_head_color.jpg", "headN": f"{t}_head_normal.jpg",
                                  "hair": f"{t}_opacity_color.png"}})
    b = brand or {}
    data = {k: v for k, v in timeline.items() if k not in ("scenes",)}
    data["lines"] = [{k: v for k, v in ln.items() if k != "words"} for ln in timeline["lines"]]
    data.update(cast=cast, logo=logo, brand_name=brand_name, primary=b.get("primary") or "#0b2545",
                primary2=b.get("primary2") or "#173a63", accent=b.get("accent") or "#00b8a3")
    d = round(timeline["duration"], 3)
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1920, height=1080" />
<title>{hitech._esc(timeline.get("title") or "Conversation")}</title>
<script>window.__hfTimelinesBuilding = true;</script>
<script src="lib/gsap.min.js"></script>
<script type="importmap">{{"imports": {{"three": "./lib/three.module.js", "three/addons/": "./lib/jsm/"}}}}</script>
<style>{(HERE / "web" / "office3d.css").read_text(encoding="utf-8")}
:root {{ --accent: {data["accent"]}; --primary: {data["primary"]}; --primary2: {data["primary2"]}; }}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{d}" data-width="1920" data-height="1080">
  <canvas id="gl" width="1920" height="1080"></canvas>
  <div id="over"></div>
  <audio id="voice" data-start="0" data-duration="{d}" data-volume="1" src="audio/mix.wav"></audio>
  <div id="driver" class="clip" data-start="0" data-duration="{d}" style="position:absolute;width:1px;height:1px;opacity:0"></div>
</div>
<script>window.VIDEO = {json.dumps(data, ensure_ascii=False).replace("</", "<\\/")};</script>
<script type="module" src="office3d.js"></script>
</body>
</html>
"""
    (project / "index.html").write_text(html, encoding="utf-8")
    return project


def render(work_dir: Path, timeline: dict, log=print, progress=None, captions: str = "soft", music: bool = True,
           avatars: tuple[str, str] = DEFAULT_3D, logo: Path | None = None, brand: dict | None = None,
           brand_name: str = "") -> Path:
    """final.mp4 (and final.srt, poster.jpg): the 3D conversation rendered by HyperFrames on the graphics card."""
    import base64
    plain.mix_audio(work_dir, timeline["duration"], music)
    logo_url = "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode() if logo and logo.exists() else None
    project = write_project(work_dir, timeline, avatars, logo_url, brand, brand_name)
    raw = work_dir / "hf_render.mp4"
    hitech.run(project, raw, timeline["duration"], log, progress, "3D, graphics card", gpu=True, workers=2,
               ready_timeout_s=300)
    return hitech.finish(work_dir, timeline, raw, captions, log)
