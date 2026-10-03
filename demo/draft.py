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
    inputs: all('input:not([type=hidden]):not([type=file]),textarea,[contenteditable=true]').map(e => ({
      tag: e.tagName.toLowerCase(), type: (e.type || '').toLowerCase(),
      label: ((e.labels && e.labels[0] && e.labels[0].innerText) || e.getAttribute('aria-label') || e.name || '').trim().slice(0, 60),
      placeholder: e.getAttribute('placeholder'), disabled: !!e.disabled})).slice(0, 30),
    selects: all('select').map(e => ({
      label: ((e.labels && e.labels[0] && e.labels[0].innerText) || e.getAttribute('aria-label') || e.name || '').trim().slice(0, 60),
      options: [...e.options].map(o => (o.label || o.text).trim()).filter(Boolean).slice(0, 25)})).slice(0, 15),
    file_inputs: document.querySelectorAll('input[type=file]').length,
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
  {"select":    {TARGET of the dropdown, "option": visible option label, "at_word"?: word}}
  {"upload":    {TARGET of the upload area (optional), "path": exact file path from the transcript, "at_word"?: word}}
TARGET is one of: {"role": "link"|"button"|"textbox"|..., "name": visible label} | {"text": visible text}
                  | {"placeholder": input placeholder} | {"css": selector}

Narration style - a natural product demo, not a voice reading out clicks:
- Keep the transcript's existing narration VERBATIM in "say" (stage directions removed). Never rephrase, shorten or
  pad good narration. Presenter instructions must NEVER be spoken: 'Click ...', 'Then, in the chat box, enter:', the
  typed prompt text, 'Send the message.', 'Check the payment status.', 'Next, click ...'. They become actions only.
- A part of the transcript that is ONLY stage directions still gets narration: write ONE short, factual bridge sentence
  (at most 14 words) that says the PURPOSE or the RESULT of those actions, never the mechanics, and anchor the main
  action to a word in it with "at_word". Examples:
    'click Agents'                          -> "Let's look at the specialist agents behind the workflow." (at_word: agents)
    filling a form with several values      -> "I'll enter the policyholder and incident details." (fills during it)
    'search for the claim'                  -> "I'll find the claim we just submitted." (at_word: find)
    'send the prompt' + waiting for the AI  -> "Let's ask the assistant to raise the requisition." (at_word: ask)
    a slow step (analysis, upload, report)  -> "The document is being analyzed." (then wait_for the result)
  Never say "click", "type", "tap", "this button" or read typed values aloud; describe what the user achieves.
- Pattern: natural narration -> the action lands on the word that names it (at_word) -> the next narration describes
  the result. Keep the transcript's segment boundaries ('---' or timestamps); a direction-only part becomes a short
  bridge segment of its own, placed before the narration that describes its result.
- Every stage direction becomes actions in the segment where it appears. Actions run in order while that segment's
  narration plays; the next segment waits until both the narration and the actions are done.
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
- Unlabelled icon buttons: use {"role": "button", "name": <title/aria-label from app_scan '[title] ...'>}.
  To send what was typed into a chat box, use that button's label if the scan shows one, otherwise {"press": "Enter"}.
  Never build a selector from placeholder text: placeholders change with the app's state (a chat box can say "Start a
  conversation first" before a chat exists and "Ask me anything" after), so the selector stops matching. Type into a
  chat box with {"fill": {"role": "textbox", "nth": "last", "value": ...}}.
- Typing: {"fill": TARGET, "value": ...} focuses the field itself - never add a click on the same field before it.
- Native dropdowns (app_scan "selects"): {"select": {TARGET of the dropdown, "option": exact option label}} - never
  click an option's text. Native date fields (app_scan inputs with type "date"): {"fill": {TARGET, "value":
  "yyyy-mm-dd"}} - never click a calendar icon or day numbers.
- Uploads: ONLY when the transcript explicitly says to upload a file AND gives its path, use {"upload": {"path": <that
  exact path>, TARGET of the visible upload area if any}}. Never invent or guess a path; without an explicit path,
  leave the upload out.
- Text fields: use role "textbox" (never "input" or "textarea", which are not roles).
- Return only the JSON object."""


class DraftError(RuntimeError):
    pass


def azure_config() -> dict | None:
    load_dotenv()
    cfg = {k: os.environ.get(f"AZURE_OPENAI_{k.upper()}", "") for k in ("endpoint", "api_key", "deployment")}
    cfg["api_version"] = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    return cfg if all(cfg[k] for k in ("endpoint", "api_key", "deployment")) else None


NAVIGATION_ERRORS = ("Execution context was destroyed", "because of a navigation", "Cannot find context with")


def _scan_page(page, log=print) -> dict:
    """Read the page with SCAN_JS. A client-side redirect or late navigation can destroy the page's JavaScript context
    mid-read; then wait for the new document and read again (at most 2 retries, only for that error)."""
    for attempt in range(3):
        try:
            return page.evaluate(SCAN_JS)
        except Exception as e:  # noqa: BLE001 - only the navigation error is retried, anything else is raised
            if attempt == 2 or not any(m in str(e) for m in NAVIGATION_ERRORS):
                raise
            log(f"  page navigated while being scanned - waiting for it to settle (retry {attempt + 1}/2)")
            try:
                page.wait_for_load_state("load", timeout=15000)
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:  # noqa: BLE001 - a page that never goes idle is still worth reading
                pass
            page.wait_for_timeout(500)
    raise AssertionError("unreachable")


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
            home = _scan_page(page, log)
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
                    out["pages"].append({"path": tp.path, "nav_label": link["text"], **_scan_page(page, log)})
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


def _is_send(actions: list[dict], fill_action: dict) -> bool:
    """True when this typing is a chat message: the next action presses Enter or clicks a button / css target."""
    if "fill" not in fill_action or fill_action not in actions:
        return False
    k = actions.index(fill_action)
    nxt = actions[k + 1] if k + 1 < len(actions) else None
    if not isinstance(nxt, dict):
        return False
    if nxt.get("press") in ("Enter", {"key": "Enter"}):
        return True
    click = nxt.get("click")
    return isinstance(click, dict) and (click.get("css") is not None or click.get("role") == "button")


ROLE_FIXES = {"input": "textbox", "textarea": "textbox", "text": "textbox", "textfield": "textbox",
              "text field": "textbox", "field": "textbox"}
TARGET_KEYS = ("testid", "role", "name", "text", "label", "placeholder", "css")
UPLOAD_LABEL = re.compile(r"upload|browse|choose file|attach|drop (a )?file", re.I)
# An explicit upload instruction with a path: 'Upload C:/Users/me/claim.pdf ...' / 'upload "/home/me/a.txt"'.
UPLOAD_PATH = re.compile(r"\bupload\b[^\n]{0,40}?[\"'`\[(]?((?:[A-Za-z]:[\\/]|/|\.{1,2}[\\/]|~[\\/])"
                         r"[^\n\"'`\])]*?\.[A-Za-z0-9]{1,6})(?=[\s\"'`\]),;]|$)", re.I)


def _norm_path(p: str) -> str:
    return p.strip().replace("\\", "/").lower()


def _same_target(a: dict, b: dict) -> bool:
    ta = {k: a[k] for k in TARGET_KEYS if a.get(k) is not None}
    tb = {k: b[k] for k in TARGET_KEYS if b.get(k) is not None}
    return bool(ta) and ta == tb


def _direction_click(direction: str) -> dict | None:
    """A silent click for a presenter instruction that was stripped from the narration and left its segment empty
    ('Check the payment status.' -> click the button whose label best matches; the recorder matches labels loosely).
    Typing instructions can't be recovered (the value is unknown), so they give None."""
    if direction.rstrip().endswith(":") or re.search(r"\b(enter|type|write|fill in|send)\b", direction, re.I):
        return None   # typing / sending: the value is unknown, nothing to perform
    quoted = re.search(r"[\"“']([^\"”']{2,60})[\"”']", direction)
    if quoted:
        label = quoted.group(1)
    else:
        label = re.sub(r"^\W*((then|next|now|finally|first|for the final stage)\W+)*", "", direction, flags=re.I)
        label = re.sub(r"^(click|tap|press)\s+(on\s+)?(the\s+)?((button|link|tab)\s+)?", "", label, flags=re.I)
        label = re.sub(r"\s+(button|link|tab)\b", "", label, flags=re.I).strip(" .!:;,")
    if not label or len(label.split()) > 8:
        return None
    return {"click": {"role": "button", "name": label, "nth": "last", "timeout": 120}}


def sanitize(doc: dict, transcript: str = "") -> list[str]:
    """Deterministic clean-up of the model's common slips:
    - stage directions left inside 'say' (they would be spoken) are removed; a segment left with nothing at all gets
      a silent click for the stripped instruction, or is dropped - never left empty
    - word anchors that don't occur in their own segment's narration are dropped (the action still runs in order)
    - HTML tag names used as roles (role: input) become role: textbox
    - a click that only focuses the field the next action types into is removed (fill focuses it)
    - uploads only keep paths the transcript states explicitly; a click on an upload area becomes an upload when the
      transcript gives exactly such a path"""
    fixes = []
    chatting = False   # set once a chat message was sent: from then on repeated buttons mean the newest reply's
    upload_paths = []
    for m in UPLOAD_PATH.finditer(transcript or ""):
        path = m.group(1).strip()
        if Path(os.path.expandvars(path)).expanduser().is_file():
            upload_paths.append(path)
        else:
            fixes.append(f"upload file {path!r} from the transcript is not on this machine - that upload is left out")
    unused_uploads = list(upload_paths)
    kept_segments = []
    for i, seg in enumerate(doc.get("segments") or [], start=1):
        if not isinstance(seg, dict):
            continue
        removed = []
        if isinstance(seg.get("say"), str):
            cleaned, removed = _strip_directions(seg["say"])
            for r in removed:
                fixes.append(f"segment {i}: not spoken (stage direction) {r[:80]!r}")
            if cleaned:
                seg["say"] = cleaned
            else:
                seg.pop("say")
        if not seg.get("say") and not seg.get("actions"):
            clicks = [c for c in (_direction_click(r) for r in removed) if c]
            if clicks:
                seg["actions"] = clicks
                fixes.append(f"segment {i}: only an instruction was left - performing it silently: "
                             + ", ".join(repr(c["click"]["name"]) for c in clicks))
            else:
                fixes.append(f"segment {i}: nothing left to say or do - segment removed")
                continue
        kept_segments.append(seg)
        say = seg.get("say")
        toks = tokens(spoken(say)) if isinstance(say, str) and say.strip() else []
        raw_actions = [a for a in seg.get("actions") or [] if isinstance(a, dict)]
        # A click that only focuses the field typed into next: fill focuses it itself.
        actions = []
        for k, action in enumerate(raw_actions):
            nxt = raw_actions[k + 1] if k + 1 < len(raw_actions) else None
            click, fill = action.get("click"), (nxt or {}).get("fill")
            if isinstance(click, dict) and isinstance(fill, dict) and _same_target(click, fill):
                if click.get("at_word") and not fill.get("at_word"):
                    fill["at_word"] = click["at_word"]
                fixes.append(f"segment {i}: removed the click before typing into the same field")
                continue
            actions.append(action)
        seg["actions"] = actions
        for k, action in enumerate(actions):
            for body in [v for v in action.values() if isinstance(v, dict)]:
                role = body.get("role")
                if isinstance(role, str) and role.lower() in ROLE_FIXES:
                    body["role"] = ROLE_FIXES[role.lower()]
                    fixes.append(f"segment {i}: role {role!r} is not an accessible role - using 'textbox'")
            up = action.get("upload")
            if isinstance(up, dict):
                path = str(up.get("path") or "")
                match = next((p for p in upload_paths if _norm_path(p) == _norm_path(path)), None)
                if match is None:
                    fixes.append(f"segment {i}: removed upload of {path!r} (the transcript gives no such file path)")
                    actions[k] = None
                    continue
                if match in unused_uploads:
                    unused_uploads.remove(match)
            click = action.get("click")
            if isinstance(click, dict) and unused_uploads and UPLOAD_LABEL.search(
                    str(click.get("name") or click.get("text") or "")):
                label = click.get("name") or click.get("text")
                path = unused_uploads.pop(0)
                actions[k] = {"upload": {"text": label, "path": path,
                                         **({"at_word": click["at_word"]} if click.get("at_word") else {})}}
                fixes.append(f"segment {i}: {label!r} is a file upload - attaching {path!r}")
        actions[:] = [a for a in actions if a]
        for action in actions:
            fill = action.get("fill")
            if isinstance(fill, dict):
                for k in [k for k, v in fill.items() if v is None]:
                    fill.pop(k)
                if not any(k in fill for k in ("testid", "role", "text", "label", "placeholder", "css")):
                    fill.update(role="textbox", nth="last")
                    fixes.append(f"segment {i}: typing had no target - using the last text box on the page")
                elif "placeholder" in fill and _is_send(actions, action):
                    old_ph = fill.pop("placeholder")
                    fill.update(role="textbox", nth="last")
                    fixes.append(f"segment {i}: chat box found by placeholder {old_ph!r} (it changes with the app's "
                                 f"state) - using the last text box on the page")
                if _is_send(actions, action):
                    chatting = True
            for kind in ("click", "wait_for", "hover"):
                body = action.get(kind)
                if chatting and isinstance(body, dict) and body.get("role") == "button" and "nth" not in body:
                    body["nth"] = "last"   # chat buttons repeat in every reply: always the newest one
                    fixes.append(f"segment {i}: {kind} {body.get('name')!r} - using the newest one (nth: last)")
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
        if not seg.get("say") and not seg["actions"]:
            kept_segments.pop()
            fixes.append(f"segment {i}: nothing left to say or do - segment removed")
    if "segments" in doc:
        doc["segments"] = kept_segments
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
            for fix in sanitize(doc, transcript):
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
