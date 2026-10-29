"""
Two-person scripts - one Azure OpenAI call, in one of two formats:
  conversation  two colleagues talk in an office: person A asks, person B explains (explainer/web/office.js)
  presenters    two co-presenters stand in a branded studio and present to camera, taking turns (explainer/web/stage.js)
The narration becomes their script in one call, then checked in code like the explainer's scenes: every line's figures and names only from the narration (and
the two people's own names), the wall screen's points tied to words of the line that says them, gestures and moods
from a fixed set.

Person A asks (a colleague, manager or customer, curious about the topic); person B explains (the one who knows the
product). Their looks and voices are presets (CAST) the user picks from; their roles are the model's, fitted to the
topic.

    plan_dialogue(narration, title, cast, target_seconds, log) -> (plan, token usage)
"""

import re

from explainer.planner import WPM, _cue, _said, _text, sentences
from ppt.writer import StoryError, _numbers_in, _scrub, _stated, _vocab, chat_json

# id -> look (drawn by explainer/web/office.js) and default voice
CAST = {
    "maya":   {"name": "Maya", "voice": "af_sarah", "skin": "#8d5a3b", "hair": "#1f1410", "hair_style": "curly",
               "top": "#0f766e", "top2": "#115e59", "glasses": False, "beard": False, "lips": "#6b3a2a",
               "eyes": "#4a2c1d", "lashes": True},
    "sam":    {"name": "Sam", "voice": "am_michael", "skin": "#f1c7a5", "hair": "#5b3a22", "hair_style": "short",
               "top": "#1e3a8a", "top2": "#1e40af", "glasses": True, "beard": False, "lips": "#b06f5a", "eyes": "#3f6e9a"},
    "priya":  {"name": "Priya", "voice": "bf_emma", "skin": "#b57a52", "hair": "#120c0a", "hair_style": "long",
               "top": "#b45309", "top2": "#92400e", "glasses": False, "beard": False, "lips": "#7a3f2d",
               "eyes": "#3b2416", "lashes": True},
    "daniel": {"name": "Daniel", "voice": "bm_george", "skin": "#5c3a26", "hair": "#0d0806", "hair_style": "buzz",
               "top": "#e5e7eb", "top2": "#475569", "glasses": False, "beard": True, "lips": "#4a2a1e", "eyes": "#3b2416"},
    "elena":  {"name": "Elena", "voice": "af_nicole", "skin": "#f5d0b5", "hair": "#d9a441", "hair_style": "bob",
               "top": "#e11d48", "top2": "#be123c", "glasses": False, "beard": False, "lips": "#c06a5a",
               "eyes": "#4f7f5a", "lashes": True},
    "kenji":  {"name": "Kenji", "voice": "am_adam", "skin": "#e8b98f", "hair": "#141018", "hair_style": "side",
               "top": "#166534", "top2": "#14532d", "glasses": True, "beard": False, "lips": "#a3604c", "eyes": "#3b2416"},
}
DEFAULT_CAST = ("maya", "sam")
# the presenters' studio people (explainer/web/stage.js): full-body, in business dress; British voices by default
STUDIO_CAST = {
    "sophie": {"name": "Sophie", "voice": "bf_emma", "body": "f", "skin": "#f1c6a6", "hair": "#5a3825",
               "hair_style": "shoulder", "eyes": "#3f6e9a", "brows": "#4a2e1f", "lips": "#c8616c", "suit": "#0b2545",
               "shirt": "#ffffff", "skirt": "#1c2b45", "legs": "#d6a283", "shoes": "#1d1d22", "necklace": "#d4af37"},
    "james": {"name": "James", "voice": "bm_george", "body": "m", "skin": "#e0ac85", "hair": "#2a1c14",
              "hair_style": "crop", "eyes": "#5a3b26", "lips": "#b0705e", "suit": "#2e3440", "shirt": "#f4f6f9",
              "tie": "#00a896", "trousers": "#2a2f3a", "shoes": "#3a2416", "pocket": "#00b8a3", "stubble": True},
    "olivia": {"name": "Olivia", "voice": "bf_isabella", "body": "f", "skin": "#8a5a3c", "hair": "#16100c",
               "hair_style": "bun", "eyes": "#3b2416", "brows": "#1a120d", "lips": "#8e4a45", "suit": "#5b1f3a",
               "shirt": "#fdf6ec", "skirt": "#2b1b26", "legs": "#7a4e33", "shoes": "#1d1d22", "necklace": "#e5e7eb"},
    "arjun": {"name": "Arjun", "voice": "bm_lewis", "body": "m", "skin": "#b07a52", "hair": "#120d0b",
              "hair_style": "crop", "eyes": "#3b2416", "lips": "#8a5444", "suit": "#1f3b57", "shirt": "#f4f6f9",
              "tie": "#7c2d12", "trousers": "#1c2f45", "shoes": "#1b1b1b", "pocket": "#f4f6f9", "stubble": True},
}
DEFAULT_STUDIO = ("sophie", "james")
FORMATS = ("conversation", "presenters")
GESTURES = ("explain", "point", "open", "count", "think", "wave", "none")
MOODS = ("neutral", "happy", "curious", "concerned", "excited")

PROMPT = """You are a scriptwriter for short animated explainer videos in which two colleagues talk in an office. Turn
the narration (in "sentences") into a natural, engaging conversation between them:
 A (named in "cast"): curious - asks the questions a viewer would ask, reacts, sums up; never the expert.
 B (named in "cast"): knows the topic - explains it clearly, with the narration's facts.
Return one JSON object:
{
 "title": the video's title (max 6 words), "app_name": the product's name (max 4 words) or "",
 "roles": {"A": A's role fitting the topic (max 3 words, e.g. "Sales lead"), "B": B's role (max 3 words)},
 "closing": the product's one-line description for the end card, from the narration (max 8 words) - not a thank-you,
 "lines": [in order, [LINES] lines, alternating mostly but not strictly:
   {"speaker": "A" or "B", "say": what they say (1-3 sentences, max 40 words, spoken English),
    "gesture": one of explain, point (at the wall screen), open (open hands, a question or welcome), count (listing
      things), think, wave (only the first greeting), none,
    "mood": one of neutral, happy, curious, concerned, excited,
    "screen": optional - what the wall screen shows from this line on: {"title": max 5 words, "points": [0-3 {"text":
      max 5 words, "cue": 1-4 words copied exactly from this line's "say", where that point is said}], "value": a figure
      from this line as digits with its unit (max 8 chars) or ""} - give it when B explains something worth showing
      (the problem, the steps, the features, a number); about every second or third line of B}
 ]
}

How to write it:
- HARD LIMIT: at most [MAXLINES] lines, each at most [PERLINE] words (A's questions shorter) - the video has a
  fixed length. Cover the narration's key points briefly rather than all of its detail. Open with a short greeting and A raising the topic; end with A summing up
  in one line and B with the closing thought or call to action from the narration.
- Keep the narration's key points, names and figures, in its order; B says the facts, A's questions lead to
  them. Short, natural sentences people really say; contractions are fine. A's lines are short (often 5-15 words).
- Facts: use ONLY what the narration states. Never invent numbers, customers, prices, results, other people's names
  or company names. They call each other only by their names in "cast".
- No stage directions, no sound effects, no emojis, no exclamation-mark spam (one or two in the whole talk is fine).
- Return only the JSON object."""


PRESENTERS = """You write the script of a short, polished corporate video in which two presenters (named in "cast")
stand side by side in a studio and present to the camera, a wall display between them. Turn the narration (in
"sentences") into their script. They are co-presenters: both speak to the audience, taking turns section by section,
with a brief natural handover by name now and then (at most twice in the whole video).
Return one JSON object:
{
 "title": the video's title (max 6 words), "app_name": the product's name (max 4 words) or "",
 "roles": {"A": A's role fitting the topic (max 3 words, e.g. "Engineering lead"), "B": B's role (max 3 words)},
 "closing": the product's one-line description for the end card, from the narration (max 8 words, e.g. "The
   bank's AI engineering platform") - not a thank-you,
 "lines": [in order, [LINES] lines, taking turns:
   {"speaker": "A" or "B", "say": what they say (1-3 sentences, max 35 words, spoken British English),
    "gesture": one of explain, count (going through a list), open (welcome, or summing up), point (at the display - only
      on a line that changes it), wave (only the very first line), none,
    "mood": one of neutral, happy, excited,
    "screen": optional - what the wall display shows from this line on: {"title": max 4 words, "points": [0-6 {"text":
      max 3 words, "cue": 1-4 words copied exactly from this line's "say", where that point is said - or ""}],
      "value": ""} - one for each section with a list or a key idea}
 ]
}

How to write it:
- HARD LIMIT: at most [MAXLINES] lines, each at most [PERLINE] words - the video must stay under [SECONDS] seconds. Cover the narration's
  sections in order, briefly: say the essentials and let the display carry the lists (the names of modes, products or
  benefits) instead of reading every item aloud.
- Open: A greets the viewers and says what the video is about; B gives the one-line definition. End: a one-line
  summary and a thank-you for watching.
- Facts: use ONLY what the narration states; keep names exactly as written (products, systems, tools). Never invent
  numbers, features, customers or claims. They call each other only by their names in "cast".
- Plain, confident, professional language; no exclamation marks, no filler, no stage directions.
- Return only the JSON object."""


def plan_dialogue(narration: str, title: str = "", cast: tuple[str, str] = DEFAULT_CAST, target_seconds: int = 120,
                  log=print, fmt: str = "conversation") -> tuple[dict, dict]:
    said = sentences(narration)
    if len(" ".join(said).split()) < 20:
        raise StoryError("the narration is too short - give at least a few sentences to talk about")
    presets = STUDIO_CAST if fmt == "presenters" else CAST
    default = DEFAULT_STUDIO if fmt == "presenters" else DEFAULT_CAST
    people = [presets.get(c) or presets[default[i]] for i, c in enumerate(cast)]
    words, n_lines = budget(target_seconds, fmt)
    prompt = (PRESENTERS if fmt == "presenters" else PROMPT).replace("[WORDS]", str(words)).replace(
        "[LINES]", f"{n_lines - 2}-{n_lines}").replace("[MAXLINES]", str(n_lines)).replace("[SECONDS]", str(target_seconds)).replace(
        "[PERLINE]", str(per_line(words, n_lines)))
    payload = {"product_name": title or None, "cast": {"A": people[0]["name"], "B": people[1]["name"]},
               "sentences": [{"n": i + 1, "text": s} for i, s in enumerate(said)]}
    raw, usage = chat_json(prompt, payload, "Writing the conversation", log, temperature=0.6)
    log(f"Conversation written: {usage['input_tokens']:,} input + {usage['output_tokens']:,} output tokens "
        f"(about ${usage['cost_usd']:.4f})")
    plan = check(raw, said, title, cast, fmt)
    plan, more = fit_length(plan, narration, title, cast, target_seconds, log, fmt)
    if more:
        usage = {**usage, **{k: round(usage[k] + more[k], 6) for k in ("input_tokens", "output_tokens", "cost_usd")}}
    return plan, usage


WORDS_PER_SECOND = 2.1      # Kokoro's British and American voices at speed 1.0, measured
LEAD_AND_CLOSE = 6.0        # the opening shot and the end card
TURN = 0.35                 # the pause between two lines


def budget(target_seconds: int, fmt: str = "conversation") -> tuple[int, int]:
    """How many words and lines fit in the video's length, after the opening, the end card and the pauses."""
    n_lines = max(5, min(30, round(target_seconds / (8.5 if fmt == "presenters" else 7.0))))
    speech = target_seconds - LEAD_AND_CLOSE - TURN * n_lines
    return max(50, int(speech * WORDS_PER_SECOND)), n_lines


def per_line(words: int, n_lines: int) -> int:
    return max(10, round(words / n_lines * 1.15))


def estimate_seconds(plan: dict) -> float:
    """The video's length from the script's words alone, before anything is voiced."""
    words = sum(len(ln["say"].split()) for ln in plan["lines"])
    return LEAD_AND_CLOSE + TURN * len(plan["lines"]) + words / WORDS_PER_SECOND


SHORTEN = """You shorten the script of a short video in which two people talk (given as JSON, the same shape you must
return). It is too long: [N] lines, [HAVE] words. It must have at most [MAXLINES] lines, each at most [PERLINE] words
- a hard limit. Merge or drop lines, cut repetition and small talk, shorten sentences; keep the
opening greeting, the most important facts with their names exactly as written, the order, and a one-line close. Keep
each line's speaker, and "gesture", "mood" and "screen" for the lines you keep ("screen" cues must be words of the
line's new "say"). Never add facts. Return the whole JSON object with "title", "app_name", "roles", "closing" and the
new "lines"."""


def fit_length(plan: dict, narration: str, title: str, cast: tuple[str, str], target_seconds: int, log=print,
               fmt: str = "conversation") -> tuple[dict, dict | None]:
    """A script that would run more than 8% over the length is given back to the model to shorten (a text-only call,
    seconds), up to three times - long before anything is voiced."""
    words, n_lines = budget(target_seconds, fmt)
    usage = None
    for _ in range(2):
        have = sum(len(ln["say"].split()) for ln in plan["lines"])
        if estimate_seconds(plan) <= target_seconds * 1.08:
            break
        log(f"The script has {have} words (about {estimate_seconds(plan):.0f}s) - asking for at most {words} words "
            f"to fit {target_seconds}s")
        people = plan["cast"]
        current = {"title": plan["title"], "app_name": plan.get("app_name", ""), "closing": plan.get("closing", ""),
                   "roles": {"A": people[0]["role"], "B": people[1]["role"]},
                   "lines": [{**{k: v for k, v in ln.items() if k in ("say", "gesture", "mood", "screen")},
                              "speaker": "AB"[ln["speaker"]]} for ln in plan["lines"]]}
        prompt = (SHORTEN.replace("[HAVE]", str(have)).replace("[N]", str(len(plan["lines"])))
                  .replace("[MAXLINES]", str(n_lines)).replace("[PERLINE]", str(per_line(words, n_lines))))
        raw, more = chat_json(prompt, current, "Shortening the script", log, temperature=0.3)
        usage = more if usage is None else {**usage, **{k: round(usage[k] + more[k], 6)
                                                        for k in ("input_tokens", "output_tokens", "cost_usd")}}
        plan = check(raw, sentences(narration), title, cast, fmt)
    if estimate_seconds(plan) > target_seconds * 1.08:
        before = sum(len(ln["say"].split()) for ln in plan["lines"])
        trim(plan, words, n_lines, target_seconds)
        log(f"Trimmed the script in code from {before} to {sum(len(ln['say'].split()) for ln in plan['lines'])} words")
    log(f"Script: {len(plan['lines'])} lines, {sum(len(ln['say'].split()) for ln in plan['lines'])} words, "
        f"about {estimate_seconds(plan):.0f}s")
    return plan, usage


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def trim(plan: dict, words: int, n_lines: int, target_seconds: int) -> None:
    """Make the script fit for sure, without the model: each line keeps its first whole sentences within the per-line
    limit (at least one), then whole question-and-answer pairs are dropped from the middle - the ones that put
    nothing on the screen first - until the length fits. The greeting and the close always stay."""
    cap = round(per_line(words, n_lines) * 1.6)
    for ln in plan["lines"]:
        kept: list[str] = []
        for s in _sentences(ln["say"]):
            lead_in = len(kept) == 1 and len(kept[0].split()) <= 4      # "Hi Maya." / "Exactly." is not a line by itself
            if kept and not lead_in and len(" ".join(kept + [s]).split()) > cap:
                break
            kept.append(s)
        ln["say"] = " ".join(kept)
        if ln.get("screen"):
            for p in ln["screen"]["points"]:
                p["cue"] = _cue(p.get("cue"), ln["say"])
    lines = plan["lines"]
    while estimate_seconds(plan) > target_seconds * 1.05 and len(lines) > 4:
        # a question with its own answer (A then B); presenters simply take turns
        pairs = [k for k in range(1, len(lines) - 2) if lines[k]["speaker"] != lines[k + 1]["speaker"]
                 and (plan.get("style") == "presenters" or lines[k]["speaker"] == 0)]
        if not pairs:
            break
        quiet = [k for k in pairs if not lines[k].get("screen") and not lines[k + 1].get("screen")]
        k = (quiet or pairs)[len(quiet or pairs) // 2]       # from the middle, where the detail is
        del lines[k:k + 2]


def _vary_gestures(lines: list[dict]) -> None:
    """Pointing only when the wall screen changes; nobody makes the same gesture three lines running (the model
    tends to give every question 'open' and every answer 'point')."""
    calm = {0: ("open", "none", "think", "none"), 1: ("explain", "count", "open", "explain")}
    last: dict[int, list[str]] = {0: [], 1: []}
    for n, ln in enumerate(lines):
        who = ln["speaker"]
        if ln["gesture"] == "point" and not ln.get("screen"):
            ln["gesture"] = "explain"
        if ln["gesture"] == "wave" and n > 1:
            ln["gesture"] = "open"
        if last[who][-2:] == [ln["gesture"]] * 2:
            ln["gesture"] = next(g for g in calm[who][n % 4:] + calm[who] if g != ln["gesture"])
        last[who].append(ln["gesture"])


def check(raw: dict, said: list[str], title: str, cast: tuple[str, str], fmt: str = "conversation") -> dict:
    """The conversation made safe: only stated figures and known names in what is said and shown, screen points
    with cues from their line, gestures and moods from the fixed sets, both speakers present."""
    narration = " ".join(said)
    numbers = _numbers_in(narration)
    presets = STUDIO_CAST if fmt == "presenters" else CAST
    default = DEFAULT_STUDIO if fmt == "presenters" else DEFAULT_CAST
    people = [presets.get(c) or presets[default[i]] for i, c in enumerate(cast)]
    app_name = title or _text(raw.get("app_name"), 4)
    vocab = _vocab(narration, title, app_name, people[0]["name"], people[1]["name"])
    fact = lambda v, n=0: _scrub(_text(v, n), numbers, vocab, title_case=True)   # noqa: E731
    lines = []
    for ln in raw.get("lines") or []:
        if not isinstance(ln, dict) or ln.get("speaker") not in ("A", "B"):
            continue
        say = _scrub(re.sub(r"\s+", " ", str(ln.get("say") or "")).strip(), numbers, vocab)
        say = re.sub(r"[*_#\[\]]", "", say).strip()
        if not say:
            continue
        out = {"speaker": 0 if ln["speaker"] == "A" else 1, "say": say,
               "gesture": ln.get("gesture") if ln.get("gesture") in GESTURES else "explain",
               "mood": ln.get("mood") if ln.get("mood") in MOODS else "neutral"}
        if out["gesture"] == "explain" and say.rstrip().endswith("?"):
            out["gesture"] = "open"
        sc = ln.get("screen")
        if isinstance(sc, dict):
            value = _text(sc.get("value"))[:9]
            screen = {"title": fact(sc.get("title"), 6),
                      "points": [{"text": x, "cue": _cue(p.get("cue"), say)} for p in sc.get("points") or []
                                 if isinstance(p, dict) and (x := fact(p.get("text"), 6))][:6 if fmt == "presenters" else 3],
                      "value": value if value and re.search(r"\d", value) and _stated(value, numbers) else ""}
            if screen["title"] or screen["points"] or screen["value"]:
                out["screen"] = screen
                if out["gesture"] in ("explain", "none"):
                    out["gesture"] = "point"
        lines.append(out)
    _vary_gestures(lines)
    if len(lines) < 3 or len({ln["speaker"] for ln in lines}) < 2:
        raise StoryError("the conversation came back too short - try again")
    roles = raw.get("roles") if isinstance(raw.get("roles"), dict) else {}
    cast_out = [{**people[i], "id": cast[i] if cast[i] in presets else default[i],
                 "role": fact(roles.get("AB"[i]), 3) or ("Colleague", "Expert")[i]} for i in range(2)]
    closing = fact(raw.get("closing"), 9)
    return {"style": fmt, "title": _text(raw.get("title"), 7) or app_name or "Conversation",
            "app_name": app_name, "cast": cast_out, "lines": lines,
            "closing": closing or _said(app_name, narration) or app_name}
