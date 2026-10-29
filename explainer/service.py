"""
The explainer skill's one entry point: narration in, animated video out, in one of two styles:

  explainer     motion graphics: titles, key points, steps, numbers and comparisons animate in as they are said
  conversation  two colleagues talk it through at a desk in an office, a wall screen showing the key points
  presenters    two co-presenters stand in a branded studio (the company's logo behind them) and present to camera

    generate(work_dir, narration, title=..., style=..., theme=..., voice=..., ...) -> (final.mp4, token usage or None)

work_dir keeps what a video needs to be made again cheaply: narration.txt, plan.json (the scenes or the dialogue -
the only step that costs tokens), timeline.json and audio/ (the voice-over), player.html (the animation, viewable in
a browser) and final.mp4 / final.srt. Changing the theme, voices, speed, captions or music reuses the plan, so it costs
no tokens; a new style, script mode, cast or length - or 'replan' - asks Azure for a new one.
"""

import base64
import json
import shutil
from pathlib import Path

from PIL import Image

from explainer import render
import re

from explainer.dialogue import fit_length, plan_dialogue, presets_for
from explainer.planner import MODES, estimate_seconds, fit_scenes, plan_scenes
from explainer.voice import narrate, narrate_dialogue

PLAN_VERSION = 2
STYLES = ("explainer", "conversation", "presenters", "hitech", "conversation3d")   # hitech, 3D: by HyperFrames
TALK = ("conversation", "presenters", "conversation3d")
MAX_SPEED = 1.12        # a script that comes out longer than asked is spoken a little faster, up to this


def stage_of(msg: str) -> str | None:
    """What a log line says the run is doing now, for the studio's progress display (None: no change)."""
    m = re.match(r"\s*line (\d+)/(\d+)", msg)
    if m:
        return f"Voicing line {int(m[1])} of {m[2]}"
    m = re.match(r"\s*scene (\d+)", msg)
    if m:
        return f"Voicing scene {int(m[1])}"
    for start, stage in (("Writing the conversation", "Writing the script"), ("Planning the scenes", "Planning the scenes"),
                         ("Shortening the script", "Shortening the script to fit the length"),
                         ("Rendering", "Animating"), ("Voicing", "Voicing the script")):
        if msg.startswith(start):
            return stage
    return None


def _add(a: dict | None, b: dict | None) -> dict | None:
    """Two AI calls' token usage added up."""
    if not a or not b:
        return a or b
    return {**a, **{k: round(a[k] + b[k], 6) for k in ("input_tokens", "output_tokens", "cost_usd")}}


def brand_colors(logo: Path) -> dict:
    """The logo's own colours for the studio: its darkest common colour (the wall) and its most vivid one (accents)."""
    img = Image.open(logo).convert("RGBA")
    img.thumbnail((300, 300))
    px = [p[:3] for p in img.get_flattened_data() if p[3] > 200] if hasattr(img, "get_flattened_data") else \
        [p[:3] for p in img.getdata() if p[3] > 200]
    bins: dict = {}
    for c in px:                       # colours grouped coarsely, each group's real average kept
        bins.setdefault(tuple(v // 16 for v in c), []).append(c)
    common = [tuple(sum(ch) // len(cs) for ch in zip(*cs)) for _, cs in sorted(bins.items(), key=lambda kv: -len(kv[1]))
              if len(cs) > 3][:40]
    hexa = lambda c: "#%02x%02x%02x" % c   # noqa: E731
    lift = lambda c, k: tuple(round(v + (255 - v) * k) for v in c)   # noqa: E731
    dark = next((c for c in common if sum(c) < 200), None)     # the most common dark colour (text, mark)
    vivid = max(common, key=lambda c: max(c) - min(c), default=None)
    out = {}
    if dark:
        out.update(primary=hexa(dark), primary2=hexa(lift(dark, 0.12)))
    if vivid and max(vivid) - min(vivid) > 80:
        out.update(accent=hexa(vivid), accent2=hexa(lift(vivid, 0.5)))
    return out


def _plan_key(style: str, title: str, mode: str, seconds: int, cast: tuple[str, str]) -> dict:
    """What a saved plan was made for; a plan made for anything else is planned again."""
    if style in TALK:
        return {"version": PLAN_VERSION, "style": style, "title": title, "seconds": seconds, "cast": list(cast)}
    return {"version": PLAN_VERSION, "style": style, "title": title, "mode": mode,
            **({"seconds": seconds} if mode == "tighten" else {})}


def _saved_plan(work_dir: Path, key: dict) -> dict | None:
    plan, narration = work_dir / "plan.json", work_dir / "narration.txt"
    if not plan.exists():
        return None
    try:
        saved = json.loads(plan.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    fresh = saved.get("made_for") == key and (not narration.exists() or plan.stat().st_mtime >= narration.stat().st_mtime)
    return saved if fresh else None


def generate(work_dir: Path, narration: str, title: str = "", theme: str = "midnight", voice: str = "af_sky",
             speed: float = 1.0, mode: str = "as_written", target_seconds: int = 120, captions: str = "soft",
             music: bool = True, replan: bool = False, log=print, progress=None, style: str = "explainer",
             cast: tuple[str, str] | None = None, voices: tuple[str, str] | None = None,
             logo: Path | None = None, brand_name: str = "") -> tuple[Path, dict | None]:
    """Plan (or reuse) the scenes or dialogue, voice them, animate them, render the MP4. progress(fraction) covers the
    render. voice: the explainer's narrator; cast and voices: the conversation's two people (preset ids from
    explainer.dialogue.CAST, or STUDIO_CAST for presenters) and, optionally, other voices for them. logo: an image of
    the company's logo for the presenters' studio (kept as logo.png; its colours become the set's); brand_name: the
    company's name, shown when there is no logo."""
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    style = style if style in STYLES else "explainer"
    mode = mode if mode in MODES else "as_written"
    presets, default = presets_for(style if style in TALK else "conversation")
    cast = tuple(c if c in presets else default[i] for i, c in enumerate(cast or default))
    if logo:
        shutil.copyfile(logo, work_dir / "logo.png") if Path(logo).resolve() != (work_dir / "logo.png") else None
    saved = work_dir / "narration.txt"
    if narration:
        if not saved.exists() or saved.read_text(encoding="utf-8") != narration:   # unchanged: the plan stays fresh
            saved.write_text(narration, encoding="utf-8")
    else:
        narration = saved.read_text(encoding="utf-8")
    key = _plan_key(style, title, mode, target_seconds, cast)
    usage = None
    plan = None if replan else _saved_plan(work_dir, key)
    if plan:
        log("Reusing the plan (plan.json) - no tokens spent")
        if style in TALK:                                 # a plan saved before the length was checked
            fitted, more = fit_length(plan, narration, title, cast, target_seconds, log, fmt=style)
            if more:
                plan, usage = {**fitted, "made_for": key}, more
                (work_dir / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        elif mode == "tighten":                           # a scene plan saved before the length was checked
            before = estimate_seconds(plan)
            fit_scenes(plan, target_seconds, log)
            if estimate_seconds(plan) < before:
                (work_dir / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        if style in TALK:
            plan, usage = plan_dialogue(narration, title, cast, target_seconds, log, fmt=style)
        else:
            plan, usage = plan_scenes(narration, title, mode, target_seconds, log)
        plan["made_for"] = key
        (work_dir / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

    if style in TALK:
        for i, v in enumerate(voices or ()):
            if v:
                plan["cast"][i]["voice"] = v
        log(f"{len(plan['lines'])} lines between {plan['cast'][0]['name']} ({plan['cast'][0]['role']}) and "
            f"{plan['cast'][1]['name']} ({plan['cast'][1]['role']})")
        log(f"Voicing the script ({plan['cast'][0]['voice']} and {plan['cast'][1]['voice']}, speed {speed})")
        timeline = narrate_dialogue(plan, work_dir, speed, log)
        if timeline["duration"] > target_seconds and speed < MAX_SPEED:
            faster = min(MAX_SPEED, round(speed * timeline["duration"] / target_seconds + 0.01, 2))
            log(f"{timeline['duration']:.0f}s is over the {target_seconds}s asked for - speaking at {faster}x")
            timeline = narrate_dialogue(plan, work_dir, faster, log)
        saved_logo = work_dir / "logo.png"       # the company's logo and colours (office and studio)
        if saved_logo.exists():
            timeline["logo"] = "data:image/png;base64," + base64.b64encode(saved_logo.read_bytes()).decode()
            timeline["brand"] = brand_colors(saved_logo)
        timeline["brand_name"] = brand_name
    else:
        log(f"{len(plan['scenes'])} scenes: {', '.join(s['type'] for s in plan['scenes'])}")
        log(f"Voicing the scenes ({voice}, speed {speed})")
        timeline = narrate(plan, work_dir, voice, speed, log)
        if mode == "tighten" and timeline["duration"] > target_seconds and speed < MAX_SPEED:
            faster = min(MAX_SPEED, round(speed * timeline["duration"] / target_seconds + 0.01, 2))
            log(f"{timeline['duration']:.0f}s is over the {target_seconds}s asked for - speaking at {faster}x")
            timeline = narrate(plan, work_dir, voice, faster, log)
    if style == "conversation3d":
        from explainer import office3d
        out = office3d.render(work_dir, timeline, log, progress, captions, music, avatars=cast,
                              logo=work_dir / "logo.png" if (work_dir / "logo.png").exists() else None,
                              brand=timeline.get("brand"), brand_name=brand_name)
        return out, usage
    if style == "hitech":
        from explainer import hitech
        saved_logo = work_dir / "logo.png"
        out = hitech.render(work_dir, timeline, theme, log, progress, captions, music,
                            logo=saved_logo if saved_logo.exists() else None,
                            brand=brand_colors(saved_logo) if saved_logo.exists() else None, brand_name=brand_name)
        return out, usage
    render.write_player(work_dir, timeline, theme)
    out = render.render(work_dir, timeline, log, progress, captions, music)
    return out, usage
