"""PDF fayllarni ingest qilish: matn qatlami (PyMuPDF) yoki OCR (skaner sahifalar).

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §3, §5
Har sahifada matn qatlami tekshiriladi; yetarli bo'lmasa OCR ga o'tiladi.
OCR ishonchi past bo'lsa sahifa DROP qilinadi (crash emas).
"""

from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image

from ufl.ingest.base import Block, Document
from ufl.ingest.ocr import run_ocr

_MIN_TEXT_LAYER_CHARS = 20
_MIN_OCR_CONFIDENCE = 60.0
_OCR_DPI = 300


def extract(
    path: Path,
    *,
    ocr_languages: str = "uzb+uzb_cyrl",
    min_ocr_confidence: float = _MIN_OCR_CONFIDENCE,
    dpi: int = _OCR_DPI,
) -> Document:
    blocks: list[Block] = []
    doc = fitz.open(str(path))
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            page_number = page_index + 1
            text = page.get_text().strip()

            if len(text) >= _MIN_TEXT_LAYER_CHARS:
                blocks.extend(Block(text=p, page=page_number) for p in _split_paragraphs(text))
                continue

            pix = page.get_pixmap(dpi=dpi)
            image = _pixmap_to_pil(pix)
            ocr_result = run_ocr(image, languages=ocr_languages)
            if ocr_result.confidence < min_ocr_confidence or not ocr_result.text.strip():
                continue  # ishonch past yoki bo'sh -> sahifa DROP
            blocks.extend(Block(text=p, page=page_number) for p in _split_paragraphs(ocr_result.text))
    finally:
        doc.close()
    return Document(blocks=blocks)


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _pixmap_to_pil(pix: fitz.Pixmap) -> Image.Image:
    mode = "RGB" if pix.n < 4 else "RGBA"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)
