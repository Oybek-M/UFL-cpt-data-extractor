import json

from bs4 import BeautifulSoup

from ufl.crawl.candidates import (
    candidates_from_page,
    extract_metadata,
    probable_article_page,
    title_with_punctuation,
)

# Chegaralar (jsonld raw>=300, fragment_text>=250) dan oshishi uchun yetarlicha uzun tana.
_BODY_HTML = (
    "<p>Birinchi paragraf: bu maqola tanasi yetarlicha uzun bo'lishi kerak, "
    "chunki ekstraktor qisqa nomzodlarni rad etadi va faqat jiddiy matnni oladi.</p>"
    "<p>Ikkinchi paragraf: qo'shimcha jumlalar bilan matn uzaytiriladi va tabiiy "
    "o'zbekcha nasr ko'rinishida bo'ladi. Yana bir necha so'z qo'shamiz.</p>"
    "<p>Uchinchi paragraf: nomzod balli yetarli bo'lishi uchun paragraflar soni "
    "va umumiy uzunlik muhim. Shuning uchun matnni yana kengaytiramiz.</p>"
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_candidates_jsonld_articlebody():
    body_json = json.dumps({"@type": "NewsArticle", "articleBody": _BODY_HTML})
    html = f'<html><head><script type="application/ld+json">{body_json}</script></head><body></body></html>'
    cands = candidates_from_page(_soup(html), title="Maqola sarlavhasi")
    assert cands
    assert any(c.method == "jsonld" for c in cands)
    assert len(cands[0].text) >= 250


def test_candidates_nuxt_payload():
    payload = ["boshqa", f'<div class="post-content">{_BODY_HTML}</div>', 42]
    html = (
        "<html><body>"
        f'<script id="__NUXT_DATA__">{json.dumps(payload)}</script>'
        "</body></html>"
    )
    cands = candidates_from_page(_soup(html), title="Maqola")
    assert any(c.method == "nuxt" for c in cands)


def test_candidates_next_data():
    payload = {"props": {"pageProps": {"article": {"body": _BODY_HTML}}}}
    html = (
        "<html><body>"
        f'<script id="__NEXT_DATA__">{json.dumps(payload)}</script>'
        "</body></html>"
    )
    cands = candidates_from_page(_soup(html), title="Maqola")
    assert any(c.method == "next" for c in cands)


def test_candidates_dom_scoring_prefers_low_link_density():
    # Navigatsiya bloki (yuqori link-zichlik) vs asosiy maqola (past link-zichlik)
    nav_links = "".join(f'<li><a href="/a{i}">Havola {i}</a></li>' for i in range(20))
    html = (
        "<html><body>"
        f'<div class="menu"><ul>{nav_links}</ul></div>'
        f'<article class="article-content">{_BODY_HTML}</article>'
        "</body></html>"
    )
    cands = candidates_from_page(_soup(html), title="Maqola sarlavhasi")
    assert cands
    # Eng yuqori balli nomzod asosiy maqola tanasi bo'lishi kerak
    assert "Birinchi paragraf" in cands[0].text


def test_candidates_boilerplate_penalty_ranks_privacy_low():
    privacy = "<p>" + ("Maxfiylik siyosati va foydalanish shartlari haqida. " * 12) + "</p>"
    html = (
        "<html><body>"
        f'<div class="privacy">{privacy}</div>'
        f'<article class="article-content">{_BODY_HTML}</article>'
        "</body></html>"
    )
    cands = candidates_from_page(_soup(html), title="Maqola sarlavhasi")
    assert "Birinchi paragraf" in cands[0].text


def test_extract_metadata_reads_title_and_date():
    html = (
        "<html><head>"
        '<meta property="og:title" content="Ajoyib sarlavha">'
        '<meta property="article:published_time" content="2026-07-16T10:00:00Z">'
        "</head><body></body></html>"
    )
    title, published = extract_metadata(_soup(html), "https://kun.uz/news/x")
    assert title == "Ajoyib sarlavha"
    assert published is not None and published.startswith("2026-07-16")


def test_probable_article_page_detects_og_article():
    html = '<html><head><meta property="og:type" content="article"></head><body></body></html>'
    assert probable_article_page(_soup(html), "https://kun.uz/news/x") is True


def test_probable_article_page_false_for_plain_page():
    html = "<html><head></head><body><p>Salom</p></body></html>"
    assert probable_article_page(_soup(html), "https://kun.uz/about") is False


def test_title_with_punctuation_adds_period():
    assert title_with_punctuation("Sarlavha") == "Sarlavha."
    assert title_with_punctuation("Savolmi?") == "Savolmi?"
