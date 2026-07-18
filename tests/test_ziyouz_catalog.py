from ufl.ziyouz.catalog import discover_links, extract_category_name

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
