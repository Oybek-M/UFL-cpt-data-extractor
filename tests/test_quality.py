from ufl.clean.quality import assess, strip_garbage_tokens


def test_assess_keeps_normal_clean_uzbek_text():
    text = (
        "Bu kitob juda qiziqarli bo'lib, unda ko'plab voqealar tasvirlangan "
        "va o'quvchilar uchun foydali ma'lumotlar mavjud."
    )
    result = assess(text)
    assert result.keep is True
    assert result.reason is None


def test_assess_drops_too_short_text():
    result = assess("Salom")
    assert result.keep is False
    assert result.reason == "juda_qisqa"


def test_assess_drops_too_few_words():
    result = assess("Assalomu alaykum baxtiyor")  # 25 belgi, 3 so'z
    assert result.keep is False
    assert result.reason == "soz_kam"


def test_assess_drops_high_non_letter_ratio():
    text = "abcd efgh ijkl mnop 1111111111111111111"
    result = assess(text)
    assert result.keep is False
    assert result.reason == "simvol_kop"


def test_assess_drops_mixed_script_word():
    mixed_word = "kit" + "о" + "b"  # o o'rnida kirill 'о' (U+043E)
    text = f"Bu {mixed_word} juda qiziqarli edi va boshqa"
    result = assess(text)
    assert result.keep is False
    assert result.reason == "aralash_alifbo"


def test_assess_drops_high_upper_ratio():
    text = "BU KITOB JUDA QIZIQARLI VA FOYDALI HISOBLANADI"
    result = assess(text)
    assert result.keep is False
    assert result.reason == "katta_harf_kop"


def test_assess_drops_high_url_ratio():
    text = "Manba https://www.example.com/uzun/manzil/sahifa"
    result = assess(text)
    assert result.keep is False
    assert result.reason == "url_kop"


def test_assess_drops_high_repeated_word_ratio():
    text = "xatolik xatolik xatolik xatolik xatolik bir marta"
    result = assess(text)
    assert result.keep is False
    assert result.reason == "ortiqcha_takror"


def test_assess_respects_custom_thresholds():
    text = "Bu qisqa lekin ijozat berilgan matn."  # ~36 belgi, 6 so'z
    assert assess(text, min_chars=100).keep is False
    assert assess(text, min_chars=10).keep is True


def test_strip_garbage_tokens_removes_symbol_and_isolated_letters():
    line = "• kayta nshlaga1^ K r k -^."
    assert strip_garbage_tokens(line) == "kayta"


def test_strip_garbage_tokens_keeps_legit_digit_suffix_words():
    line = "Voqea 5-bet va 1991-yil haqida."
    assert strip_garbage_tokens(line) == "Voqea 5-bet va 1991-yil haqida."


def test_strip_garbage_tokens_keeps_apostrophe_words():
    line = "o'zbek tug'ilgan kitobxon."
    assert strip_garbage_tokens(line) == "o'zbek tug'ilgan kitobxon."


def test_strip_garbage_tokens_keeps_normal_punctuation():
    line = "Salom, do'stim! Qandaysiz? Yaxshi: rahmat."
    assert strip_garbage_tokens(line) == line


def test_strip_garbage_tokens_leaves_blank_line_unchanged():
    assert strip_garbage_tokens("") == ""
    assert strip_garbage_tokens("   ") == "   "


def test_strip_garbage_tokens_returns_empty_when_all_garbage():
    assert strip_garbage_tokens("• ^") == ""


def test_strip_garbage_tokens_removes_digit_letter_fusion_without_hyphen():
    line = "Bu nshlaga1 xato edi."
    assert strip_garbage_tokens(line) == "Bu xato edi."


def test_strip_garbage_tokens_keeps_word_hyphen_digit_references():
    line = "Bu nashr-0 va band-3 haqida."
    assert strip_garbage_tokens(line) == "Bu nashr-0 va band-3 haqida."


def test_strip_garbage_tokens_keeps_standalone_numbers():
    line = "1. Birinchi band va 2. ikkinchi band."
    assert strip_garbage_tokens(line) == line
