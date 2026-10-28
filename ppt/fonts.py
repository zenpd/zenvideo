"""Text measuring with the designs' real fonts, so slide text is sized to fit its box before PowerPoint ever sees it."""

from pathlib import Path

from PIL import ImageFont

FONT_DIRS = [Path(r"C:\Windows\Fonts"), Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"]
DEFAULT = "Calibri"
# family -> candidates of (regular file, bold file, width scale); a missing font is measured with a stand-in that is
# scaled up to its width, so text never ends up wider in PowerPoint than it was measured.
FONT_FILES = {
    "Calibri": [("calibri.ttf", "calibrib.ttf", 1.0)],
    "Arial": [("arial.ttf", "arialbd.ttf", 1.0)],
    "Cambria": [("cambria.ttc", "cambriab.ttf", 1.0), ("georgia.ttf", "georgiab.ttf", 1.0)],
    "Bookman Old Style": [("BOOKOS.TTF", "BOOKOSB.TTF", 1.0), ("georgia.ttf", "georgiab.ttf", 1.12)],
}

_fonts: dict[tuple[str, bool, float], tuple[ImageFont.FreeTypeFont, float]] = {}


def _font(bold: bool, pt: float, family: str = DEFAULT) -> tuple[ImageFont.FreeTypeFont, float]:
    key = (family, bold, pt)
    if key not in _fonts:
        for regular, heavy, scale in FONT_FILES.get(family, []) + FONT_FILES[DEFAULT]:
            name = heavy if bold else regular
            path = next((d / name for d in FONT_DIRS if (d / name).exists()), None)
            if path:
                _fonts[key] = ImageFont.truetype(str(path), int(round(pt * 10))), scale   # 10 px per pt
                break
        else:
            _fonts[key] = ImageFont.load_default(int(round(pt * 10))), 1.1
    return _fonts[key]


def lines(text: str, pt: float, bold: bool, width_in: float, family: str = DEFAULT, tracking: float = 0) -> int:
    """Lines text wraps to in a box width_in wide; tracking is extra letter spacing in pt."""
    # 3% slack: PowerPoint's line breaking differs slightly from this measurement, so never fill a line to the edge
    (font, scale), max_px, total = _font(bold, pt, family), width_in * 72 * 10 * 0.97, 0
    width = lambda s: font.getlength(s) * scale + tracking * 10 * len(s)   # noqa: E731
    for para in text.split("\n"):
        line, n = "", 1
        for word in para.split():
            trial = f"{line} {word}".strip()
            if width(trial) <= max_px or not line:
                line = trial
            else:
                n, line = n + 1, word
        total += n
    return total


def fit(text: str, w: float, h: float, pt: float, floor: float, bold: bool = False, spacing: float = 1.2,
        family: str = DEFAULT, tracking: float = 0) -> float:
    """Largest size from pt down to floor (0.5 pt steps) at which text wraps inside w x h inches."""
    size = pt
    while size > floor and lines(text, size, bold, w, family, tracking) * size * spacing / 72 > h:
        size -= 0.5
    return size
