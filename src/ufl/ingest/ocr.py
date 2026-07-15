"""Tesseract OCR wrapper: rasmdan matn + ishonch darajasini qaytaradi."""

from __future__ import annotations

from dataclasses import dataclass

import pytesseract
from PIL import Image


@dataclass
class OcrResult:
    text: str
    confidence: float  # 0..100


def run_ocr(image: Image.Image, languages: str = "uzb+uzb_cyrl") -> OcrResult:
    data = pytesseract.image_to_data(image, lang=languages, output_type=pytesseract.Output.DICT)

    words: list[str] = []
    confidences: list[float] = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue
        try:
            conf_value = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf_value < 0:  # Tesseract -1 = ishonchsiz (bo'sh joy va h.k.)
            continue
        words.append(word)
        confidences.append(conf_value)

    text = " ".join(words)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return OcrResult(text=text, confidence=avg_confidence)
