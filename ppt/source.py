"""
Turn whatever text the user pastes into clean material for the story: a video narration (parts separated by '---',
stage directions such as 'Click "Approve"'), a meeting or call transcript (speaker labels, timestamps, filler words),
subtitles (SRT/VTT), or plain notes. Returns the spoken content as parts, in order.
"""

import re

MAX_WORDS = 6000          # beyond this the rest is dropped (cost); about 40 minutes of speech

_LEAD = r"^(?:then,?\s+|now,?\s+|next,?\s+|and\s+|first,?\s+|finally,?\s+)?"
STRONG_DIRECTION = re.compile(_LEAD + r"(click|tap|press|enter|type|send)\b", re.I)
WEAK_DIRECTION = re.compile(_LEAD + r"(scroll|select|open|go to|navigate|check the)\b", re.I)
SPEAKER = re.compile(r"^\s*(?:\[[^\]]{1,40}\]|[A-Z][\w.'-]*(?: [A-Z][\w.'-]*){0,2}|Speaker \d+)\s*:\s+", re.M)
FILLERS = re.compile(r"(?i)(?<![\w'])(?:um+|uh+|erm+|hmm+)(?![\w'])[,.]?\s*|,\s*you know,")


def _is_direction(clause: str) -> bool:
    if STRONG_DIRECTION.search(clause) or clause.endswith(":"):
        return True
    if re.fullmatch(r"[\"“'][^\"”']+[\"”']\.?", clause):
        return True
    return bool(WEAK_DIRECTION.search(clause)) and len(clause.split()) <= 8


def _strip_directions(text: str) -> str:
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        for clause in re.split(r"(?<=,)\s+(?=[A-Z])", sentence.strip()):
            if clause.strip() and not _is_direction(clause.strip()):
                kept.append(clause.strip())
    return re.sub(r",\s*$", ".", " ".join(kept))


def _chunk(text: str, size: int = 140) -> list[str]:
    """Split one long block (pasted subtitles, a transcript without paragraphs) at sentence ends every ~size words."""
    out, cur = [], []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        cur.append(sentence)
        if sum(len(s.split()) for s in cur) >= size:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def clean(text: str) -> list[str]:
    """The spoken content of a narration, transcript or notes, as parts in order."""
    t = text.replace("\r", "")
    t = re.sub(r"(?m)^\s*WEBVTT.*$|^\s*NOTE\b.*$", "", t)                                # VTT header/notes
    t = re.sub(r"(?m)^\s*\d+\s*$(?=\n\s*\d{1,2}:\d{2})", "", t)                          # SRT cue numbers
    t = re.sub(r"(?m)^.*-->.*$", "", t)                                                  # cue timings
    t = re.sub(r"(?m)^\s*\[?\(?\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?\)?\]?\s*$", "", t)   # timestamp lines
    t = re.sub(r"[\[(]\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?[\])]\s*", "", t)              # inline timestamps
    if len(SPEAKER.findall(t)) >= 3:                                                     # looks like a transcript
        t = SPEAKER.sub("", t)
    t = FILLERS.sub("", t)
    chunks = re.split(r"(?m)^\s*-{3,}\s*$", t)
    if len(chunks) == 1:
        chunks = re.split(r"\n\s*\n", t)
    parts = []
    for c in chunks:
        c = _strip_directions(re.sub(r"[ \t]+", " ", c.strip()))
        parts.extend(_chunk(c) if len(c.split()) > 260 else [c])
    parts = [p for p in parts if len(p.split()) >= 3]
    merged: list[str] = []
    for p in parts:   # a very short part (a one-liner between separators) joins the next one
        if merged and len(merged[-1].split()) < 12:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    out, total = [], 0
    for p in merged:
        if total >= MAX_WORDS:
            break
        words = p.split()[:MAX_WORDS - total]
        out.append(" ".join(words))
        total += len(words)
    return out
