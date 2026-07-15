import pytest

from ufl.stats.tokens import count_tokens, estimate_tokens, load_tokenizer_counter


def test_estimate_tokens_uses_chars_per_token_ratio():
    text = "a" * 40
    assert estimate_tokens(text, chars_per_token=4.0) == 10


def test_estimate_tokens_has_minimum_one_for_nonempty_text():
    assert estimate_tokens("abc", chars_per_token=4.0) == 1


def test_estimate_tokens_zero_for_empty_text():
    assert estimate_tokens("", chars_per_token=4.0) == 0


def test_estimate_tokens_rejects_non_positive_ratio():
    with pytest.raises(ValueError):
        estimate_tokens("abc", chars_per_token=0)


def test_count_tokens_without_exact_counter_returns_none_exact():
    result = count_tokens("Bu sinov matni.", chars_per_token=4.0)
    assert result.char_count == len("Bu sinov matni.")
    assert result.estimated_tokens > 0
    assert result.exact_tokens is None


def test_count_tokens_uses_exact_counter_when_provided():
    def fake_counter(text: str) -> int:
        return len(text.split())

    result = count_tokens("Bu besh soz iborat gap", chars_per_token=4.0, exact_counter=fake_counter)
    assert result.exact_tokens == 5


def test_count_tokens_ignores_exact_counter_errors_gracefully():
    def broken_counter(text: str) -> int:
        raise RuntimeError("tokenizer xato")

    result = count_tokens("Bu matn.", exact_counter=broken_counter)
    assert result.exact_tokens is None
    assert result.estimated_tokens > 0


def test_load_tokenizer_counter_returns_none_when_unavailable(tmp_path):
    counter = load_tokenizer_counter(
        tmp_path / "does_not_exist", "bu-yerda-mavjud-bolmagan/model-id-xyz"
    )
    assert counter is None
