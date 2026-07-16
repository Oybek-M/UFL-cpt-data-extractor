"""HTML fragmentini tartibli matn bloklariga aylantirish.

Manba: website-to-txt-collector/continuous_collector.py (184-282) — UFL uslubida port.
Bu bosqich faqat strukturaviy tozalash qiladi (blok tartibi, obvious-trash, dublikat).
Til-filtri, transliteratsiya, sifat gate — UFL'ning `ufl.clean` pipeline'ida (crawl'da
nomzod tanlangandan keyin).
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Iterable

from bs4 import BeautifulSoup, NavigableString, Tag

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "blockquote", "li", "div", "figcaption"}
DROP_TAGS = {
    "script", "style", "noscript", "svg", "form", "button", "nav", "footer",
    "header", "aside", "iframe",
}


def clean_lines(text: str) -> str:
    """Whitespace/entity normalizatsiya; qatorlar `\\n\\n` bilan, ketma-ket takror olib tashlanadi."""
    text = unicodedata.normalize("NFC", html.unescape(text))
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    previous = ""
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        line = re.sub(r"\s+([.,:;!?])", r"\1", line)
        if line and line != previous:
            lines.append(line)
            previous = line
    return "\n\n".join(lines).strip()


def fragment_blocks(fragment: str) -> list[str]:
    """HTML fragmentdan vizual tartibda matn bloklarini ajratadi (DROP_TAGS chiqarib tashlanadi)."""
    soup = BeautifulSoup(fragment, "html.parser")
    for node in soup.select(",".join(sorted(DROP_TAGS))):
        node.decompose()
    blocks: list[str] = []

    def append(value: str) -> None:
        cleaned = clean_lines(value).replace("\n\n", " ").strip()
        if cleaned and len(cleaned) >= 2 and (not blocks or blocks[-1] != cleaned):
            blocks.append(cleaned)

    def has_nested_block(node: Tag) -> bool:
        return node.find(list(BLOCK_TAGS), recursive=True) is not None

    def walk_children(node: BeautifulSoup | Tag) -> None:
        inline: list[str] = []

        def flush() -> None:
            if inline:
                append(" ".join(inline))
                inline.clear()

        for child in node.children:
            if isinstance(child, NavigableString):
                value = str(child).strip()
                if value:
                    inline.append(value)
                continue
            if not isinstance(child, Tag) or child.name in DROP_TAGS:
                continue
            if child.name in BLOCK_TAGS:
                flush()
                if has_nested_block(child):
                    walk_children(child)
                else:
                    append(child.get_text(" ", strip=True))
            elif has_nested_block(child):
                flush()
                walk_children(child)
            else:
                value = child.get_text(" ", strip=True)
                if value:
                    inline.append(value)
        flush()

    walk_children(soup)
    if not blocks:
        fallback = clean_lines(soup.get_text("\n", strip=True))
        blocks = [part for part in fallback.split("\n\n") if part.strip()]
    return blocks


def fragment_text(fragment: str) -> str:
    return "\n\n".join(fragment_blocks(fragment))


def obvious_trash_block(value: str) -> bool:
    """Aniq shovqin bloklari: reklama yorlig'i yoki qisqa foto/video/manba izohi."""
    text = clean_lines(value).strip()
    folded = text.casefold().strip(" .:—-\t")
    if folded in {"reklama", "advertisement", "реклама", "sponsored", "homiylik materiali"}:
        return True
    if len(text) <= 300 and re.match(
        r"^(foto|surat|video|illustratsiya|manba)\s*:", text, flags=re.IGNORECASE
    ):
        return True
    return False


def clean_content_blocks(blocks: Iterable[str]) -> list[str]:
    """Trash bloklarni va (normallashtirilgan kalit bo'yicha) dublikatlarni olib tashlaydi."""
    result: list[str] = []
    seen: set[str] = set()
    for value in blocks:
        cleaned = clean_lines(value).strip()
        if not cleaned or obvious_trash_block(cleaned):
            continue
        key = re.sub(r"\W+", "", cleaned.casefold(), flags=re.UNICODE)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result
