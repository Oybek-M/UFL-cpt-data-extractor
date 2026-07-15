"""O'zbek tilini aniqlash: fastText (lid.176) + o'zbekcha gevristika gibrid.

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §8
Bu modul TRANSLIT bosqichidan keyin ishlaydi — kirish matni allaqachon lotin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

FastTextPredictor = Callable[[str], tuple[str, float]]

_UZBEK_STOPWORDS = {
    "va", "bu", "shu", "u", "biz", "siz", "ular", "men", "sen",
    "bilan", "uchun", "emas", "ham", "edi", "lekin", "yoki",
    "uning", "kerak", "keyin", "faqat", "juda", "bor",
    "kim", "nima", "qanday", "qachon", "qayerda", "nega",
    "yana", "hali", "endi", "albatta", "balki", "chunki",
    "goyo", "garchi", "toki", "hatto", "deb", "esa",
}

_WORD_RE = re.compile(r"[a-zA-Z']+")


@dataclass
class LanguageResult:
    is_uzbek: bool
    heuristic_score: float
    fasttext_label: str | None
    fasttext_confidence: float | None


def heuristic_score(text: str) -> float:
    """0..1 — matn qanchalik o'zbekcha (lotin) ko'rinishga ega ekanini baholaydi."""
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return 0.0
    stopword_ratio = sum(1 for w in words if w in _UZBEK_STOPWORDS) / len(words)
    apostrophe_ratio = sum(1 for w in words if "o'" in w or "g'" in w) / len(words)
    return min(stopword_ratio * 0.8 + apostrophe_ratio * 0.2, 1.0)


def is_uzbek(
    text: str,
    *,
    fasttext_predict: FastTextPredictor | None = None,
    min_confidence: float = 0.65,
    min_heuristic_score: float = 0.20,
) -> LanguageResult:
    """Gibrid qaror: fastText 'uz' ishonchli DEYDI YOKI gevristika kuchli bo'lsa — o'zbekcha."""
    h_score = heuristic_score(text)

    ft_label: str | None = None
    ft_confidence: float | None = None
    if fasttext_predict is not None:
        try:
            ft_label, ft_confidence = fasttext_predict(text)
        except Exception:
            ft_label, ft_confidence = None, None

    strong_fasttext = (
        ft_label == "uz" and ft_confidence is not None and ft_confidence >= min_confidence
    )
    strong_heuristic = h_score >= min_heuristic_score

    return LanguageResult(
        is_uzbek=strong_fasttext or strong_heuristic,
        heuristic_score=h_score,
        fasttext_label=ft_label,
        fasttext_confidence=ft_confidence,
    )


def load_fasttext_predictor(model_path: Path) -> FastTextPredictor | None:
    """fastText lid.176 modelini yuklaydi. Topilmasa/xato bo'lsa None (crash emas, §13)."""
    model_path = Path(model_path)
    if not model_path.exists():
        return None
    try:
        import fasttext

        model = fasttext.load_model(str(model_path))
    except Exception:
        return None

    def predict(text: str) -> tuple[str, float]:
        clean_text = text.replace("\n", " ").strip()
        labels, probs = model.predict(clean_text, k=1)
        label = labels[0].replace("__label__", "")
        return label, float(probs[0])

    return predict
