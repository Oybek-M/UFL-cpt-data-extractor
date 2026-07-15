"""Token hisobi: Gemma-4 tokenizer (aniq) + belgi-nisbati (taxminiy, har doim mavjud).

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §12
Tokenizer topilmasa/yuklanmasa — faqat taxminiy hisob bilan davom etiladi
(crash emas, §13).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TokenCounter = Callable[[str], int]


@dataclass
class TokenCounts:
    char_count: int
    estimated_tokens: int
    exact_tokens: int | None  # None -> aniq tokenizer mavjud emas


def estimate_tokens(text: str, chars_per_token: float = 4.0) -> int:
    if chars_per_token <= 0:
        raise ValueError("chars_per_token > 0 bo'lishi kerak")
    if not text:
        return 0
    return max(1, round(len(text) / chars_per_token))


def count_tokens(
    text: str,
    *,
    chars_per_token: float = 4.0,
    exact_counter: TokenCounter | None = None,
) -> TokenCounts:
    exact: int | None = None
    if exact_counter is not None:
        try:
            exact = exact_counter(text)
        except Exception:
            exact = None
    return TokenCounts(
        char_count=len(text),
        estimated_tokens=estimate_tokens(text, chars_per_token),
        exact_tokens=exact,
    )


def load_tokenizer_counter(local_dir: Path, model_id: str) -> TokenCounter | None:
    """Gemma-4 tokenizerni yuklaydi. Topilmasa/xato bo'lsa None (taxminiy hisobga fallback)."""
    local_dir = Path(local_dir)
    source = str(local_dir) if local_dir.exists() and any(local_dir.iterdir()) else model_id
    try:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(source)
    except Exception:
        return None

    def counter(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    return counter
