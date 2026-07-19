"""OCR-manba imlo tuzatish: ishonchli lug'at (faqat HF-manba fayllardan) va
5 ta ma'lum chalkashlik juftligi bo'yicha yuqori-ishonchli tuzatish."""

from pathlib import Path

from ufl.finalize.spellcheck import build_trusted_dictionary, correct_line, find_correction


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_trusted_dictionary_only_uses_hf_sourced_files(tmp_path):
    output_dir = tmp_path / "output"
    _write(output_dir / "web_news" / "corpus-a__news__shard-000001.txt", "qayta ishlash kerak.")
    _write(output_dir / "web_news" / "10763_kimdir.txt", "kayta ishlash kerak edi.")

    trusted = build_trusted_dictionary(output_dir)

    assert "qayta" in trusted
    assert "kayta" not in trusted  # ziyouz-manba, lug'atga qo'shilmaydi


def test_build_trusted_dictionary_lowercases_and_strips_trailing_punct(tmp_path):
    output_dir = tmp_path / "output"
    _write(output_dir / "reference" / "corpus-c__train__shard-000001.txt", "Kitob, juda qiziq!")

    trusted = build_trusted_dictionary(output_dir)

    assert "kitob" in trusted
    assert "qiziq" in trusted
    assert "Kitob," not in trusted


def test_find_correction_fixes_known_confusion():
    trusted = {"qayta", "kitob", "salom"}
    assert find_correction("kayta", trusted) == "qayta"


def test_find_correction_preserves_capitalization():
    trusted = {"qayta"}
    assert find_correction("Kayta", trusted) == "Qayta"


def test_find_correction_returns_none_when_word_already_trusted():
    trusted = {"kitob"}
    assert find_correction("kitob", trusted) is None


def test_find_correction_returns_none_when_no_candidate_found():
    trusted = {"salom"}
    assert find_correction("nomavjud", trusted) is None


def test_find_correction_returns_none_when_ambiguous():
    # "kaha" ikkita mustaqil chalkashlik juftligi orqali ikkita turli ishonchli
    # so'zga olib keladi: q/k juftligi "kaha"->"qaha", h/x juftligi "kaha"->"kaxa".
    # Ikkalasi ham trusted'da bo'lgani uchun (2 nomzod) — aniqmas, tuzatilmaydi.
    trusted = {"qaha", "kaxa"}
    assert find_correction("kaha", trusted) is None


def test_correct_line_applies_correction_and_calls_callback():
    trusted = {"qayta", "kitob"}
    calls = []
    result = correct_line(
        "kayta kitob o'qidim.", trusted, on_correction=lambda old, new: calls.append((old, new))
    )
    assert result == "qayta kitob o'qidim."
    assert calls == [("kayta", "qayta")]


def test_correct_line_calls_on_unresolved_for_unfixable_words():
    trusted = {"kitob"}
    unresolved = []
    result = correct_line(
        "gubla kitob.", trusted, on_unresolved=lambda word: unresolved.append(word)
    )
    assert result == "gubla kitob."
    assert unresolved == ["gubla"]


def test_correct_line_leaves_blank_line_unchanged():
    assert correct_line("", {"kitob"}) == ""
    assert correct_line("   ", {"kitob"}) == "   "
