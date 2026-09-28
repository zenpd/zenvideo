"""
Draft a live demo script (demo.yaml) from an app URL + a narration transcript that contains stage directions.

1. scan the app read-only (landing page + its navigation pages, GET only): nav labels, buttons, inputs, headings
2. Azure OpenAI converts transcript -> script JSON, shown a hand-made example pair (examples/p2p_*)
3. the result is validated with the normal script loader; validation errors go back to the model (max 2 repairs)

The draft is always reviewed by a person before anything is recorded.
"""

import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import yaml
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from demo.script import ScriptError, load
from demo.text import find_phrase, spoken, tokens

EXAMPLES = Path(__file__).parent / "examples"
MAX_PAGES = 10

SCAN_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 &&
                     getComputedStyle(e).visibility !== 'hidden'; };
  const txt = e => (e.innerText || e.getAttribute('aria-label') || e.title || e.value || '').trim().replace(/\s+/g, ' ');
  const uniq = a => [...new Set(a.filter(Boolean))].slice(0, 60);
  const all = s => [...document.querySelectorAll(s)].filter(vis);
  return {
    title: document.title,
    headings: uniq(all('h1,h2,h3,h4').map(txt).map(t => t.slice(0, 80))),
    buttons: uniq(all('button,[role=button]').map(e => txt(e).slice(0, 60) || (e.title ? `[title] ${e.title}` : ''))),
    links: all('a[href]').map(a => ({text: txt(a).slice(0, 60), href: a.getAttribute('href')})).filter(l => l.text).slice(0, 60),
    inputs: all('input:not([type=hidden]),textarea,[contenteditable=true]').map(e => ({
      tag: e.tagName.toLowerCase(), placeholder: e.getAttribute('placeholder'), disabled: !!e.disabled})).slice(0, 20),
    scroll_height: document.documentElement.scrollHeight, viewport: [innerWidth, innerHeight],
  };
}"""

SYSTEM_PROMPT = """You convert a product-demo narration transcript into a JSON demo script that a browser robot performs
while the narration plays. The transcript mixes NARRATION (words to be spoken) with STAGE DIRECTIONS (what to do on
screen, e.g. 'click "Approve"', 'click agents link and scroll down', 'enter: "..."', 'Send the message').

Output a JSON object: {"title": str, "intro_subtitle": str, "outro_subtitle": str, "segments": [segment, ...]}

segment: {"id": short-kebab-id, "say": narration text (omit for a silent segment), "actions": [action, ...]}
action: exactly one of
  {"click":     {TARGET, "nth"?: "last", "timeout"?: s, "at_word"?: word, "zoom"?: false}}
  {"hover":     {TARGET, "nth"?: "last", "at_word"?: word}}
  {"fill":      {TARGET, "value": text to type}}
  {"press":     "Enter"}
  {"wait_for":  {TARGET, "nth"?: "last", "timeout"?: s}}
  {"scroll":    {"by": pixels (negative = up), "at_word"?: word}}
  {"scroll_to": {TARGET, "exact"?: true, "align": "top"|"center", "at_word": word, "until_word": later word}}
TARGET is one of: {"role": "link"|"button"|"textbox"|..., "name": visible label} | {"text": visible text}
                  | {"placeholder": input placeholder} | {"css": selector}

Rules:
- "say" is the narration VERBATIM from the transcript with stage directions removed. Never rephrase, add or drop words.
  Presenter instructions must NEVER be in "say": 'Click ...', 'Then, in the chat box, enter:', the typed prompt text,
  'Send the message.', 'Check the payment status.', 'Next, click ...'. They become actions only.
- A segment that contains only directions (no narration) is a silent segment: omit "say".
  Keep the transcript's segment boundaries ('---' or timestamps) unless a silent segment must be inserted.
- Every stage direction becomes actions in the segment where it appears. Actions run in order while that segment's
  narration plays; the next segment waits until both the narration and the actions are done.
- If the narration describes a result that only exists after an action and an AI/async reply (typing a prompt,
  sending it, waiting for the reply), put those actions in a SILENT segment (no "say") right before the narration.
- Navigation tabs: {"click": {"role": "link", "name": <exact nav label from app_scan>, "zoom": false}}.
- Use labels exactly as they appear in app_scan when the element exists there. Buttons that only appear later
  (chat reply buttons, next-step chips) are not in the scan: use the label the transcript implies, as short as the
  button text would be (e.g. 'click "Receive the goods"' -> name "Receive goods" only if the transcript/scan says so;
  otherwise keep the transcript's words).
- Chat UIs repeat labels (several "Approve" buttons): always use "nth": "last", and BEFORE clicking a repeated label
  add a wait_for on text that only the new reply contains, with "timeout": 120. The narration paraphrases the app,
  so keep that text to the 1-3 most distinctive words (e.g. "match" rather than "three-way match between the
  purchase order"); never a whole sentence. If unsure, leave the wait_for out - clicks already wait for their button.
- Anything that waits on an AI reply gets "timeout": 120.
- "at_word" (a word or short phrase that occurs in the SAME segment's say) makes the action land when it is spoken.
  Use it when the narration names what is being clicked or shown. Never use a word that is not in that say.
- 'scroll down / scroll through a list the narration walks through' -> prefer scroll_to on the item being named,
  from at_word to until_word, so the page follows the voice. Plain page scrolling -> scroll with by 600-1200.
- Unlabelled icon buttons: use {"role": "button", "name": <title from app_scan '[title] ...'>} or a css selector
  built from the scan (e.g. "input[placeholder*='Ask'] + button" for a send button next to the chat box).
- Return only the JSON object."""


class DraftError(RuntimeError):
    pass


def azure_config() -> dict | None:
    load_dotenv()
    cfg = {k: os.environ.get(f"AZURE_OPENAI_{k.upper()}", "") for k in ("endpoint", "api_key", "deployment")}
    cfg["api_version"] = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    return cfg if all(cfg[k] for k in ("endpoint", "api_key", "deployment")) else None


def scan_app(url: str, log=print) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise DraftError("the app URL must start with http:// or https://")
    out = {"url": url, "pages": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(url, wait_until="networkidle", timeout=60000)
            home = page.evaluate(SCAN_JS)
            out["title"] = home["title"]
            out["pages"].append({"path": parsed.path or "/", **home})
            seen = {parsed.path or "/"}
            for link in home["links"]:
                target = urljoin(url, link["href"])
                tp = urlparse(target)
                if tp.netloc != parsed.netloc or tp.path in seen or "/api/" in tp.path or len(seen) >= MAX_PAGES:
                    continue
                seen.add(tp.path)
                try:
                    page.goto(target, wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(800)
                    out["pages"].append({"path": tp.path, "nav_label": link["text"], **page.evaluate(SCAN_JS)})
                except Exception as e:  # a page that fails to load shouldn't stop the scan
                    log(f"  could not scan {tp.path}: {str(e).splitlines()[0]}")
        finally:
            browser.close()
    out["nav"] = [p.get("nav_label") for p in out["pages"] if p.get("nav_label")]
    return out


def _example() -> tuple[str, str]:
    transcript = (EXAMPLES / "p2p_transcript.txt").read_text(encoding="utf-8")
    data = yaml.safe_load((EXAMPLES / "p2p.yaml").read_text(encoding="utf-8"))
    style = data.get("style", {})
    example = {"title": data["title"], "intro_subtitle": style.get("intro_subtitle", ""),
               "outro_subtitle": style.get("outro_subtitle", ""), "segments": data["segments"]}
    return transcript, json.dumps(example, ensure_ascii=False)


_LEAD = r"(^|[,;]\s*)((then|next|now|finally|first|for the final stage)\s*,?\s*)?"
STRONG_DIRECTION = re.compile(_LEAD + r"(click|tap|press|enter|type|send)\b", re.I)
WEAK_DIRECTION = re.compile(_LEAD + r"(scroll|select|open|go to|navigate|check the)\b", re.I)


def _is_direction(clause: str) -> bool:
    if STRONG_DIRECTION.search(clause) or clause.endswith(":"):
        return True
    if re.fullmatch(r"[\"“'][^\"”']+[\"”']\.?", clause):
        return True
    return bool(WEAK_DIRECTION.search(clause)) and len(clause.split()) <= 8


def _strip_directions(say: str) -> tuple[str, list[str]]:
    """Remove presenter instructions that leaked into the spoken text, clause by clause."""
    kept, removed = [], []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", say):
        for clause in re.split(r"(?<=,)\s+(?=[A-Z])", sentence.strip()):
            c = clause.strip()
            if not c:
                continue
            (removed if _is_direction(c) else kept).append(c)
    text = " ".join(kept)
    return re.sub(r",\s*$", ".", text), removed


def sanitize(doc: dict) -> list[str]:
    """Deterministic clean-up of the model's common slips:
    - stage directions left inside 'say' (they would be spoken) are removed
    - word anchors that don't occur in their own segment's narration are dropped (the action still runs in order)"""
    fixes = []
    for i, seg in enumerate(doc.get("segments") or [], start=1):
        if not isinstance(seg, dict):
            continue
        if isinstance(seg.get("say"), str):
            cleaned, removed = _strip_directions(seg["say"])
            for r in removed:
                fixes.append(f"segment {i}: not spoken (stage direction) {r[:80]!r}")
            if cleaned:
                seg["say"] = cleaned
            else:
                seg.pop("say")
        say = seg.get("say")
        toks = tokens(spoken(say)) if isinstance(say, str) and say.strip() else []
        for action in seg.get("actions") or []:
            if not isinstance(action, dict):
                continue
            fill = action.get("fill")
            if isinstance(fill, dict):
                for k in [k for k, v in fill.items() if v is None]:
                    fill.pop(k)
                if not any(k in fill for k in ("testid", "role", "text", "label", "placeholder", "css")):
                    fill.update(role="textbox", nth="last")
                    fixes.append(f"segment {i}: typing had no target - using the last text box on the page")
            for kind in ("click", "wait_for", "hover"):
                body = action.get(kind)
                if isinstance(body, dict) and body.get("nth") == "last" and float(body.get("timeout") or 0) < 120:
                    body["timeout"] = 120   # a chat-reply element: allow the AI reply time to arrive
            bodies = [action] + [v for v in action.values() if isinstance(v, dict)]
            for body in bodies:
                for key in ("at_word", "until_word"):
                    word = body.get(key)
                    if isinstance(word, str) and (not toks or find_phrase(toks, word) is None):
                        body.pop(key)
                        fixes.append(f"segment {i}: removed {key} {word!r} (not in that segment's narration)")
                if "until_word" in body and "at_word" not in body and "at_word" not in action:
                    fixes.append(f"segment {i}: removed until_word {body.pop('until_word')!r} (no at_word)")
    return fixes


def compose(llm: dict, url: str, options: dict) -> dict:
    """LLM output + the user's options -> a full demo.yaml mapping."""
    doc = {
        "title": options.get("title") or llm.get("title") or "Product demo",
        "url": url,
        "voice": options.get("voice", "af_sky"),
        "speed": float(options.get("speed", 1.1)),
        "fps": 30,
        "pacing": {"gap": 0.7, "action_timeout": 30},
        "style": {"zoom": bool(options.get("zoom", True)), "zoom_max": 1.45,
                  "intro_subtitle": llm.get("intro_subtitle", ""), "outro_subtitle": llm.get("outro_subtitle", "")},
        "subtitles": {"burn": bool(options.get("burn_subtitles", True)),
                      "highlight": bool(options.get("highlight_words", True)), "soft": True},
        "segments": llm.get("segments", []),
    }
    if options.get("music"):
        doc["music"] = {"file": str(options["music"]), "volume_db": float(options.get("music_db", -30))}
    return doc


def draft_script(url: str, transcript: str, options: dict, out_file: Path, log=print) -> Path:
    cfg = azure_config()
    if not cfg:
        raise DraftError("Azure OpenAI is not configured. Add AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and "
                         "AZURE_OPENAI_DEPLOYMENT to .env, then try again.")
    from openai import AzureOpenAI

    log("Scanning the app (read-only)...")
    scan = scan_app(url, log)
    log(f"  {scan.get('title')!r}: {len(scan['pages'])} page(s), navigation: {', '.join(scan['nav']) or 'none found'}")

    ex_transcript, ex_json = _example()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "EXAMPLE transcript:\n" + ex_transcript},
        {"role": "assistant", "content": ex_json},
        {"role": "user", "content": json.dumps({"app_scan": scan, "transcript": transcript}, ensure_ascii=False)},
    ]
    client = AzureOpenAI(azure_endpoint=cfg["endpoint"], api_key=cfg["api_key"], api_version=cfg["api_version"])

    for attempt in range(1, 4):
        log(f"Drafting the script with Azure OpenAI ({cfg['deployment']}), attempt {attempt}...")
        resp = client.chat.completions.create(model=cfg["deployment"], temperature=0,
                                              response_format={"type": "json_object"}, messages=messages)
        content = resp.choices[0].message.content or "{}"
        try:
            doc = compose(json.loads(content), url, options)
            for fix in sanitize(doc):
                log(f"  auto-fix: {fix}")
            out_file.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
            with tempfile.TemporaryDirectory() as td:
                demo = load(out_file, build_dir=td)
            log(f"Draft ready: {len(demo.segments)} segments, {sum(len(s.actions) for s in demo.segments)} actions")
            return out_file
        except (ScriptError, json.JSONDecodeError, KeyError, TypeError) as e:
            log(f"  draft failed validation: {e}")
            messages += [{"role": "assistant", "content": content},
                         {"role": "user", "content": f"That script is invalid: {e}\nReturn the corrected JSON object."}]
    raise DraftError("Azure OpenAI could not produce a valid script after 3 attempts - see the log for the errors.")
