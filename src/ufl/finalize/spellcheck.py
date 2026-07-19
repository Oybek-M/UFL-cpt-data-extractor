"""OCR-manba imlo tuzatish: "kayta" kabi shaklan to'g'ri, lekin harfiy OCR-xatosi
bo'lgan so'zlarni ishonchli lug'at + ma'lum chalkashlik juftliklari orqali
yuqori-ishonch bilan tuzatadi.

Manba: docs/superpowers/specs/2026-07-19-ocr-spellcheck-design.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ufl.finalize.hf_rename import is_hf_sourced_filename

_CONFUSION_PAIRS: list[tuple[str, str]] = [
    ("q", "k"), ("g'", "g"), ("h", "x"), ("o'", "u"), ("i", "y"),
]
_TRAILING_PUNCT_CHARS = ".,!?:;)\"»"


def _split_trailing_punct(token: str) -> tuple[str, str]:
    end = len(token)
    while end > 0 and token[end - 1] in _TRAILING_PUNCT_CHARS:
        end -= 1
    return token[:end], token[end:]


def build_trusted_dictionary(output_dir: Path) -> set[str]:
    """HF-manba fayllardagi barcha (kichik harfli, tinish-belgisiz) so'zlarni
    to'playdi. Ziyouz va boshqa web-manba fayllar hisobga olinmaydi."""
    trusted: set[str] = set()
    for txt_path in sorted(Path(output_dir).glob("*/*.txt")):
        if not is_hf_sourced_filename(txt_path.name):
            continue
        try:
            text = txt_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.split("\n"):
            for token in line.split():
                core, _ = _split_trailing_punct(token.lower())
                if core:
                    trusted.add(core)
    return trusted


def find_correction(word: str, trusted: set[str]) -> str | None:
    """5 ta chalkashlik juftligi bo'yicha yagona ishonchli nomzodni qidiradi.
    So'z allaqachon lug'atda bo'lsa, yoki 0/2+ nomzod topilsa — None."""
    lower = word.lower()
    if not lower or lower in trusted:
        return None
    candidates: set[str] = set()
    for a, b in _CONFUSION_PAIRS:
        for src, dst in ((a, b), (b, a)):
            if src in lower:
                candidate = lower.replace(src, dst)
                if candidate != lower and candidate in trusted:
                    candidates.add(candidate)
    if len(candidates) != 1:
        return None
    corrected = next(iter(candidates))
    if word[:1].isupper():
        return corrected[:1].upper() + corrected[1:]
    return corrected


def correct_line(
    line: str,
    trusted: set[str],
    *,
    on_correction: Callable[[str, str], None] | None = None,
    on_unresolved: Callable[[str], None] | None = None,
) -> str:
    """Qatordagi har so'zni tekshiradi: ishonchli lug'atda bo'lsa tegilmaydi,
    yagona nomzod topilsa to'g'irlanadi (on_correction chaqiriladi), aks holda
    o'zgarishsiz qoladi (on_unresolved chaqiriladi, agar berilgan bo'lsa)."""
    if not line.strip():
        return line
    result = []
    for token in line.split():
        core, suffix = _split_trailing_punct(token)
        if not core or core.lower() in trusted:
            result.append(token)
            continue
        correction = find_correction(core, trusted)
        if correction is not None:
            corrected_token = correction + suffix
            if on_correction:
                on_correction(token, corrected_token)
            result.append(corrected_token)
        else:
            if on_unresolved:
                on_unresolved(core.lower())
            result.append(token)
    return " ".join(result)
