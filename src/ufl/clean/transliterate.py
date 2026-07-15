"""Kirill (o'zbek) matnni lotin alifbosiga o'giradi.

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §7
Bu heuristik yondashuv — 100% lingvistik to'g'rilikka da'vo qilmaydi,
maqsad kitoblardagi aksariyat kirill matnni ishonchli lotinga o'girish.
"""

from __future__ import annotations

import re

# е va ц alohida (kontekstga bog'liq) qoidaga ega, shu sababli asosiy jadvalda yo'q.
_SIMPLE_MAP: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "x", "ч": "ch", "ш": "sh", "щ": "sh",
    "ъ": "'", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}

_VOWELS = set("аеёиоуэюя")
_CYRILLIC_LETTERS = set(_SIMPLE_MAP) | {"е", "ц"}

_WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁўЎқҚғҒҳҲ]+")


def to_latin(text: str) -> str:
    """Matndagi kirill so'zlarni lotinga o'giradi; lotin/raqam/tinish belgilar o'zgarishsiz qoladi."""
    return _WORD_RE.sub(lambda m: _transliterate_word(m.group(0)), text)


def _transliterate_word(word: str) -> str:
    word_lower = word.lower()
    cased_letters = [c for c in word if c.isalpha()]
    all_caps = bool(cased_letters) and all(c.isupper() for c in cased_letters)

    parts: list[str] = []
    for index, ch in enumerate(word):
        ch_lower = ch.lower()
        if ch_lower in _CYRILLIC_LETTERS:
            latin = _transliterate_char(ch_lower, index, word_lower)
            parts.append(_apply_case(latin, ch, all_caps))
        else:
            parts.append(ch)  # allaqachon lotin yoki boshqa belgi
    return "".join(parts)


def _transliterate_char(ch_lower: str, index: int, word_lower: str) -> str:
    if ch_lower == "е":
        prev = word_lower[index - 1] if index > 0 else None
        if index == 0 or prev in _VOWELS:
            return "ye"
        return "e"
    if ch_lower == "ц":
        prev = word_lower[index - 1] if index > 0 else None
        nxt = word_lower[index + 1] if index + 1 < len(word_lower) else None
        if index == 0 or (prev in _VOWELS and nxt in _VOWELS):
            return "ts"
        return "s"
    return _SIMPLE_MAP[ch_lower]


def _apply_case(latin: str, original_char: str, all_caps_word: bool) -> str:
    if not latin or not original_char.isalpha() or not original_char.isupper():
        return latin
    if all_caps_word:
        return latin.upper()
    return latin[0].upper() + latin[1:]
