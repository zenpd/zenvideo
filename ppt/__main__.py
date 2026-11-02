"""
python -m ppt [narration.txt] [--doc plan.docx --doc figures.xlsx] [--url https://app [--try-forms]]
              [--template consulting] [--audience executive] [--length short] [--focus "ROI"] [--title "Product"]
              [--report] [--out deck.pptx]

Builds a pitch deck from a narration, call transcript or notes, documents (Word, PDF, Excel) and/or an app's link
(explored page by page); --report also writes a Word report (<out>.docx) from the same material. The story is kept in <out>.work/deck.json, so running
again with another --template reuses it (no tokens); add --rewrite for a new story.
"""

import argparse
import shutil
import sys
from pathlib import Path

from ppt.designs import DEFAULT, DESIGNS
from ppt.documents import KINDS
from ppt.service import generate, report
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
    p.add_argument("--doc", action="append", default=[], help="a Word (.docx), PDF or Excel (.xlsx) file; repeat for more")
    p.add_argument("--report", action="store_true", help="also write a Word report from the same material")
    args = p.parse_args()
    if not args.narration and not args.url and not args.doc:
        p.error("give a narration file, --doc files, an --url, or any mix")
    for d in args.doc:
        if Path(d).suffix.lower() not in KINDS or not Path(d).exists():
            p.error(f"{d}: not an existing Word (.docx), PDF or Excel (.xlsx) file")
    src = Path(args.narration) if args.narration else None
    first = Path(args.doc[0]) if args.doc else None
    out = Path(args.out) if args.out else (src or first).with_suffix(".pptx") if src or first else Path("deck.pptx")
    work = out.with_name(out.stem + ".work")
    if args.doc:      # the documents the deck is made from: work/docs/, read again when they change
        (work / "docs").mkdir(parents=True, exist_ok=True)
        for old in (work / "docs").iterdir():
            if old.name not in {Path(d).name for d in args.doc}:
                old.unlink()
        for d in args.doc:
            if not (work / "docs" / Path(d).name).exists() or Path(d).stat().st_mtime > (work / "docs" / Path(d).name).stat().st_mtime:
                shutil.copy2(d, work / "docs" / Path(d).name)
    brief = {"audience": args.audience, "length": args.length, "focus": args.focus}
    narration = src.read_text(encoding="utf-8") if src else ""
    deck, _ = generate(work, args.template, narration, args.title, args.url, args.rewrite, brief=brief,
                       try_forms=args.try_forms)
    out.write_bytes(deck.read_bytes())
    print(f"Saved {out}")
    if args.report:
        doc, _ = report(work, args.template, narration, args.title, args.url, brief=brief, rewrite=args.rewrite)
        out.with_suffix(".docx").write_bytes(doc.read_bytes())
        print(f"Saved {out.with_suffix('.docx')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
