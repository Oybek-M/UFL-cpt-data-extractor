"""Matn normalizatsiyasi: Unicode NFC, apostrof/tirnoq/chiziqcha unifikatsiyasi,
bo'sh joy va qator sindirilgan so'zlarni tozalash.

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §10
"""

from __future__ import annotations

import re
import unicodedata

_APOSTROPHE_VARIANTS = "'‘’ʻʼ`´"
_APOSTROPHE_TARGETS = {"ascii": "'", "unicode": "ʻ"}

_DOUBLE_QUOTE_VARIANTS = "«»“”„"
_QUOTE_TARGETS = {"straight": '"'}

_DASH_VARIANTS = "–—"  # en dash, em dash
_INVISIBLE_CHARS = "​‌‍﻿­"

# Wiki/CMS tahrir-havola qoldiqlari (masalan Wikipedia'da sarlavhaga yopishib qoladigan
# "[tahrirlash | manbasini tahrirlash]"). Yaxshilanish B — sessiyada haqiqiy Wikipedia
# sahifasida kuzatilgan (docs/superpowers/specs/2026-07-16-...-design.md §"Yaxshilanish B").
_WIKI_EDIT_KEYWORDS = (
    "manbasini tahrirlash", "tahrirlash", "tahrir", "edit", "изменить", "редактировать",
)
_WIKI_EDIT_GROUP = "|".join(re.escape(keyword) for keyword in _WIKI_EDIT_KEYWORDS)
_WIKI_EDIT_RE = re.compile(
    rf"\[\s*(?:{_WIKI_EDIT_GROUP})(?:\s*\|\s*(?:{_WIKI_EDIT_GROUP}))*\s*\]", re.IGNORECASE
)

_APOSTROPHE_RE = re.compile(f"[{re.escape(_APOSTROPHE_VARIANTS)}]")
_QUOTE_RE = re.compile(f"[{re.escape(_DOUBLE_QUOTE_VARIANTS)}]")
_DASH_RE = re.compile(f"[{re.escape(_DASH_VARIANTS)}]")
_INVISIBLE_RE = re.compile(f"[{re.escape(_INVISIBLE_CHARS)}]")
_HYPHEN_LINEBREAK_RE = re.compile(r"(\w)-\n(\w)")
_HORIZONTAL_WS_RE = re.compile(r"[ \t]+")
_TRAILING_SPACE_RE = re.compile(r" \n")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize(text: str, apostrophe_mode: str = "ascii", quote_style: str = "straight") -> str:
    text = unicodedata.normalize("NFC", text)
    text = _WIKI_EDIT_RE.sub("", text)
    text = _INVISIBLE_RE.sub("", text)
    text = _DASH_RE.sub("-", text)
    text = _HYPHEN_LINEBREAK_RE.sub(r"\1\2", text)
    text = _APOSTROPHE_RE.sub(_APOSTROPHE_TARGETS[apostrophe_mode], text)
    text = _QUOTE_RE.sub(_QUOTE_TARGETS[quote_style], text)
    text = _HORIZONTAL_WS_RE.sub(" ", text)
    text = _TRAILING_SPACE_RE.sub("\n", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()
