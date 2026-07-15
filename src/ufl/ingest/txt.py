"""Oddiy .txt fayllarni ingest qilish."""

from __future__ import annotations

from pathlib import Path

from ufl.ingest.base import Block, Document


def extract(path: Path) -> Document:
    text = path.read_text(encoding="utf-8", errors="replace")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    blocks = [Block(text=p, page=i) for i, p in enumerate(paragraphs)]
    return Document(blocks=blocks)
