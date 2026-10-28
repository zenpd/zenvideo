"""
Polishing a checked story (after ppt.writer.normalize) - all in code, so free, except a rare follow-up call:

  word limits   text over its slide's limit is cut back to whole sentences; what is still too long (one long sentence)
                is shortened in ONE small Azure call for just those fields - only when a story is freshly written.
  repetition    a point that says the same as an earlier one (on any slide) is dropped from its list.
  next steps    closing next steps must come from the material (a demo nobody mentioned is not a next step).
  speaker notes each slide gets a talk track: the part of the narration it is about (matched by shared words).

    polish(content, parts, log, repair=True) -> (content, usage of the follow-up call or None)
"""

import math
import re

from ppt.writer import StoryError, _numbers_in, _scrub, _vocab, chat_json

# Word limits per slide type and field (the prompt asks for these; 15% grace before anything is done).
LIMITS = {
    "statement": {"text": 14, "support": 25},
    "stats": {"title": 10, "label": 8},
    "problem": {"title": 10, "intro": 25, "points.title": 5, "points.body": 20},
    "before_after": {"title": 10, "rows.before": 10, "rows.after": 10},
    "process": {"title": 10, "intro": 20, "steps.name": 3, "steps.body": 12},
    "feature_grid": {"title": 10, "items.title": 5, "items.body": 18},
    "feature_focus": {"title": 10, "body": 35, "points": 12, "callout": 14},
    "quote": {"text": 22},
    "benefits": {"title": 10, "items.title": 4, "items.body": 18},
    "chart": {"title": 10, "takeaway": 18},
    "closing": {"title": 7, "subtitle": 14, "next_steps": 8},
}
MIN_ITEMS = {"problem": 2, "feature_grid": 3, "benefits": 2, "before_after": 2, "process": 3, "feature_focus": 0}
STOP = set("""a an and are as at be been but by can do does each for from has have how in into is it its it's of on
or our so than that the their them then there these they this to up us was we were what when where which while who
will with without you your one all every more most new just only also very via""".split())
CTA_VERBS = set("""schedule book start begin request contact launch plan set run try join explore discuss review arrange
kick kickoff organise organize set up get talk reach sign agree confirm""".split())

REPAIR_PROMPT = """Shorten each text to at most its max_words words. Keep its meaning and every fact; add nothing new;
no exclamation marks; keep any product names exactly. Return {"texts": {"<id>": "<shortened text>", ...}} only."""


def _words(text: str) -> list[str]:
    return text.split()


def _key_terms(text: str) -> set[str]:
    """Content words, roughly stemmed (first 5 letters), for comparing texts."""
    return {w[:5] for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP}


def _fields(sl: dict):
    """(path, text) for every limited text field of a slide; path like 'points.1.body' or 'callout'."""
    for spec in LIMITS.get(sl["type"], {}):
        if "." in spec:
            group, field = spec.split(".")
            for i, item in enumerate(sl.get(group) or []):
                if isinstance(item, dict) and item.get(field):
                    yield f"{group}.{i}.{field}", item[field], LIMITS[sl["type"]][spec]
        elif isinstance(sl.get(spec), list):
            for i, item in enumerate(sl[spec]):
                if isinstance(item, str) and item:
                    yield f"{spec}.{i}", item, LIMITS[sl["type"]][spec]
        elif sl.get(spec):
            yield spec, sl[spec], LIMITS[sl["type"]][spec]


def _set(sl: dict, path: str, value: str) -> None:
    keys = path.split(".")
    target = sl
    for k in keys[:-1]:
        target = target[int(k)] if k.isdigit() else target[k]
    last = keys[-1]
    if last.isdigit():
        target[int(last)] = value
    else:
        target[last] = value


def _cut_to_sentences(text: str, limit: int) -> str:
    """The longest run of whole leading sentences within the limit (the text itself if the first is already over)."""
    out = []
    for sentence in re.split(r"(?<=[.!?;])\s+", text):
        if len(_words(" ".join(out + [sentence]))) > limit:
            break
        out.append(sentence)
    return " ".join(out) if out else text


def enforce_limits(content: dict, material: str, repair: bool, log=print) -> dict | None:
    """Cut over-long text to whole sentences; shorten what is still too long in one small call (if repair)."""
    pending = {}
    for si, sl in enumerate(content["slides"]):
        for path, text, limit in list(_fields(sl)):
            if len(_words(text)) <= math.ceil(limit * 1.15):
                continue
            cut = _cut_to_sentences(text, limit)
            _set(sl, path, cut)
            if len(_words(cut)) > math.ceil(limit * 1.15):
                pending[f"{si}:{path}"] = {"text": cut, "max_words": limit}
    if not pending:
        return None
    if not repair:
        log(f"{len(pending)} text(s) longer than their slide's limit; the layout shrinks them to fit")
        return None
    try:
        out, usage = chat_json(REPAIR_PROMPT, {"texts": pending}, f"Shortening {len(pending)} over-long text(s)", log)
    except StoryError as e:
        log(f"Could not shorten over-long texts ({e}); the layout shrinks them to fit")
        return None
    numbers, vocab = _numbers_in(material), _vocab(material, content["app_name"])
    fixed = 0
    for key, short in (out.get("texts") or {}).items():
        if key not in pending or not isinstance(short, str):
            continue
        short = _scrub(re.sub(r"\s+", " ", short).strip(), numbers, vocab)
        if short and len(_words(short)) <= math.ceil(pending[key]["max_words"] * 1.15):
            si, path = key.split(":", 1)
            _set(content["slides"][int(si)], path, short)
            fixed += 1
    log(f"Shortened {fixed} of {len(pending)} text(s): {usage['input_tokens']:,} + {usage['output_tokens']:,} tokens "
        f"(about ${usage['cost_usd']:.4f})")
    return usage


def drop_repeats(content: dict, log=print) -> None:
    """Remove list entries (points, items, rows, steps) that repeat an earlier entry anywhere in the deck, or whose
    text was emptied by a fact check."""
    seen: list[set[str]] = []
    removed = 0
    for sl in content["slides"]:
        for group in ("points", "items", "rows", "steps"):
            entries = sl.get(group)
            if not isinstance(entries, list):
                continue
            room = len(entries) - MIN_ITEMS.get(sl["type"], 2)   # how many the slide can lose and still work
            keep = []
            for e in entries:
                if room > 0 and isinstance(e, dict) and "body" in e and not e["body"]:   # its sentence failed a check
                    room -= 1
                    removed += 1
                    continue
                text = " ".join(str(v) for k, v in e.items() if k not in ("icon", "metric")) if isinstance(e, dict) else str(e)
                terms = _key_terms(text)
                if room > 0 and len(terms) >= 3 and any(len(terms & s) / len(terms | s) >= 0.6 for s in seen):
                    room -= 1
                    removed += 1
                    continue
                keep.append(e)
                seen.append(terms)
            sl[group] = keep
    if removed:
        log(f"Removed {removed} repeated or empty point(s)")


def check_next_steps(content: dict, material: str, log=print) -> None:
    """Keep only next steps the material supports: besides verbs like 'schedule' or 'start', at least two thirds of
    a step's words must appear in the material (so 'Start your 30-day pilot' stays when a pilot was discussed, and
    'Schedule a demo' goes when nobody mentioned a demo)."""
    have = _key_terms(material)
    closing = next(s for s in content["slides"] if s["type"] == "closing")
    kept = []
    for step in closing.get("next_steps") or []:
        terms = {t for t in _key_terms(re.sub(r"\d+[-\w]*", "", step)) if t not in {v[:5] for v in CTA_VERBS}}
        if terms and len(terms & have) / len(terms) >= 2 / 3:
            kept.append(step)
    if len(kept) < len(closing.get("next_steps") or []):
        log(f"Removed {len(closing['next_steps']) - len(kept)} next step(s) the text doesn't mention")
    closing["next_steps"] = kept


def _slide_text(sl: dict) -> str:
    parts = []

    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k not in ("type", "icon", "screen"):
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            parts.append(v)
    walk(sl)
    return " ".join(parts)


def add_notes(content: dict, parts: list[str]) -> None:
    """Speaker notes: each content slide gets the 2-4 sentences of the narration that talk about it most (shared
    words; sentences not used yet preferred), in their original order - a talk track in the narrator's own words.
    Small talk ('thanks for joining') shares no words with any slide, so it never makes it in. The cover and closing
    get the pitch and the next steps."""
    sentences = [x.strip() for p in parts for x in re.split(r"(?<=[.!?])\s+", p) if len(x.split()) >= 4]
    vectors = [_key_terms(x) for x in sentences]
    used: set[int] = set()
    for sl in content["slides"]:
        if sl["type"] == "closing":
            steps = "\n".join(f"- {s}" for s in sl.get("next_steps") or [])
            sl["notes"] = "\n".join(x for x in (sl.get("subtitle"), steps) if x)
            continue
        terms = _key_terms(_slide_text(sl))
        scored = sorted(((len(terms & v) / math.sqrt(len(v) or 1) * (0.5 if i in used else 1.0), i)
                         for i, v in enumerate(vectors)), reverse=True)
        pick, words = [], 0
        for score, i in scored[:4]:
            if score < 0.6 or words + len(sentences[i].split()) > 90:
                continue
            pick.append(i)
            words += len(sentences[i].split())
        used.update(pick)
        sl["notes"] = " ".join(sentences[i] for i in sorted(pick))
    content["cover_notes"] = "\n".join(x for x in (content.get("pitch"), content.get("core_message")) if x)


def polish(content: dict, parts: list[str], log=print, repair: bool = True, notes_from: list[str] | None = None
           ) -> tuple[dict, dict | None]:
    """parts: all the material; notes_from: what the speaker notes quote (default: parts) - the narration, not the
    text of the app's screens."""
    material = "\n".join(parts)
    usage = enforce_limits(content, material, repair, log)
    drop_repeats(content, log)
    check_next_steps(content, material, log)
    add_notes(content, parts if notes_from is None else notes_from)
    return content, usage
