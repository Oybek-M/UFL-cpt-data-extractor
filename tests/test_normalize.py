from ufl.clean.normalize import normalize


def test_normalize_unifies_apostrophe_variants_to_ascii():
    text = "o‘zbek g’alaba oʻzbek oʼzbek"
    assert normalize(text) == "o'zbek g'alaba o'zbek o'zbek"


def test_normalize_can_use_unicode_apostrophe_mode():
    assert normalize("o'zbek", apostrophe_mode="unicode") == "oʻzbek"


def test_normalize_unifies_quotes_to_straight_double():
    text = "«Salom» va “dunyo”"
    assert normalize(text) == '"Salom" va "dunyo"'


def test_normalize_collapses_horizontal_whitespace():
    assert normalize("Bu   juda\t\tortiqcha   bo'shliq") == "Bu juda ortiqcha bo'shliq"


def test_normalize_strips_trailing_line_whitespace():
    assert normalize("Birinchi qator   \nIkkinchi qator") == "Birinchi qator\nIkkinchi qator"


def test_normalize_collapses_excess_blank_lines_to_one_paragraph_break():
    assert normalize("Birinchi.\n\n\n\nIkkinchi.") == "Birinchi.\n\nIkkinchi."


def test_normalize_joins_hyphenated_line_break_word():
    assert normalize("Bu so'z chi-\nroyli bo'ldi.") == "Bu so'z chiroyli bo'ldi."


def test_normalize_converts_dashes_to_hyphen():
    text = "2020—2024 va 10–20"
    assert normalize(text) == "2020-2024 va 10-20"


def test_normalize_removes_invisible_characters():
    assert normalize("so​z﻿") == "soz"


def test_normalize_applies_unicode_nfc():
    decomposed = "café"  # "café" ning NFD (dekompozitsiyalangan) shakli
    assert normalize(decomposed) == "café"
