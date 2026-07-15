"""DJVU fayllarni ingest qilish: matn qatlami (djvutxt) yoki OCR (skaner sahifalar).

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §3, §9
Avval har sahifaning djvutxt matn qatlami tekshiriladi; yetarli bo'lmasa
ddjvu bilan sahifa rasmga render qilinib OCR ga yuboriladi (§5: ishonch
past bo'lsa sahifa DROP, crash emas).
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from PIL import Image

from ufl.ingest.base import Block, Document
from ufl.ingest.ocr import run_ocr

_MIN_TEXT_LAYER_CHARS = 20
_MIN_OCR_CONFIDENCE = 60.0


def extract(
    path: Path,
    *,
    ocr_languages: str = "uzb+uzb_cyrl",
    min_ocr_confidence: float = _MIN_OCR_CONFIDENCE,
) -> Document:
    page_count = _get_page_count(path)
    blocks: list[Block] = []

    for page_number in range(1, page_count + 1):
        text = _extract_page_text(path, page_number)
        if len(text) >= _MIN_TEXT_LAYER_CHARS:
            blocks.extend(Block(text=p, page=page_number) for p in _split_paragraphs(text))
            continue

        image = _render_page(path, page_number)
        ocr_result = run_ocr(image, languages=ocr_languages)
        if ocr_result.confidence < min_ocr_confidence or not ocr_result.text.strip():
            continue  # ishonch past yoki bo'sh -> sahifa DROP
        blocks.extend(Block(text=p, page=page_number) for p in _split_paragraphs(ocr_result.text))

    return Document(blocks=blocks)


def _get_page_count(path: Path) -> int:
    result = subprocess.run(
        ["djvused", str(path), "-e", "n"], capture_output=True, text=True, check=True
    )
    return int(result.stdout.strip())


def _extract_page_text(path: Path, page_number: int) -> str:
    result = subprocess.run(
        ["djvutxt", f"-page={page_number}", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _render_page(path: Path, page_number: int) -> Image.Image:
    result = subprocess.run(
        ["ddjvu", "-format=ppm", f"-page={page_number}", str(path)],
        capture_output=True,
        check=True,
    )
    return Image.open(io.BytesIO(result.stdout)).convert("RGB")


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]
