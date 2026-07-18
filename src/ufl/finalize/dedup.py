"""Global (korpus-bo'ylab) exact-hash deduplikatsiya.

Ingestion paytidagi dedup (`clean/dedup.py`) faqat bitta CLI ishga tushirish
doirasida ishlaydi. Bu modul butun `data/output/` papkasi bo'ylab (turli
sanalarda/manbalardan yig'ilgan fayllar orasida ham) aynan bir xil matnli
fayllarni topib, takrorlanganlarini `data/rejected/duplicates/`ga ko'chiradi
(o'chirilmaydi — qaytarib olish mumkin).

Manba: docs/superpowers/specs/2026-07-18-finalize-corpus-design.md
"""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ufl.finalize.hf_rename import source_path_for_filename
from ufl.logging_setup import get_logger
from ufl.store.db import Store

logger = get_logger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_ZIYOUZ_ID_RE = re.compile(r"^(\d+)_")


@dataclass
class DuplicateGroup:
    kept: Path
    duplicates: list[Path]


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def _hash_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return hashlib.sha1(_normalize(text).encode("utf-8")).hexdigest()


def find_duplicate_groups(output_dir: Path) -> list[DuplicateGroup]:
    """`output_dir`dagi barcha kategoriya papkalarida (`*/*.txt`) bir xil
    (normallashtirilgan) matnli fayllarni topadi. Har guruhda birinchi fayl
    (nomi bo'yicha saralangan) saqlanadi, qolganlari 'duplicates' hisoblanadi.
    O'qib bo'lmagan fayllar jim o'tkazib yuboriladi."""
    by_hash: dict[str, list[Path]] = {}
    for txt_path in sorted(Path(output_dir).glob("*/*.txt")):
        try:
            file_hash = _hash_file(txt_path)
        except OSError:
            continue
        by_hash.setdefault(file_hash, []).append(txt_path)

    return [
        DuplicateGroup(kept=paths[0], duplicates=paths[1:])
        for paths in by_hash.values()
        if len(paths) > 1
    ]


def infer_source_path(filename: str) -> str | None:
    """Fayl nomidan ufl.db'dagi `path` qiymatini taxmin qiladi (ziyouz yoki
    HF naqshi). Mos kelmasa None (chaqiruvchi DB yozuvini yangilamasdan
    o'tkazib yuborishi kerak)."""
    hf_path = source_path_for_filename(filename)
    if hf_path is not None:
        return hf_path
    match = _ZIYOUZ_ID_RE.match(filename)
    if match is not None:
        return f"ziyouz:{match.group(1)}"
    return None


def quarantine_duplicates(
    groups: list[DuplicateGroup], *, rejected_dir: Path, store: Store
) -> int:
    """Har bir guruhdagi dublikatlarni `rejected_dir/duplicates/{category}/`ga
    ko'chiradi va DB'da (topilsa) dedup_status='duplicate' deb belgilaydi.
    Ko'chirilgan fayllar sonini qaytaradi."""
    moved = 0
    for group in groups:
        for dup_path in group.duplicates:
            category = dup_path.parent.name
            dest_dir = Path(rejected_dir) / "duplicates" / category
            dest_dir.mkdir(parents=True, exist_ok=True)
            try:
                # Path.replace() (os.rename) turli Docker bind-mountlar orasida
                # (masalan UFL-Datas vs data/) EXDEV bilan xato beradi —
                # shutil.move avtomatik nusxalab-o'chirishga o'tadi.
                shutil.move(str(dup_path), str(dest_dir / dup_path.name))
            except OSError as exc:
                logger.warning("Dublikatni ko'chirib bo'lmadi: %s — %s", dup_path, exc)
                continue
            moved += 1
            source_path = infer_source_path(dup_path.name)
            if source_path is not None:
                store.mark_duplicate(source_path)
    return moved
