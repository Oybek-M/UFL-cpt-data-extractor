"""HTML (veb-sahifa yoki DevTools dump) fayllarni ingest qilish (trafilatura)."""

from __future__ import annotations

from pathlib import Path

import trafilatura

from ufl.ingest.base import Block, Document


def extract(path: Path) -> Document:
    html = path.read_text(encoding="utf-8", errors="replace")
    extracted = trafilatura.extract(
        html, output_format="txt", include_comments=False, include_tables=False
    )
    if not extracted:
        return Document(blocks=[])
    paragraphs = [p.strip() for p in extracted.split("\n") if p.strip()]
    blocks = [Block(text=p, page=i) for i, p in enumerate(paragraphs)]
    return Document(blocks=blocks)
