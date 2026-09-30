"""Turn script text into what Kokoro actually says, and split it into subtitle/alignment tokens."""

import re
import unicodedata

from num2words import num2words

_CURRENCY = re.compile(r"\$\s?(\d+)(?:\.(\d{1,2}))?")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_DECIMAL = re.compile(r"\b(\d+)\.(\d+)\b")
_INTEGER = re.compile(r"\b\d+\b")


def _dollars(m: re.Match) -> str:
    whole = int(m.group(1))
    words = f"{num2words(whole)} {'dollar' if whole == 1 else 'dollars'}"
    if m.group(2):
        cents = int(m.group(2).ljust(2, "0"))
        if cents:
            words += f" and {num2words(cents)} {'cent' if cents == 1 else 'cents'}"
    return words


def _decimal(m: re.Match) -> str:
    return f"{num2words(int(m.group(1)))} point {' '.join(num2words(int(d)) for d in m.group(2))}"


def spoken(text: str) -> str:
    t = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("…", "...")
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    t = "".join(
        c for c in t
        if unicodedata.category(c) not in ("So", "Sk", "Cs", "Co", "Cn") and c not in "️‍"
    )
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
    t = _CURRENCY.sub(_dollars, t)
    t = _PERCENT.sub(lambda m: f"{m.group(1)} percent", t)
    t = _DECIMAL.sub(_decimal, t)
    t = _INTEGER.sub(lambda m: num2words(int(m.group(0))), t)
    t = t.replace("&", " and ")
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r",(\s*,)+", ",", t)
    return " ".join(t.split()).strip(" ,")


def norm(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", token.lower())


def tokens(spoken_text: str) -> list[str]:
    out: list[str] = []
    for tok in spoken_text.split():
        if not norm(tok) and out:
            out[-1] += tok
        else:
            out.append(tok)
    return out


def find_phrase(toks: list[str], phrase: str) -> int | None:
    """Index of the first token where the (normalized) phrase starts, or None."""
    want = [norm(w) for w in tokens(spoken(phrase)) if norm(w)]
    have = [norm(t) for t in toks]
    if not want:
        return None
    for i in range(len(have) - len(want) + 1):
        if have[i:i + len(want)] == want:
            return i
    return None
