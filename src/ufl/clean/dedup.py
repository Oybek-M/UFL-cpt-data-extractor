"""Deduplikatsiya: aynan va normallashtirilgan takror matnlarni olib tashlash.

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §11
v1: exact + normallashtirilgan hash (global, fayllar bo'ylab). Near-dup
(MinHash LSH) interfeysi shu yerda ochilgan, lekin Faza 2+ gacha implement
qilinmagan (config.dedup.near_dup_enabled hozircha har doim False).
"""

from __future__ import annotations

import hashlib
import re

_WHITESPACE_RE = re.compile(r"\s+")


class DeduplicationStore:
    """Ko'rilgan matn hashlarini saqlaydi (fayllar bo'ylab global holat)."""

    def __init__(self, near_dup_enabled: bool = False) -> None:
        if near_dup_enabled:
            raise NotImplementedError(
                "Near-dup (MinHash) dedup hali implement qilinmagan — Faza 2+ da qo'shiladi."
            )
        self._seen_hashes: set[str] = set()

    def is_duplicate(self, text: str) -> bool:
        exact_hash = _hash_text(text)
        normalized_hash = _hash_text(_normalize(text))
        return exact_hash in self._seen_hashes or normalized_hash in self._seen_hashes

    def add(self, text: str) -> None:
        self._seen_hashes.add(_hash_text(text))
        self._seen_hashes.add(_hash_text(_normalize(text)))

    def check_and_add(self, text: str) -> bool:
        """Takror bo'lsa True (qo'shmaydi); aks holda qo'shadi va False qaytaradi."""
        if self.is_duplicate(text):
            return True
        self.add(text)
        return False


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()
