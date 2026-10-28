"""Startup Pitch Dark (sample 02_Startup_Pitch_Dark): dark throughout, orange kicker labels, huge type and numbers,
rounded cards and bold circles."""

from ppt.designs.base import OVAL, ROUNDED, SAMPLES, WHITE, Design


class PitchDark(Design):
    id, name = "pitch-dark", "Startup Pitch Dark"
    description = "Dark throughout, with orange kicker labels, huge type, rounded cards and bold circles. Built for investors."
    tags = ["Dark", "Bold"]
    sample = SAMPLES / "02_Startup_Pitch_Dark.pptx"
    HEAD = BODY = "Arial"
    colors = dict(dk1="0E0E12", lt1="FFFFFF", dk2="1C1C26", lt2="A1A1AA", accent1="FF5A36", accent2="B8B5FF",
                  accent3="2A2A35", accent4="FFB199", accent5="6EE7B7", accent6="FDE68A", hlink="FF5A36",
                  folHlink="B8B5FF")
    BG, CARD, ORANGE, LAV = "0E0E12", "1C1C26", "FF5A36", "B8B5FF"
    INK, MUTED, ACCENT, STRONG, ON_STRONG = WHITE, "A1A1AA", ORANGE, ORANGE, "0E0E12"
    ACCENTS = [ORANGE, LAV, "FFB199", "6EE7B7"]
    SURFACE, LINE, RADIUS = CARD, "2A2A35", 0.15

    def frame(self, kind, kicker, title):
        s = self.slide(self.BG)
        self.text(s, (kicker or "").upper(), 0.6, 0.45, 8.8, 0.3, 12, self.ORANGE, bold=True, tracking=3, floor=9)
        self.text(s, self.c["app_name"], 0.6, 5.15, 5, 0.3, 12, self.LAV, bold=True, floor=9)
        self.text(s, str(self.n), 9.0, 5.15, 0.5, 0.3, 10, self.MUTED, align="right")
        if not title:
            return s, (0.6, 0.95, 8.8, 4.0)
        size = self.fit(title, 8.8, 1.1, 30, 20, bold=True)
        self.text(s, title, 0.6, 0.8, 8.8, 1.1, size, WHITE, bold=True)
        top = self.bottom(title, 0.8, 8.8, size, bold=True) + 0.3
        return s, (0.6, top, 8.8, 4.95 - top)

    def cover(self):
        c = self.c
        s = self.slide(self.BG)
        self.shape(s, OVAL, 6.0, -1.0, 5.2, 5.2, self.ORANGE)
        self.shape(s, OVAL, 5.3, 3.5, 1.5, 1.5, self.LAV)
        self.text(s, c["app_name"], 0.6, 0.5, 5.2, 2.0, 66, WHITE, bold=True, anchor="bottom", floor=32)
        self.text(s, c["tagline"], 0.6, 2.7, 4.6, 0.9, 20, self.MUTED, floor=14)
        self.text(s, f"PRODUCT DEMO  ·  {self.date.upper()}", 0.6, 4.6, 4.6, 0.4, 12, self.LAV, bold=True, tracking=2,
                  floor=9)

    def problem(self, sl):
        """Huge numbers over each pain point, as in the sample's problem slide."""
        s, (x, y, w, h) = self.frame("problem", sl["kicker"], sl["title"])
        top = y
        if sl["intro"]:
            self.text(s, sl["intro"], x, y, w, 0.6, 14, self.MUTED, floor=10)
            top += 0.75
        cols, cw = self.columns(x, w, len(sl["points"]), 0.3)
        for i, ((cx, _), p) in enumerate(zip(cols, sl["points"])):
            self.text(s, f"{i + 1:02d}", cx, top, cw, 0.9, 54, self.ORANGE if i == 0 else WHITE, bold=True)
            self.text(s, p["title"], cx, top + 0.98, cw, 0.4, 16, WHITE, bold=True, floor=12)
            self.text(s, p["body"], cx, top + 1.4, cw, y + h - top - 1.4, 13, self.MUTED, floor=9.5)

    def closing(self, sl):
        s, (x, y, w, h) = self.frame("closing", "Thank you", sl["title"])
        self.shape(s, OVAL, 6.6, 1.9, 3.0, 3.0, self.ORANGE, alpha=0.9)
        top = max(2.3, y + 0.2)
        self.text(s, self.c["app_name"], 0.6, top, 5.6, 0.45, 20, WHITE, bold=True, floor=14)
        self.text(s, sl["subtitle"], 0.6, top + 0.5, 5.6, 0.75, 16, self.LAV, floor=12)
        for i, st in enumerate(sl["next_steps"]):
            ry = top + 1.4 + i * 0.45
            self.shape(s, ROUNDED, 0.6, ry, 5.4, 0.36, self.CARD, radius=0.18)
            self.text(s, f"{i + 1}   {st}", 0.8, ry, 5.0, 0.36, 12, WHITE, anchor="middle", floor=9)
