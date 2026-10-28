"""Project Kickoff (sample 05_Project_Kickoff): deep teal and orange, a left navigation panel that marks the current
section, numbered objectives."""

from ppt.designs.base import OVAL, RECT, ROUNDED, SAMPLES, WHITE, Design

NAV = ["Why change", "How it works", "Capabilities", "Impact", "Next steps"]
SECTION = {"statement": 0, "stats": 0, "problem": 0, "process": 1, "feature_grid": 2, "feature_focus": 2,
           "before_after": 3, "benefits": 3, "chart": 3, "quote": 3, "closing": 4, "agenda": -1}


class Programme(Design):
    id, name = "programme", "Project Kickoff"
    description = "Deep teal and orange with a left navigation panel that marks the current section, plus numbered objectives."
    tags = ["Light", "Structured"]
    sample = SAMPLES / "05_Project_Kickoff.pptx"
    HEAD, BODY = "Bookman Old Style", "Calibri"
    colors = dict(dk1="1E293B", lt1="FFFFFF", dk2="0F4C5C", lt2="EEF5F6", accent1="E36414", accent2="5F9EA0",
                  accent3="9A031E", accent4="FFD166", accent5="06A77D", accent6="7C8B99", hlink="E36414",
                  folHlink="0F4C5C")
    TEAL, ORANGE, CADET, YELLOW, GREEN, GRAY, NAVMUTED = "0F4C5C", "E36414", "5F9EA0", "FFD166", "06A77D", "64748B", "9FC1C7"
    INK, MUTED, ACCENT, STRONG = "1E293B", GRAY, ORANGE, TEAL
    SURFACE, LINE, RADIUS = "EEF5F6", "E2E8F0", 0.08

    def frame(self, kind, kicker, title):
        nav = SECTION.get(kind, 0)
        s = self.slide()
        self.shape(s, RECT, 0, 0, 2.6, 5.625, self.TEAL)
        self.text(s, self.c["app_name"].upper(), 0.4, 0.4, 2.0, 0.5, 11, self.YELLOW, bold=True, tracking=3,
                  anchor="middle", floor=8)
        for i, item in enumerate(NAV):
            y, cur = 1.2 + i * 0.48, i == nav
            if cur:
                self.shape(s, OVAL, 0.4, y + 0.13, 0.14, 0.14, self.ORANGE)
            self.text(s, item, 0.68, y, 1.8, 0.4, 14, WHITE if cur else self.NAVMUTED, bold=cur, anchor="middle")
        self.text(s, f"Product overview  ·  {self.date}", 0.4, 5.15, 2.0, 0.3, 10, self.NAVMUTED, floor=7.5)
        self.text(s, str(self.n), 9.0, 5.15, 0.5, 0.3, 10, self.GRAY, align="right")
        self.text(s, title or kicker, 3.0, 0.4, 6.5, 0.75, 24, self.TEAL, bold=True, font=self.HEAD, anchor="middle",
                  floor=15)
        if title and kicker:
            self.text(s, kicker.upper(), 3.0, 1.22, 6.5, 0.28, 11, self.ORANGE, bold=True, tracking=2, floor=8)
            return s, (3.0, 1.65, 6.5, 3.35)
        return s, (3.0, 1.35, 6.5, 3.65)

    def cover(self):
        c = self.c
        s = self.slide(self.TEAL)
        self.text(s, c["app_name"], 0.7, 0.5, 5.4, 2.0, 44, WHITE, bold=True, font=self.HEAD, anchor="bottom", floor=24)
        self.text(s, c["tagline"], 0.7, 2.7, 5.2, 0.85, 20, self.YELLOW, floor=14)
        self.text(s, c["pitch"], 0.7, 3.6, 5.2, 0.75, 12, self.NAVMUTED, floor=9.5)
        self.text(s, f"Product overview  ·  {self.date}", 0.7, 4.5, 5.2, 0.4, 12, WHITE)
        hot = {(2, 3), (4, 1), (5, 4)}
        for r in range(7):
            for col in range(6):
                on = (r, col) in hot
                self.shape(s, OVAL, 6.8 + col * 0.5, 1.0 + r * 0.5, 0.2, 0.2, self.ORANGE if on else self.CADET,
                           alpha=None if on else 0.7)

    def closing(self, sl):
        label, items = self.wrap_up(sl)
        s, (x, y, w, h) = self.frame("closing", label, sl["title"])
        for i, item in enumerate(items):
            ry = y + i * 0.58
            self.badge(s, "✓", x, ry + 0.06, 0.32, self.GREEN, pt=12, kind=ROUNDED, radius=0.06,
                       font="Segoe UI Symbol")
            self.text(s, item, x + 0.5, ry, w - 0.5, 0.45, 15, self.INK, anchor="middle", floor=11)
        self.shape(s, RECT, x, y + h - 0.6, w, 0.6, self.TEAL)
        self.text(s, sl["subtitle"] or self.c["app_name"], x + 0.2, y + h - 0.6, w - 0.4, 0.6, 14, WHITE, bold=True,
                  anchor="middle", floor=10)
