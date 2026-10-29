"""
The explainer's scene plan: the narration split into scenes, each with what to show while it is spoken - one Azure
OpenAI call, then checked in code (like the PPT story): scene types and counts clamped, figures and names only from the
narration, icons validated, and every sentence of the narration spoken exactly once, in order.

Two script modes:
  as_written  the narration is spoken word for word; the model only decides where each scene starts (a sentence
              number) and what it shows.
  tighten     the model also rewrites the voice-over to about the target length (each scene's "say"); the rewrite is
              fact-checked like the visuals.

Every revealed item names a "cue": a few words of the scene's voice-over, so it appears exactly when they are spoken.

    plan_scenes(narration, title, mode, target_seconds, log) -> (plan, token usage)
"""

import re

from demo.text import norm, spoken, tokens
from ppt import source
from ppt.icons import ICONS
from ppt.quality import CTA_VERBS, _key_terms
from ppt.writer import StoryError, _numbers_in, _scrub, _stated, _vocab, chat_json

SCENE_TYPES = ("title", "statement", "points", "stats", "steps", "compare", "chart", "icons", "quote", "closing")
WPM = 160                  # Kokoro's pace at speed 1.0, roughly
MODES = ("as_written", "tighten")

PROMPT = """You are a motion-graphics director making an animated explainer video (like the short animated videos
companies put on their websites). The voice-over is fixed below; you plan the scenes that animate on screen while it
plays. Return one JSON object:
{
 "title": the video's title (max 6 words), "app_name": the product's name (max 4 words) or "",
 "scenes": [ in order; each scene has [SAY] and one of these layouts:
  {"type": "title", "kicker": max 3 words, "title": max 7 words, "subtitle": max 12 words}
  {"type": "statement", "text": the scene's key message (max 12 words), "highlight": 1-3 words of text to emphasise,
     "icon": ICON}
  {"type": "points", "title": max 7 words, "items": [2-4 {"text": max 6 words, "icon": ICON, "cue": CUE}]}
  {"type": "stats", "title": max 7 words, "stats": [1-3 {"value": a figure as digits with its unit, e.g. "40%",
     "3x", "2 days", "$1.2M" (max 8 chars), "label": max 6 words, "cue": CUE}]}
  {"type": "steps", "title": max 7 words, "steps": [3-5 {"name": max 3 words, "text": max 7 words, "icon": ICON,
     "cue": CUE}]}
  {"type": "compare", "title": max 7 words, "before_label": max 3 words, "after_label": max 3 words,
     "rows": [2-3 {"before": max 6 words, "after": max 6 words, "cue": CUE}]}
  {"type": "chart", "title": max 7 words, "unit": "" or a short unit like "%", "hrs", "bars": [2-6 {"label": max 3
     words, "value": a plain number}], "takeaway": max 12 words}
  {"type": "icons", "title": max 7 words, "items": [3-6 {"label": max 3 words, "icon": ICON, "cue": CUE}]}
  {"type": "quote", "text": max 20 words, "attribution": max 5 words}
  {"type": "closing", "title": max 7 words, "subtitle": max 12 words, "cta": a call to action the voice-over itself makes
     (max 5 words), else ""}
 ]
}

How to make it a strong explainer:
- The first scene is "title", the last "closing". In between, follow the voice-over: hook -> problem -> how it works
  -> what you get. Pick the layout that shows what is being said: a sequence is steps, a set of capabilities icons
  or points, a contrast with the old way compare, stated numbers stats (or chart for 3+ comparable numbers), one
  strong idea a statement. Never the same layout twice in a row; use at least 5 different layouts.
- A scene lasts while its part of the voice-over is spoken: about 15-40 words of it (6-15 seconds); never more than
  [MAXWORDS] words, and never just one short sentence - short sentences ("This is X.", "Here is how it works.") share
  a scene with what follows. Plan [SCENES] scenes in all. "title" only for the first scene.
- On screen, few words: short phrases, not sentences; no periods at the end. Call each thing by the same name.
- CUE: 1-4 words copied exactly from this scene's voice-over, where that item is said - the item appears then. Items
  appear in the order they are said, so list them in that order.
- Facts: use ONLY what the voice-over states. Never invent numbers, customers, prices or results, and never calculate
  new figures. stats and chart only with numbers the voice-over says; otherwise use other layouts.
- Plain, confident language for business viewers; no exclamation marks, no buzzwords.
- ICON: one of [ICONS] - the one that fits best; never empty.
- Return only the JSON object."""

SAY_AS_WRITTEN = """"from": the number of the sentence (in "sentences") where the scene starts - the scene runs until
the next scene's "from". The first scene has "from": 1; each next "from" is larger"""
SAY_TIGHTEN = """"say": the scene's voice-over - rewrite the narration (in "sentences") into a tight voice-over of
about [WORDS] words in all, natural to listen to, keeping its key points, names and figures exactly"""


def sentences(narration: str) -> list[str]:
    """The narration's spoken sentences, in order (stage directions, speaker labels and filler removed)."""
    out = []
    for part in source.clean(narration):
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+", part) if s.strip()]
    return out


def _text(v, limit: int = 0) -> str:
    t = re.sub(r"\s+", " ", str(v or "")).strip().rstrip(".")
    return " ".join(t.split()[:limit]) if limit else t


def _cue(v, say: str) -> str:
    """The cue when it really is in the scene's voice-over, else '' (the item is then spread over the scene)."""
    cue = _text(v, 6)
    want = [norm(w) for w in tokens(spoken(cue)) if norm(w)]
    have = [norm(w) for w in tokens(spoken(say))]
    if want and any(have[i:i + len(want)] == want for i in range(len(have) - len(want) + 1)):
        return cue
    return ""


def _said(cta: str, narration: str) -> str:
    """A call to action only when the narration says it: all its words besides verbs like 'try' or 'book' are in it
    ('Try Zen Studio Today' goes when nobody said 'today')."""
    terms = {t for t in _key_terms(cta) if t not in {v[:5] for v in CTA_VERBS}}
    return cta if terms and terms <= _key_terms(narration) else ""


def _number(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def plan_scenes(narration: str, title: str = "", mode: str = "as_written", target_seconds: int = 120,
                log=print) -> tuple[dict, dict]:
    said = sentences(narration)
    if len(" ".join(said).split()) < 20:
        raise StoryError("the narration is too short - give at least a few sentences to explain")
    mode = mode if mode in MODES else "as_written"
    # tighten: the words that fit once the pauses between scenes, the opening and the ending are taken out
    words = (len(" ".join(said).split()) if mode == "as_written" else
             max(60, round((target_seconds - 4 - 0.55 * target_seconds / 8) * 2.1)))
    n_scenes = max(3, min(18, round(words / 30)))
    say = SAY_AS_WRITTEN if mode == "as_written" else SAY_TIGHTEN.replace("[WORDS]", str(words))
    prompt = (PROMPT.replace("[SAY]", say).replace("[ICONS]", ", ".join(ICONS)).replace("[MAXWORDS]", "45")
              .replace("[SCENES]", f"{max(3, n_scenes - 2)}-{n_scenes + 2}"))
    payload = {"product_name": title or None, "sentences": [{"n": i + 1, "text": s} for i, s in enumerate(said)]}
    raw, usage = chat_json(prompt, payload, "Planning the scenes", log, temperature=0.4)
    log(f"Scenes planned: {usage['input_tokens']:,} input + {usage['output_tokens']:,} output tokens "
        f"(about ${usage['cost_usd']:.4f})")
    plan = check(raw, said, title, mode)
    if mode == "tighten":
        fit_scenes(plan, target_seconds, log)
    return plan, usage


def _voice_over(raw_scenes: list, said: list[str], mode: str, numbers: set, vocab: set) -> list[tuple[dict, str]]:
    """(scene, its voice-over) pairs. as_written: the sentences from each scene's 'from' to the next one's - all of
    them, in order, so the narration is spoken exactly as written whatever the model returned."""
    scenes = [s for s in raw_scenes if isinstance(s, dict) and s.get("type") in SCENE_TYPES]
    if mode == "tighten":
        out = []
        for s in scenes:
            text = _scrub(re.sub(r"\s+", " ", str(s.get("say") or "")).strip(), numbers, vocab)
            if text:
                out.append((s, text))
        return out
    starts, last = [], 0
    for s in scenes:
        n = s.get("from")
        n = int(n) if isinstance(n, (int, float)) or str(n).isdigit() else 0
        if last < n <= len(said):
            starts.append((n, s))
            last = n
    if not starts:
        raise StoryError("the scene plan came back without usable scenes - try again")
    starts[0] = (1, starts[0][1])
    bounds = [n for n, _ in starts] + [len(said) + 1]
    return [(s, " ".join(said[bounds[i] - 1:bounds[i + 1] - 1])) for i, (_, s) in enumerate(starts)]


def check(raw: dict, said: list[str], title: str = "", mode: str = "as_written") -> dict:
    """The plan made safe to animate: known layouts, counts clamped, only stated figures and known names, valid icons
    and cues; a title scene first and a closing scene last."""
    narration = " ".join(said)
    numbers = _numbers_in(narration)
    app_name = title or _text(raw.get("app_name"), 4)
    vocab = _vocab(narration, title, app_name)
    pairs = _merge_short(_voice_over(raw.get("scenes") or [], said, mode, numbers, vocab))
    icon = lambda v, text="": v if v in ICONS else guess_icon(text)   # noqa: E731
    fact = lambda v, n=0: _scrub(_text(v, n), numbers, vocab, title_case=True)   # noqa: E731
    scenes = []
    for s, say in pairs:
        t = s["type"]
        out = {"type": t, "say": say}
        if t == "title":
            out.update(kicker=fact(s.get("kicker"), 3), title=fact(s.get("title"), 8) or app_name or title,
                       subtitle=fact(s.get("subtitle"), 14))
        elif t == "statement":
            out.update(text=fact(s.get("text"), 14))
            out["icon"] = icon(s.get("icon"), out["text"])
            hl = _text(s.get("highlight"), 3)
            out["highlight"] = hl if hl and hl.lower() in out["text"].lower() else ""
        elif t == "points":
            out.update(title=fact(s.get("title"), 8), items=[
                {"text": x, "icon": icon(i.get("icon"), x), "cue": _cue(i.get("cue"), say)}
                for i in s.get("items") or [] if isinstance(i, dict) and (x := fact(i.get("text"), 8))][:4])
            if len(out["items"]) < 2:
                out = None
        elif t == "stats":
            out.update(title=fact(s.get("title"), 8), stats=[
                {"value": v, "label": fact(i.get("label"), 7), "cue": _cue(i.get("cue"), say)}
                for i in s.get("stats") or [] if isinstance(i, dict) and (v := _text(i.get("value"))[:9])
                and re.search(r"\d", v) and _stated(v, numbers)][:3])
            if not out["stats"]:
                out = None
        elif t == "steps":
            out.update(title=fact(s.get("title"), 8), steps=[
                {"name": n, "text": fact(i.get("text"), 8), "icon": icon(i.get("icon"), f"{n} {i.get('text')}"), "cue": _cue(i.get("cue"), say)}
                for i in s.get("steps") or [] if isinstance(i, dict) and (n := fact(i.get("name"), 4))][:5])
            if len(out["steps"]) < 3:
                out = None
        elif t == "compare":
            out.update(title=fact(s.get("title"), 8), before_label=fact(s.get("before_label"), 3) or "Before",
                       after_label=fact(s.get("after_label"), 3) or (f"With {app_name}" if app_name else "After"),
                       rows=[{"before": b, "after": a, "cue": _cue(i.get("cue"), say)}
                             for i in s.get("rows") or [] if isinstance(i, dict)
                             and (b := fact(i.get("before"), 8)) and (a := fact(i.get("after"), 8))][:3])
            if len(out["rows"]) < 2:
                out = None
        elif t == "chart":
            bars = [(_text(i.get("label"), 3), _number(i.get("value"))) for i in s.get("bars") or [] if isinstance(i, dict)]
            bars = [(lb, v) for lb, v in bars if lb and v is not None and v >= 0][:6]
            if len(bars) < 2 or not all(any(abs(v - n) < 1e-6 * max(1, abs(n)) for n in numbers) for _, v in bars):
                out = None      # numbers nobody said: no chart rather than a made-up one
            else:
                out.update(title=fact(s.get("title"), 8), unit=_text(s.get("unit"))[:5],
                           bars=[{"label": lb, "value": v} for lb, v in bars], takeaway=fact(s.get("takeaway"), 14))
        elif t == "icons":
            out.update(title=fact(s.get("title"), 8), items=[
                {"label": lb, "icon": icon(i.get("icon"), lb), "cue": _cue(i.get("cue"), say)}
                for i in s.get("items") or [] if isinstance(i, dict) and (lb := fact(i.get("label"), 4))][:6])
            if len(out["items"]) < 3:
                out = None
        elif t == "quote":
            out.update(text=fact(s.get("text"), 22).strip('"“” '), attribution=fact(s.get("attribution"), 6))
            if not out["text"]:
                out = None
        elif t == "closing":
            out.update(title=fact(s.get("title"), 8), subtitle=fact(s.get("subtitle"), 14),
                       cta=_said(fact(s.get("cta"), 6), narration))
        if out is None or (t in ("statement",) and not out["text"]):
            # its layout failed a check: the words are still spoken, over a plain statement of the scene
            out = {"type": "statement", "say": say, "text": _headline(say), "highlight": "", "icon": icon(s.get("icon"), say)}
        scenes.append(out)
    if not scenes:
        raise StoryError("the scene plan came back without usable scenes - try again")
    if scenes[0]["type"] != "title":
        scenes[0] = {"type": "title", "say": scenes[0]["say"], "kicker": "", "title": app_name or _text(raw.get("title"), 6)
                     or _headline(scenes[0]["say"]), "subtitle": scenes[0].get("text") or scenes[0].get("title") or ""}
    if len(scenes) > 1 and scenes[-1]["type"] != "closing":
        scenes.append({"type": "closing", "say": "", "title": app_name or _text(raw.get("title"), 6), "subtitle": "",
                       "cta": ""})
    for s in scenes:
        if s["type"] == "closing":
            s["title"] = s["title"] or app_name or _text(raw.get("title"), 6)
    return {"title": _text(raw.get("title"), 7) or app_name or "Explainer", "app_name": app_name, "mode": mode,
            "scenes": scenes}


MIN_WORDS = 10           # a scene with fewer words would flash by (under ~4 s): it joins its neighbour
MAX_MERGED = 50


def _merge_short(pairs: list[tuple[dict, str]]) -> list[tuple[dict, str]]:
    """Scenes too short to read are said over the next scene (whose layout is kept); a scene with the same layout as
    the one before joins it when the two are short enough together. The first scene (the title) keeps its layout."""
    out: list[list] = []
    carry = ""
    for k, (s, say) in enumerate(pairs):
        say = f"{carry} {say}".strip()
        carry = ""
        if out and len(say.split()) < MIN_WORDS and k < len(pairs) - 1:
            carry = say
            continue
        if out and s["type"] == out[-1][0]["type"] and len(f"{out[-1][1]} {say}".split()) <= MAX_MERGED:
            out[-1][1] = f"{out[-1][1]} {say}"
            continue
        out.append([s, say])
    if carry and out:
        out[-1][1] = f"{out[-1][1]} {carry}"
    return [(s, say) for s, say in out]


ICON_WORDS = {   # words in an item's text -> the icon that shows it, when the model gave none
    "edit": "write script draft edit narration", "robot": "ai automat bot openai", "clock": "time hour minute slow wait",
    "document": "file caption document transcript", "chart": "report analytics chart metric", "speed": "fast quick speed",
    "people": "team user customer people sales", "lock": "secure security private", "sync": "update change sync again",
    "check": "verify check confirm review", "search": "find search", "cloud": "cloud online", "globe": "web app browser",
    "chat": "voice talk chat conversation", "lightning": "instant automatic effect zoom", "shield": "safe protect",
    "calendar": "day week month schedule", "education": "training learn onboarding", "layers": "deck slide layer",
    "warning": "risk problem error outdated", "pulse": "record video screen",
}


def guess_icon(text: str) -> str:
    t = (text or "").lower()
    for name, keys in ICON_WORDS.items():
        if any(k in t for k in keys.split()):
            return name
    return "star"


def _headline(say: str) -> str:
    """A short on-screen line for a scene whose layout was dropped: its first sentence, cut to 10 words."""
    first = re.split(r"(?<=[.!?])\s+", say.strip())[0].rstrip(".!?")
    return " ".join(first.split()[:10]) + ("..." if len(first.split()) > 10 else "")


# ── keeping a tightened voice-over to its length, before anything is voiced ─────────────────────────────────

WORDS_PER_SECOND = 2.1     # Kokoro at speed 1.0, measured
PAUSES = 0.9 + 2.6         # before the first word and after the last (explainer.voice LEAD_IN and OUTRO)
BETWEEN = 0.55             # between two scenes (explainer.voice GAP)


def estimate_seconds(plan: dict) -> float:
    words = sum(len(sc["say"].split()) for sc in plan["scenes"])
    return PAUSES + BETWEEN * max(0, len(plan["scenes"]) - 1) + words / WORDS_PER_SECOND


def fit_scenes(plan: dict, target_seconds: int, log=print) -> None:
    """A voice-over the model wrote longer than asked is cut here, in code, so the video keeps its length: each scene
    keeps its first whole sentences within its share of the words (at least one), then whole scenes from the middle
    are dropped - statements first - until it fits. The title and the closing always stay; cues not said any more are
    cleared (those items are spread over the scene instead)."""
    if estimate_seconds(plan) <= target_seconds * 1.05:
        return
    before = sum(len(sc["say"].split()) for sc in plan["scenes"])
    scenes = plan["scenes"]
    speech = target_seconds - PAUSES - BETWEEN * (len(scenes) - 1)
    cap = max(12, round(speech * WORDS_PER_SECOND / max(1, len(scenes)) * 1.25))
    for sc in scenes:
        kept: list[str] = []
        for sent in re.split(r"(?<=[.!?])\s+", sc["say"].strip()):
            if kept and len(" ".join(kept + [sent]).split()) > cap:
                break
            kept.append(sent)
        sc["say"] = " ".join(kept)
    while estimate_seconds(plan) > target_seconds * 1.05 and len(scenes) > 3:
        middle = [k for k in range(1, len(scenes) - 1) if scenes[k]["type"] not in ("title", "closing")]
        if not middle:
            break
        plain = [k for k in middle if scenes[k]["type"] == "statement"]
        del scenes[(plain or middle)[len(plain or middle) // 2]]
    for sc in scenes:
        for key in ("items", "stats", "steps", "rows", "bars"):
            for it in sc.get(key) or []:
                if it.get("cue"):
                    it["cue"] = _cue(it["cue"], sc["say"])
    log(f"Voice-over cut from {before} to {sum(len(sc['say'].split()) for sc in scenes)} words, {len(scenes)} scenes, "
        f"about {estimate_seconds(plan):.0f}s, to fit {target_seconds}s")
