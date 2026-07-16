from ufl.crawl.categorize import category_from_section, category_from_url, resolve_category

_VALID = [
    "web_news", "gov_legal", "education", "reference",
    "books", "conversations", "technical", "domain_haf",
]


def test_manual_mode_returns_fixed_category():
    assert resolve_category("gov_legal", url="https://x.uz/a", valid_categories=_VALID) == "gov_legal"


def test_category_from_url_path_maps_known_sections():
    assert category_from_url("https://kun.uz/texnologiya/ai", _VALID) == "technical"
    assert category_from_url("https://kun.uz/talim/maktab", _VALID) == "education"
    assert category_from_url("https://kun.uz/qonunchilik/x", _VALID) == "gov_legal"


def test_category_from_url_unknown_returns_none():
    assert category_from_url("https://kun.uz/random/slug", _VALID) is None


def test_category_from_section_maps_label():
    assert category_from_section("Ta'lim", _VALID) == "education"
    assert category_from_section("Iqtisodiyot", _VALID) == "domain_haf"


def test_auto_mode_uses_url_path_without_minimax():
    # MiniMax berilmagan — URL-yo'l signal bersa, bepul aniqlanadi
    got = resolve_category(
        "auto", url="https://kun.uz/texnologiya/ai", valid_categories=_VALID, minimax=None
    )
    assert got == "technical"


def test_auto_mode_falls_back_to_web_news_without_signal():
    got = resolve_category(
        "auto", url="https://kun.uz/random/slug", valid_categories=_VALID, minimax=None
    )
    assert got == "web_news"
