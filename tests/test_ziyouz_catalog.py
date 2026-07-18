from ufl.ziyouz.catalog import discover_links, extract_category_name, walk_catalog

_CATEGORY_HTML = """
<html><body>
<div class="pd-category">
  <div class="ph-top"><a href="/kutubxona/category/1-ziyouz-com-kutubxonasi">Orqaga</a></div>
  <h3>O'zbek zamonaviy she'riyati</h3>
  <div class="row">
    <a href="/kutubxona/category/7-o-zbek-zamonaviy-she-riyati?download=1955:kitob-bir">Kitob Bir</a>
    <a href="/kutubxona/category/7-o-zbek-zamonaviy-she-riyati?download=1955:kitob-bir">Saqlash</a>
    <a href="/kutubxona/category/7-o-zbek-zamonaviy-she-riyati?download=1956:kitob-ikki">Kitob Ikki</a>
  </div>
  <ul class="pagination">
    <li><a href="/kutubxona/category/7-o-zbek-zamonaviy-she-riyati?start=100" class="pagenav">2</a></li>
  </ul>
</div>
<a href="https://boshqa-domen.uz/sahifa">Tashqi havola</a>
<a href="/kutubxona/category/7-o-zbek-zamonaviy-she-riyati?start=100&amp;utm_source=x">Kuzatuv bilan</a>
</body></html>
"""

_PAGE_URL = "https://ziyouz.com/kutubxona/category/7-o-zbek-zamonaviy-she-riyati"


def test_extract_category_name_reads_h3_inside_pd_category():
    assert extract_category_name(_CATEGORY_HTML) == "O'zbek zamonaviy she'riyati"


def test_extract_category_name_returns_none_when_missing():
    assert extract_category_name("<html><body>Bo'sh</body></html>") is None


def test_discover_links_dedupes_repeated_download_href_by_item_id():
    _, items = discover_links(_CATEGORY_HTML, _PAGE_URL)
    item_ids = [item_id for item_id, _slug, _url in items]
    assert item_ids.count("1955") == 1
    assert "1956" in item_ids


def test_discover_links_builds_absolute_download_url():
    _, items = discover_links(_CATEGORY_HTML, _PAGE_URL)
    by_id = {item_id: url for item_id, _slug, url in items}
    assert by_id["1955"] == (
        "https://ziyouz.com/kutubxona/category/7-o-zbek-zamonaviy-she-riyati"
        "?download=1955:kitob-bir"
    )


def test_discover_links_finds_same_site_kutubxona_pages_only():
    pages, _items = discover_links(_CATEGORY_HTML, _PAGE_URL)
    assert any("start=100" in page for page in pages)
    assert not any("boshqa-domen.uz" in page for page in pages)


def test_discover_links_does_not_treat_pagination_link_as_item():
    _pages, items = discover_links(_CATEGORY_HTML, _PAGE_URL)
    item_ids = [item_id for item_id, _slug, _url in items]
    assert len(item_ids) == 2


class _FakeResponse:
    def __init__(self, url: str, text: str) -> None:
        self.url = url
        self.text = text
        self.content = text.encode("utf-8")


class _FakeWeb:
    """Sinov uchun: url -> html matn xaritasi asosida ishlaydigan soxta WebClient."""

    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages
        self.requested: list[str] = []

    def get(self, url: str) -> _FakeResponse:
        self.requested.append(url)
        return _FakeResponse(url, self._pages[url])


_ROOT_HTML = """
<html><body>
<div class="pd-category"><h3>Ildiz</h3>
<a href="https://ziyouz.com/kutubxona/category/7-a">Kategoriya A</a>
</div>
</body></html>
"""

_CAT_A_PAGE1 = """
<html><body>
<div class="pd-category"><h3>Kategoriya A</h3>
<a href="https://ziyouz.com/kutubxona/category/7-a?download=10:kitob-a1">Kitob A1</a>
<a href="https://ziyouz.com/kutubxona/category/7-a?start=100" class="pagenav">2</a>
</div>
</body></html>
"""

_CAT_A_PAGE2 = """
<html><body>
<div class="pd-category"><h3>Kategoriya A</h3>
<a href="https://ziyouz.com/kutubxona/category/7-a?download=11:kitob-a2">Kitob A2</a>
</div>
</body></html>
"""


def test_walk_catalog_visits_pagination_and_yields_items_with_category():
    web = _FakeWeb({
        "https://ziyouz.com/kutubxona": _ROOT_HTML,
        "https://ziyouz.com/kutubxona/category/7-a": _CAT_A_PAGE1,
        "https://ziyouz.com/kutubxona/category/7-a?start=100": _CAT_A_PAGE2,
    })

    found = list(walk_catalog(web, start_url="https://ziyouz.com/kutubxona"))

    item_ids = sorted(item_id for item_id, _slug, _category, _url in found)
    assert item_ids == ["10", "11"]
    categories = {category for _id, _slug, category, _url in found}
    assert categories == {"Kategoriya A"}


def test_walk_catalog_never_visits_same_page_twice():
    web = _FakeWeb({
        "https://ziyouz.com/kutubxona": _ROOT_HTML,
        "https://ziyouz.com/kutubxona/category/7-a": _CAT_A_PAGE1,
        "https://ziyouz.com/kutubxona/category/7-a?start=100": _CAT_A_PAGE2,
    })

    list(walk_catalog(web, start_url="https://ziyouz.com/kutubxona"))

    assert len(web.requested) == len(set(web.requested))


def test_walk_catalog_respects_max_pages():
    web = _FakeWeb({
        "https://ziyouz.com/kutubxona": _ROOT_HTML,
        "https://ziyouz.com/kutubxona/category/7-a": _CAT_A_PAGE1,
        "https://ziyouz.com/kutubxona/category/7-a?start=100": _CAT_A_PAGE2,
    })

    list(walk_catalog(web, start_url="https://ziyouz.com/kutubxona", max_pages=2))

    assert len(web.requested) == 2
