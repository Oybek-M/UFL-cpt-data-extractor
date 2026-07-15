"""EPUB fayllarni ingest qilish (ebooklib + BeautifulSoup)."""

from __future__ import annotations

from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from ufl.ingest.base import Block, Document


def extract(path: Path) -> Document:
    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    blocks = []
    index = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        if not item.is_chapter():
            continue  # nav.xhtml kabi mundarija hujjatlari — asosiy matn emas
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup.find_all(["p", "h1", "h2", "h3", "li"]):
            text = tag.get_text(strip=True)
            if text:
                blocks.append(Block(text=text, page=index))
                index += 1
    return Document(blocks=blocks)
