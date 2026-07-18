from ufl.ziyouz.category_map import resolve_ufl_category


def test_resolve_known_category_returns_mapped_ufl_category():
    assert resolve_ufl_category("O'zbek zamonaviy she'riyati") == "books"


def test_resolve_unknown_category_returns_none():
    assert resolve_ufl_category("Mutlaqo noma'lum kategoriya nomi") is None


def test_resolve_strips_surrounding_whitespace():
    assert resolve_ufl_category("  O'zbek zamonaviy she'riyati  ") == "books"
