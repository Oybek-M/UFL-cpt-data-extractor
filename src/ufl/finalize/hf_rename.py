"""HF (HuggingFace) dataset manbasini fayl nomidan yashirish.

fetch-hf shardlarni `{dataset_slug}__{split}__shard-{N}.txt` nomida yozadi
(masalan "tahrirchi_uz-crawl__news__shard-000001.txt") — bu HF va tashkilot
nomini fosh qiladi. Bu modul dataset_slug qismini generic alias bilan
almashtiradi, split va shard raqamini saqlab qoladi.

Manba: docs/superpowers/specs/2026-07-18-finalize-corpus-design.md
Xaritada yo'q dataset uchun None qaytariladi (chaqiruvchi tomon o'tkazib
yuborishi va ogohlantirishi kerak — hech qachon taxminiy alias yaratilmaydi,
"shubha bo'lsa tashla" tamoyili, xuddi ziyouz/category_map.py'dagi kabi).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ufl.ingest.hf_dataset import dataset_slug

DATASET_ALIAS: dict[str, str] = {
    "tahrirchi/uz-crawl": "corpus-a",
    "tahrirchi/uz-books-v2": "corpus-b",
    "yakhyo/uz-wiki": "corpus-c",
}

_SLUG_TO_DATASET_ID: dict[str, str] = {
    dataset_slug(dataset_id): dataset_id for dataset_id in DATASET_ALIAS
}

_SHARD_FILENAME_RE = re.compile(r"^(?P<slug>.+)__(?P<split>.+)__shard-(?P<shard>\d+)\.txt$")


@dataclass
class HfShardMatch:
    dataset_id: str | None  # None — slug DATASET_ALIAS'da topilmadi
    slug: str
    split: str
    shard: str


def match_hf_shard_filename(filename: str) -> HfShardMatch | None:
    """Fayl nomi HF shard naqshiga (`{slug}__{split}__shard-{N}.txt`) mos
    kelmasa None. Mos kelsa, lekin slug noma'lum bo'lsa dataset_id=None
    (chaqiruvchi `match.slug` orqali ogohlantirishi mumkin)."""
    match = _SHARD_FILENAME_RE.match(filename)
    if match is None:
        return None
    slug = match.group("slug")
    return HfShardMatch(
        dataset_id=_SLUG_TO_DATASET_ID.get(slug),
        slug=slug,
        split=match.group("split"),
        shard=match.group("shard"),
    )


def source_path_for_filename(filename: str) -> str | None:
    """Fayl nomidan ufl.db'dagi `path` qiymatini (`hf:{dataset_id}:{split}:
    shard-{N}`) hisoblaydi. Mos kelmasa yoki dataset noma'lum bo'lsa None."""
    match = match_hf_shard_filename(filename)
    if match is None or match.dataset_id is None:
        return None
    return f"hf:{match.dataset_id}:{match.split}:shard-{match.shard}"


def renamed_filename(filename: str) -> str | None:
    """De-branded fayl nomini qaytaradi (dataset_slug o'rniga alias, split va
    shard saqlanadi). Mos kelmasa yoki dataset noma'lum bo'lsa None."""
    match = match_hf_shard_filename(filename)
    if match is None or match.dataset_id is None:
        return None
    alias = DATASET_ALIAS[match.dataset_id]
    return f"{alias}__{match.split}__shard-{match.shard}.txt"
