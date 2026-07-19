"""Blok-darajasidagi tozalash pipeline'i (transliteratsiya → til → sifat → normalizatsiya → dedup).

Bu mantiq `ufl.pipeline.process_file` (fayl ingest) va `ufl.crawl.collector` (sayt crawl)
ikkalasida ishlatiladi — takrorlanmasligi uchun shu yerda birlashtirilgan.
"""

from __future__ import annotations

from typing import Callable, Iterable, TypeVar

from ufl.clean.dedup import DeduplicationStore
from ufl.clean.language import FastTextPredictor, is_uzbek
from ufl.clean.normalize import normalize
from ufl.clean.quality import assess, strip_garbage_tokens
from ufl.clean.transliterate import to_latin

T = TypeVar("T")


def clean_paragraphs(
    items: Iterable[T],
    *,
    dedup_store: DeduplicationStore,
    get_text: Callable[[T], str] = lambda item: item,  # type: ignore[assignment,return-value]
    fasttext_predict: FastTextPredictor | None = None,
    min_language_confidence: float = 0.65,
    min_heuristic_score: float = 0.20,
    apostrophe_mode: str = "ascii",
    quality_kwargs: dict | None = None,
    on_drop: Callable[[T, str], None] | None = None,
) -> list[str]:
    """Har element uchun: translit → is_uzbek → assess → normalize → dedup.

    Saqlangan (normalizatsiyalangan) paragraflar ro'yxatini qaytaradi. Tashlangan har
    element uchun `on_drop(item, reason)` chaqiriladi (reason: til_ozbekcha_emas / sifat
    kodlari / normalizatsiyadan_song_bosh / takror).
    """
    quality = quality_kwargs or {}
    kept: list[str] = []
    for item in items:
        raw = get_text(item)
        latin = to_latin(raw)
        latin = "\n".join(strip_garbage_tokens(line) for line in latin.split("\n"))

        if not is_uzbek(
            latin,
            fasttext_predict=fasttext_predict,
            min_confidence=min_language_confidence,
            min_heuristic_score=min_heuristic_score,
        ).is_uzbek:
            if on_drop:
                on_drop(item, "til_ozbekcha_emas")
            continue

        result = assess(latin, **quality)
        if not result.keep:
            if on_drop:
                on_drop(item, result.reason or "sifat")
            continue

        normalized = normalize(latin, apostrophe_mode=apostrophe_mode)
        if not normalized:
            if on_drop:
                on_drop(item, "normalizatsiyadan_song_bosh")
            continue

        if dedup_store.check_and_add(normalized):
            if on_drop:
                on_drop(item, "takror")
            continue

        kept.append(normalized)
    return kept
