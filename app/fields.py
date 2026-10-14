"""Compare each application field against the text read from the label."""

import re

from rapidfuzz import fuzz

from .models import Check, Status
from .text import find_phrase, normalize, strip_edge_punctuation, tokenize

# A fuzzy score at or above this is "probably the same, a person should look".
REVIEW_THRESHOLD = 80

FIELD_LABELS = {
    "brand_name": "Brand name",
    "class_type": "Class / type",
    "alcohol_content": "Alcohol content",
    "net_contents": "Net contents",
    "bottler": "Bottler / producer name and address",
    "country_of_origin": "Country of origin",
}


def _not_checked(key: str) -> Check:
    return Check(key, FIELD_LABELS[key], Status.NOT_CHECKED, "Not provided on the application, so not checked.")


def check_text_field(key: str, expected: str, words: list[str]) -> Check:
    """Brand name, class/type, country: same words required, case and punctuation forgiven."""
    expected = expected.strip()
    label = FIELD_LABELS[key]
    if not expected:
        return _not_checked(key)

    match = find_phrase(expected, words)
    if match and match.score == 100:
        if match.found == expected:
            message = "Exact match."
        else:
            message = "Matches. Only capitalization, punctuation or accents differ."
        return Check(key, label, Status.MATCH, message, expected, match.found)
    if match and match.score >= REVIEW_THRESHOLD:
        return Check(
            key, label, Status.REVIEW,
            "Close but not identical. Please compare the spelling.",
            expected, match.found,
        )
    return Check(key, label, Status.MISMATCH, "Not found on the label.", expected, None)


# --- Alcohol content -------------------------------------------------------

_PERCENT = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*%")
_PROOF = re.compile(r"(\d{1,3}(?:[.,]\d)?)\s*°?\s*proof", re.IGNORECASE)
_NUMBER = re.compile(r"\d{1,3}(?:[.,]\d{1,2})?")


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def _fmt(value: float) -> str:
    return f"{value:g}"


def parse_alcohol(text: str) -> tuple[float | None, float | None]:
    """Return (ABV percent, proof) from text like '45% Alc./Vol. (90 Proof)'."""
    pct = _PERCENT.search(text)
    proof = _PROOF.search(text)
    abv = _num(pct.group(1)) if pct else None
    proof_value = _num(proof.group(1)) if proof else None
    if abv is None and proof_value is None:
        bare = _NUMBER.search(text)
        abv = _num(bare.group()) if bare else None
    return abv, proof_value


def check_alcohol(expected: str, label_text: str) -> Check:
    key, label = "alcohol_content", FIELD_LABELS["alcohol_content"]
    expected = expected.strip()
    if not expected:
        return _not_checked(key)

    exp_abv, exp_proof = parse_alcohol(expected)
    if exp_abv is None and exp_proof is not None:
        exp_abv = exp_proof / 2
    if exp_abv is None:
        return Check(key, label, Status.REVIEW, "Couldn't understand the application value.", expected, None)

    label_pcts = [(m.group(0), _num(m.group(1))) for m in _PERCENT.finditer(label_text)]
    label_proofs = [(m.group(0), _num(m.group(1))) for m in _PROOF.finditer(label_text)]

    pct_hit = next((raw for raw, v in label_pcts if abs(v - exp_abv) < 0.01), None)
    if pct_hit is None:
        if label_pcts:
            raw = _closest_to_alcohol_wording(label_text, label_pcts)
            return Check(
                key, label, Status.MISMATCH,
                f"Label shows {raw}, application says {_fmt(exp_abv)}%.", expected, raw,
            )
        proof_hit = next((raw for raw, v in label_proofs if abs(v / 2 - exp_abv) < 0.01), None)
        if proof_hit:
            return Check(
                key, label, Status.REVIEW,
                "Label shows proof but no percentage. Please confirm.", expected, proof_hit,
            )
        return Check(key, label, Status.MISMATCH, "No alcohol percentage found on the label.", expected, None)

    found = pct_hit
    if exp_proof is not None:
        proof_hit = next((raw for raw, v in label_proofs if abs(v - exp_proof) < 0.01), None)
        if proof_hit:
            found = f"{pct_hit} ({proof_hit})"
        elif label_proofs:
            raw = label_proofs[0][0]
            return Check(
                key, label, Status.MISMATCH,
                f"Percentage matches, but label shows {raw} and the application says {_fmt(exp_proof)} proof.",
                expected, f"{pct_hit} ({raw})",
            )
        else:
            return Check(
                key, label, Status.REVIEW,
                f"Percentage matches, but {_fmt(exp_proof)} proof was not found on the label.",
                expected, pct_hit,
            )
    return Check(key, label, Status.MATCH, "Matches.", expected, found)


def _closest_to_alcohol_wording(text: str, candidates: list[tuple[str, float]]) -> str:
    """Of several percentages on a label, pick the one next to 'alc' or 'vol'.

    The context around each one stops at the neighboring numbers, so
    "100% corn. 45% Alc./Vol." credits "Alc" to 45%, not 100%.
    """
    for raw, _ in candidates:
        idx = text.find(raw)
        before = re.split(r"\d", text[max(0, idx - 20) : idx])[-1]
        after = re.split(r"\d", text[idx + len(raw) : idx + len(raw) + 20])[0]
        context = (before + after).lower()
        if "alc" in context or "vol" in context:
            return raw
    return candidates[0][0]


# --- Net contents ----------------------------------------------------------

_UNITS_ML = {
    "ml": 1.0, "milliliter": 1.0, "milliliters": 1.0, "millilitre": 1.0, "millilitres": 1.0,
    "cl": 10.0, "centiliter": 10.0, "centiliters": 10.0, "centilitre": 10.0, "centilitres": 10.0,
    "l": 1000.0, "liter": 1000.0, "liters": 1000.0, "litre": 1000.0, "litres": 1000.0,
    "floz": 29.5735, "fluidounce": 29.5735, "fluidounces": 29.5735, "oz": 29.5735,
}
_VOLUME = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(milliliters?|millilitres?|ml|centiliters?|centilitres?|cl|liters?|litres?|l"
    r"|fl\.?\s*oz\.?|fluid\s+ounces?|oz)(?![a-z])",
    re.IGNORECASE,
)


def parse_volumes(text: str) -> list[tuple[str, float]]:
    """All volumes in the text as (raw text, millilitres)."""
    found = []
    for m in _VOLUME.finditer(text):
        unit = re.sub(r"[\s.]", "", m.group(2).lower())
        found.append((strip_edge_punctuation(m.group(0)), _num(m.group(1)) * _UNITS_ML[unit]))
    return found


def check_net_contents(expected: str, label_text: str) -> Check:
    key, label = "net_contents", FIELD_LABELS["net_contents"]
    expected = expected.strip()
    if not expected:
        return _not_checked(key)

    exp = parse_volumes(expected)
    if not exp:
        return Check(key, label, Status.REVIEW, "Couldn't understand the application value.", expected, None)
    exp_ml = exp[0][1]

    on_label = parse_volumes(label_text)
    for raw, ml in on_label:
        if abs(ml - exp_ml) <= exp_ml * 0.01:
            return Check(key, label, Status.MATCH, "Matches.", expected, raw)
    if on_label:
        raw = on_label[0][0]
        return Check(key, label, Status.MISMATCH, f"Label shows {raw}, application says {expected}.", expected, raw)
    return Check(key, label, Status.MISMATCH, "No net contents found on the label.", expected, None)


# --- Name and address ------------------------------------------------------

def check_name_address(expected: str, words: list[str]) -> Check:
    """Addresses wrap across lines and get reformatted, so check word by word."""
    key, label = "bottler", FIELD_LABELS["bottler"]
    expected = expected.strip()
    if not expected:
        return _not_checked(key)

    exact = find_phrase(expected, words)
    if exact and exact.score == 100:
        return Check(key, label, Status.MATCH, "Matches.", expected, exact.found)

    exp_tokens = normalize(expected).split()
    label_tokens = {t.norm for t in tokenize(words)}
    close, missing = [], []
    for token in exp_tokens:
        if token in label_tokens:
            continue
        if len(token) >= 4 and any(fuzz.ratio(token, t) >= 85 for t in label_tokens):
            close.append(token)
        else:
            missing.append(token)

    if not close and not missing:
        return Check(
            key, label, Status.MATCH,
            "All words found on the label (spread across lines).", expected, None,
        )
    found_share = 1 - len(missing) / len(exp_tokens)
    problems = missing + close
    detail = ", ".join(f'"{t}"' for t in problems[:6])
    if found_share >= 0.7:
        return Check(
            key, label, Status.REVIEW,
            f"Mostly found. Please check: {detail}.", expected, None,
        )
    return Check(key, label, Status.MISMATCH, f"Not found on the label. Missing: {detail}.", expected, None)
