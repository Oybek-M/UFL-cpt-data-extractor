"""OCR-manba imlo tuzatish: "kayta" kabi shaklan to'g'ri, lekin harfiy OCR-xatosi
bo'lgan so'zlarni ishonchli lug'at + ma'lum chalkashlik juftliklari orqali
yuqori-ishonch bilan tuzatadi.

Manba: docs/superpowers/specs/2026-07-19-ocr-spellcheck-design.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Protocol

from ufl.finalize.hf_rename import is_hf_sourced_filename

_CONFUSION_PAIRS: list[tuple[str, str]] = [
    ("q", "k"), ("g'", "g"), ("h", "x"), ("o'", "u"), ("i", "y"),
]
_TRAILING_PUNCT_CHARS = ".,!?:;)\"»"

DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7-highspeed"
DEFAULT_MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"


class _PostResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


def _default_post(url: str, headers: dict[str, str], json_body: dict[str, Any], timeout: float) -> _PostResponse:
    import httpx

    return httpx.post(url, headers=headers, json=json_body, timeout=timeout)


def _first_json_object(text: str) -> dict:
    start = text.find("{")
    if start == -1:
        raise ValueError("Javobda JSON obyekt topilmadi")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise ValueError("Javobda to'liq JSON obyekt topilmadi")


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


def query_minimax_corrections(
    words: list[str],
    *,
    api_key: str,
    model: str = DEFAULT_MINIMAX_MODEL,
    url: str = DEFAULT_MINIMAX_URL,
    batch_size: int = 200,
    post: Any = None,
) -> tuple[dict[str, str], int]:
    """Qoidaga asoslangan usul hal qila olmagan noyob so'zlarni MiniMax'ga yuboradi.

    Qaytaradi: ({asl_so'z: tuzatilgan_so'z} lug'ati, yuborilgan so'rovlar soni).
    Kalitsiz, bo'sh ro'yxat, tarmoq xatosi yoki javobni tahlil qilib bo'lmasa —
    bo'sh lug'at (xavfsiz standart, so'z tuzatilmagan holda qoladi)."""
    if not words or not api_key:
        return {}, 0
    post_fn = post or _default_post
    corrections: dict[str, str] = {}
    call_count = 0
    for start in range(0, len(words), batch_size):
        chunk = words[start : start + batch_size]
        call_count += 1
        request_body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You correct likely OCR letter-confusion errors in Uzbek words.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": (
                                "Each word below is NOT found in a trusted Uzbek dictionary "
                                "and could not be auto-corrected by a simple rule. For each "
                                "word, if you are confident it is a single-letter OCR misread "
                                "of a real Uzbek word, return the corrected word. If not "
                                "confident, or the word looks like a proper noun/loanword, "
                                "return null. Return one JSON object: "
                                '{"corrections": {"word1": "fix1_or_null", ...}}'
                            ),
                            "words": chunk,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "stream": False,
            "max_completion_tokens": 2000,
            "temperature": 0.1,
        }
        try:
            response = post_fn(
                url,
                {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                request_body,
                60.0,
            )
        except Exception:  # noqa: BLE001 — tarmoq xatosi: so'z tuzatilmagan qoladi
            continue
        if response.status_code != 200:
            continue
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            decision = _first_json_object(content)
            chunk_corrections = decision.get("corrections", {})
        except Exception:  # noqa: BLE001
            continue
        corrections.update(
            {word: fix for word, fix in chunk_corrections.items() if isinstance(fix, str) and fix}
        )
    return corrections, call_count


def apply_known_corrections(
    line: str,
    corrections: dict[str, str],
    *,
    on_correction: Callable[[str, str], None] | None = None,
) -> str:
    """Tashqi manbadan (masalan MiniMax) olingan {asl: tuzatilgan} lug'atini
    qatorga qo'llaydi — chalkashlik-juftlik mantig'isiz, to'g'ridan-to'g'ri qidiruv."""
    if not line.strip():
        return line
    result = []
    for token in line.split():
        core, suffix = _split_trailing_punct(token)
        fix = corrections.get(core.lower())
        if fix:
            corrected_token = (fix[:1].upper() + fix[1:]) + suffix
            if on_correction:
                on_correction(token, corrected_token)
            result.append(corrected_token)
        else:
            result.append(token)
    return " ".join(result)
