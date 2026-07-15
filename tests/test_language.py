from ufl.clean.language import heuristic_score, is_uzbek, load_fasttext_predictor


def test_heuristic_score_high_for_real_uzbek_text():
    text = "Bu kitob juda qiziqarli bo'lib, u yerda ko'plab voqealar bor edi va uchun ham foydali."
    assert heuristic_score(text) > 0.3


def test_heuristic_score_low_for_english_text():
    text = "This book is very interesting and contains many events that were useful for the reader."
    assert heuristic_score(text) < 0.1


def test_heuristic_score_low_for_romanized_russian_text():
    text = "Eto ochen' interesnaya kniga kotoraya soderjit mnogo sobytiy"
    assert heuristic_score(text) < 0.15


def test_is_uzbek_true_when_heuristic_strong_even_without_fasttext():
    text = "Bu kitob juda qiziqarli bo'lib, u yerda ko'plab voqealar bor edi."
    result = is_uzbek(text)
    assert result.is_uzbek is True
    assert result.fasttext_label is None


def test_is_uzbek_false_for_english_without_fasttext():
    text = "This is clearly an English sentence with no Uzbek words at all here."
    result = is_uzbek(text)
    assert result.is_uzbek is False


def test_is_uzbek_uses_fasttext_when_confident_even_if_heuristic_weak():
    def fake_predict(text: str) -> tuple[str, float]:
        return ("uz", 0.9)

    result = is_uzbek("xyz abc qwe", fasttext_predict=fake_predict)
    assert result.is_uzbek is True
    assert result.fasttext_label == "uz"


def test_is_uzbek_rejects_when_both_fasttext_and_heuristic_weak():
    def fake_predict(text: str) -> tuple[str, float]:
        return ("en", 0.95)

    result = is_uzbek("xyz abc qwe", fasttext_predict=fake_predict)
    assert result.is_uzbek is False


def test_is_uzbek_ignores_fasttext_errors_gracefully():
    def broken_predict(text: str) -> tuple[str, float]:
        raise RuntimeError("model xato")

    text = "Bu kitob juda qiziqarli bo'lib, u yerda ko'plab voqealar bor edi."
    result = is_uzbek(text, fasttext_predict=broken_predict)
    assert result.is_uzbek is True  # gevristika hali ishlaydi
    assert result.fasttext_label is None


def test_load_fasttext_predictor_returns_none_when_model_missing(tmp_path):
    predictor = load_fasttext_predictor(tmp_path / "does_not_exist.ftz")
    assert predictor is None
