"""Sitemap XML (va gzip) parseri.

Manba: website-to-txt-collector/continuous_collector.py (648-669) — UFL uslubida port.
`urlset` (maqola URL'lari) va `sitemapindex` (ichki sitemaplar) farqlanadi; natija
`lastmod`/`publication_date` bo'yicha teskari (eng yangi birinchi) saralanadi.
"""

from __future__ import annotations

import gzip
import html
import xml.etree.ElementTree as ET


def local_name(tag: str) -> str:
    """XML namespace prefiksini olib tashlaydi (`{ns}loc` -> `loc`)."""
    return tag.rsplit("}", 1)[-1].lower()


def parse_sitemap(content: bytes) -> tuple[str, list[tuple[str, str | None]]]:
    """(root_turi, [(url, lastmod_yoki_None), ...]) qaytaradi, eng yangi birinchi."""
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    root = ET.fromstring(content)
    result: list[tuple[str, str | None]] = []
    for child in list(root):
        location = ""
        modified: str | None = None
        for node in child.iter():
            name = local_name(node.tag)
            if name == "loc" and not location:
                location = html.unescape((node.text or "").strip())
            elif name in {"lastmod", "publication_date"} and not modified:
                modified = (node.text or "").strip()
        if location:
            result.append((location, modified))
    result.sort(key=lambda item: item[1] or "", reverse=True)
    return local_name(root.tag), result
