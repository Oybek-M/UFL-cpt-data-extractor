"""Fayl formatini avtomatik aniqlash: kengaytma, topilmasa tarkib (magic bytes)."""

from __future__ import annotations

import zipfile
from pathlib import Path

_EXTENSION_MAP = {
    ".pdf": "pdf",
    ".djvu": "djvu",
    ".epub": "epub",
    ".docx": "docx",
    ".fb2": "fb2",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
}


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _EXTENSION_MAP:
        return _EXTENSION_MAP[suffix]

    try:
        head = path.read_bytes()[:2048]
    except OSError:
        return "unknown"

    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return _detect_zip_subtype(path)
    if head.lstrip().startswith(b"<"):
        return "html"
    return "txt"


def _detect_zip_subtype(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except (zipfile.BadZipFile, OSError):
        return "unknown"
    if "mimetype" in names or any(n.endswith(".opf") for n in names):
        return "epub"
    if "[Content_Types].xml" in names or any(n.startswith("word/") for n in names):
        return "docx"
    return "unknown"
