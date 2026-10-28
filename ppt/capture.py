"""
Exploring an app for a deck: a hidden browser opens the app's link once and goes through it like a person would -
page by page through its navigation, and on each page through what it can do: tabs and option buttons (e.g. a region
switch), accordions, the first item of a list (its detail view), and - only when try_forms is on - the main button of a
form that is already filled in (demo/test apps). Everything is clicked inside the app, never opened by address, so
single-page apps whose server doesn't serve deep links work too.

Static and dynamic pages alike are captured once they have settled: the network is quiet, no "Loading..." or busy
region, lazy content scrolled into view, and the text has stopped changing (counters like "2 seconds ago" ignored).
After an action, the screenshot is taken where the page changed and the new text is what gets recorded.

Each distinct screen is saved as a screenshot plus its headings, buttons, text and how it was reached ("via"), in
pages/*.png and pages.json - written after every screen, so the UI can show them as they come in. Buttons that could
change data or end the session (delete, save, pay, send, regenerate, log out...) are never clicked.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PIL import Image


class CaptureError(RuntimeError):
    pass


MAX_SCREENS = 14
TIME_LIMIT = 240     # seconds for the whole exploration
PER_PAGE = 3         # screens from actions on one page (on top of the page itself)
SAME = 2.0           # mean abs difference (64x36 grey) below which two screenshots may be the same screen
VIEWPORT = {"width": 1440, "height": 810}     # x 4/3 device scale -> 1920 x 1080 screenshots
# Never clicked, whatever the mode: anything that could change or share data, cost money or end the session.
NEVER = re.compile(r"\b(delete|remove|log ?out|sign ?out|pay|purchase|buy|checkout|cancel|archive|reset|clear|regenerate|"
                   r"revoke|rotate|approve|reject|upload|download|export|print|install|uninstall|deploy|send|invite|"
                   r"share|transfer|withdraw|refund|save|update|edit|rename|close|copy|disconnect|unsubscribe|"
                   r"deactivate|disable|block|ban|publish|merge|restart|shutdown|terminate|destroy|drop|wipe)\b", re.I)
# Links that leave the app's pages: files, APIs, mail.
SKIP_LINK = re.compile(r"(^mailto:|^tel:|^javascript:|/api/|\.(pdf|zip|png|jpe?g|csv|xlsx?|docx?|json)$)", re.I)

ROOT_JS = "(document.querySelector('main, [role=main]') || document.body)"

NAV_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 &&
                     getComputedStyle(e).visibility !== 'hidden'; };
  const txt = e => (e.innerText || e.getAttribute('aria-label') || e.title || '').trim().replace(/\s+/g, ' ');
  const bars = 'nav, header, aside, [role=navigation], [role=tablist], [role=menubar]';
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    if (vis(a) && txt(a)) out.push({kind: 'link', role: 'link', text: txt(a).slice(0, 60), href: a.getAttribute('href'),
                                    nav: !!a.closest(bars)});
  }
  for (const b of document.querySelectorAll('button, [role=tab], [role=menuitem]')) {
    if (!vis(b) || !txt(b) || b.disabled || b.closest('a[href]') || !b.closest(bars)) continue;
    const role = b.getAttribute('role');
    out.push({kind: 'button', role: role === 'menuitem' ? 'menuitem' : role === 'tab' ? 'tab' : 'button',
              text: txt(b).slice(0, 60), nav: true});
  }
  return out.slice(0, 80);
}"""

INFO_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const txt = e => (e.innerText || e.getAttribute('aria-label') || e.title || '').trim().replace(/\s+/g, ' ');
  const uniq = a => [...new Set(a.filter(Boolean))].slice(0, 30);
  const root = """ + ROOT_JS + r""";
  const all = s => [...root.querySelectorAll(s)].filter(vis);
  return {title: document.title, headings: uniq(all('h1,h2,h3,h4').map(e => txt(e).slice(0, 80))),
          buttons: uniq(all('button,[role=button]').map(e => txt(e).slice(0, 60))),
          text: (root.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 2500),
          login: [...document.querySelectorAll('input[type=password]')].some(vis),
          // the app's frame around the page (logo, product name, menu) - where its name usually is
          frame: [...document.querySelectorAll('header, aside, nav, [role=banner]')].filter(e => vis(e) && !root.contains(e))
                   .map(e => (e.innerText || '').trim().replace(/\s+/g, ' ')).join(' / ').slice(0, 200)};
}"""

# Clickable things inside the page, tagged with data-zen so they can be clicked right away. Kinds: 'toggle' (the
# second option of a group of tabs / option buttons), 'expand' (an accordion), 'item' (the first item of a list or
# table that opens something), 'form' (the main button of a form whose fields are all filled in).
ACTIONS_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 &&
                     getComputedStyle(e).visibility !== 'hidden'; };
  const txt = e => (e.innerText || e.value || e.getAttribute('aria-label') || e.title || '').trim().replace(/\s+/g, ' ');
  const bars = 'nav, header, aside, [role=navigation], [role=menubar]';
  const root = """ + ROOT_JS + r""";
  document.querySelectorAll('[data-zen]').forEach(e => e.removeAttribute('data-zen'));
  let n = 0;
  const out = [];
  const add = (e, kind, extra = {}) => { e.setAttribute('data-zen', String(++n));
                                         out.push({id: String(n), kind, text: txt(e).slice(0, 60), ...extra}); };
  const clickable = 'button, [role=button], [role=tab], [role=radio], input[type=submit], input[type=button]';
  // groups of 2-8 short sibling options: tabs, segmented buttons, region/period switches
  const groups = new Set();
  for (const b of root.querySelectorAll(clickable)) {
    const p = b.parentElement;
    if (!p || groups.has(p) || b.closest(bars) || b.closest('form')) continue;
    const opts = [...p.children].filter(c => c.matches(clickable) && vis(c) && !c.disabled);
    if (opts.length < 2 || opts.length > 8 || opts.some(o => txt(o).length === 0 || txt(o).length > 24)) continue;
    groups.add(p);
    // the selected option: marked by ARIA or a class, else the one option styled unlike the others
    const marked = o => o.getAttribute('aria-selected') === 'true' || o.getAttribute('aria-pressed') === 'true' ||
                        o.getAttribute('aria-checked') === 'true' || /\b(active|selected|current)\b/i.test(o.className);
    const looks = opts.map(o => { const st = getComputedStyle(o); return `${st.backgroundColor}|${st.color}|${st.fontWeight}`; });
    let on = opts.findIndex(marked);
    if (on < 0 && opts.length > 2) {
      const unique = looks.map(l => looks.filter(x => x === l).length === 1);
      if (unique.filter(Boolean).length === 1) on = unique.indexOf(true);
    }
    add(on >= 0 ? opts.find((o, i) => i !== on) : opts[1], 'toggle', {group: opts.map(txt).slice(0, 8)});
  }
  // accordions and disclosures
  for (const e of root.querySelectorAll('[aria-expanded=false], details:not([open]) > summary')) {
    if (vis(e) && txt(e) && !e.closest(bars) && !e.closest('[aria-haspopup]') && e.tagName !== 'SELECT') {
      add(e, 'expand'); break;
    }
  }
  // the first item of a list or table that opens something
  const rows = [...root.querySelectorAll('tbody tr, [role=row], ul > li, ol > li, [role=listitem]')].filter(vis);
  for (const r of rows) {
    if (r.closest(bars) || r.parentElement.children.length < 2) continue;
    const link = r.querySelector('a[href]');
    const pointer = getComputedStyle(r).cursor === 'pointer' || r.hasAttribute('onclick');
    if (link && vis(link)) { add(link, 'item', {href: link.getAttribute('href')}); break; }
    if (pointer && txt(r)) { add(r, 'item'); break; }
  }
  // the main button of each form, with how many of its fields are empty: buttons are grouped by their innermost
  // container with 2+ fields (a <form>, or a card of fields); a container holding another form's is a page, not a form
  const fields = c => [...c.querySelectorAll('input, select, textarea')].filter(f => vis(f) &&
    !['hidden', 'checkbox', 'radio', 'range', 'file', 'submit', 'button', 'color'].includes(f.type));
  const container = b => {
    let c = b.parentElement;
    for (let i = 0; c && c !== document.body && i < 6; i++, c = c.parentElement) {
      if (c.tagName === 'FORM' || fields(c).length >= 2) return c;
    }
    return null;
  };
  const forms = new Map();
  for (const b of root.querySelectorAll('button, input[type=submit], [role=button]')) {
    if (!vis(b) || b.disabled || b.closest(bars) || b.hasAttribute('data-zen') || txt(b).length < 3 ||
        txt(b).length > 40) continue;
    const c = container(b);
    if (c) forms.set(c, [...(forms.get(c) || []), b]);
  }
  for (const [c, buttons] of forms) {
    if ([...forms.keys()].some(o => o !== c && c.contains(o))) continue;
    const main = buttons.find(b => b.type === 'submit') || buttons[buttons.length - 1];   // the last one: Submit, Go
    const fs = fields(c);
    add(main, 'form', {fields: fs.length, empty: fs.filter(f => !String(f.value || '').trim()).length});
  }
  return out;
}"""

# Watching what an action changes: the outermost changed elements, their text, and where the change starts.
WATCH_JS = r"""() => {
  const root = """ + ROOT_JS + r""";
  window.__zenChanged = new Set();
  if (window.__zenObserver) window.__zenObserver.disconnect();
  window.__zenObserver = new MutationObserver(ms => {
    for (const m of ms) {
      if (m.type === 'characterData' && m.target.parentElement) window.__zenChanged.add(m.target.parentElement);
      for (const x of m.addedNodes) window.__zenChanged.add(x.nodeType === 1 ? x : x.parentElement);
    }
  });
  window.__zenObserver.observe(root, {childList: true, subtree: true, characterData: true});
}"""

CHANGED_JS = r"""() => {
  if (window.__zenObserver) window.__zenObserver.disconnect();
  const els = [...(window.__zenChanged || [])].filter(e => e && e.isConnected);
  const outer = els.filter(e => !els.some(o => o !== e && o.contains(e)));
  const vis = outer.filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  const text = vis.map(e => (e.innerText || '').trim()).filter(Boolean).join(' / ').replace(/\s+/g, ' ').slice(0, 1500);
  const big = vis.filter(e => (e.innerText || '').trim().length > 20);
  const top = big.length ? Math.min(...big.map(e => e.getBoundingClientRect().top + window.scrollY)) : null;
  return {text, top};
}"""

STATE_JS = "() => (document.body.innerText || '').replace(/\\d+/g, '#').length + ':' + " \
           "(document.body.innerText || '').replace(/\\d+/g, '#').slice(-400)"


# Content still on its way: an indeterminate progress bar, a busy region, or a visible spinner or skeleton (a running,
# endlessly repeating animation named or classed like one, at least 14px - small pulsing status dots don't count).
BUSY_JS = r"""() => {
  const vis = e => { if (!e || !e.getBoundingClientRect) return false; const r = e.getBoundingClientRect();
                     return r.width >= 14 && r.height >= 14 && getComputedStyle(e).visibility !== 'hidden'; };
  for (const e of document.querySelectorAll('[aria-busy=true], [role=progressbar]:not([aria-valuenow])')) {
    if (vis(e)) return true;
  }
  const busy = /spin|rotat|load|shimmer|skeleton|pulse/i;
  for (const a of (document.getAnimations ? document.getAnimations() : [])) {
    const t = a.effect && a.effect.target;
    const timing = a.effect && a.effect.getComputedTiming();
    if (a.playState !== 'running' || !timing || timing.iterations !== Infinity || !vis(t)) continue;
    const cls = typeof t.className === 'string' ? t.className : (t.className && t.className.baseVal) || '';
    if (busy.test(a.animationName || '') || busy.test(cls)) return true;
  }
  return false;
}"""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:30] or "page"


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", text.lower()))


def _quiet(page, limit: float) -> None:
    """Wait until the page's text stops changing (numbers ignored, so live clocks and counters don't count)."""
    end, last, since = time.time() + limit, None, time.time()
    while time.time() < end:
        try:
            state = page.evaluate(STATE_JS)
        except Exception:  # noqa: BLE001 - navigating: try again
            state = None
        if state != last:
            last, since = state, time.time()
        elif time.time() - since >= 1.5:
            return
        page.wait_for_timeout(400)


def _settle(page, limit: float = 10, patience: float = 15, log=None) -> None:
    """Static or dynamic: wait for the network, loading messages, spinners and changing text to stop; scroll once
    through the page so lazy content loads. patience: how long to wait for spinners - long for the first page, as an
    app whose server was asleep can take a minute to answer."""
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:  # noqa: BLE001 - an app that keeps polling never goes idle; it is still worth a screenshot
        pass
    try:   # data still arriving: a "Loading..." message
        page.wait_for_function("() => !/\\bloading\\b/i.test(document.body.innerText || '')", timeout=8000)
    except Exception:  # noqa: BLE001 - some apps always show the word; take the screenshot anyway
        pass
    try:   # a spinner, skeleton or busy region
        page.wait_for_function(f"() => !({BUSY_JS})()", timeout=6000)
    except Exception:  # noqa: BLE001
        if log and patience > 6:
            log("  still loading - waiting for the app (its server may be starting up)...")
        try:
            page.wait_for_function(f"() => !({BUSY_JS})()", timeout=max(0, patience - 6) * 1000)
        except Exception:  # noqa: BLE001 - an always-spinning element: take the screenshot anyway
            pass
    try:
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(500)
        page.evaluate("() => window.scrollTo(0, 0)")
    except Exception:  # noqa: BLE001
        pass
    _quiet(page, limit)
    page.wait_for_timeout(500)


def _read(page, js):
    """Evaluate js; a page that navigates while being read gets one more try once it has settled."""
    try:
        return page.evaluate(js)
    except Exception:  # noqa: BLE001 - e.g. "Execution context was destroyed" during a client-side redirect
        _settle(page)
        return page.evaluate(js)


def _thumb(path: Path):
    import numpy as np
    return np.asarray(Image.open(path).convert("L").resize((64, 36)), dtype="float32")


def capture_app(url: str, out_dir: Path, log=print, max_screens: int = MAX_SCREENS, try_forms: bool = False
                ) -> list[dict]:
    """Explore the app and save its distinct screens -> out_dir/pages/*.png and out_dir/pages.json.
    try_forms: also click the main button of forms that are already filled in (only for demo/test apps)."""
    from playwright.sync_api import sync_playwright

    start = urlparse(url)
    if start.scheme not in ("http", "https"):
        raise CaptureError("the app link must start with http:// or https://")
    shots_dir = out_dir / "pages"
    shots_dir.mkdir(parents=True, exist_ok=True)
    for old in shots_dir.glob("*.png"):
        old.unlink()
    pages: list[dict] = []
    thumbs: list = []
    began = time.time()

    def out_of_budget() -> bool:
        return len(pages) >= max_screens or time.time() - began > TIME_LIMIT

    def snap(page, label: str, via: str, kind: str, text: str | None = None, top: float | None = None) -> bool:
        """Screenshot the screen (at the change, for an action) unless it is one already captured."""
        info = _read(page, INFO_JS)
        page_text = info["text"]
        if len(page_text) < 20:
            log(f"  {label}: the page is empty - skipped")
            return False
        y = max(0, top - 80) if top is not None and top > VIEWPORT["height"] * 0.6 else 0
        page.evaluate(f"() => window.scrollTo(0, {y})")
        page.wait_for_timeout(300)
        path = shots_dir / f"{len(pages) + 1:02d}.png"
        page.screenshot(path=str(path))
        thumb = _thumb(path)
        words = _words(text or page_text)    # an action's screen: judged by what it changed
        for p, t in zip(pages, thumbs):
            overlap = len(words & p["_words"]) / (len(words | p["_words"]) or 1)
            if overlap > 0.92 and float(abs(thumb - t).mean()) < SAME * 3:
                path.unlink()
                log(f"  {label}: same screen as '{p['label']}' - skipped")
                return False
        ids = {p["id"] for p in pages}
        pid = _slug(label)
        while pid in ids:
            pid += "-2"
        pages.append({"id": pid, "label": label, "kind": kind, "via": via, "url": page.url, "file": path.name,
                      "title": info["title"], "frame": info["frame"], "headings": info["headings"][:12],
                      "buttons": info["buttons"][:15],
                      "text": (text or page_text)[:1500], "_words": words})
        thumbs.append(thumb)
        (out_dir / "pages.json").write_text(json.dumps([{k: v for k, v in x.items() if k != "_words"} for x in pages],
                                                       indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"  captured {label} ({via})")
        return True

    def act(page, locator, wait: float) -> dict | None:
        """Click and wait for the page to settle; what changed (text and where), or None when nothing did."""
        page.evaluate(WATCH_JS)
        before = page.url
        locator.click(timeout=5000)
        page.wait_for_timeout(600)
        _settle(page, wait, patience=wait, log=log)
        if page.url != before:
            return {"text": None, "top": None, "moved": True}
        changed = page.evaluate(CHANGED_JS)
        return changed if len(changed["text"]) >= 15 else None

    def explore(page, label: str, via: str) -> None:
        """What the page can do: a form's result, a list item's detail, another tab/option, an accordion."""
        try:
            found = page.evaluate(ACTIONS_JS)
        except Exception:  # noqa: BLE001
            return
        order = {"form": 0, "item": 1, "toggle": 2, "expand": 3}
        found = sorted(found, key=lambda a: order[a["kind"]])
        shots, forms = 0, 0
        home = page.url
        for a in found:
            if shots >= PER_PAGE or out_of_budget():
                break
            if NEVER.search(a["text"]):
                continue
            if a["kind"] == "form":
                if not try_forms or forms or a["empty"]:
                    if try_forms and a["empty"] and not forms:
                        log(f"  {label}: the form behind '{a['text']}' needs input - not submitted")
                    continue
                forms += 1
            if a["kind"] == "item" and a.get("href"):
                target = urlparse(urljoin(page.url, a["href"]))
                if target.netloc != start.netloc or SKIP_LINK.search(a["href"]):
                    continue
            loc = page.locator(f'[data-zen="{a["id"]}"]').first
            what = {"form": f"clicked “{a['text']}” with the form's pre-filled values",
                    "item": f"opened the first item (“{a['text'][:40]}”)",
                    "toggle": f"chose “{a['text']}”" + (f" (of {', '.join(a['group'])})" if a.get("group") else ""),
                    "expand": f"expanded “{a['text'][:40]}”"}[a["kind"]]
            try:
                changed = act(page, loc, 45 if a["kind"] == "form" else 8)
            except Exception as e:  # noqa: BLE001 - an element that went away or can't be clicked
                log(f"  {label}: could not click '{a['text']}': {str(e).splitlines()[0][:100]}")
                continue
            if not changed:
                log(f"  {label}: '{a['text']}' changed nothing visible")
                continue
            name = {"form": f"{label} - {a['text']} result", "item": f"{label} - detail",
                    "toggle": f"{label} - {a['text']}", "expand": f"{label} - {a['text'][:30]}"}[a["kind"]]
            kind = {"form": "result", "item": "detail", "toggle": "view", "expand": "view"}[a["kind"]]
            if snap(page, name, f"{via} → {what}", kind, changed["text"], changed["top"]):
                shots += 1
            if changed.get("moved"):     # a detail page: back to the list for the next action
                try:
                    page.go_back(wait_until="load", timeout=20000)
                    _settle(page)
                except Exception:  # noqa: BLE001
                    page.goto(home, wait_until="load", timeout=30000)
                    _settle(page)

    log(f"Opening {url} in a hidden browser...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_context(viewport=VIEWPORT, device_scale_factor=4 / 3).new_page()
            page.goto(url, wait_until="load", timeout=60000)
            _settle(page, 15, patience=90, log=log)
            if _read(page, INFO_JS)["login"]:
                log("  The app shows a sign-in form: only what is visible without signing in is captured")
            home_label = "Home"
            snap(page, home_label, "opened the link", "page")
            explore(page, home_label, "Home")
            seen = {(urlparse(page.url).path.rstrip("/"), urlparse(page.url).fragment)}
            found = _read(page, NAV_JS)
            queue = [c for c in found if c["nav"]] + [c for c in found if not c["nav"]]
            done_text: set[str] = set()
            while queue and not out_of_budget():
                c = queue.pop(0)
                if c["text"] in done_text or NEVER.search(c["text"]) or (c["kind"] == "button" and len(c["text"]) > 30):
                    continue
                if c["kind"] == "link":
                    t = urlparse(urljoin(url, c["href"]))
                    key = (t.path.rstrip("/"), t.fragment)
                    if t.scheme not in ("http", "https") or t.netloc != start.netloc or SKIP_LINK.search(c["href"]) \
                            or key in seen:
                        continue
                done_text.add(c["text"])
                via = f"clicked “{c['text']}” in the navigation" if c["nav"] else f"clicked the “{c['text']}” link"
                try:
                    loc = page.get_by_role(c["role"], name=c["text"], exact=True).first
                    if not loc.is_visible():          # only reachable from the start page
                        page.goto(url, wait_until="load", timeout=30000)
                        _settle(page)
                        loc = page.get_by_role(c["role"], name=c["text"], exact=True).first
                    loc.click(timeout=5000)
                    _settle(page)
                except Exception as e:  # noqa: BLE001 - a page that fails to open shouldn't stop the exploring
                    if c["kind"] != "link":
                        log(f"  could not open {c['text']!r}: {str(e).splitlines()[0][:120]}")
                        continue
                    page.goto(urljoin(url, c["href"]), wait_until="load", timeout=30000)
                    _settle(page)
                seen.add((urlparse(page.url).path.rstrip("/"), urlparse(page.url).fragment))
                if snap(page, c["text"], via, "page"):
                    explore(page, c["text"], c["text"])
                for more in _read(page, NAV_JS):     # links this page adds (its own sub-pages)
                    if more["text"] not in done_text and all(more["text"] != q["text"] for q in queue):
                        queue.append(more)
        finally:
            browser.close()
    save_pages = [{k: v for k, v in p.items() if k != "_words"} for p in pages]
    (out_dir / "pages.json").write_text(json.dumps(save_pages, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Explored the app in {time.time() - began:.0f}s: {len(pages)} screen(s)")
    return save_pages
