"""
Post-production effects, all computed from the event log (never hand-timed):
auto-zoom camera, click ripples, framed layout, intro/outro cards.
"""

import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
ZOOM_EASE_S = 0.7
ZOOM_MIN_WORTH = 1.12
ZOOM_PAD = 90
RIPPLE_S = 0.6
ACCENT = (99, 102, 241)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    for n in names:
        p = FONT_DIR / n
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


def ease(p: float) -> float:
    p = min(1.0, max(0.0, p))
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


@dataclass
class _Window:
    start: float
    end: float
    box: tuple[float, float, float, float]


class Camera:
    """Eased zoom toward interacted elements. Nearby events share one zoom instead of jittering."""

    def __init__(self, events: list[dict], width: int, height: int, zoom_max: float):
        self.w, self.h = width, height
        self.zoom_max = zoom_max
        self.keyframes = self._keyframes(self._windows(events))

    def _target(self, box) -> tuple[float, float, float] | None:
        x0, y0, x1, y1 = box
        crop_w = max(x1 - x0, (y1 - y0) * self.w / self.h)
        z = min(self.zoom_max, self.w / crop_w)
        if z < ZOOM_MIN_WORTH:
            return None
        return (x0 + x1) / 2, (y0 + y1) / 2, z

    def _windows(self, events: list[dict]) -> list[_Window]:
        raw = []
        for e in events:
            if not e.get("width") or e.get("zoom") is False or e["type"] not in ("click", "type", "hover", "focus"):
                continue
            if isinstance(e.get("zoom"), list):
                x, y, w, h = e["zoom"]
                box = (x, y, x + w, y + h)
            else:
                box = (e["x"] - ZOOM_PAD, e["y"] - ZOOM_PAD, e["x"] + e["width"] + ZOOM_PAD, e["y"] + e["height"] + ZOOM_PAD)
            if e["type"] == "focus":
                start, end = e["t"], e.get("t_end", e["t"] + 2)
            elif e["type"] == "type":
                start, end = e["t"] - 0.6, e.get("t_end", e["t"]) + 1.0
            else:
                start, end = e["t"] - 0.8, e["t"] + 1.4
            raw.append(_Window(start, end, box))
        raw.sort(key=lambda w: w.start)

        merged: list[_Window] = []
        for w in raw:
            if merged and w.start <= merged[-1].end + 0.5:
                m = merged[-1]
                union = (min(m.box[0], w.box[0]), min(m.box[1], w.box[1]), max(m.box[2], w.box[2]), max(m.box[3], w.box[3]))
                if self._target(union):
                    merged[-1] = _Window(m.start, max(m.end, w.end), union)
                    continue
            merged.append(w)
        return [w for w in merged if self._target(w.box)]

    def _keyframes(self, windows: list[_Window]) -> list[tuple[float, tuple[float, float, float]]]:
        base = (self.w / 2, self.h / 2, 1.0)
        kfs = [(0.0, base)]
        for i, w in enumerate(windows):
            target = self._target(w.box)
            if len(kfs) >= 2 and kfs[-1][1] == kfs[-2][1] and kfs[-1][1] != base:
                # Straight from one zoom to the next: leave the previous one early enough for a full-length move
                # (a 0.2 s whip-pan across the screen reads as a cut), but not before the camera got there.
                kfs[-1] = (max(kfs[-2][0], min(kfs[-1][0], w.start - ZOOM_EASE_S)), kfs[-1][1])
            move_start = max(kfs[-1][0], w.start - ZOOM_EASE_S)
            kfs.append((move_start, kfs[-1][1]))
            kfs.append((max(w.start, move_start + ZOOM_EASE_S), target))
            kfs.append((max(w.end, kfs[-1][0]), target))
            nxt = windows[i + 1] if i + 1 < len(windows) else None
            if nxt is None or nxt.start - ZOOM_EASE_S > w.end + ZOOM_EASE_S:
                kfs.append((kfs[-1][0] + ZOOM_EASE_S, base))
        return kfs

    def at(self, t: float) -> tuple[float, float, float]:
        kfs = self.keyframes
        if t >= kfs[-1][0]:
            return kfs[-1][1]
        for (t0, a), (t1, b) in zip(kfs, kfs[1:]):
            if t0 <= t < t1:
                p = ease((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
                z = math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * p)
                return a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p, z
        return kfs[0][1]

    def crop(self, t: float) -> tuple[float, float, float, float]:
        cx, cy, z = self.at(t)
        cw, ch = self.w / z, self.h / z
        x0 = min(max(cx - cw / 2, 0.0), self.w - cw)
        y0 = min(max(cy - ch / 2, 0.0), self.h - ch)
        return x0, y0, x0 + cw, y0 + ch


def _gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    p = (yy / h * 0.7 + xx / w * 0.3)[..., None]
    arr = np.array(top, np.float32) * (1 - p) + np.array(bottom, np.float32) * p
    return Image.fromarray(arr.astype(np.uint8), "RGB")


class Compositor:
    def __init__(self, out_w: int, out_h: int, src_w: int, src_h: int, style: dict):
        self.out_w, self.out_h = out_w, out_h
        top, bottom = (_hex(c) for c in style["background"])
        self.background = _gradient(out_w, out_h, top, bottom)
        if style["frame"]:
            cw = round(out_w * 0.91)
            ch = round(cw * src_h / src_w)
            if ch > out_h * 0.91:
                ch = round(out_h * 0.91)
                cw = round(ch * src_w / src_h)
            radius = round(out_h * 0.016)
        else:
            cw, ch = out_w, min(out_h, round(out_w * src_h / src_w))
            radius = 0
        self.size = (cw, ch)
        self.offset = ((out_w - cw) // 2, (out_h - ch) // 2)
        self.mask = Image.new("L", self.size, 0)
        ImageDraw.Draw(self.mask).rounded_rectangle((0, 0, cw - 1, ch - 1), radius=radius, fill=255)
        self.base = self.background.copy()
        if style["frame"]:
            shadow = Image.new("L", (out_w, out_h), 0)
            ox, oy = self.offset
            ImageDraw.Draw(shadow).rounded_rectangle((ox, oy + 14, ox + cw, oy + ch + 14), radius=radius, fill=150)
            shadow = shadow.filter(ImageFilter.GaussianBlur(26))
            self.base = Image.composite(Image.new("RGB", (out_w, out_h), (4, 4, 16)), self.base, shadow)

    def compose(self, src: Image.Image, crop: tuple, ripples: list[tuple[float, float, float]]) -> Image.Image:
        content = src.resize(self.size, Image.BICUBIC, box=crop)
        if ripples:
            scale = self.size[0] / (crop[2] - crop[0])
            overlay = Image.new("RGBA", self.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(overlay)
            for x, y, p in ripples:
                u, v = (x - crop[0]) * scale, (y - crop[1]) * scale
                grow = 1 - (1 - p) ** 3
                r = (10 + 34 * grow) * scale
                alpha = int(230 * (1 - p))
                d.ellipse((u - r, v - r, u + r, v + r), outline=(*ACCENT, alpha), width=max(2, round(4 * scale)))
                inner = r * 0.45
                d.ellipse((u - inner, v - inner, u + inner, v + inner), fill=(*ACCENT, alpha // 3))
            content = Image.alpha_composite(content.convert("RGBA"), overlay).convert("RGB")
        out = self.base.copy()
        out.paste(content, self.offset, self.mask)
        return out


def ripples_at(clicks: list[dict], t: float) -> list[tuple[float, float, float]]:
    out = []
    for e in clicks:
        p = (t - e["t"]) / RIPPLE_S
        if 0 <= p < 1:
            out.append((e["x"] + e["width"] / 2, e["y"] + e["height"] / 2, p))
    return out


def card(out_w: int, out_h: int, style: dict, title: str, subtitle: str, small: str) -> Image.Image:
    top, bottom = (_hex(c) for c in style["background"])
    img = _gradient(out_w, out_h, top, bottom)
    d = ImageDraw.Draw(img)
    s = out_h / 1080
    f_title, f_sub, f_small = _font(round(76 * s), True), _font(round(38 * s)), _font(round(26 * s))
    cx, cy = out_w / 2, out_h / 2
    d.rounded_rectangle((cx - 60 * s, cy - 150 * s, cx + 60 * s, cy - 138 * s), radius=6 * s, fill=ACCENT)
    d.text((cx, cy - 60 * s), title, font=f_title, fill=(255, 255, 255), anchor="mm")
    if subtitle:
        d.text((cx, cy + 30 * s), subtitle, font=f_sub, fill=(199, 210, 254), anchor="mm")
    if small:
        d.text((cx, cy + 110 * s), small, font=f_small, fill=(148, 163, 184), anchor="mm")
    return img
