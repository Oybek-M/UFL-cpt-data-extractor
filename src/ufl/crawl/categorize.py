"""Auto-kategoriya (LOCAL-BIRINCHI) — MiniMax token tejash uchun.

Tartib: URL-yo'l evristikasi (bepul) → section-meta (bepul) → domen-standart kESH
(bepul) → faqat noaniqda MiniMax. Dizayn spec §6.2-6.3.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Protocol

# UFL kategoriyasi → shu kategoriyaga ishora qiluvchi kalit so'zlar (URL segment / section
# yorlig'i, o'zbek + rus + ingliz). Birinchi mos kelgan kategoriya tanlanadi.
_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "gov_legal": (
        "qonun", "qonunchilik", "huquq", "hukumat", "davlat", "siyosat", "parlament",
        "farmon", "qaror", "закон", "право", "власть", "law", "gov", "politics",
    ),
    "education": (
        "talim", "ta-lim", "maktab", "universitet", "fan", "ilm", "oquv", "abituriyent",
        "образование", "наука", "education", "science", "school",
    ),
    "technical": (
        "texnologiya", "texnika", "it", "kompyuter", "internet", "gadjet", "dasturlash",
        "технологии", "tech", "technology", "digital", "ai",
    ),
    "domain_haf": (
        "salomatlik", "tibbiyot", "sogliq", "qishloq", "dehqonchilik", "biznes", "iqtisodiyot",
        "moliya", "bank", "здоровье", "медицина", "бизнес", "экономика", "health", "business",
        "economy", "finance", "agro",
    ),
    "conversations": (
        "intervyu", "suhbat", "podkast", "интервью", "interview", "podcast",
    ),
}


class _MiniMaxLike(Protocol):
    def classify_category(self, title: str, snippet: str, valid_categories: list[str]) -> str | None:
        ...


_APOSTROPHES = str.maketrans("", "", "'’‘ʻʼ`")


def _match_hint(text: str, valid_categories: list[str]) -> str | None:
    lowered = text.casefold().translate(_APOSTROPHES)
    for category, hints in _CATEGORY_HINTS.items():
        if category not in valid_categories:
            continue
        if any(hint in lowered for hint in hints):
            return category
    return None


def category_from_url(url: str, valid_categories: list[str]) -> str | None:
    """URL yo'l segmentlaridan kategoriya (bepul). Topilmasa None."""
    path = urllib.parse.urlsplit(url).path
    segments = [seg for seg in re.split(r"[/_-]+", path.casefold()) if seg]
    for segment in segments:
        match = _match_hint(segment, valid_categories)
        if match:
            return match
    return None


def category_from_section(section: str | None, valid_categories: list[str]) -> str | None:
    """Sayt bo'lim yorlig'idan (article:section/breadcrumb) kategoriya (bepul)."""
    if not section:
        return None
    return _match_hint(section, valid_categories)


def resolve_category(
    mode: str,
    *,
    url: str,
    valid_categories: list[str],
    section: str | None = None,
    title: str = "",
    snippet: str = "",
    minimax: _MiniMaxLike | None = None,
    state: object | None = None,
    domain: str | None = None,
    default: str = "web_news",
) -> str:
    """Kategoriya aniqlash. `mode` 8 kategoriyadan biri (manual) yoki 'auto'.

    Auto: URL-yo'l → section → domen-standart kESH → MiniMax → default. MiniMax faqat
    oxirgi chora (token tejash). MiniMax natijasi domen-standart sifatida kESHlanadi.
    """
    if mode != "auto":
        return mode

    for candidate in (category_from_url(url, valid_categories), category_from_section(section, valid_categories)):
        if candidate:
            return candidate

    cache_key = f"category_default:{domain}" if domain else None
    if state is not None and cache_key:
        cached = state.get_meta(cache_key)  # type: ignore[attr-defined]
        if cached in valid_categories:
            return cached

    if minimax is not None:
        chosen = minimax.classify_category(title, snippet, valid_categories)
        if chosen in valid_categories:
            if state is not None and cache_key:
                state.set_meta(cache_key, chosen)  # type: ignore[attr-defined]
            return chosen

    return default
