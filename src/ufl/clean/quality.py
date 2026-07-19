"""Sifat gate: buzuq/shovqinli bloklarni CPT uchun DROP qilish.

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §9
Falsafa: shubha bo'lsa — tashla (precision > recall).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_URL_RE = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")


@dataclass
class QualityResult:
    keep: bool
    reason: str | None = None


def assess(
    text: str,
    *,
    min_chars: int = 25,
    min_words: int = 4,
    max_non_letter_ratio: float = 0.40,
    max_repeated_ngram_ratio: float = 0.30,
    max_upper_ratio: float = 0.70,
    max_url_ratio: float = 0.20,
) -> QualityResult:
    stripped = text.strip()

    if len(stripped) < min_chars:
        return QualityResult(False, "juda_qisqa")

    words = _WORD_RE.findall(stripped)
    if len(words) < min_words:
        return QualityResult(False, "soz_kam")

    non_space = [c for c in stripped if not c.isspace()]
    non_letter = [c for c in non_space if not c.isalpha()]
    if non_space and len(non_letter) / len(non_space) > max_non_letter_ratio:
        return QualityResult(False, "simvol_kop")

    if any(_LATIN_RE.search(w) and _CYRILLIC_RE.search(w) for w in words):
        return QualityResult(False, "aralash_alifbo")

    letters = [c for c in non_space if c.isalpha()]
    upper_letters = [c for c in letters if c.isupper()]
    if letters and len(upper_letters) / len(letters) > max_upper_ratio:
        return QualityResult(False, "katta_harf_kop")

    url_chars = sum(len(m.group()) for m in _URL_RE.finditer(stripped))
    if non_space and url_chars / len(non_space) > max_url_ratio:
        return QualityResult(False, "url_kop")

    most_common_count = Counter(w.lower() for w in words).most_common(1)[0][1]
    if most_common_count / len(words) > max_repeated_ngram_ratio:
        return QualityResult(False, "ortiqcha_takror")

    return QualityResult(True, None)


_ALLOWED_EXTRA_CHARS = set("'-.,!?:;()\"«»–—…")
# Defis toza raqam-guruhini toza harf-guruhidan ajratsa (ikkala tartibda ham:
# "5-bet", "1991-yil" yoki "nashr-0", "band-3"), bu OCR-chiqindi emas — real
# chiqindida (masalan "nshlaga1^") raqam va harf hech qanday defissiz to'g'ridan
# to'g'ri yopishgan bo'ladi.
_DIGIT_FIRST_RE = re.compile(r"^\d+-[^\W\d_]+[.,!?:;]*$", re.UNICODE)
_WORD_FIRST_RE = re.compile(r"^[^\W\d_]+-\d+[.,!?:;]*$", re.UNICODE)


def _is_garbage_token(token: str) -> bool:
    if any(not (ch.isalpha() or ch.isdigit() or ch in _ALLOWED_EXTRA_CHARS) for ch in token):
        return True
    if len(token) == 1 and token.isalpha():
        return True
    has_digit = any(ch.isdigit() for ch in token)
    has_letter = any(ch.isalpha() for ch in token)
    if has_digit and has_letter:
        if _DIGIT_FIRST_RE.match(token) or _WORD_FIRST_RE.match(token):
            return False
        return True
    return False


def strip_garbage_tokens(line: str) -> str:
    """OCR-chiqindi tokenlarni (g'ayrioddiy ramz, izolyatsiyalangan yakka harf,
    raqam-harf yopishish) qatordan olib tashlaydi, qolganlarini bo'shliq bilan
    qayta birlashtiradi. Bo'sh/faqat-bo'shliq qator o'zgarishsiz qaytariladi."""
    if not line.strip():
        return line
    kept = [token for token in line.split() if not _is_garbage_token(token)]
    return " ".join(kept)
