"""Barcha ingest modullari (PDF, EPUB, DOCX, ...) uchun umumiy hujjat modeli."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    """Hujjatning bitta matn bo'lagi (paragraf/qator)."""

    text: str
    page: int  # PDF/DJVU uchun 1-based sahifa; boshqa formatlar uchun ketma-ket/0
    y_position: float | None = None  # sahifadagi vertikal joylashuv (header/footer aniqlash uchun)
    kind: str = "body"  # "body" | "header" | "footer" | "toc" | ... (keyingi bosqichlar belgilaydi)


@dataclass
class Document:
    blocks: list[Block] = field(default_factory=list)
