from pathlib import Path

import pytest

from ufl.clean.transliterate import to_latin

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "translit_pairs.tsv"


def _load_pairs() -> list[tuple[str, str]]:
    pairs = []
    for line in FIXTURES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cyrillic, latin = line.split("\t")
        pairs.append((cyrillic, latin))
    return pairs


@pytest.mark.parametrize("cyrillic,expected", _load_pairs())
def test_to_latin_golden_pairs(cyrillic: str, expected: str):
    assert to_latin(cyrillic) == expected


def test_to_latin_passes_through_already_latin_text():
    assert to_latin("Bu allaqachon lotin matn.") == "Bu allaqachon lotin matn."


def test_to_latin_preserves_punctuation_and_digits():
    assert to_latin("Китоб 2024-йил, 45-бет.") == "Kitob 2024-yil, 45-bet."


def test_to_latin_drops_soft_sign_and_keeps_apostrophe_for_hard_sign():
    assert to_latin("маъно ва толь") == "ma'no va tol"
