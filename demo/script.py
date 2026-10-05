"""
Load and validate demo.yaml. Every mistake is reported with its location, before anything runs.

Two modes share one schema:
  live   - `url:` is opened and every action is performed by Playwright while the screen is captured.
  source - `source: {video: ...}` is an existing screen recording. Actions describe what already happens in it
           (`at:` seconds, `box:` [x, y, w, h] in video pixels); segments say which `span:` of the video they cover.
"""

import difflib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from demo.text import find_phrase, spoken, tokens

# The installed Kokoro model (v0.19) ships English voices only.
KOKORO_LANGS = {"en": "en-us", "en-us": "en-us", "en-gb": "en-gb"}
ISO639_2 = {"en": "eng", "en-us": "eng", "en-gb": "eng"}

TARGET_KINDS = ("testid", "role", "text", "label", "placeholder", "css")
TARGET_EXTRAS = ("name", "nth", "exact")
COMMON_PARAMS = {"zoom"}
LIVE_PARAMS = {
    "click": {"timeout"},
    "fill": {"value", "instant", "timeout"},
    "hover": {"timeout"},
    "wait_for": {"timeout", "state"},
    "scroll": {"by", "duration"},
    "scroll_to": {"duration", "until_word", "align"},
    "press": {"key"},
    "goto": {"url"},
    "wait": {"seconds"},
    "select": {"option", "timeout"},       # native <select>: choose an option by its label (or value)
    "upload": {"path", "timeout"},         # attach a file to a file input; the target (optional) is the upload area
}
SOURCE_PARAMS = {
    "click": {"ripple"},
    "fill": {"value"},
    "hover": set(),
    "wait_for": set(),
    "scroll": {"by"},
    "press": {"key"},
    "focus": set(),
}
SOURCE_TIMING = {"at", "t_end", "box"}
NEEDS_TARGET = {"click", "fill", "hover", "wait_for", "scroll_to", "select"}
NO_TARGET = {"press", "goto", "wait"}
NEEDS_BOX = {"click", "fill", "hover", "focus"}
NEEDS_END = {"focus"}

DEFAULT_PACING = {
    "lead_in": 1.0,
    "gap": 0.6,
    "tail": 1.5,
    "cursor_ms": 550,
    "highlight_ms": 300,
    "typing_ms": 45,
    "action_timeout": 20.0,
    "narration_scroll": 1.0,  # 1 = keep the page moving while narration outlasts the actions, 0 = hold still
}
DEFAULT_STYLE = {
    "intro": True,
    "outro": True,
    "frame": True,
    "zoom": True,
    "zoom_max": 1.6,
    "intro_subtitle": "",
    "outro_subtitle": "",
    "background": ["#0f1033", "#2b2a78"],
}


class ScriptError(ValueError):
    pass


@dataclass
class Target:
    testid: str | None = None
    role: str | None = None
    name: str | None = None
    text: str | None = None
    label: str | None = None
    placeholder: str | None = None
    css: str | None = None
    nth: str | int | None = None
    exact: bool = False

    def describe(self) -> str:
        parts = [f"{k}={getattr(self, k)!r}" for k in (*TARGET_KINDS, "name", "nth") if getattr(self, k) is not None]
        return "{" + ", ".join(parts) + "}"


@dataclass
class Action:
    kind: str
    target: Target | None
    params: dict
    at_word: dict[str, str] = field(default_factory=dict)
    until_word: dict[str, str] = field(default_factory=dict)
    where: str = ""
    at: float | None = None
    t_end: float | None = None
    box: tuple[float, float, float, float] | None = None

    def describe(self) -> str:
        bits = [self.kind]
        if self.target:
            bits.append(self.target.describe())
        if self.params:
            bits.append(str(self.params))
        return " ".join(bits)


@dataclass
class Segment:
    index: int
    id: str
    say: dict[str, str]
    actions: list[Action]
    hold: float
    span: tuple[float, float] | None = None

    @property
    def silent(self) -> bool:
        return not self.say

    def spoken(self, lang: str) -> str:
        return spoken(self.say[lang]) if self.say else ""

    def tokens(self, lang: str) -> list[str]:
        return tokens(self.spoken(lang))


@dataclass
class Demo:
    path: Path
    title: str
    url: str | None
    source_video: Path | None
    languages: list[str]
    voice: dict[str, str]
    speed: float
    fps: int
    resolution: tuple[int, int]
    monitor: int
    capture: str            # "background" (hidden browser, screen stays free) or "screen" (full-screen kiosk + ddagrab)
    storage_state: Path | None
    hide: list[str]
    hide_scrollbars: bool
    music: dict | None
    subtitles: dict
    pacing: dict
    style: dict
    segments: list[Segment]
    build_root: Path

    @property
    def mode(self) -> str:
        return "source" if self.source_video else "live"

    def lang_dir(self, lang: str) -> Path:
        return self.build_root / lang

    def kokoro_lang(self, lang: str) -> str:
        return KOKORO_LANGS[lang]


def _err(where: str, msg: str) -> ScriptError:
    return ScriptError(f"{where}: {msg}")


def _suggest(word: str, options) -> str:
    close = difflib.get_close_matches(word, list(options), n=1)
    return f" (did you mean {close[0]!r}?)" if close else ""


def _per_lang(value, languages: list[str], where: str, what: str) -> dict[str, str]:
    if isinstance(value, str):
        return {lang: value for lang in languages}
    if isinstance(value, dict):
        missing = [lang for lang in languages if lang not in value]
        if missing:
            raise _err(where, f"{what} is missing language(s) {missing}")
        return {lang: str(value[lang]) for lang in languages}
    raise _err(where, f"{what} must be a string or a {{lang: text}} mapping")


def _parse_target(spec: dict, where: str) -> Target:
    kinds = [k for k in TARGET_KINDS if k in spec]
    if len(kinds) != 1:
        raise _err(where, f"target needs exactly one of {list(TARGET_KINDS)}, got {kinds or 'none'}")
    t = Target(**{k: spec[k] for k in (*TARGET_KINDS, *TARGET_EXTRAS) if k in spec})
    if t.name is not None and t.role is None:
        raise _err(where, "'name' only works together with 'role'")
    if t.nth is not None and t.nth not in ("first", "last") and not isinstance(t.nth, int):
        raise _err(where, "nth must be 'first', 'last' or an integer index")
    return t


def _parse_action(raw, languages: list[str], where: str, source_mode: bool) -> Action:
    table = SOURCE_PARAMS if source_mode else LIVE_PARAMS
    if not isinstance(raw, dict):
        raise _err(where, f"an action must be a mapping like {{click: {{testid: save}}}}, got {raw!r}")
    raw = dict(raw)
    at_word = raw.pop("at_word", None)
    if len(raw) != 1:
        raise _err(where, f"each action needs exactly one action key from {sorted(table)}, got {sorted(raw)}")
    kind, spec = next(iter(raw.items()))
    if kind not in table:
        other = LIVE_PARAMS if source_mode else SOURCE_PARAMS
        if kind in other:
            raise _err(where, f"{kind!r} is only available in {'live' if source_mode else 'source-video'} scripts")
        raise _err(where, f"unknown action {kind!r}{_suggest(kind, table)}")

    if kind == "press" and isinstance(spec, str):
        spec = {"key": spec}
    elif kind == "goto" and isinstance(spec, str):
        spec = {"url": spec}
    elif kind == "wait" and isinstance(spec, (int, float)):
        spec = {"seconds": spec}
    if not isinstance(spec, dict):
        raise _err(where, f"{kind}: expected a mapping, got {spec!r}")

    spec = dict(spec)
    if "at_word" in spec:
        at_word = spec.pop("at_word")
    target_keys = {k: spec.pop(k) for k in (*TARGET_KINDS, *TARGET_EXTRAS) if k in spec}
    target_keys = {k: v for k, v in target_keys.items() if v is not None}
    if kind == "scroll_to" and "label" in target_keys and "text" not in target_keys:
        target_keys["text"] = target_keys.pop("label")
    timing = {k: spec.pop(k) for k in SOURCE_TIMING if k in spec} if source_mode else {}
    allowed = table[kind] | COMMON_PARAMS
    unknown = set(spec) - allowed
    if unknown:
        u = sorted(unknown)[0]
        raise _err(where, f"{kind}: unknown option {u!r}{_suggest(u, allowed | set(TARGET_KINDS))}")

    z = spec.get("zoom", True)
    if not (isinstance(z, bool) or (isinstance(z, (list, tuple)) and len(z) == 4 and z[2] > 0 and z[3] > 0)):
        raise _err(where, "zoom must be true, false, or a region [x, y, width, height] to frame instead")

    target = None
    if target_keys:
        if kind in NO_TARGET:
            raise _err(where, f"{kind} does not take a target")
        target = _parse_target(target_keys, where)
    elif kind in NEEDS_TARGET and not source_mode:
        raise _err(where, f"{kind} needs a target, e.g. {{testid: ...}} or {{role: button, name: ...}}")

    at = t_end = box = None
    if source_mode:
        if "at" not in timing:
            raise _err(where, f"{kind} needs 'at' (seconds into the source video)")
        at = float(timing["at"])
        if "t_end" in timing:
            t_end = float(timing["t_end"])
            if t_end < at:
                raise _err(where, "t_end is before at")
        elif kind in NEEDS_END:
            raise _err(where, f"{kind} needs 't_end'")
        if "box" in timing:
            b = timing["box"]
            if not (isinstance(b, (list, tuple)) and len(b) == 4 and b[2] > 0 and b[3] > 0):
                raise _err(where, "box must be [x, y, width, height] in video pixels")
            box = tuple(float(v) for v in b)
        elif kind in NEEDS_BOX:
            raise _err(where, f"{kind} needs 'box: [x, y, width, height]' (video pixels)")
    else:
        if kind == "fill" and "value" not in spec:
            raise _err(where, "fill needs a 'value'")
        if kind == "select" and not str(spec.get("option") or "").strip():
            raise _err(where, "select needs an 'option' (the visible label of the choice)")
        if kind == "upload" and not str(spec.get("path") or "").strip():
            raise _err(where, "upload needs a 'path' to the file to attach")
        if kind == "scroll" and "by" not in spec:
            raise _err(where, "scroll needs 'by' (pixels, negative scrolls up)")
        if kind == "wait_for" and spec.get("state", "visible") not in ("visible", "hidden"):
            raise _err(where, "wait_for state must be 'visible' or 'hidden'")
    if at_word is not None and kind in ("wait", "goto", "focus"):
        raise _err(where, f"at_word makes no sense on {kind}")

    if kind == "scroll_to" and spec.get("align", "center") not in ("center", "top"):
        raise _err(where, "scroll_to align must be 'center' or 'top'")
    until = spec.pop("until_word", None)
    if until is not None and at_word is None:
        raise _err(where, "until_word needs an at_word to start from")

    words = _per_lang(at_word, languages, where, "at_word") if at_word is not None else {}
    until_words = _per_lang(until, languages, where, "until_word") if until is not None else {}
    return Action(kind=kind, target=target, params=spec, at_word=words, until_word=until_words, where=where,
                  at=at, t_end=t_end, box=box)


def _resolve_url(url: str, base: Path) -> str:
    expanded = os.path.expandvars(url)
    if "$" in expanded:
        raise ScriptError(f"url: environment variable not set in {url!r}")
    if re.match(r"^[a-z][a-z0-9+.-]*://", expanded, re.I):
        return expanded
    p = (base / expanded).resolve()
    if not p.exists():
        raise ScriptError(f"url: {expanded!r} is neither a URL nor an existing file (looked at {p})")
    return p.as_uri()


def load(path: str | Path, build_dir: str | Path | None = None, require_uploads: bool = True) -> Demo:
    path = Path(path).resolve()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ScriptError(f"{path.name}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ScriptError(f"{path.name}: top level must be a mapping")
    base = path.parent

    known = {"title", "url", "source", "languages", "voice", "speed", "fps", "resolution", "monitor", "capture",
             "storage_state", "hide", "hide_scrollbars", "music", "subtitles", "pacing", "style", "segments"}
    unknown = set(data) - known
    if unknown:
        u = sorted(unknown)[0]
        raise ScriptError(f"{path.name}: unknown key {u!r}{_suggest(u, known)}")
    if "segments" not in data:
        raise ScriptError(f"{path.name}: missing required key 'segments'")

    source_video = None
    if data.get("source"):
        src = data["source"]
        src = src if isinstance(src, dict) else {"video": src}
        if "video" not in src:
            raise ScriptError("source: needs 'video: <path to screen recording>'")
        source_video = (base / os.path.expandvars(str(src["video"]))).resolve()
        if not source_video.exists():
            raise ScriptError(f"source: video not found: {source_video}")
        if "url" in data:
            raise ScriptError("use either 'url' (live recording) or 'source' (existing video), not both")
    elif "url" not in data:
        raise ScriptError(f"{path.name}: needs 'url' (live recording) or 'source: {{video: ...}}' (existing video)")
    source_mode = source_video is not None

    languages = data.get("languages", ["en"])
    if isinstance(languages, str):
        languages = [languages]
    for lang in languages:
        if lang not in KOKORO_LANGS:
            raise ScriptError(
                f"languages: {lang!r} is not supported by the installed Kokoro model (v0.19, English voices only); "
                f"supported: {sorted(KOKORO_LANGS)}"
            )

    fps = int(data.get("fps", 30))
    if fps not in (30, 60):
        raise ScriptError("fps: must be 30 or 60")

    pacing = dict(DEFAULT_PACING)
    for k, v in (data.get("pacing") or {}).items():
        if k not in DEFAULT_PACING:
            raise ScriptError(f"pacing: unknown key {k!r}{_suggest(k, DEFAULT_PACING)}")
        pacing[k] = float(v)

    style = dict(DEFAULT_STYLE)
    for k, v in (data.get("style") or {}).items():
        if k not in DEFAULT_STYLE:
            raise ScriptError(f"style: unknown key {k!r}{_suggest(k, DEFAULT_STYLE)}")
        style[k] = v

    music = data.get("music")
    if music:
        if isinstance(music, str):
            music = {"file": music}
        mfile = (base / music["file"]).resolve()
        if not mfile.exists():
            raise ScriptError(f"music: file not found: {mfile}")
        music = {"file": mfile, "volume_db": float(music.get("volume_db", -28))}

    subtitles = {"burn": True, "highlight": True, "soft": True, **(data.get("subtitles") or {})}

    storage_state = data.get("storage_state")
    storage_state = (base / storage_state).resolve() if storage_state else None

    raw_segments = data["segments"]
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ScriptError("segments: must be a non-empty list")

    segments = []
    prev_end = 0.0
    for i, raw in enumerate(raw_segments, start=1):
        where = f"segments[{i}]"
        if not isinstance(raw, dict):
            raise _err(where, "each segment must be a mapping with 'say' and/or 'actions'")
        extra = set(raw) - {"id", "say", "actions", "hold", "span"}
        if extra:
            raise _err(where, f"unknown key(s) {sorted(extra)}")
        if "say" not in raw and not raw.get("actions"):
            raise _err(where, "a segment needs a 'say', 'actions', or both")
        say = _per_lang(raw["say"], languages, where, "say") if raw.get("say") else {}

        span = None
        if source_mode:
            s = raw.get("span")
            if not (isinstance(s, (list, tuple)) and len(s) == 2 and float(s[1]) > float(s[0]) >= 0):
                raise _err(where, "source-video segments need 'span: [start, end]' in seconds")
            span = (float(s[0]), float(s[1]))
            if span[0] < prev_end - 1e-6:
                raise _err(where, f"span starts at {span[0]}s, before the previous segment ends ({prev_end}s)")
            prev_end = span[1]
        elif "span" in raw:
            raise _err(where, "'span' is only for source-video scripts")

        actions = [
            _parse_action(a, languages, f"{where}.actions[{j}]", source_mode)
            for j, a in enumerate(raw.get("actions") or [], start=1)
        ]
        for a in actions:
            if a.kind == "upload":
                f = Path(os.path.expandvars(str(a.params["path"]))).expanduser()
                f = f if f.is_absolute() else (base / f)
                # Only `record` (and `validate`, which exists to catch exactly this) actually needs
                # the file on disk; `tts`/`render`/`check` never touch it, so a script re-run on one
                # of those after the upload file moved or was cleaned up shouldn't hard-fail on it.
                if require_uploads and not f.is_file():
                    raise _err(a.where, f"upload: file not found on this machine: {f}")
                a.params["path"] = str(f.resolve())
        seg = Segment(index=i, id=str(raw.get("id", f"seg{i:03d}")), say=say, actions=actions,
                      hold=float(raw.get("hold", 0.0)), span=span)
        last_at = span[0] if span else 0.0
        for a in actions:
            if a.at_word and seg.silent:
                raise _err(a.where, "at_word needs narration, but this segment has no 'say'")
            for lang, word in a.at_word.items():
                start_i = find_phrase(seg.tokens(lang), word)
                if start_i is None:
                    raise _err(a.where, f"at_word {word!r} does not occur in the {lang} narration: {seg.spoken(lang)!r}")
                if lang in a.until_word:
                    end_i = find_phrase(seg.tokens(lang), a.until_word[lang])
                    if end_i is None or end_i <= start_i:
                        raise _err(a.where, f"until_word {a.until_word[lang]!r} must occur after {word!r} in the "
                                            f"{lang} narration")
            if span:
                if not span[0] <= a.at <= span[1]:
                    raise _err(a.where, f"at={a.at}s is outside the segment span {list(span)}")
                if a.at < last_at - 1e-6:
                    raise _err(a.where, f"at={a.at}s is earlier than the previous action ({last_at}s)")
                last_at = a.at
        segments.append(seg)

    ids = [s.id for s in segments]
    dupes = sorted({x for x in ids if ids.count(x) > 1})
    if dupes:
        raise ScriptError(f"segments: duplicate id(s) {dupes}")

    voice = _per_lang(data.get("voice", "af_sky"), languages, "voice", "voice")
    resolution = tuple(data.get("resolution", (1920, 1080)))
    capture = str(data.get("capture", "background"))
    if capture not in ("background", "screen"):
        raise ScriptError(f"capture: must be 'background' or 'screen', not {capture!r}")

    return Demo(
        path=path,
        title=str(data.get("title", path.stem)),
        url=None if source_mode else _resolve_url(str(data["url"]), base),
        source_video=source_video,
        languages=languages,
        voice=voice,
        speed=float(data.get("speed", 1.0)),
        fps=fps,
        resolution=(int(resolution[0]), int(resolution[1])),
        monitor=int(data.get("monitor", 0)),
        capture=capture,
        storage_state=storage_state,
        hide=list(data.get("hide") or []),
        hide_scrollbars=bool(data.get("hide_scrollbars", True)),
        music=music,
        subtitles=subtitles,
        pacing=pacing,
        style=style,
        segments=segments,
        build_root=Path(build_dir).resolve() if build_dir else Path.cwd() / "build" / path.stem,
    )
