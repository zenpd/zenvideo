"""Consulting (sample 01_Consulting_Strategy): white and direct - full-sentence action titles, a navy cover band,
labelled rows, chevron processes and a source line on every page."""

from pptx.enum.shapes import MSO_SHAPE

from ppt.designs.base import RECT, SAMPLES, WHITE, Design


class Consulting(Design):
    id, name = "consulting", "Consulting"
    description = "White and direct: full-sentence headlines, a navy cover band, labelled rows, chevron processes and a source line."
    tags = ["Light", "Executive"]
    sample = SAMPLES / "01_Consulting_Strategy.pptx"
    HEAD = BODY = "Arial"
    colors = dict(dk1="222222", lt1="FFFFFF", dk2="0B1F3A", lt2="F2F4F7", accent1="1B998B", accent2="5B7DB1",
                  accent3="A9B8CC", accent4="D64933", accent5="8C9AAD", accent6="F2C14E", hlink="1B998B",
                  folHlink="5B7DB1")
    INK, MUTED, NAVY, TEAL, PALE, GRAY = "222222", "4B5563", "0B1F3A", "1B998B", "A9B8CC", "6B7280"
    ACCENT, STRONG, SURFACE, LINE, RADIUS = TEAL, NAVY, "F2F4F7", "D1D5DB", None
    ACCENTS = [TEAL, "5B7DB1", NAVY, "D64933"]

    def frame(self, kind, kicker, title):
        s = self.slide()
        self.text(s, kicker, 6.0, 0.2, 3.5, 0.3, 10, self.GRAY, align="right", floor=8)
        self.text(s, f"Source: {self.c.get('source') or 'product narration'}", 0.5, 5.15, 8.0, 0.3, 10, self.GRAY,
                  anchor="middle")
        self.text(s, str(self.n), 9.0, 5.15, 0.5, 0.3, 10, self.GRAY, align="right", anchor="middle")
        if not title:
            return s, (0.5, 0.75, 9.0, 4.2)
        self.text(s, title, 0.5, 0.5, 9.0, 0.85, 20, self.NAVY, bold=True, floor=15)
        return s, (0.5, 1.5, 9.0, 3.45)

    def cover(self):
        c = self.c
        s = self.slide()
        self.shape(s, RECT, 0, 3.55, 10, 2.075, self.NAVY)
        self.text(s, "PRODUCT BRIEFING", 0.6, 0.45, 4, 0.3, 11, self.TEAL, bold=True, tracking=3)
        self.text(s, c["app_name"], 0.6, 0.9, 8.6, 1.6, 34, self.NAVY, bold=True, anchor="bottom", floor=24)
        self.text(s, c["tagline"], 0.6, 2.65, 8.6, 0.6, 16, self.INK, floor=12)
        self.text(s, c["pitch"], 0.6, 3.85, 8.8, 0.9, 14, WHITE, anchor="middle", floor=11)
        self.text(s, self.date, 0.6, 4.85, 6, 0.35, 12, self.PALE)

    def problem(self, sl):
        """Situation-style labelled rows: navy label, grey statement."""
        s, (x, y, w, h) = self.frame("problem", sl["kicker"], sl["title"])
        top = y
        if sl["intro"]:
            self.text(s, sl["intro"], x, y, w, 0.5, 13, self.MUTED, floor=10.5)
            top += 0.65
        rh = (y + h - top - 0.1 * (len(sl["points"]) - 1)) / len(sl["points"])
        size = self.fit_all([p["title"] for p in sl["points"]], 1.9, rh - 0.1, 14, 10, True)
        for i, p in enumerate(sl["points"]):
            ry = top + i * (rh + 0.1)
            self.shape(s, RECT, x, ry, 2.2, rh, self.NAVY)
            self.text(s, p["title"], x + 0.15, ry, 1.9, rh, size, WHITE, bold=True, align="center", anchor="middle")
            self.shape(s, RECT, x + 2.3, ry, w - 2.3, rh, self.SURFACE)
            self.text(s, p["body"], x + 2.55, ry, w - 2.8, rh, 14, self.INK, anchor="middle", floor=10)

    def process(self, sl):
        """Chevrons across the page, each step's detail underneath."""
        s, (x, y, w, h) = self.frame("process", sl["kicker"], sl["title"])
        top = y
        if sl["intro"]:
            self.text(s, sl["intro"], x, y, w, 0.5, 13, self.MUTED, floor=10.5)
            top += 0.7
        steps, depth, ch = sl["steps"], 0.25, 0.62
        cw = (w + (len(steps) - 1) * (depth - 0.05)) / len(steps)
        tw = cw - 2 * depth - 0.05
        size = self.fit_all([st["name"] for st in steps], tw, ch, 12, 8, True)
        for i, st in enumerate(steps):
            cx = x + i * (cw - depth + 0.05)
            kind = MSO_SHAPE.PENTAGON if i == 0 else MSO_SHAPE.CHEVRON
            shp = self.shape(s, kind, cx, top, cw, ch, self.TEAL if i == len(steps) - 1 else self.NAVY)
            shp.adjustments[0] = depth / ch
            self.text(s, st["name"], cx + depth, top, tw, ch, size, WHITE, bold=True, align="center", anchor="middle")
            self.text(s, st["body"], cx + 0.12, top + ch + 0.2, cw - depth - 0.2, y + h - top - ch - 0.2, 12,
                      self.INK, floor=9)

    def closing(self, sl):
        label, items = self.wrap_up(sl)
        s, (x, y, w, h) = self.frame("closing", label, sl["title"])
        for i, item in enumerate(items):
            ry = y + 0.1 + i * 0.75
            self.shape(s, RECT, x, ry, 0.08, 0.55, self.TEAL)
            self.text(s, f"{i + 1:02d}", x + 0.3, ry, 0.6, 0.55, 16, self.TEAL, bold=True, anchor="middle")
            self.text(s, item, x + 1.0, ry, w - 1.0, 0.55, 15, self.INK, anchor="middle", floor=11)
        self.shape(s, RECT, x, y + h - 0.6, w, 0.6, self.NAVY)
        self.text(s, sl["subtitle"] or self.c["app_name"], x + 0.25, y + h - 0.6, w - 0.5, 0.6, 14, WHITE, bold=True,
                  anchor="middle", floor=10)
