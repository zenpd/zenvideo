"""
Stage -1: generate_recording.py
================================
Dynamic, URL-agnostic browser recording for dynamic AI/chat applications.

Fixes & Enhancements:
1. Eliminates initial page load offset by waiting for network idle before starting timers.
2. Fixes timing drift by including LLM extraction duration inside segment_start measurement.
3. Native screen resolution auto-detection to eliminate gray margins/letterboxing.
4. Targets the LATEST visible action buttons in live chat streams.
5. Injected Cursor Visual FX (Glide movement, Highlight Rings, Click Ripples).
6. Exports hyperframe event timestamps & initial_load_delay (hyperframes.json) for Stage 3 sync.
"""

import os
import re
import sys
import json
import time
import shutil
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from playwright.sync_api import (
    sync_playwright,
    Page,
    Locator,
    BrowserContext,
    TimeoutError as PlaywrightTimeoutError,
)
from openai import AzureOpenAI

# Cursor Visual Effects import
from cursor_fx import (
    CURSOR_INIT_SCRIPT,
    glide_to,
    highlight_box,
    unhighlight,
    click_ripple,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("browser-recording")


def emit_log(message: str, log_callback=None) -> None:
    logger.info(message)
    if log_callback:
        log_callback(message)


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

WPM = int(os.environ.get("WPM", "150"))
RECORDING_OUTPUT_DIR = os.environ.get("RECORDING_OUTPUT_DIR", "./output")

MIN_SEGMENT_SECONDS = float(os.environ.get("MIN_SEGMENT_SECONDS", "2.5"))
MAX_SEGMENT_SECONDS = float(os.environ.get("MAX_SEGMENT_SECONDS", "40.0"))

WAIT_FOR_ELEMENT_SECONDS = float(os.environ.get("WAIT_FOR_ELEMENT_SECONDS", "25"))
TYPE_DELAY_MS = int(os.environ.get("TYPE_DELAY_MS", "35"))
POST_ACTION_SETTLE_SECONDS = float(os.environ.get("POST_ACTION_SETTLE_SECONDS", "1.0"))
MAX_VISIBLE_ELEMENTS = int(os.environ.get("MAX_VISIBLE_ELEMENTS", "150"))
DISABLE_POPUP_REDIRECT = os.environ.get("DISABLE_POPUP_REDIRECT", "false").lower() == "true"

TIMESTAMP_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$")


def _clean_text(text: str) -> str:
    """Strips emojis, unicode symbols, and extra whitespace from button labels."""
    if not text:
        return ""
    clean = re.sub(r"[^\w\s\-\?\!\.\,\:\'\"]+", " ", text, flags=re.UNICODE)
    return " ".join(clean.split()).strip()


# --------------------------------------------------------------------------
# Transcript parsing
# --------------------------------------------------------------------------

def _parse_timestamp_to_seconds(line: str) -> Optional[float]:
    m = TIMESTAMP_RE.match(line)
    if not m:
        return None
    a, b, c = m.groups()
    if c is not None:
        h, mnt, s = int(a), int(b), int(c)
        return h * 3600 + mnt * 60 + s
    return int(a) * 60 + int(b)


def parse_segments(transcript_path: str) -> List[Dict[str, Any]]:
    text = Path(transcript_path).read_text(encoding="utf-8")
    raw_segments = [s.strip() for s in text.split("---")]
    raw_segments = [s for s in raw_segments if s]
    if not raw_segments:
        raise ValueError(f"No segments found in {transcript_path}")

    segments = []
    for raw in raw_segments:
        lines = raw.splitlines()
        timestamp = None
        if lines and _parse_timestamp_to_seconds(lines[0]) is not None:
            timestamp = _parse_timestamp_to_seconds(lines[0])
            body = "\n".join(lines[1:]).strip()
        else:
            body = raw
        if body:
            segments.append({"timestamp": timestamp, "text": body})

    logger.info(f"Parsed {len(segments)} segments from {transcript_path}")
    return segments


def compute_segment_durations(segments: List[Dict[str, Any]]) -> List[float]:
    durations = []
    for i, seg in enumerate(segments):
        ts = seg["timestamp"]
        next_ts = segments[i + 1]["timestamp"] if i + 1 < len(segments) else None
        if ts is not None and next_ts is not None and next_ts > ts:
            durations.append(max(MIN_SEGMENT_SECONDS, min(MAX_SEGMENT_SECONDS, next_ts - ts)))
        else:
            word_count = max(1, len(seg["text"].split()))
            est = (word_count / WPM) * 60.0
            durations.append(max(MIN_SEGMENT_SECONDS, min(MAX_SEGMENT_SECONDS, est)))
    return durations


# --------------------------------------------------------------------------
# Live page scan
# --------------------------------------------------------------------------

_SCAN_JS = """
() => {
    const selector = [
        'a[href]', 'button', 'input', 'textarea', 'select',
        '[role="button"]', '[role="link"]', '[role="tab"]',
        '[role="checkbox"]', '[onclick]', '[contenteditable="true"]',
        'button *', '[role="button"] *'
    ].join(',');

    const els = Array.from(document.querySelectorAll(selector));
    const seen = new Set();
    const results = [];

    function cleanLabel(raw) {
        if (!raw) return '';
        return raw.replace(/[^\\p{L}\\p{N}\\s\\-_\\+]/gu, ' ').replace(/\\s+/g, ' ').trim();
    }

    for (const el of els) {
        const rect = el.getBoundingClientRect();
        const visible = rect.width > 0 && rect.height > 0 &&
            getComputedStyle(el).visibility !== 'hidden' &&
            getComputedStyle(el).display !== 'none';
        if (!visible) continue;

        const rawText = (el.innerText || el.value || el.getAttribute('aria-label') ||
                         el.getAttribute('title') || el.getAttribute('placeholder') || '').trim();
        
        let text = cleanLabel(rawText).slice(0, 80);
        if (!text && (rawText === '+' || el.textContent.trim() === '+')) {
            text = '+';
        }
        if (!text) continue;

        const role = el.getAttribute('role') || el.tagName.toLowerCase();
        const key = role + '|' + text;
        if (seen.has(key)) continue;
        seen.add(key);

        results.push({ role, text });
    }
    return results;
}
"""


def scan_visible_elements(page: Page, limit: int = MAX_VISIBLE_ELEMENTS) -> List[Dict[str, str]]:
    try:
        elements = page.evaluate(_SCAN_JS)
    except Exception as e:
        logger.warning(f"Element scan failed: {e}")
        return []
    return elements[:limit]


# --------------------------------------------------------------------------
# Step extraction via Azure OpenAI
# --------------------------------------------------------------------------

STEP_EXTRACTION_SYSTEM_PROMPT = """You convert a piece of video-narration/script text into an ordered list of
literal browser UI steps, grounded on the REAL elements currently visible on the page.

You are given:
1. "narration": the text to convert.
2. "visible_elements": a JSON list of {"role": "...", "text": "..."} for interactive elements visible on page.

Return ONLY JSON of the form:
{"steps": [ {...}, {...} ]}

Each step is one of:
  {"type": "click", "label": "<copied VERBATIM from visible_elements[].text or clean action name>", "intent": "<short phrase>"}
  {"type": "type", "value": "<exact text to type>", "intent": "<short phrase>"}
  {"type": "press_enter", "intent": "<short phrase>"}
  {"type": "scroll", "direction": "down" | "up", "intent": "<short phrase>"}

Rules:
- Express UI actions described in the narration as steps.
- For click labels, keep plain button text (e.g. "Approve", "Reject", "Create the PO", "Onboard supplier", "+").
- Output strictly valid JSON. No markdown fences.
"""

REPAIR_SYSTEM_PROMPT = """A browser-automation step could not be completed because its target label was
not found on the page. Given the ORIGINAL INTENT of that step and the REAL elements
currently visible on the page, pick the single best matching element text.

Return ONLY JSON: {"label": "<copied verbatim from visible_elements[].text>"} or
{"label": null} if nothing matches.
"""


class StepExtractor:
    def __init__(self):
        if not (AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT):
            raise RuntimeError("Missing Azure OpenAI config in environment variables.")
        self.client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )

    def extract(self, segment_text: str, visible_elements: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        try:
            response = self.client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                response_format={"type": "json_object"},
                temperature=0,
                messages=[
                    {"role": "system", "content": STEP_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({
                        "narration": segment_text,
                        "visible_elements": visible_elements,
                    })},
                ],
            )
            parsed = json.loads(response.choices[0].message.content)
            steps = parsed.get("steps", [])
            return steps if isinstance(steps, list) else []
        except Exception as e:
            logger.warning(f"Step extraction failed: {e}")
            return []

    def repair_label(self, intent: str, visible_elements: List[Dict[str, str]]) -> Optional[str]:
        try:
            response = self.client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                response_format={"type": "json_object"},
                temperature=0,
                messages=[
                    {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({
                        "original_intent": intent,
                        "visible_elements": visible_elements,
                    })},
                ],
            )
            parsed = json.loads(response.choices[0].message.content)
            return parsed.get("label")
        except Exception as e:
            logger.warning(f"Repair lookup failed: {e}")
            return None


# --------------------------------------------------------------------------
# Locators (Targets the LATEST visible element)
# --------------------------------------------------------------------------

def _candidate_locators_priority(page: Page, label: str) -> List[Locator]:
    clean_label = _clean_text(label)
    if not clean_label:
        clean_label = label

    pattern = re.compile(re.escape(clean_label), re.IGNORECASE)

    return [
        page.get_by_role("button", name=pattern),
        page.get_by_role("link", name=pattern),
        page.get_by_role("tab", name=pattern),
        page.locator(f'button:has-text("{clean_label}")'),
        page.locator(f'[role="button"]:has-text("{clean_label}")'),
        page.get_by_text(pattern),
        page.locator(f':has-text("{clean_label}")'),
    ]


def wait_for_clickable(page: Page, label: str, timeout_seconds: float) -> Optional[Locator]:
    """Polls DOM and picks the LAST rendered visible + enabled element."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for loc in _candidate_locators_priority(page, label):
            try:
                count = loc.count()
                if count == 0:
                    continue
                for i in reversed(range(count)):
                    candidate = loc.nth(i)
                    if candidate.is_visible() and candidate.is_enabled():
                        return candidate
            except Exception:
                continue
        time.sleep(0.3)
    return None


def find_text_input(page: Page) -> Optional[Locator]:
    candidates = [
        page.locator("textarea:visible"),
        page.locator('[contenteditable="true"]:visible'),
        page.locator('input[type="text"]:visible'),
        page.locator('input[placeholder*="talk" i]:visible'),
        page.locator('input[placeholder*="message" i]:visible'),
        page.locator('input[placeholder*="chat" i]:visible'),
        page.locator('input:not([type="hidden"]):visible'),
    ]
    for loc in candidates:
        try:
            count = loc.count()
            if count > 0:
                for i in reversed(range(count)):
                    cand = loc.nth(i)
                    if cand.is_visible() and cand.is_enabled():
                        return cand
        except Exception:
            continue
    return None


def execute_step(page: Page, step: Dict[str, Any], extractor: StepExtractor) -> bool:
    kind = step.get("type")
    try:
        if kind == "click":
            label = step.get("label", "")
            intent = step.get("intent", label)
            cleaned_label = _clean_text(label)
            logger.info(f'  -> click "{cleaned_label}" (waiting up to {WAIT_FOR_ELEMENT_SECONDS:.0f}s)')
            
            target = wait_for_clickable(page, cleaned_label, WAIT_FOR_ELEMENT_SECONDS)

            if target is None:
                logger.warning(f'  target "{cleaned_label}" not found - attempting repair via live re-scan')
                fresh_elements = scan_visible_elements(page)
                new_label = extractor.repair_label(intent, fresh_elements)
                if new_label:
                    logger.info(f'  repair suggested "{new_label}" for intent "{intent}"')
                    target = wait_for_clickable(page, _clean_text(new_label), WAIT_FOR_ELEMENT_SECONDS / 2)

            if target is None:
                logger.warning(f'  [FAILED] could not find clickable element for "{label}" (intent: {intent})')
                return False

            target.scroll_into_view_if_needed(timeout=5000)

            # --- Visual Cursor FX ---
            box = target.bounding_box()
            x, y = None, None
            if box:
                x, y = glide_to(page, box)
                highlight_box(page, box)

            target.click(force=True, timeout=5000)

            if box and x is not None and y is not None:
                click_ripple(page, x, y)
                unhighlight(page)
            # ------------------------

            time.sleep(1.0)
            return True

        elif kind == "type":
            value = step.get("value", "")
            logger.info(f'  -> type "{value[:60]}{"..." if len(value) > 60 else ""}"')
            
            deadline = time.time() + WAIT_FOR_ELEMENT_SECONDS
            target = None
            while time.time() < deadline:
                target = find_text_input(page)
                if target is not None:
                    break
                time.sleep(0.3)

            if target is None:
                logger.warning("  [FAILED] could not find a text input to type into")
                return False

            target.scroll_into_view_if_needed(timeout=5000)

            # --- Visual Cursor FX ---
            box = target.bounding_box()
            if box:
                glide_to(page, box)

            target.click(force=True, timeout=5000)
            
            try:
                target.focus()
            except Exception:
                pass

            try:
                target.fill("")
            except Exception:
                pass
            
            try:
                target.press_sequentially(value, delay=TYPE_DELAY_MS)
            except AttributeError:
                target.type(value, delay=TYPE_DELAY_MS)
            return True

        elif kind == "press_enter":
            logger.info("  -> press Enter")
            page.keyboard.press("Enter")
            time.sleep(0.5)
            return True

        elif kind == "scroll":
            direction = step.get("direction", "down")
            amount = 500 if direction == "down" else -500
            logger.info(f"  -> scroll {direction}")
            page.mouse.wheel(0, amount)
            return True

        else:
            logger.warning(f"  [skip] unknown step type: {kind}")
            return False

    except PlaywrightTimeoutError as e:
        logger.warning(f"  [FAILED] step '{kind}' timed out: {e}")
        return False
    except Exception as e:
        logger.warning(f"  [FAILED] step '{kind}' raised: {e}")
        return False


# --------------------------------------------------------------------------
# Same-tab enforcement
# --------------------------------------------------------------------------

FORCE_SAME_TAB_INIT_SCRIPT = """
(function () {
    function neutralize(root) {
        try {
            root.querySelectorAll('a[target]').forEach((a) => a.removeAttribute('target'));
            root.querySelectorAll('form[target]').forEach((f) => f.removeAttribute('target'));
        } catch (e) {}
    }
    window.open = function (url) {
        if (url) window.location.href = url;
        return window;
    };
    document.addEventListener('DOMContentLoaded', () => neutralize(document));
    neutralize(document);
    try {
        new MutationObserver(() => neutralize(document)).observe(document.documentElement, {
            childList: true, subtree: true
        });
    } catch (e) {}
})();
"""


def make_popup_handler(page: Page, log=None):
    def _on_popup(popup_page):
        try:
            popup_url = popup_page.url
            emit_log(f"[popup event] new tab opened -> {popup_url}", log)

            if DISABLE_POPUP_REDIRECT:
                return

            if not popup_url or popup_url in ("about:blank",) or popup_url.startswith("chrome-error"):
                popup_page.close()
                return

            if popup_url == page.url:
                popup_page.close()
                return

            popup_page.close()
            page.goto(popup_url, wait_until="domcontentloaded", timeout=15000)

        except Exception as e:
            logger.warning(f"Failed to handle popup: {e}")

    return _on_popup


# --------------------------------------------------------------------------
# Main driver
# --------------------------------------------------------------------------

def generate_recording(
    url: str,
    transcript_path: str,
    output_path: str,
    log=None,
) -> Path:
    output_path = Path(output_path)
    output_dir_path = output_path.parent
    output_dir_path.mkdir(parents=True, exist_ok=True)

    segments = parse_segments(transcript_path)
    durations = compute_segment_durations(segments)
    extractor = StepExtractor()

    total_attempted = 0
    total_succeeded = 0
    failures: List[str] = []
    hyperframe_events = []

    emit_log(f"Starting browser recording for: {url}", log)
    emit_log(f"Transcript: {transcript_path}", log)
    emit_log(f"Output: {output_path}", log)

    with sync_playwright() as pw:
        emit_log("Launching Chromium (Native Screen Fit + Visual FX)...", log)

        browser = pw.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        # Detect native display size to prevent borders or scaling distortion
        temp_context = browser.new_context()
        temp_page = temp_context.new_page()
        screen_size = temp_page.evaluate("""() => ({
            width: window.screen.availWidth || 1366,
            height: window.screen.availHeight || 768
        })""")
        temp_context.close()

        sw, sh = screen_size["width"], screen_size["height"]
        emit_log(f"Detected screen resolution: {sw}x{sh}", log)

        context: BrowserContext = browser.new_context(
            record_video_dir=str(output_dir_path),
            record_video_size={"width": sw, "height": sh},
            viewport={"width": sw, "height": sh},
            device_scale_factor=1,
        )
        
        # Inject same-tab enforcement AND cursor FX scripts
        context.add_init_script(FORCE_SAME_TAB_INIT_SCRIPT)
        context.add_init_script(CURSOR_INIT_SCRIPT)

        # Video recording begins the exact instant context.new_page() is called
        video_init_time = time.time()
        page = context.new_page()
        context.on("page", lambda p: make_popup_handler(page, log)(p) if p != page else None)

        emit_log(f"Navigating to {url}", log)
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Pause to settle DOM rendering before starting action timers
        time.sleep(1.0)
        
        # Mark the exact timestamp when the page is rendered and actions begin
        recording_start_time = time.time()
        initial_load_delay = round(recording_start_time - video_init_time, 2)
        emit_log(f"Dynamic page load delay: {initial_load_delay}s", log)

        for i, (segment, target_duration) in enumerate(zip(segments, durations), start=1):
            segment_text = segment["text"]
            emit_log(
                f"Segment {i}/{len(segments)} (target {target_duration:.1f}s): {segment_text[:70]!r}",
                log,
            )

            # Measure segment time INCLUDING the LLM extraction duration
            segment_start = time.time()

            visible_elements = scan_visible_elements(page)
            steps = extractor.extract(segment_text, visible_elements)
            emit_log(f"  Extracted {len(steps)} browser action(s).", log)

            for step in steps:
                total_attempted += 1
                ok = execute_step(page, step, extractor)

                if ok:
                    total_succeeded += 1
                    emit_log(f"  Action completed: {step.get('type')}", log)
                    time.sleep(POST_ACTION_SETTLE_SECONDS)
                else:
                    failures.append(f"segment {i}: {step}")
                    emit_log(f"  Action failed: {step}", log)

            elapsed = time.time() - segment_start
            remaining = target_duration - elapsed
            if remaining > 0:
                time.sleep(remaining)

            # Record Hyperframe timing event relative to recording_start_time
            hyperframe_events.append({
                "segment_index": i,
                "target_duration": target_duration,
                "video_timestamp": round(time.time() - recording_start_time, 2)
            })

        emit_log(
            f"Summary: {total_succeeded}/{total_attempted} step(s) succeeded across {len(segments)} segment(s)",
            log,
        )
        if failures:
            emit_log(f"{len(failures)} action(s) could not be completed:", log)
            for f in failures:
                emit_log(f"  - {f}", log)

        video_handle = page.video
        context.close()
        browser.close()

        recorded_path = Path(video_handle.path()) if video_handle else None

    # Write Hyperframe metadata JSON including the dynamic initial load delay
    hyperframe_data = {
        "initial_load_delay": initial_load_delay,
        "events": hyperframe_events
    }

    hyperframe_json_path = output_dir_path / "hyperframes.json"
    with open(hyperframe_json_path, "w", encoding="utf-8") as f:
        json.dump(hyperframe_data, f, indent=2)

    if not recorded_path or not recorded_path.exists():
        raise RuntimeError("Playwright did not produce a video file as expected.")

    if output_path.exists():
        output_path.unlink()
    shutil.move(str(recorded_path), str(output_path))

    emit_log(f"Done. Recording saved to: {output_path}", log)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Stage -1: generate recordings.webm from URL + transcript")
    parser.add_argument("--url", required=True, help="Website URL to open and interact with")
    parser.add_argument("--transcript", required=True, help="Path to raw_transcript.txt")
    parser.add_argument("--output-dir", default=RECORDING_OUTPUT_DIR, help="Directory to write recordings.webm into")
    args = parser.parse_args()

    generate_recording(
        url=args.url,
        transcript_path=args.transcript,
        output_path=str(Path(args.output_dir) / "recordings.webm"),
    )


if __name__ == "__main__":
    main()