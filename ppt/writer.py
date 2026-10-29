"""
The deck's story: one Azure OpenAI call turns the material (narration, transcript or notes, cleaned by ppt.source)
into a planned deck - the model picks which slide types tell this product's story best - and code then checks it:
counts and lengths clamped, unknown slide types and icons dropped, and any number the material doesn't contain removed,
so the deck never states a figure nobody said.

Cost: about 2-3k input and 1.5-2.5k output tokens per story; switching design reuses the story (no tokens).
AZURE_OPENAI_PPT_DEPLOYMENT picks a different (e.g. stronger) deployment for decks than for the rest of the app.
"""

import json
import os
import re

from dotenv import load_dotenv

from ppt.icons import ICONS


class StoryError(RuntimeError):
    pass


SLIDE_TYPES = ("statement", "stats", "chart", "problem", "before_after", "process", "feature_grid", "feature_focus",
               "quote", "benefits", "closing")
CHARTS = ("bar", "column", "line", "pie", "doughnut")

PROMPT = """You are a senior product marketer who builds strong, persuasive pitch decks. From the material below (a
product narration, a call or meeting transcript, or notes - in order, as "sections" - and/or an "app_tour" of the live
app), plan and write a deck that sells this product to its buyers.

First decide the story, then write the slides. Return one JSON object:
{
 "audience": who the deck is for (max 8 words),
 "core_message": the one idea the audience must remember (max 15 words),
 "app_name": product name (max 4 words), "tagline": (max 9 words), "pitch": one sentence (max 28 words),
 "slides": [[COUNT] slides in order (closing included), each one of these types:
  {"type": "statement", "kicker": max 3 words, "text": a bold claim (max 14 words), "support": max 25 words}
  {"type": "stats", "kicker", "title": max 8 words, "stats": [2-4 {"value": max 7 chars, "label": max 8 words}]}
  {"type": "chart", "kicker", "title", "chart": "bar"|"column"|"line"|"pie"|"doughnut", "series": what the numbers
     measure (max 5 words), "unit": "" or a short unit like "%", "hrs", "$K", "categories": [2-8 labels, max 4 words
     each], "values": [one plain number per category], "takeaway": what the chart shows (max 18 words)}
  {"type": "problem", "kicker", "title", "intro": max 25 words,
     "points": [3 {"title": max 5 words, "body": max 20 words, "icon": ICON}]}
  {"type": "before_after", "kicker", "title", "before_label": max 3 words, "after_label": max 3 words,
     "rows": [3-4 {"before": max 10 words, "after": max 10 words}]}
  {"type": "process", "kicker", "title", "intro": max 20 words, "steps": [3-6 {"name": max 3 words, "body": max 12 words}]}
  {"type": "feature_grid", "kicker", "title", "items": [3, 4 or 6 {"title": max 5 words, "body": max 18 words, "icon": ICON}]}
  {"type": "feature_focus", "kicker", "title", "body": max 35 words, "points": [2-3, max 12 words each],
     "callout": the key takeaway (max 14 words), "screen": SCREEN}
  {"type": "quote", "text": max 22 words, "attribution": max 6 words}
  {"type": "benefits", "kicker", "title", "items": [3 {"metric": max 7 chars or "", "title": max 4 words,
     "body": max 18 words, "icon": ICON}]}
  {"type": "closing", "title": max 7 words, "subtitle": max 14 words, "next_steps": [0-3, max 8 words each]}
 ]
}

How to build a strong deck:
- Story arc: open with a hook (a statement, or stats when the material gives numbers) -> the problem -> how the product
  solves it (process and/or feature_grid) -> 1-3 feature_focus slides on the most important capabilities -> the
  difference it makes (before_after and/or benefits) -> closing. A quote only if the material has a memorable line.
- Titles are insights, not labels: "Approvals happen inside the chat", not "Approvals". Kickers are short section labels.
- Pick the slide type that fits the content: a sequence is a process, a set of capabilities a feature_grid, a contrast
  with the old way a before_after. Never two slides of the same type in a row (feature_focus at most twice, or three
  times with an app_tour).
- Every slide adds something new: no point is repeated across slides. Call each thing by the same name everywhere.
- Facts: use ONLY what the material states. Never invent numbers, customers, prices, integrations or results, and
  never calculate new figures from stated ones (no percentages, ratios or totals the material does not say itself).
- Figures persuade: when the material states results or numbers (time saved, durations, counts, amounts), use them -
  a stats slide near the start and/or metrics in benefits, written as digits with a short unit ("2 days", "3 hrs",
  "20 min", "11", "600K"). Without stated numbers, use no stats slide and leave metrics "".
- Charts: when the material gives 3 or more comparable numbers (over time, by category, or parts of a whole), a chart
  slide shows them best - line for a trend over time, bar/column to compare categories, pie/doughnut only for parts
  of one whole. Every value must be a number stated in the material or the instructions; never estimate or fill gaps.
- Ignore stage directions, filler, small talk and speaker chatter in transcripts; keep the product story.
- The closing title is a call to action or the promise restated (never a label like "Next steps"); next_steps are
  concrete actions from the material (e.g. a pilot it mentions), else [].
- Plain, confident language for business readers. No exclamation marks, no buzzword chains. Titles without a period.
- ICON: one of [ICONS] - the one that fits best.
- SCREEN: the id of the app_tour screen that shows the capability, or "" (without an app_tour, always ""). Each
  screen at most once. The screens that show the product at work are the strongest: a "result" (what the app produced
  after an action, e.g. its recommendation) first, then a "detail" or "view", then the main page; settings last.
- "app_tour" (when given) is what a browser saw going through the live app: each screen in the order visited, its
  "kind", how it was reached ("via") and its visible text; the first also has the browser tab's "page_title" and the
  "app_frame" (logo, product name and menu around the pages) - app_name is the name the app shows there. It is material too: what the app's pages show and do, and
  the flow a user goes through (e.g. pick a region, submit a payment, get the AI's recommendation) - a process slide
  can follow it. Numbers on its screens are the app's demo data: never put them in the deck's text (no stats,
  metrics, charts or percentages from them) - the screenshots show them; describe what the screens do in words. With
  "sections" too, the sections lead the story and the tour adds screens and detail. With only the tour, frame the
  problem from what the product clearly addresses, without claims about customers or the market.
- Follow the "brief": write for its audience (what they care about decides which slide types and points lead), keep to
  the slide count, and give its focus extra weight - its own slide(s) where the material supports it. The brief never
  overrides the facts rule: if the material says nothing about the focus, do not make anything up.
- "instructions" (when given) are the user's own requests for this deck - follow every one of them exactly, as long
  as it doesn't break the facts rule (a chart needs real numbers from the material or the instructions). Slide numbers
  in instructions don't count the automatic title slide: "slide 1" is the first slide of "slides". Instructions win over
  the brief's audience and slide count. Then add "requests": [{"request": the request in a few words, "slide": its
  slide number or null, "type": the slide type it asked for or "", "chart": the chart kind it asked for or "",
  "status": "done" or "not_possible", "note": why not, when not possible (max 15 words)}] - one entry per request;
  anything you cannot do in a deck of these slide types (logos, photos, animations, ...) is "not_possible".
- Return only the JSON object."""

# Who the deck is for: id -> (label, one-line description for the UI, guidance for the model). "auto" lets the model
# infer the audience from the material.
AUDIENCES = {
    "auto": ("Auto", "Worked out from your text",
             "Infer the most likely audience from the material."),
    "executive": ("Executives", "Outcomes, cost, risk and time to value",
                  "Business leaders deciding whether to invest: lead with outcomes, cost, risk and time to value; keep "
                  "how-it-works brief; favour stats, before_after and benefits."),
    "investor": ("Investors", "The problem's size, the edge, results, the ask",
                 "Investors: the size of the problem, why now, what makes the product different, results the material "
                 "states, and the ask or next step; bold and concise."),
    "customer": ("Customers", "Their pains, how their day changes, benefits",
                 "Prospective customers: their daily pains, how their work changes, ease of adoption and concrete "
                 "benefits; favour problem, feature_focus and before_after."),
    "technical": ("Technical team", "How it works, integrations, data, security",
                  "Technical evaluators (IT, architects): how it works, process, integrations, data, security and "
                  "governance; favour process, feature_grid and feature_focus; few marketing claims."),
    "internal": ("Internal team", "What it is, what changes, next steps",
                 "Colleagues and stakeholders: what it is, how it works, what it changes for the team, and next "
                 "steps; plain and informative."),
    "custom": ("Custom", "Tell the AI exactly what you want",
               "Follow the user's instructions; infer the audience from them and the material."),
}
# How long: id -> (label, fewest slides, most slides) - closing included, cover and agenda added on top.
LENGTHS = {"short": ("Short", 5, 7), "standard": ("Standard", 8, 11), "detailed": ("Detailed", 12, 15)}


def clean_brief(brief: dict | None) -> dict:
    b = brief or {}
    return {"audience": b.get("audience") if b.get("audience") in AUDIENCES else "auto",
            "length": b.get("length") if b.get("length") in LENGTHS else "standard",
            "focus": re.sub(r"\s+", " ", str(b.get("focus") or "")).strip()[:200],
            "instructions": str(b.get("instructions") or "").strip()[:1500] if b.get("audience") == "custom" else ""}

# Estimated cost per 1M tokens (USD). Defaults are the list prices of gpt-4.1-mini; set AZURE_OPENAI_PRICE_INPUT and
# AZURE_OPENAI_PRICE_OUTPUT in .env for your deployment's actual rates.
PRICE_INPUT, PRICE_OUTPUT = 0.40, 1.60


def azure_config() -> dict | None:
    load_dotenv()
    cfg = {k: os.environ.get(f"AZURE_OPENAI_{k.upper()}", "") for k in ("endpoint", "api_key", "deployment")}
    cfg["deployment"] = os.environ.get("AZURE_OPENAI_PPT_DEPLOYMENT") or cfg["deployment"]
    cfg["api_version"] = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    return cfg if all(cfg[k] for k in ("endpoint", "api_key", "deployment")) else None


def write_story(parts: list[str], title: str = "", screens: list[dict] | None = None, log=print,
                brief: dict | None = None) -> tuple[dict, dict]:
    """One Azure OpenAI call: the raw story JSON (run normalize on it) and the call's token usage and estimated cost.
    parts: the narration's sections (may be empty when there are screens); screens: the app tour, [{"screen": id,
    "via": how it was reached, "text": what it shows}]; brief: {"audience", "length", "focus"} (see AUDIENCES, LENGTHS)."""
    brief = clean_brief(brief)
    _, lo, hi = LENGTHS[brief["length"]]
    payload = {"product_name": title or None,
               "brief": {"audience": AUDIENCES[brief["audience"]][2], "slides": f"{lo}-{hi}",
                         "focus": brief["focus"] or None},
               "sections": parts or None}
    if brief["instructions"]:
        payload["instructions"] = brief["instructions"]
    if screens:
        payload["app_tour"] = screens
    prompt = PROMPT.replace("[ICONS]", ", ".join(ICONS)).replace("[COUNT]", f"{lo}-{hi}")
    content, usage = chat_json(prompt, payload, "Writing the deck's story", log, temperature=0.4)
    log(f"Story written: {usage['input_tokens']:,} input + {usage['output_tokens']:,} output tokens "
        f"(about ${usage['cost_usd']:.4f})")
    return content, usage


def chat_json(system: str, payload: dict, what: str, log=print, temperature: float = 0.2) -> tuple[dict, dict]:
    """One Azure OpenAI call that returns JSON: (the JSON, token usage and estimated cost)."""
    cfg = azure_config()
    if not cfg:
        raise StoryError("Azure OpenAI is not configured (AZURE_OPENAI_* in .env) - it writes the deck's story.")
    from openai import AzureOpenAI

    client = AzureOpenAI(azure_endpoint=cfg["endpoint"], api_key=cfg["api_key"], api_version=cfg["api_version"])
    log(f"{what} with Azure OpenAI ({cfg['deployment']})...")
    resp = client.chat.completions.create(
        model=cfg["deployment"], temperature=temperature, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}])
    try:
        content = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError as e:
        raise StoryError(f"Azure OpenAI returned invalid JSON: {e}") from e
    tin, tout = (resp.usage.prompt_tokens, resp.usage.completion_tokens) if resp.usage else (0, 0)
    pin = float(os.environ.get("AZURE_OPENAI_PRICE_INPUT") or PRICE_INPUT)
    pout = float(os.environ.get("AZURE_OPENAI_PRICE_OUTPUT") or PRICE_OUTPUT)
    return content, {"model": cfg["deployment"], "input_tokens": tin, "output_tokens": tout,
                     "cost_usd": round((tin * pin + tout * pout) / 1e6, 6)}


def add_usage(a: dict | None, b: dict | None) -> dict | None:
    """Two calls' usage added up (either may be None)."""
    if not a or not b:
        return a or b
    return {"model": a["model"], "input_tokens": a["input_tokens"] + b["input_tokens"],
            "output_tokens": a["output_tokens"] + b["output_tokens"],
            "cost_usd": round(a["cost_usd"] + b["cost_usd"], 6)}


# ── checking the story ───────────────────────────────────────────────────────

_SCALE = {"k": 1e3, "m": 1e6, "b": 1e9, "bn": 1e9, "mn": 1e6}


def _numbers_in(text: str) -> set[float]:
    """Every number the material states, as digits or as words ('six hundred thousand' -> 600000)."""
    found = set()
    for m in re.finditer(r"(\d+(?:[.,]\d+)*)\s*(k|m|b|bn|mn|thousand|million|billion)?\b", text.lower()):
        v = float(m[1].replace(",", ""))
        mult = {"thousand": 1e3, "million": 1e6, "billion": 1e9}.get(m[2] or "", _SCALE.get(m[2] or "", 1))
        found |= {v, v * mult}
    found |= _word_numbers(text)
    return found


_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                     "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if i > 1}
_MULT = {"hundred": 100, "thousand": 1e3, "million": 1e6, "billion": 1e9}


def _word_numbers(text: str) -> set[float]:
    """Numbers written as words, e.g. 'one thousand, two hundred' -> 1200, 'a dozen' -> 12, 'half' -> 0.5."""
    out = {12.0} if re.search(r"\bdozen\b", text, re.I) else set()
    words = re.findall(r"[a-z]+", text.lower().replace("-", " "))
    total = cur = 0.0
    seen = False
    for w in words + ["."]:
        if w in _UNITS or w in _TENS:
            cur += _UNITS.get(w, 0) + _TENS.get(w, 0)
            seen = True
        elif w == "hundred" and seen:
            cur *= 100
        elif w in _MULT and seen:
            total += cur * _MULT[w]
            cur = 0
        elif w == "and" and seen:
            continue
        else:
            if seen:
                out |= {total + cur, cur}
            total = cur = 0
            seen = False
    return out


def _stated(value: str, numbers: set[float]) -> bool:
    """True when a figure like '600K', '$1.2M', '40%' or '3x' is a number the material states (or has no number)."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(k|m|b|bn|mn)?\b", value.lower().replace(",", ""))
    if not m:
        return True
    v = float(m[1]) * _SCALE.get(m[2] or "", 1)
    return any(abs(v - n) < 1e-6 * max(1, abs(n)) for n in numbers)


_FIGURE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:k|m|b|bn|mn)?\b", re.I)
# Words that look like names but are generic enough to allow without the material saying them.
_GENERIC_CAPS = {"I", "OK", "IT", "CEO", "CFO", "CIO", "CTO", "COO", "KPI", "KPIs", "ROI", "FAQ", "UI", "UX", "PDF",
                 "PO", "POs", "PR", "PRs"}
_TITLE_KEYS = {"title", "kicker", "name", "label", "before_label", "after_label", "audience"}


def _vocab(*texts: str) -> set[str]:
    """Every word of the texts, lower case, with and without a plural s."""
    words = set()
    for t in texts:
        for w in re.findall(r"[A-Za-z][A-Za-z0-9&'-]*", t or ""):
            w = w.lower().strip("'-")
            words |= {w, w.rstrip("s"), w.removesuffix("'s")}
    return words


def _names(sentence: str, title_case: bool) -> list[str]:
    """Words in a sentence that look like names of products, companies or systems: CamelCase (OpenTelemetry),
    letters with digits (S4HANA), all capitals (SAP) - and, in normal sentences, a capitalised word that doesn't start
    the sentence (Salesforce). Titles are often Title Case, so there only the first three kinds count."""
    found = []
    for i, m in enumerate(re.finditer(r"[A-Za-z][A-Za-z0-9&]*(?:'[A-Za-z]+)?", sentence)):   # hyphens split words
        w = m[0]
        camel = re.search(r"[a-z][A-Z]", w) or (re.search(r"\d", w) and re.search(r"[A-Za-z]{2}", w))
        caps = re.fullmatch(r"[A-Z]{2,}s?", w)
        capital = (not title_case and i > 0 and re.fullmatch(r"[A-Z][a-z]+", w)
                   and sentence[m.start() - 2:m.start()] != ": " and sentence[m.start() - 1:m.start()] != "-")
        if (camel or caps or capital) and w not in _GENERIC_CAPS:
            found.append(w)
    return found


def _scrub(text: str, numbers: set[float], vocab: set[str] | None = None, title_case: bool = False) -> str:
    """text without the sentences that state a figure the material doesn't (e.g. a percentage the model worked out)
    or name something it never mentions (e.g. an integration it doesn't have)."""
    if not re.search(r"\d", text) and vocab is None:
        return text
    keep = []
    for x in re.split(r"(?<=[.!?;])\s+", text):
        if not all(_stated(m[0], numbers) for m in _FIGURE.finditer(x)):
            continue
        if vocab is not None and any(_vocab(n).isdisjoint(vocab) for n in _names(x, title_case)):
            continue
        keep.append(x)
    return " ".join(keep).strip()


def _scrub_all(v, numbers: set[float], vocab: set[str] | None = None, key: str = ""):
    """_scrub on every string of the story, except stats values and metrics (checked whole, below) and the product
    name."""
    if isinstance(v, dict):
        return {k: x if k in ("value", "values", "metric", "type", "icon", "screen", "app_name", "requests", "chart") else
                _scrub_all(x, numbers, vocab, k) for k, x in v.items()}
    if isinstance(v, list):
        return [_scrub_all(x, numbers, vocab, key) for x in v]
    return _scrub(v, numbers, vocab, key in _TITLE_KEYS) if isinstance(v, str) else v


def _text(v, limit: int = 0) -> str:
    t = re.sub(r"\s+", " ", str(v or "")).strip().rstrip()
    return " ".join(t.split()[:limit]) if limit else t


def normalize(raw: dict, material: str, screen_ids: list[str] | None = None, title: str = "",
              length: str = "standard", instructions: str = "", figures: str | None = None) -> dict:
    """Make the story safe to lay out: known slide types only, counts clamped, figures checked against the material
    (and the user's instructions, which may give a chart's numbers), icons and screens validated, a closing slide
    last, and each of the user's requests checked against the slides it produced.
    figures: the text whose numbers the deck may state, when not all of the material (an app's screens show demo data:
    their numbers stay in the screenshots)."""
    source = f"{material}\n{instructions}"
    numbers = _numbers_in(f"{material if figures is None else figures}\n{instructions}")
    raw = _scrub_all(raw, numbers, _vocab(source, title, str(raw.get("app_name") or "")))
    dropped_charts = 0
    screens = set(screen_ids or [])
    icon = lambda v: v if v in ICONS else ""   # noqa: E731
    c = {"audience": _text(raw.get("audience")), "core_message": _text(raw.get("core_message")),
         "app_name": title or _text(raw.get("app_name"), 6) or "Our product", "tagline": _text(raw.get("tagline")),
         "pitch": _text(raw.get("pitch"))}
    slides = []
    for s in raw.get("slides") or []:
        if not isinstance(s, dict) or s.get("type") not in SLIDE_TYPES:
            continue
        t = s["type"]
        out = {"type": t, "kicker": _text(s.get("kicker"), 4), "title": _text(s.get("title"))}
        if t == "statement":
            out.update(text=_text(s.get("text")), support=_text(s.get("support")))
            if not out["text"]:
                continue
        elif t == "stats":
            stats = [{"value": _text(x.get("value"))[:8], "label": _text(x.get("label"))} for x in s.get("stats") or []
                     if isinstance(x, dict) and _text(x.get("value")) and _stated(_text(x.get("value")), numbers)]
            if len(stats) < 2:
                continue
            out["stats"] = stats[:4]
        elif t == "chart":
            kind = s.get("chart") if s.get("chart") in CHARTS else "column"
            pairs = [(_text(cat)[:32], _number(v)) for cat, v in zip(s.get("categories") or [], s.get("values") or [])]
            pairs = [(cat, v) for cat, v in pairs if cat and v is not None][:8]
            if len(pairs) < 2 or not all(any(abs(v - n) < 1e-6 * max(1, abs(n)) for n in numbers) for _, v in pairs):
                dropped_charts += 1       # numbers nobody stated: no chart rather than a made-up one
                continue
            if kind in ("pie", "doughnut") and any(v <= 0 for _, v in pairs):
                kind = "column"
            out.update(chart=kind, series=_text(s.get("series"), 6), unit=_text(s.get("unit"))[:6],
                       categories=[cat for cat, _ in pairs], values=[v for _, v in pairs],
                       takeaway=_text(s.get("takeaway")))
        elif t == "problem":
            pts = [{"title": _text(x.get("title")), "body": _text(x.get("body")), "icon": icon(x.get("icon"))}
                   for x in s.get("points") or [] if isinstance(x, dict) and _text(x.get("title"))]
            if len(pts) < 2:
                continue
            out.update(intro=_text(s.get("intro")), points=pts[:3])
        elif t == "before_after":
            rows = [{"before": _text(x.get("before")), "after": _text(x.get("after"))} for x in s.get("rows") or []
                    if isinstance(x, dict) and _text(x.get("before")) and _text(x.get("after"))]
            if len(rows) < 2:
                continue
            out.update(before_label=_text(s.get("before_label"), 3) or "Today",
                       after_label=_text(s.get("after_label"), 3) or f"With {c['app_name']}", rows=rows[:4])
        elif t == "process":
            steps = [{"name": _text(x.get("name"), 4), "body": _text(x.get("body"))} for x in s.get("steps") or []
                     if isinstance(x, dict) and _text(x.get("name"))]
            if len(steps) < 3:
                continue
            out.update(intro=_text(s.get("intro")), steps=steps[:6])
        elif t == "feature_grid":
            items = [{"title": _text(x.get("title")), "body": _text(x.get("body")), "icon": icon(x.get("icon"))}
                     for x in s.get("items") or [] if isinstance(x, dict) and _text(x.get("title"))]
            if len(items) < 3:
                continue
            out["items"] = items[:6] if len(items) >= 6 else items[:4] if len(items) >= 4 else items[:3]
        elif t == "feature_focus":
            out.update(body=_text(s.get("body")), points=[_text(p) for p in s.get("points") or [] if _text(p)][:3],
                       callout=_text(s.get("callout")), screen=s.get("screen") if s.get("screen") in screens else "")
            if not out["title"] or not (out["body"] or out["points"]):
                continue
        elif t == "quote":
            out.update(text=_text(s.get("text")).strip('"“” '), attribution=_text(s.get("attribution")))
            if not out["text"]:
                continue
        elif t == "benefits":
            items = [{"metric": m if (m := _text(x.get("metric"))[:8]) and _stated(m, numbers) and re.search(r"\d", m) else "",
                      "title": _text(x.get("title")), "body": _text(x.get("body")), "icon": icon(x.get("icon"))}
                     for x in s.get("items") or [] if isinstance(x, dict) and _text(x.get("title"))]
            if len(items) < 2:
                continue
            out["items"] = items[:3]
        elif t == "closing":
            out.update(subtitle=_text(s.get("subtitle")), next_steps=[_text(x) for x in s.get("next_steps") or [] if _text(x)][:3])
        slides.append(out)
    closing = next((x for x in slides if x["type"] == "closing"), None)
    slides = [x for x in slides if x["type"] != "closing"][:LENGTHS.get(length, LENGTHS["standard"])[2] - 1]
    if not slides:
        raise StoryError("the story came back without usable slides - try again or give more material")
    closing = closing or {"type": "closing", "kicker": "", "title": "", "subtitle": "", "next_steps": []}
    closing["title"] = closing["title"] or c["tagline"] or c["app_name"]
    closing["subtitle"] = closing["subtitle"] or c["core_message"] or c["tagline"]
    c["slides"] = slides + [closing]
    c["requests"] = _check_requests(raw.get("requests"), c["slides"], dropped_charts)
    return c


def _number(v) -> float | None:
    """A chart value as a float: 12, "12", "1,200", "40%", "$600K" -> 600000."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(k|m|b|bn|mn)?\b", str(v or "").lower().replace(",", ""))
    return float(m[1]) * _SCALE.get(m[2] or "", 1) if m else None


# Requests the deck engine cannot carry out, whatever the model claims: (pattern, the reason shown to the user).
UNSUPPORTED = [
    (r"\blogos?\b", "Logos can't be added from instructions yet"),
    (r"\b(images?|photos?|pictures?|illustrations?|screenshots?)\b", "Images can't be added from instructions yet"),
    (r"\b(animat\w*|transitions?)\b", "Animations and transitions aren't supported"),
    (r"\b(videos?|gifs?|audio|sound|music)\b", "Video and audio can't be embedded in the deck"),
    (r"\b(fonts?|typefaces?)\b", "Fonts come from the chosen design"),
    (r"\b(colou?rs?|branding|brand colou?rs?)\b", "Colours come from the chosen design"),
]


def _check_requests(requests, slides: list[dict], dropped_charts: int) -> list[dict]:
    """The user's requests as the model reported them, with "done" verified: anything the deck engine can't produce
    (UNSUPPORTED) is "not_possible" whatever the model says, and a request for a slide type or chart must match the
    actual slide it names - otherwise "not_done" with the reason."""
    out = []
    for r in requests or []:
        if not isinstance(r, dict) or not _text(r.get("request")):
            continue
        slide = r.get("slide") if isinstance(r.get("slide"), int) and r.get("slide") > 0 else None
        kind, chart = r.get("type") if r.get("type") in SLIDE_TYPES else "", r.get("chart") if r.get("chart") in CHARTS else ""
        item = {"request": _text(r.get("request"))[:140], "slide": slide, "type": kind, "chart": chart,
                "status": "done" if r.get("status") == "done" else "not_possible", "note": _text(r.get("note"))[:160]}
        reason = next((why for pattern, why in UNSUPPORTED if re.search(pattern, item["request"], re.I)), None)
        if reason and not (kind or chart):
            item.update(status="not_possible", note=reason)
        elif item["status"] == "done" and (kind or chart):
            candidates = [slides[slide - 1]] if slide and slide <= len(slides) else [] if slide else slides
            ok = any((not kind or x["type"] == kind) and (not chart or x.get("chart") == chart) for x in candidates)
            if not ok:
                item["status"] = "not_done"
                item["note"] = ("A chart needs real numbers, and they aren't in your text or instructions"
                                if (chart or kind == "chart") and dropped_charts else
                                "The deck came out differently - try rewording the request")
        out.append(item)
    return out


# ── revising a deck after a review ───────────────────────────────────────────

REVISE = """You edit a pitch deck after a review. You get the deck's current story ("deck": its title slide fields and
its "slides", each numbered "n"), the material it was written from ("sections" and/or "app_tour"), and the reviewer's
comments ("comments": each has an "id", a "target" - "slides[N]" (the slide with "n": N, whose current "headline" is
given too), "title slide", "agenda" (the agenda lists the slides' kickers) or "deck" (the whole deck) - and the
"comment").

Do NOT rewrite the deck. Return only the edits the comments need, as one JSON object:
{"edits": [   (every edit has "for": the id of the comment it answers)
   {"do": "update", "target": "slides[N]", "headline": the slide's current title (or text) word for word,
     "set": {only the fields that change, e.g. {"title": "..."} or {"points": [...]}}} - the usual edit,
   {"do": "replace", "target": "slides[N]", "headline": its current title word for word, "slide": a complete slide of
     another type} - only when the comment asks for a different kind of slide,
   {"do": "insert_after", "target": "slides[N]", "slide": a complete new slide} (N = 0: insert at the start),
   {"do": "delete", "target": "slides[N]", "headline": its current title word for word},
   {"do": "title", "app_name": ..., "tagline": ..., "pitch": ...} (only the fields that change)
 ],
 "changes": [{"id": the comment's id, "status": "done" or "not_possible", "note": what you changed, or why not
   (max 15 words)}] - one per comment}

How:
- A comment with a "slides[N]" target is about that slide only: edit that slide (the edit's "target" is the
  comment's target). Never apply a comment to another slide. A slide's "title" or "headline" is its "title" field ("text" on a
  statement or quote slide) - not its "kicker" (the small label above it). A comment on the whole deck (e.g. tone)
  replaces every slide it affects. Anything you do not edit stays exactly as it is.
- Replaced and new slides follow the deck's rules below: the slide types, their fields and word limits, and the
  facts rule - only what the material states; the reviewer's comments count as material too (a figure or fact they
  give may be used). Anything a deck of these slide types cannot do (animations, videos, logos, photos) is
  "not_possible".

The deck's rules (for the slides you write):

"""


def _key(v) -> str:
    """A headline compared loosely: lower case, letters and digits only."""
    return re.sub(r"[^a-z0-9]+", " ", str(v or "").lower()).strip()


def revise_story(content: dict, comments: list[dict], parts: list[str], screens: list[dict] | None, title: str = "",
                 log=print) -> tuple[dict, list[dict], dict]:
    """One Azure OpenAI call for the edits the reviewer's comments need ([{"slide": n or None, "about": ...,
    "comment": ...}]), applied here to the current story - so nothing the comments don't touch can change. Returns the
    edited story (run normalize on it, with the comments' text as instructions), the model's report and the usage."""
    deck = {k: content.get(k) for k in ("app_name", "tagline", "pitch")}
    deck["slides"] = [{"n": i + 1, **{k: v for k, v in s.items() if k != "notes"}} for i, s in enumerate(content["slides"])]
    prompt = REVISE + PROMPT.replace("[ICONS]", ", ".join(ICONS)).replace("[COUNT]", "the same number of")
    asked = [{"id": i + 1, "target": c.get("about") or ("deck" if not c.get("slide") else "agenda"),
              "comment": c["comment"]} for i, c in enumerate(comments)]
    for a in asked:
        m = re.fullmatch(r"slides\[(\d+)\]", a["target"])
        if m and 1 <= int(m[1]) <= len(deck["slides"]):
            sl = deck["slides"][int(m[1]) - 1]
            a["headline"] = sl.get("title") or sl.get("text") or ""
    payload = {"product_name": title or None, "deck": deck, "comments": asked, "sections": parts or None}
    if screens:
        payload["app_tour"] = screens
    raw, usage = chat_json(prompt, payload, f"Revising the deck ({len(comments)} comment(s))", log, temperature=0.2)
    log(f"Deck revised: {usage['input_tokens']:,} input + {usage['output_tokens']:,} output tokens "
        f"(about ${usage['cost_usd']:.4f})")
    story = {k: content.get(k) for k in ("audience", "core_message", "app_name", "tagline", "pitch")}
    slides = [{"n": i + 1, **{k: v for k, v in s.items() if k != "notes"}} for i, s in enumerate(content["slides"])]
    made = 0
    for e in raw.get("edits") or []:
        if not isinstance(e, dict):
            continue
        if e.get("do") == "title":
            story.update({k: e[k] for k in ("app_name", "tagline", "pitch") if isinstance(e.get(k), str) and e[k].strip()})
            made += 1
            continue
        target = str(e.get("target") or "")
        answers = next((a for a in asked if a["id"] == e.get("for")), None)
        if answers and answers["target"].startswith("slides[") and e.get("do") in ("update", "replace", "delete"):
            target, e["headline"] = answers["target"], answers.get("headline") or e.get("headline")   # the comment's slide
        m = re.fullmatch(r"\s*slides\[(\d+)\]\s*", target)
        if not m:
            continue
        n = int(m[1])
        at = next((k for k, s in enumerate(slides) if s.get("n") == n), None)
        new = e.get("slide") if isinstance(e.get("slide"), dict) and e["slide"].get("type") in SLIDE_TYPES else None
        quoted = _key(e.get("headline"))
        if e.get("do") in ("update", "replace", "delete") and quoted:
            # the model names the slide by its headline too: if the number points elsewhere, the headline wins;
            # if neither matches, the edit is not applied (a wrong slide is never touched)
            if at is None or _key(slides[at].get("title") or slides[at].get("text")) != quoted:
                at = next((k for k, s in enumerate(slides) if _key(s.get("title") or s.get("text")) == quoted), None)
                if at is None:
                    continue
        if e.get("do") == "update" and at is not None and isinstance(e.get("set"), dict):
            slides[at] = {**slides[at], **{k: v for k, v in e["set"].items() if k not in ("n", "type")}}
        elif e.get("do") == "replace" and at is not None and new:
            slides[at] = {**new, "n": slides[at]["n"]}
        elif e.get("do") == "delete" and at is not None:
            del slides[at]
        elif e.get("do") == "insert_after" and new and (at is not None or n == 0):
            slides.insert(0 if n == 0 else at + 1, {**new, "n": None})
        else:
            continue
        made += 1
    story["slides"] = [{k: v for k, v in s.items() if k != "n"} for s in slides]
    log(f"{made} edit(s) applied")
    by_id = {c.get("id"): c for c in raw.get("changes") or [] if isinstance(c, dict)}
    changes = []
    for i, c in enumerate(comments):      # one line per comment, with the reviewer's own words and slide number
        got = by_id.get(i + 1) or {}
        changes.append({"comment": _text(c["comment"], 14), "slide": c.get("slide"),
                        "status": got.get("status") if got.get("status") in ("done", "not_possible") else "not_possible",
                        "note": _text(got.get("note"), 20) or ("" if got else "No change was made")})
    if not made:      # nothing was actually changed: say so, whatever the model reported
        changes = [{**c, "status": "not_possible", "note": c["note"] or "No change was made"} for c in changes]
    return story, changes, usage
