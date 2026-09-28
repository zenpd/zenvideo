"""
Stage 2: record. Two capture modes, both constant frame rate:
  background (default) - a hidden headless Chromium whose own screencast frames are captured; the screen stays free.
  screen               - headed Chromium in kiosk mode, the whole monitor captured by ffmpeg ddagrab.

Audio drives the timeline: each segment runs its actions, then holds until its narration (+gap) is over.
All times are taken with time.perf_counter() while recording, then converted to raw.mp4 time using two small
sync markers (a 32 px square in the bottom-right corner, before the first and after the last segment - both are
outside the final cut) that are found frame-exactly in the capture.
"""

import json
import os
import re
import shutil
import tempfile
import time
import winsound
from pathlib import Path

import numpy as np
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, sync_playwright

from cursor_fx import CURSOR_INIT_SCRIPT
from demo import media, winfocus
from demo.capture import BrowserCapture, CaptureError, ScreenCapture
from demo.script import Action, Demo, Segment, Target
from demo.text import find_phrase

MARKER_CSS_PX = 32
MARKER_ON = f"""async () => {{
    const d = document.createElement('div');
    d.id = '__demo_marker';
    d.style.cssText = 'position:fixed;right:0;bottom:0;width:{MARKER_CSS_PX}px;height:{MARKER_CSS_PX}px;' +
                      'background:#ff00ff;z-index:2147483647;pointer-events:none';
    document.documentElement.appendChild(d);
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
}}"""
MARKER_OFF = """async () => {
    document.getElementById('__demo_marker')?.remove();
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
}"""
MARKER_SECONDS = 0.3
SCROLL_PX_PER_S = 240          # default pace of a plain scroll
SCROLL_MIN_PX_PER_S = 160      # word-anchored scrolls never crawl slower than this, however long the span
# Narration that outlasts a segment's actions tours the page instead of showing a frozen screen.
TOUR_MIN_S = 4.0               # only when at least this much narration is left
TOUR_PX_PER_S = (15, 240)      # slowest (a gentle drift on short pages) / fastest tour pace
TOUR_MIN_PX = 150              # less room than this to scroll: stay still
# Play each narration clip on the speakers during the take (a preview only; the video's audio comes from the WAVs).
# Off by default so recording is silent; set DEMO_MONITOR_AUDIO=1 to hear it.
MONITOR_AUDIO = os.environ.get("DEMO_MONITOR_AUDIO", "0") == "1"

# Eased (smoothstep) scroll of the nearest scrollable ancestor of the point, driven by requestAnimationFrame.
SCROLLER_JS = """(x, y) => {
    for (let e = document.elementFromPoint(x, y); e && e !== document.body; e = e.parentElement) {
      const oy = getComputedStyle(e).overflowY;
      if (/(auto|scroll|overlay)/.test(oy) && e.scrollHeight > e.clientHeight + 1) return e;
    }
    return document.scrollingElement || document.documentElement;
  }"""
SCROLL_ROOM = """([x, y]) => {
  const box = (""" + SCROLLER_JS + """)(x, y);
  return {up: box.scrollTop, down: box.scrollHeight - box.clientHeight - box.scrollTop};
}"""
SMOOTH_SCROLL = """async ([dy, ms, x, y]) => {
  const box = (""" + SCROLLER_JS + """)(x, y);
  const from = box.scrollTop;
  const to = Math.max(0, Math.min(box.scrollHeight - box.clientHeight, from + dy));
  const behavior = box.style.scrollBehavior;
  box.style.scrollBehavior = 'auto';
  const t0 = performance.now();
  await new Promise((done) => {
    const step = (t) => {
      const p = Math.min(1, (t - t0) / Math.max(ms, 1));
      box.scrollTop = from + (to - from) * p * p * (3 - 2 * p);
      if (p < 1) requestAnimationFrame(step); else done();
    };
    requestAnimationFrame(step);
  });
  box.style.scrollBehavior = behavior;
  return to - from;
}"""

# The synthetic cursor is hidden except around pointer actions (click / type / hover).
CURSOR_VISIBILITY_CSS = "#__vcursor{opacity:0;transition:opacity .2s ease}#__vcursor.__vshow{opacity:1}"
CURSOR_SHOW = "() => document.getElementById('__vcursor')?.classList.add('__vshow')"
CURSOR_HIDE_LATER = """(ms) => {
    clearTimeout(window.__vhideTimer);
    window.__vhideTimer = setTimeout(() => document.getElementById('__vcursor')?.classList.remove('__vshow'), ms);
}"""
CURSOR_LINGER_MS = 700

KIOSK_ARGS = [
    "--kiosk",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-session-crashed-bubble",
    "--disable-features=Translate,MediaRouter,DownloadBubble",
    "--deny-permission-prompts",
    "--disable-smooth-scrolling",
]


def background_args(viewport: tuple[int, int], dpr: float) -> list[str]:
    """Headless window at the recording viewport, rendered at the real device scale (the screencast then delivers
    full-resolution frames; Playwright's emulated scale factor would give CSS-pixel-sized ones)."""
    return [
        f"--window-size={viewport[0]},{viewport[1]}",
        f"--force-device-scale-factor={dpr}",
        "--hide-scrollbars",
        "--no-first-run",
        "--disable-features=Translate,MediaRouter,DownloadBubble",
        "--deny-permission-prompts",
        "--disable-smooth-scrolling",
    ]


_NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                 "eleven", "twelve"]


def loose_text(text: str) -> re.Pattern:
    """Pattern for visible text that the narration only paraphrases: case-insensitive, hyphens/spaces/punctuation
    interchangeable, number words and digits equal ('three-way match' finds '3-way match' and 'Three way match')."""
    parts = []
    for w in re.findall(r"[A-Za-z0-9]+", text):
        lw = w.lower()
        if lw in _NUMBER_WORDS:
            parts.append(f"(?:{lw}|{_NUMBER_WORDS.index(lw)})")
        elif lw.isdigit() and int(lw) < len(_NUMBER_WORDS):
            parts.append(f"(?:{lw}|{_NUMBER_WORDS[int(lw)]})")
        else:
            parts.append(re.escape(lw))
    return re.compile(r"[\W_]*".join(parts) or re.escape(text), re.IGNORECASE)


# A text wait that can't find its words gives up once the page has been this still (after at least SOFT_WAIT_MIN_S).
SOFT_WAIT_MIN_S = 15.0
SOFT_WAIT_QUIET_S = 6.0
MUTATION_WATCH = """() => {
  window.__zvLastMut = performance.now();
  if (!window.__zvMut) {
    window.__zvMut = new MutationObserver(() => { window.__zvLastMut = performance.now(); });
    window.__zvMut.observe(document.body, {subtree: true, childList: true, characterData: true, attributes: true});
  }
}"""


# Chat UIs keep every old reply on screen, so "the last Approve button" can be a stale one from an earlier step.
# Just before each click / key press every element on the page is stamped "old", and a clicked element is stamped
# "used". A chat-style target (nth: last) then only matches elements that appeared after the previous click and were
# never clicked; if none turns up and the page has settled, an old-but-unused one is accepted.
STAMP_OLD = "() => { for (const e of document.querySelectorAll('body *')) e.setAttribute('data-zv-old', ''); }"
MARK_USED = "(e) => e.setAttribute('data-zv-used', '')"
FRESH_KINDS = {"click", "hover", "wait_for"}
FRESH_FALLBACK_S = (10.0, 6.0)     # accept an older element after this long a wait, once the page is this quiet


class ActionError(RuntimeError):
    pass


class FocusLost(RuntimeError):
    pass


def now() -> float:
    return time.perf_counter()


def _hide_script(selectors: list[str], hide_scrollbars: bool) -> str:
    css = CURSOR_VISIBILITY_CSS
    if selectors:
        css += ",".join(selectors) + "{display:none!important}"
    if hide_scrollbars:
        css += "::-webkit-scrollbar{display:none!important}*{scrollbar-width:none!important}"
    return f"""(() => {{
        const add = () => {{
            if (document.getElementById('__demo_hide')) return;
            const s = document.createElement('style');
            s.id = '__demo_hide';
            s.textContent = {json.dumps(css)};
            (document.head || document.documentElement).appendChild(s);
        }};
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
        document.documentElement.spellcheck = false;
        document.addEventListener('focusin', e => {{ if (e.target) e.target.spellcheck = false; }}, true);
    }})();"""


class Recorder:
    def __init__(self, page: Page, demo: Demo, dpr: float, log=print):
        self.page = page
        self.log = log
        self.pacing = demo.pacing
        self.dpr = dpr
        self.events: list[dict] = []
        vw, vh = page.evaluate("() => [innerWidth, innerHeight]")
        self.mouse = (vw / 2, vh / 2)
        self.segment: Segment | None = None

    # -- timing -----------------------------------------------------------
    def wait_until(self, target: float) -> None:
        while True:
            remaining = target - now()
            if remaining <= 0:
                return
            self.page.wait_for_timeout(max(1.0, min(remaining, 0.25) * 1000))

    def event(self, kind: str, t: float, **fields) -> None:
        e = {"t": t, "type": kind, "segment": self.segment.index if self.segment else None}
        for k in ("x", "y", "width", "height", "x0", "y0"):
            if k in fields and fields[k] is not None:
                fields[k] = round(fields[k] * self.dpr, 1)
        if isinstance(fields.get("zoom"), (list, tuple)):
            fields["zoom"] = [round(v * self.dpr, 1) for v in fields["zoom"]]
        e.update(fields)
        self.events.append(e)

    def marker(self) -> tuple[float, float]:
        t_on = now()
        self.page.evaluate(MARKER_ON)
        self.page.wait_for_timeout(MARKER_SECONDS * 1000)
        t_off = now()
        self.page.evaluate(MARKER_OFF)
        return t_on, t_off

    # -- focus ------------------------------------------------------------
    watch_focus = False
    hwnd: int | None = None

    def has_focus(self) -> bool:
        if self.hwnd:
            return winfocus.foreground() == self.hwnd
        return self.page.evaluate("() => document.hasFocus()")

    def check_focus(self) -> None:
        if self.watch_focus and not self.has_focus():
            where = f"segment {self.segment.index} ({self.segment.id})" if self.segment else "setup"
            raise FocusLost(f"the recording window lost focus during {where} (another window was brought to the "
                            f"front, so it would have been captured instead). Leave the screen alone and re-run.")

    def hold_until(self, target: float) -> None:
        while now() < target:
            self.check_focus()
            self.wait_until(min(target, now() + 0.5))

    # -- locating ---------------------------------------------------------
    def _base(self, t: Target, fresh: bool = False) -> Locator:
        loc = self._base_any(t)
        if t.nth == "last":
            loc = loc.and_(self.page.locator(":not([data-zv-used])" + (":not([data-zv-old])" if fresh else "")))
        return loc

    def _base_any(self, t: Target) -> Locator:
        p = self.page
        if t.testid is not None:
            loc = p.get_by_test_id(t.testid)
        elif t.role is not None:
            loc = p.get_by_role(t.role, name=t.name, exact=t.exact) if t.name else p.get_by_role(t.role)
        elif t.text is not None:
            loc = p.get_by_text(t.text if t.exact else loose_text(t.text))
        elif t.label is not None:
            loc = p.get_by_label(t.label, exact=t.exact)
        elif t.placeholder is not None:
            loc = p.get_by_placeholder(t.placeholder, exact=t.exact)
        else:
            loc = p.locator(t.css)
        return loc.filter(visible=True)

    def _closest_label(self, t: Target) -> str | None:
        """Best visible label of the same role for a name that doesn't match exactly (e.g. 'Receive the goods' vs
        'Receive goods'): every meaningful word of the shorter label must appear in the longer one."""
        if not (t.role and t.name):
            return None
        try:
            names = self.page.get_by_role(t.role).filter(visible=True).evaluate_all(
                "els => els.map(e => (e.innerText || e.getAttribute('aria-label') || e.title || '').trim())")
        except PlaywrightError:
            return None
        stop = {"the", "a", "an", "on", "to", "button", "link", "of"}
        want = {w for w in re.findall(r"[a-z0-9]+", t.name.lower()) if w not in stop}
        best, best_score = None, 0.0
        for name in set(filter(None, names)):
            have = {w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in stop}
            if not want or not have:
                continue
            small, big = (want, have) if len(want) <= len(have) else (have, want)
            if small <= big:
                score = len(small) / len(big)
                if score > best_score:
                    best, best_score = name, score
        return best if best_score >= 0.5 else None

    kind: str | None = None   # kind of the action being run (set by run())

    def _settled(self, since: float) -> bool:
        """Waited at least FRESH_FALLBACK_S[0] since `since` and the page has not changed for FRESH_FALLBACK_S[1]."""
        waited, quiet = FRESH_FALLBACK_S
        if now() - since < waited:
            return False
        return self.page.evaluate("() => (performance.now() - window.__zvLastMut) / 1000") > quiet

    def locate(self, t: Target, timeout: float, need_enabled: bool, where: str) -> Locator:
        fresh = t.nth == "last" and self.kind in FRESH_KINDS
        if fresh:
            self.page.evaluate(MUTATION_WATCH)
        loc = self._base(t, fresh)
        t_start = now()
        deadline = now() + timeout
        fuzzy_after = now() + min(4.0, timeout / 2)
        warned = False
        while True:
            n = loc.count()
            if n >= 1:
                nth = t.nth
                if n > 1 and nth is None:
                    nth = "last"
                    if not warned:
                        self.log(f"      WARNING: {where}: {t.describe()} matches {n} elements - using the last one")
                        warned = True
                idx = {"first": 0, "last": n - 1}.get(nth, nth if isinstance(nth, int) else 0)
                idx = n + idx if idx < 0 else idx
                if idx < n:
                    el = loc.nth(idx)
                    if not need_enabled or el.is_enabled():
                        return el
            elif fuzzy_after and now() > fuzzy_after:
                fuzzy_after = None
                label = self._closest_label(t)
                if label:
                    self.log(f"      {where}: no exact '{t.name}' - using the closest label '{label}'")
                    t = Target(role=t.role, name=label, exact=True, nth=t.nth)
                    loc = self._base(t, fresh)
                    continue
                fuzzy_after = now() + 2.0
            if fresh and n == 0 and self._settled(t_start) and self._base(t).count():
                fresh = False
                self.log(f"      {where}: no new {t.describe()} appeared - using the latest one already on screen")
                loc = self._base(t)
                continue
            if now() > deadline:
                state = "visible and enabled" if need_enabled else "visible"
                raise ActionError(f"{where}: no {state} element for {t.describe()} within {timeout:.0f}s")
            self.page.wait_for_timeout(150)

    def _box(self, el: Locator, where: str) -> dict:
        el.scroll_into_view_if_needed(timeout=5000)
        box = el.bounding_box()
        if not box:
            raise ActionError(f"{where}: element has no bounding box (detached or zero-size)")
        return box

    # -- cursor -----------------------------------------------------------
    def glide(self, x: float, y: float) -> None:
        x0, y0 = self.mouse
        if abs(x - x0) + abs(y - y0) < 2:
            return
        ms = self.pacing["cursor_ms"]
        t0 = now()
        self.page.evaluate("([x, y, d]) => window.__vcursor && window.__vcursor.moveTo(x, y, d)", [x, y, ms])
        steps = max(6, int(ms / 16))
        for k in range(1, steps + 1):
            p = k / steps
            ease = 1 - (1 - p) ** 3
            self.page.mouse.move(x0 + (x - x0) * ease, y0 + (y - y0) * ease)
            self.wait_until(t0 + ms / 1000 * p)
        self.mouse = (x, y)
        self.event("move", t0, t_end=now(), x0=x0, y0=y0, x=x, y=y)

    def glide_to_box(self, box: dict) -> tuple[float, float]:
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.glide(x, y)
        return x, y

    # -- actions ----------------------------------------------------------
    def lead_time(self, a: Action) -> float:
        """How long before its word an anchored action must start, so the visible moment lands on the word."""
        cursor = self.pacing["cursor_ms"] / 1000
        if a.kind == "click":
            return cursor + self.pacing["highlight_ms"] / 1000
        if a.kind in ("hover", "fill"):
            return cursor
        return 0.0

    def run(self, a: Action) -> None:
        timeout = float(a.params.get("timeout", self.pacing["action_timeout"]))
        where = f"{a.where} [{a.kind}]"
        self.check_focus()
        self.kind = a.kind
        try:
            getattr(self, f"_do_{a.kind}")(a, timeout, where)
        except ActionError:
            raise
        except PlaywrightError as e:
            raise ActionError(f"{where}: {a.describe()} failed: {str(e).splitlines()[0]}") from e

    def _target_fields(self, a: Action, box: dict) -> dict:
        t = a.target
        return {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"],
                "testid": t.testid, "role": t.role, "name": t.name or t.text or t.label or t.placeholder,
                "zoom": a.params.get("zoom", True), "action": a.where}

    def cursor_show(self) -> None:
        self.page.evaluate(CURSOR_SHOW)

    def cursor_hide_later(self) -> None:
        self.page.evaluate(CURSOR_HIDE_LATER, CURSOR_LINGER_MS)

    def _do_click(self, a: Action, timeout: float, where: str) -> None:
        el = self.locate(a.target, timeout, need_enabled=True, where=where)
        box = self._box(el, where)
        self.cursor_show()
        x, y = self.glide_to_box(box)
        self.page.evaluate("([x, y, w, h]) => window.__vcursor && window.__vcursor.highlight(x, y, w, h)",
                           [box["x"], box["y"], box["width"], box["height"]])
        self.page.wait_for_timeout(self.pacing["highlight_ms"])
        handle = el.element_handle(timeout=5000)   # pinned: the stamps below make `el` stop matching itself
        handle.evaluate(MARK_USED)
        self.page.evaluate(STAMP_OLD)
        t = now()
        handle.click(timeout=5000)
        self.page.evaluate("([x, y]) => { window.__vcursor && (window.__vcursor.ripple(x, y), window.__vcursor.unhighlight()) }",
                           [x, y])
        self.cursor_hide_later()
        self.event("click", t, **self._target_fields(a, box))

    def _do_fill(self, a: Action, timeout: float, where: str) -> None:
        el = self.locate(a.target, timeout, need_enabled=True, where=where)
        box = self._box(el, where)
        self.cursor_show()
        x, y = self.glide_to_box(box)
        t = now()
        el.click(timeout=5000)
        self.page.evaluate("([x, y]) => window.__vcursor && window.__vcursor.ripple(x, y)", [x, y])
        self.cursor_hide_later()
        value = str(a.params["value"])
        el.fill("")
        if a.params.get("instant"):
            el.fill(value)
        else:
            el.press_sequentially(value, delay=self.pacing["typing_ms"])
        self.event("type", t, t_end=now(), chars=len(value), **self._target_fields(a, box))

    def _do_hover(self, a: Action, timeout: float, where: str) -> None:
        el = self.locate(a.target, timeout, need_enabled=False, where=where)
        box = self._box(el, where)
        self.cursor_show()
        self.glide_to_box(box)
        t = now()
        el.hover(timeout=5000)
        self.cursor_hide_later()
        self.event("hover", t, **self._target_fields(a, box))

    def _do_scroll(self, a: Action, timeout: float, where: str) -> None:
        """Eased, constant-pace wheel scroll (Chrome's own smooth scrolling is off, so this is the motion)."""
        if a.target:
            el = self.locate(a.target, timeout, need_enabled=False, where=where)
            box = self._box(el, where)
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        else:
            x, y = self.page.evaluate("() => [innerWidth / 2, innerHeight / 2]")
        dy = float(a.params["by"])
        duration = max(float(a.params.get("duration", 0)), abs(dy) / SCROLL_PX_PER_S, self.duration_override or 0)
        self._wheel(dy, duration, x, y)

    def _do_scroll_to(self, a: Action, timeout: float, where: str) -> None:
        """Scroll the page until the target sits at the top/centre of the view, timed to the narration."""
        el = self.locate(a.target, timeout, need_enabled=False, where=where)
        box = el.bounding_box()
        if not box:
            raise ActionError(f"{where}: element has no bounding box")
        vw, vh = self.page.evaluate("() => [innerWidth, innerHeight]")
        if a.params.get("align", "center") == "top":
            dy = box["y"] - vh * 0.14
        else:
            dy = box["y"] + box["height"] / 2 - vh / 2
        spoken = self.duration_override
        if spoken is not None:   # finish by the until_word, but no slower than SCROLL_MIN_PX_PER_S
            duration = min(spoken - 0.15, abs(dy) / SCROLL_MIN_PX_PER_S)   # 0.15 s: call overhead
        else:
            duration = max(float(a.params.get("duration", 0)), abs(dy) / SCROLL_PX_PER_S)
        self._wheel(dy, max(duration, 0.5, abs(dy) / (SCROLL_PX_PER_S * 3)), vw / 2, vh / 2)

    duration_override: float | None = None

    def narration_tour(self, narration_end: float, had_actions: bool) -> None:
        """The actions are done but the voice keeps talking: scroll on through the page (down while there is more
        to see; back to the top in a pure-narration segment that has nothing left below) instead of a still frame."""
        remaining = narration_end - now()
        if not self.pacing.get("narration_scroll", 1) or remaining < TOUR_MIN_S:
            return
        vw, vh = self.page.evaluate("() => [innerWidth, innerHeight]")
        tail = 0.8                        # stop just before the voice ends
        slow, fast = TOUR_PX_PER_S
        self.hold_until(now() + 0.8)      # let the viewer take in the screen (and a freshly opened page load)
        give_up = now() + 3.0             # content that loads after a click may need a moment to appear
        while True:
            room = self.page.evaluate(SCROLL_ROOM, [vw / 2, vh / 2])
            budget = narration_end - tail - now()
            if budget < TOUR_MIN_S - 1.6:
                return
            if room["down"] >= TOUR_MIN_PX:
                dy = min(room["down"], budget * fast)
                break
            if not had_actions and room["up"] >= TOUR_MIN_PX:
                dy = -min(room["up"], budget * fast)
                break
            if now() > give_up:
                return
            self.hold_until(now() + 0.5)
        duration = max(min(budget, abs(dy) / slow), abs(dy) / fast)
        self._wheel(dy, duration, vw / 2, vh / 2)

    def _wheel(self, dy: float, duration: float, x: float, y: float) -> None:
        """Eased scroll of the scroll container under (x, y), animated inside the page, so it takes exactly
        `duration` however slow the browser is to answer (stepping with wheel events ran up to 2x long headless)."""
        t0 = now()   # no pointer move: the page scrolls itself, so nothing under a parked cursor lights up
        moved = self.page.evaluate(SMOOTH_SCROLL, [dy, duration * 1000, x, y])
        self.event("scroll", t0, t_end=now(), dy=moved, x=x, y=y)

    def _do_press(self, a: Action, timeout: float, where: str) -> None:
        self.page.evaluate(STAMP_OLD)
        t = now()
        self.page.keyboard.press(a.params["key"])
        self.event("press", t, key=a.params["key"])

    def _do_goto(self, a: Action, timeout: float, where: str) -> None:
        t = now()
        self.page.goto(a.params["url"], wait_until="load", timeout=timeout * 1000)
        self.event("navigate", t, t_end=now(), url=a.params["url"])

    def _do_wait_for(self, a: Action, timeout: float, where: str) -> None:
        t = now()
        if a.params.get("state", "visible") == "hidden":
            try:
                self._base(a.target).first.wait_for(state="hidden", timeout=timeout * 1000)
            except PlaywrightError as e:
                raise ActionError(f"{where}: {a.target.describe()} still visible after {timeout:.0f}s") from e
        elif a.target.text is not None and not a.target.exact:
            self._wait_text_soft(a.target, timeout, where)
        else:
            self.locate(a.target, timeout, need_enabled=False, where=where)
        self.event("wait_for", t, t_end=now(), testid=a.target.testid)

    def _wait_text_soft(self, t: Target, timeout: float, where: str) -> None:
        """Wait for reply text that may be worded differently on screen than in the narration. Instead of failing the
        whole take, give up once the page has stopped changing (the reply is done) and let the next action decide."""
        self.page.evaluate(MUTATION_WATCH)
        # Reply text: only in elements that appeared after the last click (an older reply may say the same thing).
        loc = self._base_any(t).and_(self.page.locator(":not([data-zv-old])"))
        t0 = now()
        while not loc.count():
            waited = now() - t0
            quiet = self.page.evaluate("() => (performance.now() - window.__zvLastMut) / 1000")
            if (waited > SOFT_WAIT_MIN_S and quiet > SOFT_WAIT_QUIET_S) or waited > timeout:
                self.log(f"      WARNING: {where}: {t.describe()} never appeared; the page settled after "
                         f"{waited:.0f}s, continuing (reword this wait in the script)")
                return
            self.check_focus()
            self.page.wait_for_timeout(250)

    def _do_wait(self, a: Action, timeout: float, where: str) -> None:
        t = now()
        self.page.wait_for_timeout(float(a.params["seconds"]) * 1000)
        self.event("wait", t, t_end=now())


def _apply_storage_state(context, path: Path) -> None:
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("cookies"):
        context.add_cookies(state["cookies"])
    for origin in state.get("origins", []):
        items = {i["name"]: i["value"] for i in origin.get("localStorage", [])}
        if items:
            context.add_init_script(f"""(() => {{
                if (location.origin !== {json.dumps(origin['origin'])}) return;
                const items = {json.dumps(items)};
                for (const k in items) if (localStorage.getItem(k) === null) localStorage.setItem(k, items[k]);
            }})();""")


def _flash_runs(raw: Path, marker_px: int | None) -> list[tuple[int, int]]:
    """Frame ranges showing the sync marker (bottom-right square; full screen for older takes)."""
    if marker_px:
        v = media.stream(raw, "video")
        inner = max(4, marker_px - 8)
        crop = (inner, inner, int(v["width"]) - marker_px + 4, int(v["height"]) - marker_px + 4)
        thumbs = media.decode_video_thumbs(raw, 4, 4, crop=crop)
    else:
        thumbs = media.decode_video_thumbs(raw)
    mean = thumbs.reshape(len(thumbs), -1, 3).mean(axis=1)
    flash = (mean[:, 0] > 200) & (mean[:, 1] < 70) & (mean[:, 2] > 200)
    runs, start = [], None
    for i, f in enumerate(flash):
        if f and start is None:
            start = i
        elif not f and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(flash)))
    return runs


def _fit_clock(flashes: list[tuple[float, float]], runs: list[tuple[int, int]], fps: int) -> dict:
    """Least-squares map perf_counter -> raw.mp4 time from the four flash edges."""
    py, vid = [], []
    for (t_on, t_off), (f_on, f_off) in zip(flashes, runs):
        py += [t_on, t_off]
        vid += [(f_on - 0.5) / fps, (f_off - 0.5) / fps]
    py_arr, vid_arr = np.array(py), np.array(vid)
    b, a = np.polyfit(py_arr - py_arr[0], vid_arr, 1)
    residual_ms = (vid_arr - (a + b * (py_arr - py_arr[0]))) * 1000
    return {"origin": py[0], "a": float(a), "b": float(b),
            "residual_ms": [round(float(r), 1) for r in residual_ms]}


def run_record(demo: Demo, lang: str, log=print, progress=None) -> None:
    out_dir = demo.lang_dir(lang)
    durations_file = out_dir / "durations.json"
    words_file = out_dir / "words.json"
    if not durations_file.exists() or not words_file.exists():
        raise FileNotFoundError(f"run the tts stage first ({durations_file} missing)")
    durations = {d["index"]: d for d in json.loads(durations_file.read_text(encoding="utf-8"))["segments"]}
    words = {w["index"]: w["words"] for w in json.loads(words_file.read_text(encoding="utf-8"))["segments"]}
    for seg in demo.segments:
        d = durations.get(seg.index)
        if not d or d["text"] != seg.spoken(lang):
            raise RuntimeError(f"narration for segment {seg.index} ({seg.id}) is out of date - rerun the tts stage")

    raw_capture = out_dir / "raw.capture.mp4"
    background = demo.capture == "background"
    # Background takes use the same layout as a 1080p monitor at 150 % (1280x720 CSS px), so scripts and zoom regions
    # made for either mode line up.
    dpr = demo.resolution[1] / 720
    viewport = (round(demo.resolution[0] / dpr), round(demo.resolution[1] / dpr))
    if background:
        capture = BrowserCapture(raw_capture, demo.fps, demo.resolution)
    else:
        capture = ScreenCapture(raw_capture, demo.fps, demo.monitor)
    p = demo.pacing
    flashes: list[tuple[float, float]] = []
    timeline_segments: list[dict] = []

    if demo.storage_state and not demo.storage_state.exists():
        raise FileNotFoundError(f"storage_state {demo.storage_state} missing - run: python -m demo auth <script>")

    if background:
        log("Recording in the background with a hidden browser - you can keep using this computer.")
    else:
        log("Close notifications/popups: the whole monitor is captured. Don't touch mouse or keyboard until done.")
    profile = tempfile.mkdtemp(prefix="demo-chromium-")
    (Path(profile) / "Default").mkdir()
    (Path(profile) / "Default" / "Preferences").write_text(json.dumps({
        "browser": {"enable_spellchecking": False},
        "spellcheck": {"dictionaries": [], "use_spelling_service": False},
        "credentials_enable_service": False,
        "profile": {"password_manager_enabled": False},
        "translate": {"enabled": False},
    }), encoding="utf-8")
    with sync_playwright() as pw:
        # Kiosk mode only applies to the browser's own first window, hence a persistent context.
        context = pw.chromium.launch_persistent_context(
            profile, headless=background, no_viewport=True, ignore_default_args=["--enable-automation"],
            args=background_args(viewport, dpr) if background else KIOSK_ARGS,
        )
        try:
            if demo.storage_state:
                _apply_storage_state(context, demo.storage_state)
            context.add_init_script(_hide_script(demo.hide, demo.hide_scrollbars))
            context.add_init_script(CURSOR_INIT_SCRIPT)
            page = context.pages[0] if context.pages else context.new_page()
            hwnd = None
            if background:
                # Look like the regular browser to the app (headless Chrome says "HeadlessChrome").
                ua = page.evaluate("() => navigator.userAgent").replace("HeadlessChrome", "Chrome")
                ua_session = context.new_cdp_session(page)
                ua_session.send("Network.setUserAgentOverride", {"userAgent": ua})
            else:
                page.bring_to_front()
                marker_title = f"zenvideo-recorder-{os.getpid()}-{int(time.time())}"
                page.evaluate("(t) => { document.title = t; }", marker_title)
                hwnd = winfocus.find_window(marker_title)
                if hwnd is None or not winfocus.bring_to_front(hwnd):
                    raise CaptureError("couldn't bring the recording browser to the front of the screen - close any "
                                       "window that is pinned on top or asking for attention, then try again")
            log(f"Opening {demo.url}")
            page.goto(demo.url, wait_until="load", timeout=60000)
            page.evaluate("() => document.fonts.ready")

            deadline = now() + 8
            while True:
                geo = page.evaluate("() => ({w: innerWidth, h: innerHeight, sw: screen.width, sh: screen.height, dpr: devicePixelRatio})")
                want = viewport if background else (geo["sw"], geo["sh"])
                if abs(geo["w"] - want[0]) <= 2 and abs(geo["h"] - want[1]) <= 2:
                    break
                if now() > deadline:
                    what = "hidden browser is not at the recording size" if background else "browser is not fullscreen"
                    raise CaptureError(f"{what} (page {geo['w']}x{geo['h']}, expected {want[0]}x{want[1]})")
                page.wait_for_timeout(200)
            log(f"Viewport {geo['w']}x{geo['h']} CSS px at devicePixelRatio {geo['dpr']}")

            rec = Recorder(page, demo, geo["dpr"], log)
            if background:
                capture.start(page)
            else:
                rec.hwnd = hwnd
                if not winfocus.bring_to_front(hwnd):
                    raise CaptureError("the recording browser lost the front of the screen before recording started")
                rec.watch_focus = True
                capture.start()
            try:
                flashes.append(rec.marker())
                page.evaluate("([x, y]) => window.__vcursor && window.__vcursor.moveTo(x, y, 1)", list(rec.mouse))
                rec.hold_until(now() + p["lead_in"])

                for seg in demo.segments:
                    if progress:
                        progress((seg.index - 1) / len(demo.segments))
                    rec.segment = seg
                    audio_dur = durations[seg.index]["duration"]
                    toks = seg.tokens(lang)
                    start = now()
                    if MONITOR_AUDIO and durations[seg.index]["file"]:
                        winsound.PlaySound(str(out_dir / durations[seg.index]["file"]),
                                           winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                    late = []
                    log(f"  [{seg.index:03d}] {seg.id}  narration {audio_dur:.2f}s, {len(seg.actions)} action(s)")
                    for k, a in enumerate(seg.actions):
                        rec.duration_override = None
                        if a.kind == "scroll" and not a.at_word and "duration" not in a.params and audio_dur > 0:
                            # Plain scrolls share out the narration that is left, so the page keeps moving with the
                            # voice instead of finishing early and sitting still until the narration ends.
                            rest = seg.actions[k:]
                            scrolls = sum(1 for x in rest if x.kind == "scroll" and not x.at_word)
                            others = len(rest) - scrolls
                            budget = start + audio_dur - now() - others * 1.5
                            if budget > 0:
                                rec.duration_override = min(budget * 0.85 / scrolls, 20.0)
                        if a.until_word:
                            w0 = words[seg.index][find_phrase(toks, a.at_word[lang])]["start"]
                            w1 = words[seg.index][find_phrase(toks, a.until_word[lang])]["start"]
                            rec.duration_override = max(0.3, w1 - w0)
                        if a.at_word:
                            word = words[seg.index][find_phrase(toks, a.at_word[lang])]
                            fire = start + word["start"] - rec.lead_time(a)
                            lateness = now() - fire
                            if lateness > 0.1:
                                late.append({"action": a.where, "word": a.at_word[lang], "late_s": round(lateness, 3)})
                                log(f"      WARNING: {a.where} fires {lateness:.2f}s after '{a.at_word[lang]}' (earlier actions ran long)")
                            rec.wait_until(fire)
                        rec.run(a)
                    narration_end = start + audio_dur
                    rec.narration_tour(narration_end, had_actions=bool(seg.actions))
                    rec.hold_until(narration_end + p["gap"] + seg.hold)
                    overrun = now() - (narration_end + p["gap"] + seg.hold)
                    timeline_segments.append({
                        "index": seg.index, "id": seg.id, "start": start, "audio_duration": audio_dur,
                        "narration_end": narration_end, "end": now(),
                        "overrun_s": round(max(0.0, overrun), 3), "late_actions": late,
                    })
                    if overrun > 0.05:
                        log(f"      actions ran {overrun:.2f}s past the narration; next segment starts later (silence)")

                rec.hold_until(now() + p["tail"])
                flashes.append(rec.marker())
                page.wait_for_timeout(1200)
            finally:
                stats = capture.stop()
                winsound.PlaySound(None, 0)
        finally:
            context.close()
            shutil.rmtree(profile, ignore_errors=True)

    capture.remux_mp4(out_dir / "raw.mp4")
    raw_capture.unlink(missing_ok=True)
    capture.progress.unlink(missing_ok=True)

    (out_dir / "recording.json").write_text(json.dumps({
        "clock": "perf_counter",
        "fps": demo.fps,
        "capture_mode": demo.capture,
        "monitor": demo.monitor,
        "viewport_css": [geo["w"], geo["h"]],
        "dpr": geo["dpr"],
        "marker_px": round(MARKER_CSS_PX * geo["dpr"]),
        "flashes": flashes,
        "capture": stats,
        "segments": timeline_segments,
        "events": rec.events,
    }, indent=2), encoding="utf-8")
    finalize(out_dir, log)


def finalize(out_dir: Path, log=print) -> None:
    """recording.json (perf_counter times) + raw.mp4 -> timeline.json and events.jsonl in raw.mp4 time."""
    rec = json.loads((out_dir / "recording.json").read_text(encoding="utf-8"))
    raw_mp4 = out_dir / "raw.mp4"
    fps = rec["fps"]

    ok, detail = media.cfr_report(raw_mp4, fps)
    if not ok:
        raise CaptureError(f"raw.mp4 is not constant frame rate: {detail}")

    runs = _flash_runs(raw_mp4, rec.get("marker_px"))
    if len(runs) != 2:
        hint = ("the page may have stopped painting" if rec.get("capture_mode") == "background" else
                f"was the browser covered, minimized or on another monitor than output_idx={rec['monitor']}?")
        raise CaptureError(f"expected 2 sync markers in raw.mp4, found {len(runs)} - {hint}")
    clock = _fit_clock([tuple(f) for f in rec["flashes"]], runs, fps)
    span = rec["flashes"][1][0] - rec["flashes"][0][0]
    allowed = 0.002 + (1.5 / fps) / span  # frame quantization at the flashes dominates on short takes
    if abs(clock["b"] - 1) > allowed:
        raise CaptureError(f"capture clock drifted {abs(clock['b'] - 1) * 100:.2f}% (allowed {allowed * 100:.2f}%) "
                           f"- the encoder could not keep up")
    worst = max(abs(r) for r in clock["residual_ms"])

    def v(t: float) -> float:
        return round(clock["a"] + clock["b"] * (t - clock["origin"]), 4)

    segments = []
    for s in rec["segments"]:
        s = dict(s)
        for k in ("start", "narration_end", "end"):
            s[k] = v(s[k])
        segments.append(s)

    vstream = media.stream(raw_mp4, "video")
    timeline = {
        "fps": fps,
        "video": "raw.mp4",
        "video_size": [int(vstream["width"]), int(vstream["height"])],
        "viewport_css": rec["viewport_css"],
        "dpr": rec["dpr"],
        "usable": [round((runs[0][1] + 1) / fps, 4), round((runs[1][0] - 1) / fps, 4)],
        "sync": {**clock, "worst_residual_ms": worst, "cfr": detail, **{f"capture_{k}": x for k, x in rec["capture"].items()}},
        "segments": segments,
    }
    (out_dir / "timeline.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    with open(out_dir / "events.jsonl", "w", encoding="utf-8") as f:
        for e in rec["events"]:
            e = dict(e)
            e["t"] = v(e["t"])
            if "t_end" in e:
                e["t_end"] = v(e["t_end"])
            f.write(json.dumps(e) + "\n")

    log(f"raw.mp4: {media.duration(raw_mp4):.1f}s, {detail}")
    log(f"Clock sync: worst flash residual {worst:.1f} ms, drift {(clock['b'] - 1) * 1e6:+.0f} ppm, "
        f"capture dup={rec['capture'].get('dup')} drop={rec['capture'].get('drop')}")
    if worst > 25:
        log("WARNING: flash residual above 25 ms - check CPU load during capture")


def run_auth(demo: Demo) -> None:
    if not demo.storage_state:
        raise SystemExit("set storage_state: <path> in the script first")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx_args = {"no_viewport": True}
        if demo.storage_state.exists():
            ctx_args["storage_state"] = str(demo.storage_state)
        context = browser.new_context(**ctx_args)
        page = context.new_page()
        page.goto(demo.url)
        input("Log in in the browser window, then press Enter here to save the session... ")
        demo.storage_state.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(demo.storage_state))
        browser.close()
    print(f"Saved {demo.storage_state} (keep it out of git)")
