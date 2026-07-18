from ufl.ziyouz.category_map import resolve_ufl_category


def test_resolve_known_category_returns_mapped_ufl_category():
    assert resolve_ufl_category("O'zbek zamonaviy she'riyati") == "books"


def test_resolve_unknown_category_returns_none():
    assert resolve_ufl_category("Mutlaqo noma'lum kategoriya nomi") is None


def test_resolve_strips_surrounding_whitespace():
    assert resolve_ufl_category("  O'zbek zamonaviy she'riyati  ") == "books"


def test_resolve_matches_unicode_curly_apostrophe_from_live_site():
    """ziyouz.com HTML'da ba'zan U+2018 (‘) qo'shtirnoq belgisi ishlatiladi,
    xaritamizda esa ASCII (') bo'lishi mumkin — normalizatsiya bilan ikkalasi
    ham bir xil kategoriyaga tushishi kerak (2026-07-18 real crawl'da
    aniqlangan mos kelmaslik: "O‘zbek xalq og‘zaki ijodi" "Noma'lum
    kategoriya" deb belgilangan edi)."""
    assert resolve_ufl_category("O‘zbek xalq og‘zaki ijodi") == "books"
