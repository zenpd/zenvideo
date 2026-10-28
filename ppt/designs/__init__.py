"""The deck designs: Zen Studio (the original product deck) and one per sample deck in ppt/assets/samples/."""

from ppt.designs.base import Design
from ppt.designs.consulting import Consulting
from ppt.designs.dashboard import Dashboard
from ppt.designs.editorial import Editorial
from ppt.designs.pitch_dark import PitchDark
from ppt.designs.programme import Programme
from ppt.designs.zen import Zen

DESIGNS: dict[str, type[Design]] = {d.id: d for d in (Zen, Consulting, PitchDark, Editorial, Dashboard, Programme)}
DEFAULT = "zen"


def design(template: str) -> type[Design]:
    if template not in DESIGNS:
        raise ValueError(f"unknown deck design {template!r} - one of {', '.join(DESIGNS)}")
    return DESIGNS[template]


def deck_file(template: str) -> str:
    """File name of a design's deck: deck.pptx for the default design, deck-<id>.pptx otherwise."""
    return "deck.pptx" if template == DEFAULT else f"deck-{template}.pptx"


def catalog() -> list[dict]:
    return [{"id": d.id, "name": d.name, "description": d.description, "tags": d.tags,
             "fonts": d.HEAD if d.HEAD == d.BODY else f"{d.HEAD} + {d.BODY}",
             "sample": bool(d.sample and d.sample.exists())} for d in DESIGNS.values()]
