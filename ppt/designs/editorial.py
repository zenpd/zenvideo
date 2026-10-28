"""Editorial Report (sample 03_Annual_Report_Editorial): a magazine feel - large serif type that isn't bold, ink and
gold, numbers instead of cards, half-page panels and full-bleed gold pull quotes."""

import datetime

from ppt.designs.base import QUOTE, RECT, SAMPLES, WHITE, Design


class Editorial(Design):
    id, name = "editorial", "Editorial Report"
    description = "A magazine feel: large serif type, ink and gold, half-page chapter panels and full-bleed pull quotes."
    tags = ["Light", "Serif"]
    sample = SAMPLES / "03_Annual_Report_Editorial.pptx"
    HEAD, BODY, HEAD_BOLD = "Cambria", "Calibri", False
    colors = dict(dk1="1D2433", lt1="FFFFFF", dk2="1D2433", lt2="F2F4F7", accent1="C98B2B", accent2="8FA9C4",
                  accent3="5E7A99", accent4="E9D3A8", accent5="7A8B5C", accent6="A3473A", hlink="C98B2B",
                  folHlink="5E7A99")
    INK, GOLD, GRAY = "1D2433", "C98B2B", "6B7280"
    MUTED, ACCENT, STRONG, LINE = "4B5563", GOLD, INK, "D1D5DB"
    SURFACE, RADIUS, MARKER = None, None, "number"

    def frame(self, kind, kicker, title):
        s = self.slide()
        self.text(s, f"{self.c['app_name']}  ·  Product overview", 0.6, 5.15, 5, 0.3, 10, self.GRAY, floor=8)
        self.text(s, str(self.n), 9.0, 5.15, 0.5, 0.3, 10, self.GRAY, align="right")
        if kicker:
            self.text(s, kicker.upper(), 0.6, 0.4, 8.8, 0.3, 11, self.GOLD, bold=True, tracking=3, floor=8)
        if not title:
            return s, (0.6, 0.9, 8.8, 4.05)
        size = self.fit(title, 8.8, 0.85, 32, 22, font=self.HEAD)
        self.text(s, title, 0.6, 0.72, 8.8, 0.85, size, self.INK, font=self.HEAD)
        top = self.bottom(title, 0.72, 8.8, size, font=self.HEAD) + 0.3
        return s, (0.6, top, 8.8, 4.95 - top)

    def pull_quote(self, quote, attribution):
        s = self.slide(self.GOLD)
        self.text(s, QUOTE, 0.8, 0.2, 2, 1.8, 160, self.INK, font=self.HEAD)
        self.text(s, quote, 0.8, 1.6, 8.2, 2.4, 32, self.INK, italic=True, font=self.HEAD, floor=20)
        self.text(s, attribution, 0.8, 4.2, 8, 0.4, 14, self.INK, bold=True, floor=10)

    def cover(self):
        c = self.c
        s = self.slide()
        self.shape(s, RECT, 0, 0, 4.6, 5.625, self.INK)
        self.text(s, "PRODUCT OVERVIEW", 0.6, 0.6, 3.6, 0.3, 12, WHITE, bold=True, tracking=4)
        self.text(s, str(datetime.date.today().year), 0.5, 3.3, 4.0, 1.5, 96, self.GOLD, font=self.HEAD,
                  anchor="bottom")
        self.text(s, c["app_name"], 5.1, 0.6, 4.4, 2.4, 40, self.INK, font=self.HEAD, anchor="bottom", floor=26)
        self.text(s, c["tagline"], 5.1, 3.2, 4.2, 0.8, 16, self.GRAY, floor=12)
        self.text(s, c["pitch"], 5.1, 4.05, 4.2, 0.9, 12, self.GRAY, floor=9.5)

    def quote(self, sl):
        self.pull_quote(sl["text"], sl["attribution"])

    def problem(self, sl):
        """The sample's letter layout: the problem as a large italic quote on the left, its points on the right."""
        s, _ = self.frame("problem", sl["kicker"], None)
        self.text(s, QUOTE, 0.5, 0.6, 1.2, 1.2, 96, self.GOLD, font=self.HEAD)
        self.text(s, sl["intro"] or sl["title"], 0.6, 1.6, 4.2, 2.25, 24, self.INK, italic=True, font=self.HEAD,
                  floor=14)
        self.text(s, sl["title"], 0.6, 4.0, 4.2, 0.6, 14, self.INK, bold=True, floor=10)
        ph = 4.1 / len(sl["points"])
        for i, p in enumerate(sl["points"]):
            y = 0.85 + i * ph
            self.text(s, f"{i + 1:02d}", 5.4, y, 0.6, 0.4, 16, self.GOLD, font=self.HEAD)
            self.text(s, p["title"], 6.0, y, 3.5, 0.4, 17, self.INK, font=self.HEAD, floor=12)
            self.text(s, p["body"], 6.0, y + 0.42, 3.5, ph - 0.55, 13, self.INK, floor=10)

    def closing(self, sl):
        attribution = "  ·  ".join(sl["next_steps"]) or sl["subtitle"] or self.c["app_name"]
        self.pull_quote(sl["title"] + (f". {sl['subtitle']}" if sl["next_steps"] and sl["subtitle"] else ""), attribution)
