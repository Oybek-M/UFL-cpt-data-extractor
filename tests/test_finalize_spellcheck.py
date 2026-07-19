"""OCR-manba imlo tuzatish: ishonchli lug'at (faqat HF-manba fayllardan) va
5 ta ma'lum chalkashlik juftligi bo'yicha yuqori-ishonchli tuzatish."""

from pathlib import Path

from ufl.finalize.spellcheck import (
    apply_known_corrections,
    build_trusted_dictionary,
    correct_line,
    find_correction,
    query_minimax_corrections,
)


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


class _FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def _minimax_body(corrections: dict) -> dict:
    import json

    return {"choices": [{"message": {"content": json.dumps({"corrections": corrections})}}]}


def test_query_minimax_corrections_returns_empty_without_api_key():
    corrections, calls = query_minimax_corrections(["gubla"], api_key="")
    assert corrections == {}
    assert calls == 0


def test_query_minimax_corrections_returns_empty_for_empty_word_list():
    corrections, calls = query_minimax_corrections([], api_key="fake-key")
    assert corrections == {}
    assert calls == 0


def test_query_minimax_corrections_parses_response():
    def fake_post(url, headers, json_body, timeout):
        return _FakeResponse(200, _minimax_body({"gubla": "gulla", "xyzabc": None}))

    corrections, calls = query_minimax_corrections(
        ["gubla", "xyzabc"], api_key="fake-key", post=fake_post
    )
    assert corrections == {"gubla": "gulla"}
    assert calls == 1


def test_query_minimax_corrections_batches_large_word_lists():
    call_log = []

    def fake_post(url, headers, json_body, timeout):
        call_log.append(json_body)
        return _FakeResponse(200, _minimax_body({}))

    words = [f"word{i}" for i in range(5)]
    _, calls = query_minimax_corrections(words, api_key="fake-key", post=fake_post, batch_size=2)

    assert calls == 3  # 5 so'z, batch_size=2 -> 3 so'rov (2+2+1)


def test_query_minimax_corrections_returns_empty_on_network_error():
    def fake_post(url, headers, json_body, timeout):
        raise ConnectionError("network down")

    corrections, calls = query_minimax_corrections(["gubla"], api_key="fake-key", post=fake_post)
    assert corrections == {}
    assert calls == 1  # urinish qilindi, lekin xato bo'ldi


def test_query_minimax_corrections_returns_empty_on_bad_status():
    def fake_post(url, headers, json_body, timeout):
        return _FakeResponse(401, {})

    corrections, calls = query_minimax_corrections(["gubla"], api_key="fake-key", post=fake_post)
    assert corrections == {}
    assert calls == 1


def test_apply_known_corrections_replaces_matching_words():
    corrections = {"gubla": "gulla"}
    calls = []
    result = apply_known_corrections(
        "Bu gubla, chiroyli.", corrections, on_correction=lambda old, new: calls.append((old, new))
    )
    assert result == "Bu Gulla, chiroyli."
    assert calls == [("gubla,", "Gulla,")]


def test_apply_known_corrections_leaves_unmatched_words_unchanged():
    result = apply_known_corrections("Bu kitob edi.", {"gubla": "gulla"})
    assert result == "Bu kitob edi."
