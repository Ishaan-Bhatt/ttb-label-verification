from app.fields import (
    check_alcohol,
    check_name_address,
    check_net_contents,
    check_text_field,
    parse_alcohol,
    parse_volumes,
)
from app.models import Status
from app.text import normalize

LABEL_WORDS = "OLD TOM DISTILLERY Kentucky Straight Bourbon Whiskey 45% Alc./Vol. (90 Proof) 750 mL".split()
LABEL_TEXT = " ".join(LABEL_WORDS)


def test_normalize_forgives_case_apostrophes_and_accents():
    assert normalize("STONE'S THROW") == normalize("Stone’s Throw") == "stones throw"
    assert normalize("CHÂTEAU") == "chateau"


def test_brand_exact_match():
    check = check_text_field("brand_name", "OLD TOM DISTILLERY", LABEL_WORDS)
    assert check.status == Status.MATCH
    assert check.message == "Exact match."


def test_brand_case_difference_is_a_match_with_note():
    words = "STONE'S THROW Small Batch Gin".split()
    check = check_text_field("brand_name", "Stone's Throw", words)
    assert check.status == Status.MATCH
    assert "capitalization" in check.message
    assert check.found == "STONE'S THROW"


def test_brand_one_letter_off_needs_review():
    check = check_text_field("brand_name", "OLD TOM DISTILLERS", LABEL_WORDS)
    assert check.status == Status.REVIEW


def test_brand_absent_is_mismatch():
    check = check_text_field("brand_name", "Blue Heron Vodka", LABEL_WORDS)
    assert check.status == Status.MISMATCH


def test_empty_application_field_is_not_checked():
    assert check_text_field("country_of_origin", "  ", LABEL_WORDS).status == Status.NOT_CHECKED


def test_parse_alcohol():
    assert parse_alcohol("45% Alc./Vol. (90 Proof)") == (45.0, 90.0)
    assert parse_alcohol("13,5 %") == (13.5, None)
    assert parse_alcohol("45") == (45.0, None)


def test_alcohol_match_including_proof():
    check = check_alcohol("45% Alc./Vol. (90 Proof)", LABEL_TEXT)
    assert check.status == Status.MATCH


def test_alcohol_wrong_percentage():
    check = check_alcohol("40% Alc./Vol.", LABEL_TEXT)
    assert check.status == Status.MISMATCH
    assert "45%" in check.message


def test_alcohol_wrong_proof():
    check = check_alcohol("45% Alc./Vol. (80 Proof)", LABEL_TEXT)
    assert check.status == Status.MISMATCH


def test_alcohol_missing_from_label():
    assert check_alcohol("45%", "OLD TOM 750 mL").status == Status.MISMATCH


def test_alcohol_picks_the_percentage_next_to_alc():
    check = check_alcohol("40%", "Made with 100% corn. 45% Alc./Vol.")
    assert check.status == Status.MISMATCH
    assert check.found == "45%"


def test_parse_volumes_units():
    assert [ml for _, ml in parse_volumes("750 mL")] == [750]
    assert [ml for _, ml in parse_volumes("1.75 L")] == [1750]
    assert [ml for _, ml in parse_volumes("75cl")] == [750]
    assert round(parse_volumes("12 FL. OZ.")[0][1]) == 355


def test_net_contents_equivalent_units_match():
    assert check_net_contents("750 mL", "Contents 75 cl").status == Status.MATCH
    assert check_net_contents("750 ml", LABEL_TEXT).status == Status.MATCH


def test_net_contents_mismatch():
    check = check_net_contents("1 L", LABEL_TEXT)
    assert check.status == Status.MISMATCH
    assert check.found == "750 mL"


def test_address_across_lines_matches():
    words = "Distilled and Bottled by Old Tom Distillery Bardstown, Kentucky".split()
    check = check_name_address("Old Tom Distillery, Bardstown, Kentucky", words)
    assert check.status == Status.MATCH


def test_address_reordered_matches_word_by_word():
    words = "Bardstown, Kentucky Bottled by Old Tom Distillery".split()
    check = check_name_address("Old Tom Distillery, Bardstown, Kentucky", words)
    assert check.status == Status.MATCH


def test_address_wrong_city_needs_review():
    words = "Old Tom Distillery Louisville, Kentucky".split()
    check = check_name_address("Old Tom Distillery, Bardstown, Kentucky", words)
    assert check.status == Status.REVIEW
    assert "bardstown" in check.message
