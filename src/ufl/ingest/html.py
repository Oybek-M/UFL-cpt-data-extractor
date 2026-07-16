"""HTML (veb-sahifa yoki DevTools dump) fayllarni ingest qilish.

Yaxshilanish A (Faza 4.2): avval crawl'ning ko'p-strategiyali ekstraktori ishlaydi
(JSON-LD / Nuxt / Next.js / DOM-skorlash) — zamonaviy JS-og'ir saytlarda (masalan
Nuxt bo'lgan daryo.uz) trafilatura yolg'iz o'zi ushlamaydigan holatlarni qamrab oladi.
Nomzod topilmasa yoki juda qisqa bo'lsa — trafilatura'ga fallback.
"""

from __future__ import annotations

from pathlib import Path

import trafilatura
from bs4 import BeautifulSoup

from ufl.crawl.candidates import candidates_from_page, extract_metadata
from ufl.ingest.base import Block, Document

_MIN_CANDIDATE_CHARS = 250


def extract(path: Path) -> Document:
    html = path.read_text(encoding="utf-8", errors="replace")
    return html_to_document(html)


def html_to_document(html: str) -> Document:
    # 1. Ko'p-strategiyali ekstraksiya (crawl candidates)
    try:
        soup = BeautifulSoup(html, "html.parser")
        title, _ = extract_metadata(soup, "")
        candidates = candidates_from_page(soup, title)
    except Exception:  # noqa: BLE001 — buzuq HTML: trafilatura fallback'ga o't
        candidates = []
    if candidates and len(candidates[0].text) >= _MIN_CANDIDATE_CHARS:
        best = candidates[0]
        paragraphs = best.blocks or [p.strip() for p in best.text.split("\n\n") if p.strip()]
        return Document(blocks=[Block(text=p, page=i) for i, p in enumerate(paragraphs)])

    # 2. Trafilatura fallback
    extracted = trafilatura.extract(
        html, output_format="txt", include_comments=False, include_tables=False
    )
    if not extracted:
        return Document(blocks=[])
    paragraphs = [p.strip() for p in extracted.split("\n") if p.strip()]
    return Document(blocks=[Block(text=p, page=i) for i, p in enumerate(paragraphs)])
