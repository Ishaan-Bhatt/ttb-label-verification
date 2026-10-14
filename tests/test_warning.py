"""Warning-text logic on synthetic OCR output (no image or Tesseract needed)."""

import numpy as np

from app.models import Status
from app.ocr import OcrResult, Word
from app.warning import STANDARD_WARNING, check_warning


def ocr_of(text: str, conf: float = 95.0) -> OcrResult:
    # Boxes are too small to measure bold, so the bold check reports "review";
    # these tests look at the other sub-checks.
    words = [Word(t, i * 10, 0, 8, 8, conf, (1, 1, 1)) for i, t in enumerate(text.split())]
    return OcrResult(words=words, gray=np.full((20, 2000), 255, np.uint8))


def sub(result, key):
    return next(c for c in result.checks if c.key == key)


def test_standard_warning_wording_and_heading_match():
    result = check_warning(ocr_of("OLD TOM 750 mL " + STANDARD_WARNING + " Bardstown KY"))
    assert sub(result, "present").status == Status.MATCH
    assert sub(result, "heading").status == Status.MATCH
    assert sub(result, "wording").status == Status.MATCH
    assert result.differences == []


def test_title_case_heading_fails():
    text = STANDARD_WARNING.replace("GOVERNMENT WARNING:", "Government Warning:")
    result = check_warning(ocr_of(text))
    assert sub(result, "heading").status == Status.MISMATCH
    assert result.status == Status.MISMATCH


def test_missing_colon_needs_review():
    result = check_warning(ocr_of(STANDARD_WARNING.replace("WARNING:", "WARNING")))
    assert sub(result, "heading").status == Status.REVIEW


def test_missing_warning():
    result = check_warning(ocr_of("OLD TOM DISTILLERY 45% Alc./Vol. 750 mL"))
    assert result.status == Status.MISMATCH
    assert "No government warning" in result.message


def test_body_without_heading():
    body = STANDARD_WARNING.replace("GOVERNMENT WARNING: ", "")
    result = check_warning(ocr_of(body))
    assert result.status == Status.MISMATCH
    assert "heading is missing" in result.message


def test_changed_words_fail_and_are_listed():
    text = STANDARD_WARNING.replace("should not drink", "should avoid drinking")
    result = check_warning(ocr_of(text))
    assert sub(result, "wording").status == Status.MISMATCH
    assert [(d.expected, d.found) for d in result.differences] == [("not drink", "avoid drinking")]


def test_dropped_clause_fails():
    text = STANDARD_WARNING.replace(", and may cause health problems", "")
    result = check_warning(ocr_of(text))
    assert sub(result, "wording").status == Status.MISMATCH
    assert result.differences[-1].found == ""


def test_single_letter_misread_needs_review_not_fail():
    text = STANDARD_WARNING.replace("pregnancy", "pregnancv")
    result = check_warning(ocr_of(text))
    assert sub(result, "wording").status == Status.REVIEW


def test_text_after_warning_is_not_counted_as_a_difference():
    result = check_warning(ocr_of(STANDARD_WARNING + " Distilled and bottled by Old Tom Distillery"))
    assert sub(result, "wording").status == Status.MATCH
