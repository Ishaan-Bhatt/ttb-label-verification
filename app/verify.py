"""Run every check for one label and roll the results up into a verdict."""

import time

from . import fields
from .models import Status, Verification, worst
from .ocr import ImageError, OcrResult, read_label
from .warning import check_warning

APPLICATION_FIELDS = tuple(fields.FIELD_LABELS)

# Fewer words than this means OCR found essentially nothing usable.
MIN_WORDS = 5


def verify_label(image: bytes, application: dict[str, str]) -> Verification:
    started = time.perf_counter()
    ocr = read_label(image)
    if len(ocr.words) < MIN_WORDS:
        raise ImageError(
            "We couldn't read any text on this image. Please upload a clear, "
            "straight-on photo or scan of the label."
        )
    result = check_application(ocr, application)
    result.elapsed_ms = round((time.perf_counter() - started) * 1000)
    return result


def check_application(ocr: OcrResult, application: dict[str, str]) -> Verification:
    words = [w.text for w in ocr.words]
    text = ocr.text
    app = {k: (application.get(k) or "") for k in APPLICATION_FIELDS}

    checks = [
        fields.check_text_field("brand_name", app["brand_name"], words),
        fields.check_text_field("class_type", app["class_type"], words),
        fields.check_alcohol(app["alcohol_content"], text),
        fields.check_net_contents(app["net_contents"], text),
        fields.check_name_address(app["bottler"], words),
        fields.check_text_field("country_of_origin", app["country_of_origin"], words),
    ]
    warning = check_warning(ocr)

    statuses = [c.status for c in checks] + [warning.status]
    overall = worst(statuses)
    problems = sum(s == Status.MISMATCH for s in statuses)
    reviews = sum(s == Status.REVIEW for s in statuses)

    if overall == Status.MISMATCH:
        verdict = "fail"
        headline = f"{problems} problem{'s' if problems != 1 else ''} found"
        if reviews:
            headline += f", {reviews} more to review"
    elif overall == Status.REVIEW:
        verdict = "review"
        headline = f"{reviews} item{'s' if reviews != 1 else ''} need{'s' if reviews == 1 else ''} a closer look"
    else:
        verdict = "pass"
        headline = "Everything matches the application"

    return Verification(verdict, headline, checks, warning, text, elapsed_ms=0)
