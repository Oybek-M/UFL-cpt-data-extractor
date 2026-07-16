import gzip

from ufl.crawl.sitemap import parse_sitemap

_URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://kun.uz/news/a</loc><lastmod>2026-07-10</lastmod></url>
  <url><loc>https://kun.uz/news/b</loc><lastmod>2026-07-16</lastmod></url>
  <url><loc>https://kun.uz/news/c</loc></url>
</urlset>"""

_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://kun.uz/sitemap-1.xml</loc><lastmod>2026-07-01</lastmod></sitemap>
  <sitemap><loc>https://kun.uz/sitemap-2.xml</loc><lastmod>2026-07-15</lastmod></sitemap>
</sitemapindex>"""


def test_parse_sitemap_urlset_returns_entries():
    kind, entries = parse_sitemap(_URLSET)
    assert kind == "urlset"
    locs = [loc for loc, _ in entries]
    assert "https://kun.uz/news/a" in locs
    assert len(entries) == 3


def test_parse_sitemap_sorts_newest_first():
    _, entries = parse_sitemap(_URLSET)
    # Eng yangi lastmod (2026-07-16) birinchi bo'lishi kerak
    assert entries[0][0] == "https://kun.uz/news/b"


def test_parse_sitemap_detects_sitemapindex():
    kind, entries = parse_sitemap(_INDEX)
    assert kind == "sitemapindex"
    assert entries[0][0] == "https://kun.uz/sitemap-2.xml"  # newest first


def test_parse_sitemap_handles_gzip():
    kind, entries = parse_sitemap(gzip.compress(_URLSET))
    assert kind == "urlset"
    assert len(entries) == 3
