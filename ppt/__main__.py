"""
python -m ppt [narration.txt] [--url https://app [--try-forms]] [--template consulting] [--audience executive]
              [--length short] [--focus "ROI"] [--title "Product"] [--out deck.pptx]

Builds a pitch deck from a narration, call transcript or notes, and/or an app's link (explored page by page). The story is kept in <out>.work/deck.json, so running
again with another --template reuses it (no tokens); add --rewrite for a new story.
"""

import argparse
import sys
from pathlib import Path

from ppt.designs import DEFAULT, DESIGNS
from ppt.service import generate
from ppt.writer import AUDIENCES, LENGTHS


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="python -m ppt", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("narration", nargs="?", help="text file: narration, transcript (txt/srt/vtt) or notes")
    p.add_argument("--template", default=DEFAULT, choices=list(DESIGNS))
    p.add_argument("--title", default="", help="product name (default: taken from the text)")
    p.add_argument("--url", default="", help="app link: explored once, page by page; its screens become material "
                                             "and screenshots")
    p.add_argument("--try-forms", action="store_true",
                   help="while exploring, submit forms that are already filled in (demo/test apps only)")
    p.add_argument("--out", help="default: <narration>.pptx next to the text file, or deck.pptx")
    p.add_argument("--audience", default="auto", choices=list(AUDIENCES), help="who the deck is for")
    p.add_argument("--length", default="standard", choices=list(LENGTHS),
                   help="short ~6, standard ~10, detailed ~14 slides")
    p.add_argument("--focus", default="", help="what to emphasise, e.g. 'compliance and audit'")
    p.add_argument("--rewrite", action="store_true", help="write a new story even if one exists")
    args = p.parse_args()
    if not args.narration and not args.url:
        p.error("give a narration file, an --url, or both")
    src = Path(args.narration) if args.narration else None
    out = Path(args.out) if args.out else src.with_suffix(".pptx") if src else Path("deck.pptx")
    work = out.with_name(out.stem + ".work")
    deck, _ = generate(work, args.template, src.read_text(encoding="utf-8") if src else "", args.title, args.url,
                       args.rewrite, brief={"audience": args.audience, "length": args.length, "focus": args.focus},
                       try_forms=args.try_forms)
    out.write_bytes(deck.read_bytes())
    print(f"Saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
