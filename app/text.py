"""Text normalization and phrase search over OCR output."""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

_APOSTROPHES = "'’‘`´"


def normalize(text: str) -> str:
    """Lowercase, drop accents and apostrophes, turn other punctuation into spaces.

    "STONE'S THROW" and "Stone's Throw" both become "stones throw";
    "CHÂTEAU" becomes "chateau".
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    for mark in _APOSTROPHES:
        text = text.replace(mark, "")
    text = re.sub(r"[^\w\s]|_", " ", text.casefold())
    return " ".join(text.split())


@dataclass
class Token:
    norm: str
    word_index: int  # which OCR word this token came from


def tokenize(words: list[str]) -> list[Token]:
    return [Token(t, i) for i, w in enumerate(words) for t in normalize(w).split()]


def strip_edge_punctuation(text: str) -> str:
    return text.strip(" ,.;:")


@dataclass
class PhraseMatch:
    score: float  # 0-100; 100 means identical after normalization
    found: str  # the label's words as printed


def find_phrase(expected: str, words: list[str]) -> PhraseMatch | None:
    """Find the run of label words that best matches `expected`.

    Slides a window (expected length +/- 1 token) across the label so a phrase
    split over lines, or with a word dropped or added, still lines up.
    """
    target_tokens = normalize(expected).split()
    tokens = tokenize(words)
    if not target_tokens or not tokens:
        return None
    target = " ".join(target_tokens)

    best_score, best_window = -1.0, None
    n = len(target_tokens)
    for size in sorted({max(1, n - 1), n, n + 1}):
        for start in range(len(tokens) - size + 1):
            window = tokens[start : start + size]
            candidate = " ".join(t.norm for t in window)
            score = 100.0 if candidate == target else fuzz.ratio(target, candidate)
            if score > best_score:
                best_score, best_window = score, window
    if best_window is None:
        return None

    first, last = best_window[0].word_index, best_window[-1].word_index
    found = strip_edge_punctuation(" ".join(words[first : last + 1]))
    return PhraseMatch(score=best_score, found=found)
