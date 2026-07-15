"""FB2 (FictionBook) fayllarni ingest qilish (lxml)."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from ufl.ingest.base import Block, Document


def extract(path: Path) -> Document:
    tree = etree.parse(str(path))
    paragraphs = tree.xpath("//*[local-name()='body']//*[local-name()='p']")
    blocks = []
    for i, p in enumerate(paragraphs):
        text = "".join(p.itertext()).strip()
        if text:
            blocks.append(Block(text=text, page=i))
    return Document(blocks=blocks)
