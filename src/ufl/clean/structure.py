"""Struktura tozalash: front-matter, kolontitul, sahifa raqami, mundarija,
bibliografiya kabi shovqinni asosiy matndan ajratib olib tashlaydi.

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §6
Bu bosqich "mukammal" bo'lolmaydi — maqsad aksariyat shovqinni olib tashlash;
qolgan noaniqliklarni keyingi sifat gate (clean/quality.py) ushlaydi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ufl.ingest.base import Block, Document

_PAGE_NUMBER_RE = re.compile(r"^[\-–—\s]*\d{1,4}[\-–—\s]*(bet)?[\-–—\s]*$", re.IGNORECASE)
_TOC_RE = re.compile(r"\.{3,}\s*\d{1,4}\s*$")
_YEAR_RE = re.compile(r"(19|20)\d{2}")
_DIGITS_RE = re.compile(r"\d+")
_WHITESPACE_RE = re.compile(r"\s+")

_FRONT_MATTER_KEYWORDS = (
    "isbn", "udk", "kbk", "nashriyot", "mundarija", "tahrir", "muharrir", "litsenziya",
)

# Kolontitul sifatida hisoblash uchun matn shu uzunlikdan qisqa bo'lishi kerak
# (uzun paragraflar tasodifan takrorlangan bo'lsa ham noto'g'ri tashlanmasin).
_MAX_HEADER_FOOTER_LENGTH = 100


@dataclass
class StructureResult:
    kept_blocks: list[Block]
    dropped: list[tuple[Block, str]]


def clean_structure(
    document: Document,
    *,
    header_footer_min_repeats: int = 3,
    detect_toc: bool = True,
    detect_bibliography: bool = True,
    front_matter_max_page: int = 3,
) -> StructureResult:
    repeated_texts = _find_repeated_header_footer_texts(document.blocks, header_footer_min_repeats)

    kept: list[Block] = []
    dropped: list[tuple[Block, str]] = []

    for block in document.blocks:
        text = block.text.strip()
        normalized = _normalize_for_repeat_check(text)

        if _is_page_number(text):
            dropped.append((block, "sahifa_raqami"))
            continue
        if normalized in repeated_texts:
            dropped.append((block, "kolontitul"))
            continue
        if detect_toc and _is_toc_entry(text):
            dropped.append((block, "mundarija"))
            continue
        if block.page <= front_matter_max_page and _is_front_matter_keyword(text):
            dropped.append((block, "front_matter"))
            continue
        if detect_bibliography and _is_bibliography_entry(text):
            dropped.append((block, "bibliografiya"))
            continue

        kept.append(block)

    return StructureResult(kept_blocks=kept, dropped=dropped)


def _is_page_number(text: str) -> bool:
    return bool(_PAGE_NUMBER_RE.match(text))


def _is_toc_entry(text: str) -> bool:
    return bool(_TOC_RE.search(text))


def _is_front_matter_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _FRONT_MATTER_KEYWORDS)


def _is_bibliography_entry(text: str) -> bool:
    separator_count = text.count(",") + text.count(";")
    return separator_count >= 3 and bool(_YEAR_RE.search(text))


def _normalize_for_repeat_check(text: str) -> str:
    without_digits = _DIGITS_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", without_digits).strip().lower()


def _find_repeated_header_footer_texts(blocks: list[Block], min_repeats: int) -> set[str]:
    pages_by_text: dict[str, set[int]] = {}
    for block in blocks:
        normalized = _normalize_for_repeat_check(block.text.strip())
        if not normalized or len(normalized) >= _MAX_HEADER_FOOTER_LENGTH:
            continue
        pages_by_text.setdefault(normalized, set()).add(block.page)
    return {text for text, pages in pages_by_text.items() if len(pages) >= min_repeats}
