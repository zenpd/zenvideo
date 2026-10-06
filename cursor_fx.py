"""
cursor_fx.py
============
Playwright's video recording captures only the page's rendered DOM - it never
draws a system mouse cursor, so by default every click in a recording is
invisible: the button just changes state with no visible cause. This module
injects a small, self-contained overlay (a fake cursor + a pulsing highlight
ring + a click ripple) as real elements INSIDE the page, so they get captured
by the recording like anything else on screen. This is the same technique
product-demo tools (Arcade, Tango, Supademo, etc.) use.

Usage in generate_recording.py:

    from cursor_fx import CURSOR_INIT_SCRIPT, glide_to, highlight_box, \\
        unhighlight, click_ripple

    context.add_init_script(CURSOR_INIT_SCRIPT)   # once, at context creation

    # inside execute_step(), before a click:
    target.scroll_into_view_if_needed(timeout=5000)
    box = target.bounding_box()
    if box:
        x, y = glide_to(page, box)
        highlight_box(page, box)
    target.click(force=True, timeout=5000)
    if box:
        click_ripple(page, x, y)
        unhighlight(page)

Tuning (env vars, all optional):
    CURSOR_MOVE_MS        how long the glide animation takes (default 550)
    CURSOR_HIGHLIGHT_MS   how long the highlight ring holds before clicking (default 350)
"""

import os
from typing import Optional, Tuple

from playwright.sync_api import Page

CURSOR_MOVE_MS = int(os.environ.get("CURSOR_MOVE_MS", "550"))
CURSOR_HIGHLIGHT_MS = int(os.environ.get("CURSOR_HIGHLIGHT_MS", "350"))

# Injected once per document via context.add_init_script - persists across
# every navigation automatically, since Playwright re-runs init scripts on
# each new document in the context.
CURSOR_INIT_SCRIPT = r"""
(function () {
    let cursorX = window.innerWidth / 2;
    let cursorY = window.innerHeight / 2;

    function ensure() {
        if (document.getElementById('__vcursor')) return;

        const style = document.createElement('style');
        style.textContent = `
            #__vcursor {
                position: fixed; top: 0; left: 0; width: 28px; height: 28px;
                pointer-events: none; z-index: 2147483647;
                transform: translate(-9999px, -9999px);
                will-change: transform;
                filter: drop-shadow(0 2px 3px rgba(0,0,0,.35));
            }
            #__vhighlight {
                position: fixed; pointer-events: none; z-index: 2147483646;
                border-radius: 8px; opacity: 0;
                box-shadow: 0 0 0 3px rgba(59,130,246,.95), 0 0 18px 5px rgba(59,130,246,.5);
                transition: left .35s cubic-bezier(.2,.8,.2,1), top .35s cubic-bezier(.2,.8,.2,1),
                            width .35s cubic-bezier(.2,.8,.2,1), height .35s cubic-bezier(.2,.8,.2,1),
                            opacity .2s ease;
            }
            .__vripple {
                position: fixed; pointer-events: none; z-index: 2147483647;
                width: 14px; height: 14px; border-radius: 50%;
                background: rgba(59,130,246,.55);
                transform: translate(-50%, -50%) scale(0); opacity: 1;
                animation: __vripple-anim .5s ease-out forwards;
            }
            @keyframes __vripple-anim {
                to { transform: translate(-50%, -50%) scale(6); opacity: 0; }
            }
        `;
        document.head.appendChild(style);

        const cursor = document.createElement('div');
        cursor.id = '__vcursor';
        cursor.style.transform = `translate(${cursorX - 4}px, ${cursorY - 2}px)`;
        // Built with DOM calls, not innerHTML: pages that enforce Trusted Types reject innerHTML assignments.
        const SVG = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(SVG, 'svg');
        svg.setAttribute('width', '28');
        svg.setAttribute('height', '28');
        svg.setAttribute('viewBox', '0 0 24 24');
        const path = document.createElementNS(SVG, 'path');
        path.setAttribute('d', 'M3 2l6.5 18 2.4-7.6L19 10z');
        path.setAttribute('fill', 'white');
        path.setAttribute('stroke', 'black');
        path.setAttribute('stroke-width', '1.2');
        path.setAttribute('stroke-linejoin', 'round');
        svg.appendChild(path);
        cursor.appendChild(svg);
        document.documentElement.appendChild(cursor);

        const hl = document.createElement('div');
        hl.id = '__vhighlight';
        document.documentElement.appendChild(hl);
    }

    window.__vcursor = {
        moveTo(x, y, durationMs) {
            ensure();
            const el = document.getElementById('__vcursor');
            const start = `translate(${cursorX - 4}px, ${cursorY - 2}px)`;
            const end = `translate(${x - 4}px, ${y - 2}px)`;
            el.style.transform = start;

            const animation = el.animate(
                [{ transform: start }, { transform: end }],
                { duration: Math.max(0, durationMs), easing: 'cubic-bezier(0.16, 1, 0.3, 1)', fill: 'forwards' }
            );
            return animation.finished.then(() => {
                animation.commitStyles();
                animation.cancel();
                cursorX = x;
                cursorY = y;
            });
        },

        highlight(x, y, w, h) {
            ensure();
            const hl = document.getElementById('__vhighlight');
            hl.style.left = (x - 4) + 'px';
            hl.style.top = (y - 4) + 'px';
            hl.style.width = (w + 8) + 'px';
            hl.style.height = (h + 8) + 'px';
            hl.style.opacity = '1';
        },

        unhighlight() {
            const hl = document.getElementById('__vhighlight');
            if (hl) hl.style.opacity = '0';
        },

        ripple(x, y) {
            ensure();
            const r = document.createElement('div');
            r.className = '__vripple';
            r.style.left = x + 'px';
            r.style.top = y + 'px';
            document.documentElement.appendChild(r);
            setTimeout(() => r.remove(), 550);
        },
    };

    ensure();
})();
"""


def _center(box: dict) -> Tuple[float, float]:
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def glide_to(page: Page, box: dict, duration_ms: int = CURSOR_MOVE_MS) -> Tuple[float, float]:
    """Animate the synthetic cursor to the center of `box` (a Playwright
    bounding_box() dict) and block until the glide finishes, so the motion is
    actually visible in the recording rather than happening instantly."""
    x, y = _center(box)
    animated = False
    try:
        animated = page.evaluate(
            "([x, y, d]) => window.__vcursor"
            " ? window.__vcursor.moveTo(x, y, d).then(() => true)"
            " : false",
            [x, y, duration_ms],
        )
    except Exception:
        pass  # never let the cosmetic layer break a real action
    if not animated:
        page.wait_for_timeout(duration_ms)
    return x, y


def highlight_box(page: Page, box: dict, hold_ms: int = CURSOR_HIGHLIGHT_MS) -> None:
    """Draw the pulsing ring around `box` and hold briefly so the viewer
    registers what's about to be clicked before it happens."""
    try:
        page.evaluate(
            "([x, y, w, h]) => window.__vcursor && window.__vcursor.highlight(x, y, w, h)",
            [box["x"], box["y"], box["width"], box["height"]],
        )
    except Exception:
        pass
    page.wait_for_timeout(hold_ms)


def unhighlight(page: Page) -> None:
    try:
        page.evaluate("() => window.__vcursor && window.__vcursor.unhighlight()")
    except Exception:
        pass


def click_ripple(page: Page, x: float, y: float) -> None:
    try:
        page.evaluate(
            "([x, y]) => window.__vcursor && window.__vcursor.ripple(x, y)",
            [x, y],
        )
    except Exception:
        pass


def show_click(page: Page, box: Optional[dict]) -> None:
    """Convenience: full glide -> highlight -> (caller clicks) -> call
    finish_click() after. Split in two calls so the real Playwright click
    happens between the highlight and the ripple, matching what the viewer
    expects to see."""
    if box is None:
        return
    x, y = glide_to(page, box)
    highlight_box(page, box)


def finish_click(page: Page, box: Optional[dict]) -> None:
    if box is None:
        return
    x, y = _center(box)
    click_ripple(page, x, y)
    unhighlight(page)