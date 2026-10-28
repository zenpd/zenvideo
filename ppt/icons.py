"""Line icons for slides, drawn from Windows' Segoe Fluent Icons font into coloured PNGs and embedded in the deck (so
they show on any computer). The story writer picks icons by name from ICONS; an unknown name, or a computer without
the font, simply means no icon and the layout falls back to a numbered badge."""

import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = Path(r"C:\Windows\Fonts\SegoeIcons.ttf")
CACHE = Path(tempfile.gettempdir()) / "zen-ppt-icons"

ICONS = {   # name -> Segoe Fluent Icons code point (each checked by rendering it)
    "people": 0xE716, "team": 0xE902, "user": 0xE77B, "settings": 0xE713, "gears": 0xE9F5, "mail": 0xE715,
    "search": 0xE721, "lock": 0xE72E, "key": 0xE8D7, "shield": 0xEA18, "chat": 0xE8BD, "conversation": 0xE8F2,
    "chart": 0xE9D2, "pie-chart": 0xEB05, "report": 0xE9F9, "pulse": 0xE9D9, "clock": 0xE823, "calendar": 0xE787,
    "check": 0xE73E, "warning": 0xE7BA, "calculator": 0xE8EF, "tag": 0xE8EC, "box": 0xE7B8, "folder": 0xE8B7,
    "document": 0xE8A5, "edit": 0xE70F, "list": 0xEA37, "lightning": 0xE945, "speed": 0xEC4A, "flag": 0xE7C1,
    "globe": 0xE774, "link": 0xE71B, "sync": 0xE895, "bank": 0xE825, "cart": 0xE7BF, "truck": 0xE806,
    "briefcase": 0xE912, "robot": 0xE99A, "bulb": 0xEA80, "cloud": 0xE753, "code": 0xE943, "phone": 0xE717,
    "layers": 0xE81E, "puzzle": 0xEA86, "filter": 0xE71C, "star": 0xE734, "heart": 0xEB51, "health": 0xE95E,
    "education": 0xE7BE, "certificate": 0xEB95, "home": 0xE80F,
}


def available() -> bool:
    return FONT.exists()


def icon_png(name: str, color: str) -> Path | None:
    """A 256 px PNG of the icon in the colour (hex), or None when there is no such icon or no icon font."""
    code = ICONS.get(name)
    if code is None or not available():
        return None
    path = CACHE / f"{name}-{color.lower()}.png"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        size = 256
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        font = ImageFont.truetype(str(FONT), int(size * 0.86))
        rgb = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
        draw = ImageDraw.Draw(img)
        l, t, r, b = draw.textbbox((0, 0), chr(code), font=font)
        draw.text(((size - (r - l)) / 2 - l, (size - (b - t)) / 2 - t), chr(code), font=font, fill=rgb + (255,))
        img.save(path)
    return path
