"""PII (shaxsiy ma'lumot: email, telefon) tozalash.

CPT (Continued Pre-Training) uchun standart amaliyot (Dolma, FineWeb — regex
asosida email/telefon maskalash). Kitob/gazeta/davlat hujjatlari kabi
user-generated bo'lmagan matnlarda kamdan-kam uchraydi (masalan kitob kolofoni
yoki gazeta muharriri aloqasi), lekin arzon va standart himoya qatlami.

Manba: docs/superpowers/specs/2026-07-18-finalize-corpus-design.md
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"\+998[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"
    r"|\b0\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b"
)


def scrub_pii(text: str) -> tuple[str, int]:
    """Email va telefon raqamlarini matndan olib tashlaydi. (tozalangan matn,
    olib tashlangan mosliklar soni) qaytaradi."""
    count = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return ""

    cleaned = _EMAIL_RE.sub(_replace, text)
    cleaned = _PHONE_RE.sub(_replace, cleaned)
    return cleaned, count
