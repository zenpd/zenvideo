"""
The PPT skill's one entry point: material in, deck out.

    generate(work_dir, template, narration=..., title=..., url=...) -> (deck path, token usage or None)

work_dir keeps everything a deck needs to be regenerated for free: narration.txt (the material), pages/ and pages.json
(the app explored page by page, only when a link was given - once), deck.json (the story). Switching design reuses the
story, so it costs no tokens; rewrite asks Azure for a new story; recapture explores the app again.

The material is the narration and/or the app tour (each screen's text and how it was reached); a link alone is enough.
"""

import json
from pathlib import Path

from ppt import source
from ppt.capture import capture_app
from ppt.designs import deck_file, design
from ppt.quality import polish
from ppt.writer import StoryError, add_usage, clean_brief, normalize, write_story

STORY_VERSION = 2      # deck.json written by an older version of the writer is rewritten, not reused


def story_is_fresh(work_dir: Path, brief: dict | None = None) -> bool:
    """deck.json was written by this writer version, for this brief (when given), after the material it is based on,
    so it can be reused."""
    story = work_dir / "deck.json"
    if not story.exists():
        return False
    try:
        saved = json.loads(story.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    # both sides cleaned: a brief saved before a field existed still matches
    if saved.get("version") != STORY_VERSION or (brief is not None and
                                                 clean_brief(saved.get("brief")) != clean_brief(brief)):
        return False
    inputs = [p for p in (work_dir / "narration.txt", work_dir / "pages.json") if p.exists()]
    return all(story.stat().st_mtime >= p.stat().st_mtime for p in inputs)


def _pages(work_dir: Path) -> list[dict]:
    f = work_dir / "pages.json"
    pages = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    return [p for p in pages if (work_dir / "pages" / p["file"]).exists()]


def _tour(pages: list[dict]) -> list[dict]:
    """The app tour the story is written from: each screen's id, how it was reached and what it shows."""
    tour = [{"screen": p["id"], "kind": p.get("kind") or "page", "via": p.get("via") or p["label"],
             "text": p["text"][:1500 if p.get("kind") == "result" else 900]} for p in pages]
    if tour:     # where the app shows its own name: the browser tab's title and the frame around the pages
        tour[0].update(page_title=pages[0].get("title") or "", app_frame=pages[0].get("frame") or "")
    return tour


def generate(work_dir: Path, template: str, narration: str = "", title: str = "", url: str = "",
             rewrite: bool = False, recapture: bool = False, log=print, brief: dict | None = None,
             try_forms: bool = False) -> tuple[Path, dict | None]:
    """Build the deck in the chosen design; returns its path and the story's token usage (None: story reused).
    brief: who the deck is for, how long, what to emphasise (ppt.writer.AUDIENCES / LENGTHS); a story written for
    another brief is rewritten. try_forms: while exploring, also submit forms that are already filled in."""
    brief = clean_brief(brief)
    work_dir.mkdir(parents=True, exist_ok=True)
    if url and (recapture or not (work_dir / "pages.json").exists()):
        log("Exploring the app page by page" + (" - forms already filled in are submitted" if try_forms else
                                                " (read-only)"))
        capture_app(url, work_dir, log, try_forms=try_forms)
    elif url:
        log("Reusing the explored screens")
    pages = _pages(work_dir) if url else []
    parts = source.clean(narration) if narration else []
    tour = _tour(pages)
    if not parts and not tour:
        raise StoryError("nothing to build the deck from - give a narration of at least a few sentences, or an app "
                         "link whose pages could be opened")
    # what the facts are checked against: names and claims - the narration and everything the app's screens show;
    # figures - only the narration (the screens' numbers are demo data, shown in the screenshots)
    material = "\n".join(parts + [f"{t['via']}: {t['text']}" for t in tour] +
                         [f"{t.get('page_title', '')} {t.get('app_frame', '')}" for t in tour[:1]] +
                         [f"{p['label']}: {'; '.join(p['headings'])}" for p in pages])
    screen_ids = [p["id"] for p in pages]
    story = work_dir / "deck.json"
    usage = None
    if not rewrite and story_is_fresh(work_dir, brief):
        log("Reusing the deck's story (deck.json) - no tokens spent")
        content = normalize(json.loads(story.read_text(encoding="utf-8")), material, screen_ids, title,
                            brief["length"], brief["instructions"], figures="\n".join(parts))
        content, _ = polish(content, material.split("\n"), log, repair=False, notes_from=parts)
    else:
        focus = f", focus: {brief['focus']}" if brief["focus"] else ""
        log(f"Material: {len(parts)} narration part(s), {len(tour)} app screen(s), {len(material.split()):,} words; "
            f"for {brief['audience']}, {brief['length']} length{focus}")
        raw, usage = write_story(parts, title, tour or None, log, brief)
        content = normalize(raw, material, screen_ids, title, brief["length"], brief["instructions"],
                            figures="\n".join(parts))
        content, fix = polish(content, material.split("\n"), log, repair=True, notes_from=parts)
        usage = add_usage(usage, fix)
    via = {p["id"]: p.get("via") for p in pages}
    for sl in content["slides"]:     # the talk track says where to show it in the app
        if via.get(sl.get("screen") or ""):
            sl["notes"] = "\n\n".join(x for x in (sl.get("notes"), f"In the app: {via[sl['screen']]}.") if x)
    content["source"] = ("product narration and live app" if parts and pages else "live app walkthrough" if pages
                         else "product narration")
    content["version"], content["brief"] = STORY_VERSION, brief
    story.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    out = work_dir / deck_file(template)
    shots = {p["id"]: work_dir / "pages" / p["file"] for p in pages}
    n = design(template)(content, shots).save(out)
    log(f"Deck ready: {n} slides ({', '.join(s['type'] for s in content['slides'])}) -> {out.name}")
    return out, usage
