from ufl.clean.quality import assess


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
