"""Estimate whether words are set in bold type by measuring stroke thickness.

OCR returns text, not font weight, so we measure it from the pixels: for a run
of ink with stroke width w and length L, area ~ w*L and perimeter ~ 2L, so
w ~ 2 * area / perimeter.

The heading is compared with words from the rest of the statement in the same
image, so blur, resolution and font size affect both sides equally. Measured on
the sample labels (clean, photographed and half-resolution), a bold heading is
1.4-2.1x thicker than the body text and a regular one 1.05-1.15x.
"""

import statistics

import cv2
import numpy as np

from .ocr import Word

# Words shorter than this (in pixels) are too low-resolution to judge.
MIN_HEIGHT_PX = 12

# Heading-vs-body thickness ratio thresholds; between the two is "unsure".
BOLD_RATIO = 1.3
NOT_BOLD_RATIO = 1.2

# Stroke width / letter height above which body text looks bold on its own.
# Regular samples measured 0.10-0.16, bold ones 0.19-0.20.
BOLD_ABSOLUTE = 0.175

_ASCENDERS = set("bdfhklt")
_DESCENDERS = set("gjpqy")


def stroke_width(gray: np.ndarray, word: Word) -> float | None:
    if word.height < MIN_HEIGHT_PX or word.width < 4:
        return None
    pad = 2
    y0, x0 = max(0, word.top - pad), max(0, word.left - pad)
    crop = gray[y0 : word.top + word.height + pad, x0 : word.left + word.width + pad]
    if crop.size == 0:
        return None
    _, ink = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    area = cv2.countNonZero(ink)
    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    perimeter = sum(cv2.arcLength(c, True) for c in contours)
    if area == 0 or perimeter == 0:
        return None
    return 2 * area / perimeter


def is_cap_height_word(text: str) -> bool:
    """True for words whose box height is about the capital-letter height.

    Words like "the" or "birth" (ascenders, no descenders) are the fairest
    comparison for an all-caps heading.
    """
    if not text.isalpha():
        return False
    letters = set(text)
    has_tall = any(c.isupper() for c in text) or bool(letters & _ASCENDERS)
    return has_tall and not (letters & _DESCENDERS)


def measure(gray: np.ndarray, words: list[Word]) -> tuple[float, float] | None:
    """Median (stroke width, letter height) in pixels, or None if unmeasurable."""
    pairs = [(sw, w.height) for w in words if (sw := stroke_width(gray, w)) is not None]
    if not pairs:
        return None
    return statistics.median(p[0] for p in pairs), statistics.median(p[1] for p in pairs)
