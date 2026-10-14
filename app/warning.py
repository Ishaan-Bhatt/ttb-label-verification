"""Government Health Warning Statement check (27 CFR 16.21 and 16.22).

Required on every label, word for word. "GOVERNMENT WARNING" must be in capital
letters and bold type; the rest of the statement may not be bold.
"""

from difflib import SequenceMatcher

from rapidfuzz import fuzz

from . import bold
from .models import Check, Difference, Status, WarningResult, worst
from .ocr import OcrResult, Word
from .text import normalize, tokenize

STANDARD_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)
HEADING = "GOVERNMENT WARNING:"
_BODY_TOKENS = normalize(STANDARD_WARNING[len(HEADING):]).split()

# When OCR confidence on the warning is at least this, wording differences are
# treated as real rather than as misreads.
CONFIDENT_OCR = 80


def _find_heading(words: list[Word]) -> tuple[int, int] | None:
    """Return (index of first heading word, number of heading words)."""
    norms = [normalize(w.text) for w in words]
    for i, norm in enumerate(norms):
        if fuzz.ratio(norm, "government warning") >= 85 or fuzz.ratio(norm, "governmentwarning") >= 85:
            return i, 1
        if i + 1 < len(norms) and fuzz.ratio(norm, "government") >= 80 and fuzz.ratio(norms[i + 1], "warning") >= 80:
            return i, 2
    return None


def _find_body_without_heading(words: list[Word]) -> int | None:
    tokens = tokenize([w.text for w in words])
    target = "according to the surgeon general"
    for i in range(len(tokens) - 4):
        if fuzz.ratio(" ".join(t.norm for t in tokens[i : i + 5]), target) >= 85:
            return tokens[i].word_index
    return None


def check_warning(ocr: OcrResult) -> WarningResult:
    words = ocr.words
    heading = _find_heading(words)

    if heading is None:
        if _find_body_without_heading(words) is not None:
            message = 'Warning text found, but the "GOVERNMENT WARNING:" heading is missing.'
        else:
            message = "No government warning statement found on the label."
        present = Check("present", "Warning statement present", Status.MISMATCH, message)
        return WarningResult(Status.MISMATCH, message, [present])

    start, count = heading
    heading_words = words[start : start + count]
    body_words, differences, wording = _check_wording(words, start + count)

    checks = [
        Check("present", "Warning statement present", Status.MATCH, "Found on the label."),
        _check_heading_caps(heading_words, words, start + count),
        _check_bold(ocr, heading_words, body_words),
        wording,
    ]
    status = worst(c.status for c in checks)
    found_text = " ".join(w.text for w in heading_words + body_words)

    if status == Status.MATCH:
        message = "Matches the required statement and formatting."
    else:
        message = " ".join(c.message for c in checks if c.status == status)
    return WarningResult(status, message, checks, found_text, differences)


def _check_heading_caps(heading_words: list[Word], words: list[Word], after: int) -> Check:
    key, label = "heading", 'Heading reads "GOVERNMENT WARNING:" in capitals'
    raw = " ".join(w.text for w in heading_words)
    letters = [c for c in raw if c.isalpha()]

    lowercase = sum(c.islower() for c in letters)
    if lowercase > 1:
        message = f'Heading must be all capitals. Label shows "{raw}".'
        return Check(key, label, Status.MISMATCH, message, HEADING, raw)
    if lowercase == 1:
        # One stray lowercase letter is more likely a misread than a real violation.
        return Check(key, label, Status.REVIEW, f'Heading may not be all capitals: "{raw}".', HEADING, raw)

    has_colon = raw.endswith(":") or (after < len(words) and words[after].text.startswith(":"))
    if not has_colon:
        return Check(key, label, Status.REVIEW, "Colon after the heading was not detected.", HEADING, raw)
    return Check(key, label, Status.MATCH, "In capital letters.", HEADING, raw)


def _check_wording(words: list[Word], body_start: int) -> tuple[list[Word], list[Difference], Check]:
    key, label = "wording", "Wording matches word for word"
    window = words[body_start : body_start + len(_BODY_TOKENS) + 15]
    tokens = tokenize([w.text for w in window])
    label_norms = [t.norm for t in tokens]

    matcher = SequenceMatcher(None, _BODY_TOKENS, label_norms, autojunk=False)
    # The window may run past the warning into other label text; end it after
    # the last solid run of matching words.
    solid = [b for b in matcher.get_matching_blocks() if b.size >= 2]
    if not solid:
        msg = "The text after the heading doesn't match the required statement."
        return [], [], Check(key, label, Status.MISMATCH, msg)
    end = solid[-1].b + solid[-1].size
    tokens, label_norms = tokens[:end], label_norms[:end]
    matcher = SequenceMatcher(None, _BODY_TOKENS, label_norms, autojunk=False)
    body_words = window[: tokens[-1].word_index + 1]

    def label_words(j1: int, j2: int) -> str:
        if j1 == j2:
            return ""
        idx = sorted({t.word_index for t in tokens[j1:j2]})
        return " ".join(window[i].text for i in idx)

    differences = []
    likely_misread = True
    changed = 0
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        differences.append(Difference(" ".join(_BODY_TOKENS[i1:i2]), label_words(j1, j2)))
        changed += max(i2 - i1, j2 - j1)
        same_shape = op == "replace" and (i2 - i1) == (j2 - j1)
        if not same_shape or any(
            fuzz.ratio(a, b) < 75 for a, b in zip(_BODY_TOKENS[i1:i2], label_norms[j1:j2])
        ):
            likely_misread = False

    if not differences:
        return body_words, [], Check(key, label, Status.MATCH, "Matches the required text word for word.")

    confidence = sum(w.conf for w in body_words) / len(body_words)
    if likely_misread and changed <= 3:
        msg = "Small differences. Could be a misread or a changed word. Please compare."
        return body_words, differences, Check(key, label, Status.REVIEW, msg)
    if confidence < CONFIDENT_OCR and matcher.ratio() < 0.8:
        msg = "The warning text couldn't be read clearly. Please check it by eye."
        return body_words, differences, Check(key, label, Status.REVIEW, msg)
    msg = f"Differs from the required statement in {len(differences)} place{'s' if len(differences) > 1 else ''}."
    return body_words, differences, Check(key, label, Status.MISMATCH, msg)


def _check_bold(ocr: OcrResult, heading_words: list[Word], body_words: list[Word]) -> Check:
    key, label = "bold", "Heading in bold, rest of statement not bold"
    reference = [w for w in body_words if bold.is_cap_height_word(w.text)]
    heading = bold.measure(ocr.gray, heading_words)
    body = bold.measure(ocr.gray, reference)

    if heading is None or body is None:
        return Check(key, label, Status.REVIEW, "The image resolution is too low to judge bold type. Please check by eye.")

    ratio = heading[0] / body[0]
    body_looks_bold = body[0] / body[1] >= bold.BOLD_ABSOLUTE
    if ratio >= bold.BOLD_RATIO:
        if body_looks_bold:
            return Check(key, label, Status.REVIEW, "Heading is bold, but the rest of the statement may also be bold. Please check.")
        return Check(key, label, Status.MATCH, "Heading is bold. The rest is regular weight.")
    if ratio <= bold.NOT_BOLD_RATIO:
        # The heading is no heavier than the text after it, which breaks the
        # rule either way: say which way it most likely breaks it.
        if body_looks_bold:
            return Check(key, label, Status.MISMATCH, "The whole statement appears bold. Only the heading may be bold.")
        return Check(key, label, Status.MISMATCH, "Heading does not appear to be in bold type.")
    return Check(key, label, Status.REVIEW, "Can't tell for sure whether the heading is bold. Please check by eye.")
