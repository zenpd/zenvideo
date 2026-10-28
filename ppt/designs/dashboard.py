"""QBR Dashboard (sample 04_QBR_Dashboard): a light-grey canvas of white tiles with soft shadows, coloured accent
strips, and a navy cover with dashboard tiles."""

from ppt.designs.base import RECT, ROUNDED, SAMPLES, WHITE, Design, shadow


class Dashboard(Design):
    id, name = "dashboard", "QBR Dashboard"
    description = "A light-grey canvas of white tiles with shadows, coloured accent strips and a navy cover with dashboard tiles."
    tags = ["Light", "Data"]
    sample = SAMPLES / "04_QBR_Dashboard.pptx"
    colors = dict(dk1="1F2937", lt1="FFFFFF", dk2="233044", lt2="EEF1F5", accent1="6D28D9", accent2="14B8A6",
                  accent3="F59E0B", accent4="EF4444", accent5="22C55E", accent6="94A3B8", hlink="6D28D9",
                  folHlink="233044")
    NAVY, CANVAS, PURPLE, TEAL, AMBER, GREEN, GRAY = "233044", "EEF1F5", "6D28D9", "14B8A6", "F59E0B", "22C55E", "64748B"
    INK, MUTED, BG, ACCENT, STRONG = "1F2937", GRAY, CANVAS, PURPLE, NAVY
    ACCENTS = [PURPLE, TEAL, AMBER, GREEN]
    SURFACE, LINE, RADIUS, CARD_SHADOW = WHITE, "E5E7EB", 0.08, shadow("000000", 0.08)

    def frame(self, kind, kicker, title):
        s = self.slide(self.CANVAS)
        self.text(s, title or kicker, 0.5, 0.25, 6.5, 0.55, 24, self.NAVY, bold=True, anchor="middle", floor=15)
        if title:
            self.text(s, kicker, 7.0, 0.3, 2.5, 0.45, 12, self.GRAY, align="right", anchor="middle", floor=9)
        self.text(s, f"{self.c['app_name']}  ·  Product overview", 0.5, 5.2, 5, 0.3, 10, self.GRAY, floor=8)
        self.text(s, str(self.n), 9.0, 5.2, 0.5, 0.3, 10, self.GRAY, align="right")
        return s, (0.5, 1.0, 9.0, 4.05)

    def cover_page(self, title, subtitle, note, meta):
        s = self.slide(self.NAVY)
        self.text(s, title, 0.6, 0.6, 4.8, 2.2, 36, WHITE, bold=True, anchor="bottom", floor=24)
        self.text(s, subtitle, 0.6, 2.95, 4.8, 0.75, 22, self.TEAL, bold=True, floor=13)
        self.text(s, note, 0.6, 3.75, 4.8, 0.75, 12, "CBD5E1", floor=9.5)
        self.text(s, meta, 0.6, 4.6, 4.8, 0.4, 12, "CBD5E1", floor=9)
        for x, y, w, h in [(5.9, 0.7, 1.7, 1.1), (7.8, 0.7, 1.7, 1.1), (5.9, 2.0, 3.6, 1.6), (5.9, 3.8, 1.7, 1.1),
                           (7.8, 3.8, 1.7, 1.1)]:
            self.shape(s, ROUNDED, x, y, w, h, "2E3D55", radius=0.08)
        for i, v in enumerate([0.5, 0.75, 0.6, 0.95, 0.8, 1.15, 1.0]):
            self.shape(s, RECT, 6.2 + i * 0.45, 3.35 - v, 0.28, v, self.TEAL if i == 6 else self.PURPLE)
        for x, y, color in [(6.15, 0.95, self.TEAL), (8.05, 0.95, self.AMBER), (6.15, 4.05, self.GREEN),
                            (8.05, 4.05, self.PURPLE)]:
            self.shape(s, RECT, x, y, 0.7, 0.12, color)
            self.shape(s, RECT, x, y + 0.3, 1.1, 0.25, "3B4C68")

    def cover(self):
        c = self.c
        self.cover_page(c["app_name"], c["tagline"], c["pitch"], f"Product overview  ·  {self.date}")

    def closing(self, sl):
        steps = "   ".join(f"{i + 1}. {st}" for i, st in enumerate(sl["next_steps"]))
        self.cover_page(sl["title"], sl["subtitle"], steps, f"{self.c['app_name']}  ·  {self.date}")
