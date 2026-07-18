# ziyouz.com Ommaviy Fayl-Yuklovchi (fetch-ziyouz) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Yangi `ufl fetch-ziyouz` CLI buyrug'i qo'shish — ziyouz.com "Kutubxona"
bo'limidagi barcha yuklab olinadigan fayllarni (PDF/EPUB/DOC/FB2/DJVU/TXT/HTML)
topib, mavjud `process_file` pipeline'i orqali toza o'zbekcha matnga aylantirish.

**Architecture:** Generic BFS (breadth-first) link-yurish — `/kutubxona` ildiz
sahifasidan boshlab, sahifadagi barcha `/kutubxona/*` havolalarini kuzatadi
(pagination ham shu orqali avtomatik qamraladi, chunki u oddiy `<a href>`).
Har bir topilgan `?download=<id>:<slug>` havolasi bitta "element" — yuklab olinadi,
kategoriya `<h3>` sarlavhasidan `category_map.py` orqali UFL kategoriyasiga
o'giriladi, so'ng mavjud `process_file()`/`write_output()`/`Store` orqali xuddi
`ufl run`dagi kabi qayta ishlanadi. Davomiylik — `Store.is_processed("ziyouz:<id>")`.

**Tech Stack:** Python 3.12, BeautifulSoup4 (mavjud), httpx (mavjud `WebClient`),
mavjud `pipeline.process_file`, mavjud `store.db.Store`.

---

## Haqiqiy tekshirilgan ma'lumotlar (implementatsiya davomida ishonch uchun)

Bular 2026-07-18'da ziyouz.com'dan real HTML orqali tasdiqlangan (taxmin emas):

- Kategoriya sarlavhasi: `<div class="pd-category">...<h3>O‘zbek zamonaviy she’riyati</h3>`
  — CSS selector: `div.pd-category h3`.
- Yuklab olish havolasi: `<a href="/kutubxona/category/7-o-zbek-zamonaviy-she-riyati?download=1955:a-zam-o-ktam-kuzda-kulgan-chechaklar">...</a>`
  — bir xil `?download=<id>:<slug>` href ikki marta uchraydi (sarlavha havolasi +
  "Saqlash" tugmasi) — `item_id` bo'yicha dedup shart.
- `?download=` havolasiga GET so'rov 303 bilan **haqiqiy statik faylga** redirect
  qiladi (masalan `/books/uzbek_zamonaviy_sheriyati/A'zam O'ktam...pdf`) — `httpx`
  `follow_redirects=True` bilan avtomatik ergashadi (mavjud `WebClient` xuddi shunday
  sozlangan), `response.url` final faylning haqiqiy yo'lini beradi.
- Pagination: oddiy `<a href="...?start=100" class="pagenav">2</a>` — maxsus
  pagination-parser kerak emas, generic BFS bilan avtomatik topiladi.
- `robots.txt` `/kutubxona`ni taqiqlamaydi.

---

## Fayl tuzilishi

- Create: `src/ufl/ziyouz/__init__.py` (bo'sh)
- Create: `src/ufl/ziyouz/category_map.py` — Joomla kategoriya nomi → UFL kategoriya
- Create: `src/ufl/ziyouz/catalog.py` — HTML parsing (kategoriya nomi, havolalar) + BFS yurish
- Test: `tests/test_ziyouz_category_map.py`
- Test: `tests/test_ziyouz_catalog.py`
- Test: `tests/test_cli_fetch_ziyouz.py`
- Modify: `src/ufl/cli.py` — `fetch-ziyouz` buyrug'i qo'shiladi
- Modify: `README.md`, `docs/DOCKER.md` — hujjatlashtirish

---

### Task 1: `category_map.py` — Joomla kategoriya nomi → UFL kategoriya

**Files:**
- Create: `src/ufl/ziyouz/__init__.py`
- Create: `src/ufl/ziyouz/category_map.py`
- Test: `tests/test_ziyouz_category_map.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ziyouz_category_map.py
from ufl.ziyouz.category_map import resolve_ufl_category


def test_resolve_known_category_returns_mapped_ufl_category():
    assert resolve_ufl_category("O‘zbek zamonaviy she’riyati") == "books"


def test_resolve_unknown_category_returns_none():
    assert resolve_ufl_category("Mutlaqo noma'lum kategoriya nomi") is None


def test_resolve_strips_surrounding_whitespace():
    assert resolve_ufl_category("  O‘zbek zamonaviy she’riyati  ") == "books"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm ufl python -m pytest tests/test_ziyouz_category_map.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ufl.ziyouz'`

- [ ] **Step 3: Write minimal implementation**

Create `src/ufl/ziyouz/__init__.py` (bo'sh fayl).

Create `src/ufl/ziyouz/category_map.py`:

```python
"""ziyouz.com "Kutubxona" bo'limidagi Joomla kategoriya nomlarini UFL'ning 8
kategoriyasiga xaritalaydi.

Manba: docs/superpowers/specs/2026-07-18-ziyouz-bulk-downloader-design.md
Nomlar ziyouz.com'dan 2026-07-18'da real olingan (o'zgarmagan bo'lishi kerak,
lekin sayt strukturasi o'zgarsa yangilanadi). Xaritada yo'q nom uchun
`resolve_ufl_category` None qaytaradi — chaqiruvchi tomon bunday elementni
o'tkazib yuborishi va ogohlantirish chiqarishi kerak (hech qachon taxminiy
kategoriyaga yozmaslik — "shubha bo'lsa tashla" tamoyili).
"""

from __future__ import annotations

CATEGORY_MAP: dict[str, str] = {
    # --- Ziyouz.com kutubxonasi (badiiy/ilmiy adabiyot) ---
    "O‘zbek xalq og‘zaki ijodi": "books",
    "O‘zbek mumtoz adabiyoti": "books",
    "Alisher Navoiy asarlari": "books",
    "O‘zbek zamonaviy she’riyati": "books",
    "O‘zbek nasri": "books",
    "O‘zbek dramaturgiyasi": "books",
    "O‘zbek adabiy tili": "reference",
    "O‘zbek tilining izohli lug‘ati": "reference",
    "O‘zbekiston Milliy Ensiklopediyasi": "reference",
    "Jahon xalqlari og‘zaki ijodi": "books",
    "Sharq mumtoz adabiyoti": "books",
    "Jahon nasri": "books",
    "Jahon she’riyati": "books",
    "Jahon dramaturgiyasi": "books",
    "Bolalar kutubxonasi": "books",
    "Tasavvufga oid kitoblar": "books",
    "Axloq-odobga oid kitoblar": "books",
    "Hikmatlar xazinasi (Aforizmlar)": "books",
    "Tarixga oid kitoblar": "books",
    "Prezident asarlari": "gov_legal",
    "Ilmiy-tarixiy, adabiy maqolalar, risolalar": "books",
    "Adabiyotshunoslik": "books",
    "Adabiy antologiya va to‘plamlar": "books",
    "Adabiy, tarixiy bukletlar": "books",
    "Adabiy esdaliklar, xotiralar": "books",
    "Hajviyot": "web_news",
    "Tarjimashunoslik": "books",
    "Eski o‘zbek yozuvi": "reference",
    "Lug‘atlar": "reference",
    "Turli mavzulardagi kitoblar": "books",
    "Chet tillari": "education",
    "Tibbiyotga oid risolalar": "domain_haf",
    "Publitsistika": "web_news",
    "Falsafa": "books",
    "Aniq fanlar": "education",
    "Jurnalistika": "web_news",
    "San’atshunoslik": "books",
    "Statistika": "books",
    "Hunarmadchilik": "books",
    "Uzbek literature (in English)": "books",
    "Sport": "books",
    # --- Ziyouz.com jurnalxonasi ---
    "\"Tafakkur\" jurnali": "web_news",
    "\"Sharq yulduzi\" jurnali": "web_news",
    "Журнал \"Звезда Востока\"": "web_news",
    "\"Yoshlik\" jurnali": "web_news",
    "\"Jahon adabiyoti\" jurnali": "web_news",
    "\"Hidoyat\" jurnali": "web_news",
    "\"Muloqot\" jurnali": "web_news",
    "\"Moziydan sado\" jurnali": "web_news",
    "\"Guliston\" jurnali": "web_news",
    "\"Vatandosh\" gazetasi": "web_news",
    "\"Yosh kuch\" jurnali": "web_news",
    "Журнал \"Молодая смена\"": "web_news",
    "\"Fan va turmush\" jurnali": "web_news",
    "\"Til va adabiyot ta’limi\" jurnali": "web_news",
    "\"O‘zbekistonda ijtimoiy fanlar\" jurnali": "web_news",
    "\"O‘zbekiston arxeologiyasi\" jurnali": "web_news",
    "\"O‘zbekiston moddiy madaniyati tarixi\" to‘plami": "web_news",
    "\"O‘zbekistonda arxeologik tadqiqotlar\" to‘plami": "web_news",
    "\"Saodat\" jurnali": "web_news",
    "\"Sirli olam\" jurnali": "web_news",
    "\"Iqtisod va hisobot\" jurnali": "domain_haf",
    "\"Ijod olami\" jurnali": "web_news",
    # --- Bibliografik nashrlar ---
    "Gazeta maqolalari solnomasi (1977)": "reference",
    "Jurnal maqolalari letopisi (1961-1967)": "reference",
    "Kitob letopisi (1932-1967)": "reference",
    "Sovet O‘zbekiston kitobi (1917-1975)": "reference",
    "O‘zbekiston kitoblarining yilnomasi (1976-1998)": "reference",
    "O‘zbekiston matbuoti solnomasi (1968-2014)": "reference",
    # --- Oliy va o'rta maxsus ta'lim muassasalari darsliklari (hammasi ta'lim) ---
    "Aloqa va axborot texnologiyalari": "education",
    "Biologiya": "education",
    "Ekologiya": "education",
    "Geodeziya": "education",
    "Geografiya": "education",
    "Geologiya": "education",
    "Huquq": "education",
    "Iqtisodiyot": "education",
    "Jismoniy tarbiya": "education",
    "Kimyo": "education",
    "Mantiq": "education",
    "Ma’naviyat": "education",
    "Matematika": "education",
    "Me’morchilik": "education",
    "Ona tili va adabiyot": "education",
    "Pedagogika": "education",
    "Psixologiya": "education",
    "Qishloq xo'jaligi": "education",
    "San’at": "education",
    "Tabiiy fanlar": "education",
    "Tarix": "education",
    "Texnika va texnologiya": "education",
    "Tibbiyot": "education",
    # --- Maktab darsliklari (hammasi ta'lim) ---
    "Alifbo": "education",
    "Adabiyot": "education",
    "Chizmachilik": "education",
    "Fizika": "education",
    "Fransuz tili": "education",
    "Informatika": "education",
    "Ingliz tili": "education",
    "Musiqa": "education",
    "Nemis tili": "education",
    "Odobnoma": "education",
    "O'zbek tili": "education",
    "Rus tili": "education",
    "Tasviriy san’at": "education",
    "Yangi darsliklar (2014-2023)": "education",
    "Tojik maktablari uchun darsliklar": "education",
    "Turkman maktablari uchun darsliklar": "education",
    # --- Mobil kutubxona ---
    "Badiiy kitoblar": "books",
    "O'zbek xalq og'zaki ijodi": "books",
    "Turli mavzudagi kitoblar": "books",
    "Android uchun kitoblar": "books",
    "E-readerlar uchun EPUB kitoblar": "books",
    # --- Библиотека Ziyouz.com (rus tilida) ---
    "Узбекское устное народное творчество": "books",
    "Узбекская классическая литература": "books",
    "Узбекская современная проза": "books",
    "Узбекская современная поэзия": "books",
    "Узбекская драматургия": "books",
    "Узбекская детская литература": "books",
    "Сборники по узбекской литературы": "books",
    "Русскоязычная проза Узбекистана": "books",
    "Узбекский язык и литература": "reference",
    "Русскоязычная поэзия Узбекистана": "books",
    "Каракалпакская литература": "books",
    "Научные произведения великих мыслителей Узбекистана": "books",
    "Жизнь и деятельность великих предков Узбекистана": "books",
    "Литературы по истории тюркских народов": "books",
    "Словари тюркских языков": "reference",
    "Узбекская кулинария": "books",
    "Избранная лирика Востока": "books",
    # --- Qaraqalpaq kitapxanası ---
    "Qaraqalpaq folklorı": "books",
    "Qaraqalpaq poeziyası": "books",
    "Qaraqalpaq prozası": "books",
    "Qaraqalpaq tili sózlikleri": "reference",
    "Qaraqalpaqstan tariyxı": "books",
    "İlimiy kitaplar": "books",
    "Qaraqalpaqsha sabaqlıqlar": "education",
    "Jáhán ádebiyatı qaraqalpaq tilinde": "books",
    "Balalar ádebiyatı": "books",
}


def resolve_ufl_category(joomla_category_name: str) -> str | None:
    """Ziyouz kategoriya nomini UFL kategoriyasiga o'giradi; xaritada yo'q
    bo'lsa None (chaqiruvchi tomon bunday elementni o'tkazib yuborishi kerak)."""
    return CATEGORY_MAP.get(joomla_category_name.strip())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm ufl python -m pytest tests/test_ziyouz_category_map.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ufl/ziyouz/__init__.py src/ufl/ziyouz/category_map.py tests/test_ziyouz_category_map.py
git commit -m "ziyouz: Joomla kategoriya -> UFL kategoriya xaritasi"
```

---

### Task 2: `catalog.py` — kategoriya nomi va havolalarni HTML'dan ajratish

**Files:**
- Create: `src/ufl/ziyouz/catalog.py`
- Test: `tests/test_ziyouz_catalog.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ziyouz_catalog.py
from ufl.ziyouz.catalog import discover_links, extract_category_name

_CATEGORY_HTML = """
<html><body>
<div class="pd-category">
  <div class="ph-top"><a href="/kutubxona/category/1-ziyouz-com-kutubxonasi">Orqaga</a></div>
  <h3>O‘zbek zamonaviy she’riyati</h3>
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
    assert extract_category_name(_CATEGORY_HTML) == "O‘zbek zamonaviy she’riyati"


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm ufl python -m pytest tests/test_ziyouz_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ufl.ziyouz.catalog'`

- [ ] **Step 3: Write minimal implementation**

Create `src/ufl/ziyouz/catalog.py`:

```python
"""ziyouz.com "Kutubxona" HTML sahifalarini tahlil qilish: kategoriya nomi va
davom etiladigan/yuklab olinadigan havolalarni ajratish.

Pagination uchun maxsus parser YO'Q — Joomla pagination oddiy `<a href>` bo'lgani
uchun generic same-site link-yurish (bu modulning vazifasi) uni tabiiy ravishda
qamraydi (docs/superpowers/plans/2026-07-18-ziyouz-bulk-downloader.md).
"""

from __future__ import annotations

import re
import urllib.parse

from bs4 import BeautifulSoup

# `download`ning qiymati "id:slug" formatida — buni parse_qs bilan (regex bilan
# emas) o'qiymiz, chunki bitta-parametrli query'da ("?download=...") qiymatdan
# oldin '?' yoki '&' belgisi YO'Q — `[?&]download=` uslubidagi regex bunday
# holatni o'tkazib yuboradi (real HTML bilan tasdiqlangan xato).
_DOWNLOAD_VALUE_RE = re.compile(r"^(\d+):([\w-]+)$")
_TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "fbclid", "gclid"}


def _download_item(parsed: urllib.parse.SplitResult) -> tuple[str, str] | None:
    """`?download=<id>:<slug>` query-parametridan (id, slug) ajratadi; yo'q/mos
    kelmasa None."""
    values = urllib.parse.parse_qs(parsed.query).get("download")
    if not values:
        return None
    match = _DOWNLOAD_VALUE_RE.match(values[0])
    if not match:
        return None
    return match.group(1), match.group(2)


def extract_category_name(html: str) -> str | None:
    """`<div class="pd-category">` ichidagi `<h3>` matnini qaytaradi; topilmasa None."""
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one("div.pd-category h3")
    if heading is None:
        return None
    text = heading.get_text(strip=True)
    return text or None


def discover_links(html: str, page_url: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Sahifadagi havolalarni ikkiga ajratadi:
    - `pages`: davom etiladigan bir-xil-saytdagi `/kutubxona/*` HTML sahifa URL'lari
      (kuzatuv query-parametrlari olib tashlanadi, dublikat yo'q).
    - `items`: `(item_id, slug, absolute_download_url)` — yuklab olish havolalari,
      `item_id` bo'yicha dedup qilingan (bir xil kitobga ikkita havola — sarlavha
      va "Saqlash" tugmasi — bo'lishi mumkin).
    """
    soup = BeautifulSoup(html, "html.parser")
    base_host = urllib.parse.urlsplit(page_url).hostname

    pages: list[str] = []
    seen_pages: set[str] = set()
    items: list[tuple[str, str, str]] = []
    seen_items: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        absolute = urllib.parse.urljoin(page_url, href)
        parsed = urllib.parse.urlsplit(absolute)

        download_item = _download_item(parsed)
        if download_item:
            item_id, slug = download_item
            if item_id not in seen_items:
                seen_items.add(item_id)
                items.append((item_id, slug, absolute))
            continue

        if parsed.hostname != base_host:
            continue
        if not parsed.path.startswith("/kutubxona"):
            continue

        cleaned = _strip_tracking_params(parsed)
        if cleaned not in seen_pages:
            seen_pages.add(cleaned)
            pages.append(cleaned)

    return pages, items


def _strip_tracking_params(parsed: urllib.parse.SplitResult) -> str:
    pairs = [
        (key, value) for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_KEYS
    ]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(pairs), "")
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm ufl python -m pytest tests/test_ziyouz_catalog.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ufl/ziyouz/catalog.py tests/test_ziyouz_catalog.py
git commit -m "ziyouz: kategoriya-nomi va havolalarni HTML'dan ajratish (catalog.py)"
```

---

### Task 3: `catalog.py` — `walk_catalog` BFS generator

**Files:**
- Modify: `src/ufl/ziyouz/catalog.py`
- Test: `tests/test_ziyouz_catalog.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ziyouz_catalog.py`:

```python
from ufl.ziyouz.catalog import walk_catalog


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm ufl python -m pytest tests/test_ziyouz_catalog.py -v -k walk_catalog`
Expected: FAIL with `ImportError: cannot import name 'walk_catalog'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/ufl/ziyouz/catalog.py` (bottom of file):

```python
from typing import Iterator, Protocol


class _WebGetter(Protocol):
    def get(self, url: str) -> object:
        ...  # .url: str, .text: str


def walk_catalog(
    web: _WebGetter,
    *,
    start_url: str = "https://ziyouz.com/kutubxona",
    max_pages: int = 0,
) -> Iterator[tuple[str, str, str, str]]:
    """`/kutubxona`ni BFS bilan yuradi va har bir topilgan yuklab-olish elementini
    `(item_id, slug, category_name, download_url)` sifatida yield qiladi.

    `category_name` — element topilgan sahifaning `<h3>` sarlavhasi (None bo'lsa
    "Noma'lum" qaytariladi, chaqiruvchi tomon buni ham tashlab yuborishi kerak).
    Pagination sahifalari maxsus ishlov talab qilmaydi — ular ham oddiy
    `/kutubxona/*` sahifa sifatida navbatga tushadi.
    """
    visited: set[str] = set()
    queue: list[str] = [start_url]
    pages_fetched = 0

    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        if max_pages and pages_fetched >= max_pages:
            return
        response = web.get(url)
        pages_fetched += 1

        html = response.text  # type: ignore[attr-defined]
        page_url = str(getattr(response, "url", url))
        category_name = extract_category_name(html) or "Noma'lum"
        sub_pages, items = discover_links(html, page_url)

        for sub_page in sub_pages:
            if sub_page not in visited:
                queue.append(sub_page)

        for item_id, slug, download_url in items:
            yield item_id, slug, category_name, download_url
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm ufl python -m pytest tests/test_ziyouz_catalog.py -v`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ufl/ziyouz/catalog.py tests/test_ziyouz_catalog.py
git commit -m "ziyouz: walk_catalog BFS generator (resumable emas — item darajasida Store orqali)"
```

---

### Task 4: CLI `fetch-ziyouz` buyrug'i

**Files:**
- Modify: `src/ufl/cli.py`
- Test: `tests/test_cli_fetch_ziyouz.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_fetch_ziyouz.py
"""`ufl fetch-ziyouz` integratsiya testi — haqiqiy tarmoq so'rovisiz, soxta
WebClient orqali. `_build_web_client`ni monkeypatch qiladi.

`_write_test_config` — `tests/test_cli_fetch_hf.py`dagi bilan bir xil naqsh
(Config'ning barcha majburiy bo'limlari to'ldirilishi kerak, pydantic default'siz)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import ufl.cli as cli_module
from ufl.cli import app
from ufl.store.db import Store

runner = CliRunner()


def _write_test_config(tmp_path: Path) -> Path:
    config_content = f"""
[paths]
input = "{(tmp_path / "input").as_posix()}"
output = "{(tmp_path / "output").as_posix()}"
rejected = "{(tmp_path / "rejected").as_posix()}"
reports = "{(tmp_path / "reports").as_posix()}"
models_dir = "{(tmp_path / "models").as_posix()}"
db = "{(tmp_path / "ufl.db").as_posix()}"

[budget.categories]
books = 1000
education = 1000

[tokenizer]
model_id = "bu-yerda-mavjud-bolmagan/model-id-xyz"
local_dir = "{(tmp_path / "models" / "tokenizer").as_posix()}"
chars_per_token = 4.0

[normalize]
apostrophe_mode = "ascii"
quote_style = "straight"

[quality]
min_chars = 10
min_words = 2
max_non_letter_ratio = 0.40
max_repeated_ngram_ratio = 0.30
max_upper_ratio = 0.70
max_url_ratio = 0.20

[language]
min_confidence = 0.65
min_heuristic_score = 0.20
fasttext_model_path = "{(tmp_path / "models" / "lid.176.ftz").as_posix()}"

[ocr]
languages = "uzb+uzb_cyrl"
min_confidence = 60
dpi = 300

[structure]
header_footer_min_repeats = 3
detect_toc = true
detect_bibliography = true

[dedup]
enabled = true
near_dup_enabled = false
"""
    config_path = tmp_path / "test_ufl.toml"
    config_path.write_text(config_content, encoding="utf-8")
    return config_path

_ROOT_HTML = """
<html><body>
<div class="pd-category"><h3>Ildiz</h3>
<a href="https://ziyouz.com/kutubxona/category/7-a">Kategoriya A</a>
</div>
</body></html>
"""

_CAT_A_HTML = """
<html><body>
<div class="pd-category"><h3>O‘zbek zamonaviy she’riyati</h3>
<a href="https://ziyouz.com/kutubxona/category/7-a?download=10:kitob-a1">Kitob A1</a>
</div>
</body></html>
"""


class _FakeResponse:
    def __init__(self, url: str, content: bytes) -> None:
        self.url = url
        self.content = content
        self.text = content.decode("utf-8", errors="ignore")


class _FakeWebClient:
    """`_download_url`ga GET qilinganda haqiqiy .pdf faylga "redirect qilingan"
    deb, final .url'ni fayl-kengaytmali qilib qaytaradi."""

    def __init__(self, download_url: str, file_bytes: bytes, final_url: str) -> None:
        self._pages = {
            "https://ziyouz.com/kutubxona": _ROOT_HTML,
            "https://ziyouz.com/kutubxona/category/7-a": _CAT_A_HTML,
        }
        self._download_url = download_url
        self._file_bytes = file_bytes
        self._final_url = final_url

    def get(self, url: str):
        if url == self._download_url:
            return _FakeResponse(self._final_url, self._file_bytes)
        return _FakeResponse(url, self._pages[url].encode("utf-8"))

    def close(self) -> None:
        pass


def test_fetch_ziyouz_downloads_processes_and_records_one_item(tmp_path, monkeypatch):
    download_url = "https://ziyouz.com/kutubxona/category/7-a?download=10:kitob-a1"
    final_url = "https://ziyouz.com/books/uzbek_zamonaviy_sheriyati/Kitob A1.txt"
    file_bytes = "Bu sinov uchun yozilgan o'zbekcha matn kitobi.".encode("utf-8")

    fake_client = _FakeWebClient(download_url, file_bytes, final_url)
    monkeypatch.setattr(cli_module, "_build_web_client", lambda config: fake_client)
    # `walk_catalog`ning standart `start_url`i ("https://ziyouz.com/kutubxona") allaqachon
    # `_FakeWebClient._pages`dagi kalit bilan bir xil — qo'shimcha monkeypatch shart emas.

    config_path = _write_test_config(tmp_path)

    result = runner.invoke(app, ["fetch-ziyouz", "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    with Store(tmp_path / "ufl.db") as store:
        assert store.is_processed("ziyouz:10") is True
        books = store.list_books()
    assert len(books) == 1
    assert books[0].category == "books"
    assert (tmp_path / "output" / "books" / "10_kitob-a1.txt").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm ufl python -m pytest tests/test_cli_fetch_ziyouz.py -v`
Expected: FAIL — `fetch-ziyouz` buyrug'i mavjud emas (Typer "No such command").

- [ ] **Step 3: Write minimal implementation**

`src/ufl/cli.py`ga import qo'shish (mavjud importlar qatoriga, `hf_state` importidan keyin):

```python
from ufl.ziyouz.catalog import walk_catalog
from ufl.ziyouz.category_map import resolve_ufl_category
```

`fetch_hf` buyrug'idan keyin (crawl_status'dan oldin) yangi buyruq qo'shish:

```python
ZIYOUZ_SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".docx", ".doc", ".fb2", ".djvu", ".txt", ".html"}
ZIYOUZ_MAX_FILE_BYTES = 200 * 1024 * 1024


@app.command("fetch-ziyouz")
def fetch_ziyouz(
    category: str = typer.Option(
        None, "--category", help="Faqat shu UFL kategoriyasidagi elementlarni yuklash (bo'sh — hammasi)"
    ),
    limit: int = typer.Option(0, "--limit", help="Shuncha elementdan keyin to'xtash (0 — cheklovsiz)"),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
    """ziyouz.com "Kutubxona" bo'limidan ommaviy fayl yuklab, UFL pipeline'idan o'tkazish."""
    setup_logging()
    if category is not None and category not in CRAWL_CATEGORIES:
        console.print(
            f"[bold red]Xato:[/bold red] noto'g'ri kategoriya '{category}'. "
            f"Ruxsat etilgan: {', '.join(CRAWL_CATEGORIES)}."
        )
        raise typer.Exit(code=1)

    config = Config.load(config_path)
    web = _build_web_client(config)
    fasttext_predict = load_fasttext_predictor(config.language.fasttext_model_path)
    exact_token_counter = load_tokenizer_counter(config.tokenizer.local_dir, config.tokenizer.model_id)
    quality_kwargs = {
        "min_chars": config.quality.min_chars,
        "min_words": config.quality.min_words,
        "max_non_letter_ratio": config.quality.max_non_letter_ratio,
        "max_repeated_ngram_ratio": config.quality.max_repeated_ngram_ratio,
        "max_upper_ratio": config.quality.max_upper_ratio,
        "max_url_ratio": config.quality.max_url_ratio,
    }
    dedup_store = DeduplicationStore()
    tmp_dir = config.paths.db.parent / "tmp_ziyouz"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    skip_count = 0
    error_count = 0
    unmapped_categories: set[str] = set()

    try:
        with Store(config.paths.db) as store:
            for item_id, slug, joomla_category, download_url in walk_catalog(web):
                if limit and ok_count >= limit:
                    break

                source_key = f"ziyouz:{item_id}"
                if store.is_processed(source_key):
                    skip_count += 1
                    continue

                ufl_category = resolve_ufl_category(joomla_category)
                if ufl_category is None:
                    if joomla_category not in unmapped_categories:
                        unmapped_categories.add(joomla_category)
                        console.print(
                            f"[yellow]Noma'lum kategoriya:[/yellow] '{joomla_category}' — "
                            "o'tkazib yuborilmoqda (category_map.py ga qo'shish mumkin)."
                        )
                    skip_count += 1
                    continue
                if category is not None and ufl_category != category:
                    skip_count += 1
                    continue

                try:
                    response = web.get(download_url)
                except Exception as exc:  # noqa: BLE001 — bitta faylni izolyatsiya qilish
                    error_count += 1
                    console.print(f"[red]Yuklab olishda xato:[/red] {download_url} — {exc}")
                    continue

                final_url = str(getattr(response, "url", download_url))
                extension = Path(final_url.split("?")[0]).suffix.lower()
                if extension not in ZIYOUZ_SUPPORTED_EXTENSIONS:
                    skip_count += 1
                    continue
                if len(response.content) > ZIYOUZ_MAX_FILE_BYTES:
                    skip_count += 1
                    continue

                tmp_path = tmp_dir / f"{item_id}_{slug}{extension}"
                tmp_path.write_bytes(response.content)
                try:
                    result = process_file(
                        tmp_path,
                        category=ufl_category,
                        dedup_store=dedup_store,
                        fasttext_predict=fasttext_predict,
                        exact_token_counter=exact_token_counter,
                        chars_per_token=config.tokenizer.chars_per_token,
                        header_footer_min_repeats=config.structure.header_footer_min_repeats,
                        detect_toc=config.structure.detect_toc,
                        detect_bibliography=config.structure.detect_bibliography,
                        min_language_confidence=config.language.min_confidence,
                        min_heuristic_score=config.language.min_heuristic_score,
                        apostrophe_mode=config.normalize.apostrophe_mode,
                        quality_kwargs=quality_kwargs,
                    )
                    write_output(
                        result,
                        output_dir=config.paths.output,
                        rejected_dir=config.paths.rejected,
                        reports_dir=config.paths.reports,
                    )
                    dropped_pct = (
                        len(result.dropped) / result.total_blocks * 100 if result.total_blocks else 0.0
                    )
                    store.record_book(
                        BookRecord(
                            path=source_key,
                            category=ufl_category,
                            format=result.format,
                            char_count=result.char_count,
                            estimated_tokens=result.estimated_tokens,
                            exact_tokens=result.exact_tokens,
                            total_blocks=result.total_blocks,
                            kept_blocks=result.kept_blocks,
                            dropped_pct=round(dropped_pct, 2),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 — bitta faylni izolyatsiya qilish
                    error_count += 1
                    console.print(f"[red]Qayta ishlashda xato:[/red] {download_url} — {exc}")
                    continue
                finally:
                    tmp_path.unlink(missing_ok=True)

                ok_count += 1
                console.print(f"[green]OK[/green] {ufl_category}: {joomla_category} — {item_id}")
    finally:
        web.close()

    console.print(
        f"\n[bold green]Tugadi.[/bold green] Muvaffaqiyatli: {ok_count}, "
        f"O'tkazib yuborildi: {skip_count}, Xato: {error_count}."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose run --rm ufl python -m pytest tests/test_cli_fetch_ziyouz.py -v`
Expected: `1 passed`

Run full suite to confirm no regressions: `docker compose run --rm ufl python -m pytest tests/ -q`
Expected: all tests pass (no failures).

- [ ] **Step 5: Commit**

```bash
git add src/ufl/cli.py tests/test_cli_fetch_ziyouz.py
git commit -m "ufl fetch-ziyouz: ziyouz.com'dan ommaviy fayl yuklab pipeline'dan o'tkazish"
```

---

### Task 5: Hujjatlar (README, DOCKER.md)

**Files:**
- Modify: `README.md`
- Modify: `docs/DOCKER.md`

- [ ] **Step 1: `README.md`ga bitta bullet qo'shish**

"Nima qiladi" ro'yxatidagi `fetch-hf` bulletidan keyin:

```markdown
- ✅ ziyouz.com Kutubxonasidan ommaviy yig'ish (`ufl fetch-ziyouz`): "Kutubxona"
  bo'limidagi barcha kategoriyalarni (~13,000 fayl) avtomatik topib, PDF/EPUB/DOC/FB2
  fayllarni mavjud tozalash pipeline'i orqali o'tkazadi (audio va mos kelmaydigan
  formatlar avtomatik o'tkazib yuboriladi); davomiylik — allaqachon qayta ishlangan
  elementlar qayta yuklab olinmaydi
```

- [ ] **Step 2: `docs/DOCKER.md`ga yangi bo'lim qo'shish**

`## 8. HuggingFace dataset'lardan yig'ish` bo'limidan keyin (fayl oxiriga yaqin):

```markdown
---

## 9. ziyouz.com Kutubxonasidan ommaviy yig'ish (fetch-ziyouz)

"Kutubxona" bo'limidagi (~13,000 fayl, 42 kategoriya) barcha PDF/EPUB/DOC/FB2/DJVU/TXT
faylni avtomatik topib, mavjud tozalash pipeline'i orqali o'tkazadi. Dizayn:
[2026-07-18-ziyouz-bulk-downloader-design.md](superpowers/specs/2026-07-18-ziyouz-bulk-downloader-design.md).

### 9.1 Ishlatish

\`\`\`bash
# Butun kutubxonani yig'ish (uzluksiz, davomiy)
docker compose run --rm ufl ufl fetch-ziyouz

# Sinov uchun: 5 ta elementdan keyin to'xtaydi
docker compose run --rm ufl ufl fetch-ziyouz --limit 5

# Faqat bitta UFL kategoriyasi
docker compose run --rm ufl ufl fetch-ziyouz --category books
\`\`\`

### 9.2 Davomiylik va litsenziya

Har bir element `ufl.db`da `ziyouz:<id>` kaliti bilan qayd etiladi — to'xtatib qayta
ishga tushirilsa, allaqachon qayta ishlangan elementlar qayta yuklab olinmaydi.
Kutubxona sahifalari (pagination) esa har safar qaytadan yuriladi (arzon — bir necha
yuz sahifa), faqat qimmat qism (yuklab olish+qayta ishlash) qayta bajarilmaydi.

Audio (mp3) va boshqa matn-bo'lmagan fayllar kengaytma bo'yicha avtomatik o'tkazib
yuboriladi. Xaritada yo'q (yangi paydo bo'lgan) kategoriya nomi ogohlantirish bilan
o'tkazib yuboriladi — `src/ufl/ziyouz/category_map.py`ga qo'shish mumkin.

> **Litsenziya:** sayt "faqat shaxsiy mutolaa, tijoriy foydalanish taqiqlanadi" deydi —
> hozirgi bosqich uchun (tijoriy bo'lmagan MVP tayyorgarlik) qabul qilingan qaror,
> tijoriylashuvdan oldin qayta ko'rib chiqiladi (spec §"Litsenziya eslatmasi"ga qarang).
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/DOCKER.md
git commit -m "Hujjatlar: fetch-ziyouz (README bullet + DOCKER.md #9)"
```

---

### Task 6: Real tekshiruv (qo'lda, subagent emas — men o'zim bajaraman)

Bu bosqich avtomatlashtirilmaydi — implementatsiya tugagach quyidagilarni qo'lda
tekshiraman:

1. `docker compose run --rm ufl ufl fetch-ziyouz --limit 5` — real ziyouz.com bilan
   ishga tushirib, 5 ta fayl to'g'ri kategoriyaga yozilganini va `ufl stats`da
   ko'rinishini tasdiqlayman.
2. `data/tmp_ziyouz/` bo'sh qolganini (vaqtinchalik fayllar o'chirilgan) tekshiraman.
3. Har qanday `unmapped_categories` ogohlantirishi chiqsa, `category_map.py`ni
   yangilab, alohida kichik commit qilaman.
4. `git push`.
