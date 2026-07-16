"""URL kanonizatsiya, sayt-a'zolik va SSRF xavfsizlik.

Manba: website-to-txt-collector/continuous_collector.py (96-181) — UFL uslubida port.
`canonical_url` string darajasida SSRF himoyasi qiladi (literal ichki IP, localhost,
credential-URL, juda uzun URL, ortiqcha query rad etiladi). DNS-darajasidagi qo'shimcha
SSRF tekshiruvi `ufl.ingest.url`da (host haqiqatda xususiy IP'ga resolve bo'lsa).
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# utm_* va shu kabi kuzatuv parametrlari kanonizatsiyada tashlanadi.
TRACKING_KEYS = {
    "fbclid", "gclid", "yclid", "ref", "source", "utm_campaign", "utm_content",
    "utm_medium", "utm_source", "utm_term",
}

# Maqola bo'lmagan (media/hujjat/arxiv) kengaytmalar crawl'dan chiqariladi.
SKIP_EXTENSIONS = {
    ".7z", ".aac", ".avi", ".bmp", ".css", ".csv", ".doc", ".docx", ".eot",
    ".exe", ".flac", ".gif", ".gz", ".ico", ".iso", ".jar", ".jpeg", ".jpg",
    ".js", ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".mpeg", ".mpg",
    ".ogg", ".otf", ".pdf", ".png", ".ppt", ".pptx", ".rar", ".rss", ".svg",
    ".tar", ".tif", ".tiff", ".tsv", ".ttf", ".wav", ".webm", ".webp", ".woff",
    ".woff2", ".xls", ".xlsx", ".xml", ".zip",
}


def prepare_url(value: str) -> str:
    """Foydalanuvchi kiritgan xom qiymatni to'liq kanonik URL'ga aylantiradi."""
    value = value.strip()
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        value = "https://" + value
    return canonical_url(value)


def canonical_url(value: str) -> str:
    """URL'ni normallashtirib qaytaradi; xavfli/yaroqsiz bo'lsa ValueError.

    Rad etiladi: http(s) bo'lmagan sxema, hostsiz, credential-URL, localhost,
    literal xususiy/loopback/link-local/reserved IP, 6 tadan ortiq query, 2048+ belgi.
    Kuzatuv (utm_*/fbclid/...) parametrlari olib tashlanadi, query saralanadi.
    """
    parsed = urllib.parse.urlsplit(value.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    if scheme not in {"http", "https"} or not host:
        raise ValueError("Invalid HTTP/HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("Credential-bearing URLs are not accepted")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Local addresses are not accepted")
    try:
        address = ipaddress.ip_address(host.strip("[]"))
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ValueError("Private or reserved addresses are not accepted")
    except ValueError as exc:
        if "not accepted" in str(exc):
            raise
    port = parsed.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    pairs = [
        (key, item) for key, item in pairs
        if key.lower() not in TRACKING_KEYS and not key.lower().startswith("utm_")
    ]
    if len(pairs) > 6:
        raise ValueError("Too many query parameters")
    result = urllib.parse.urlunsplit(
        (scheme, netloc, path, urllib.parse.urlencode(sorted(pairs)), "")
    )
    if len(result) > 2048:
        raise ValueError("URL is too long")
    return result


def host_key(host: str) -> str:
    """Hostni `www.` prefiksisiz, kichik harflarda qaytaradi (taqqoslash uchun)."""
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def belongs_to_site(url: str, seed: str) -> bool:
    """URL seed sayt (yoki uning subdomeni / ota-domeni) ichidami?"""
    candidate = host_key(urllib.parse.urlsplit(url).hostname or "")
    base = host_key(urllib.parse.urlsplit(seed).hostname or "")
    return candidate == base or candidate.endswith("." + base) or base.endswith("." + candidate)


def collectable_url(url: str, seed: str) -> bool:
    """URL kanonik, seed saytga tegishli va media/hujjat kengaytmasi emasmi?"""
    try:
        normalized = canonical_url(url)
    except ValueError:
        return False
    if not belongs_to_site(normalized, seed):
        return False
    return Path(urllib.parse.urlsplit(normalized).path.lower()).suffix not in SKIP_EXTENSIONS


def domain_folder(seed: str) -> str:
    """Seed'dan fayl-tizimi uchun xavfsiz domen papka nomi (masalan `kun.uz`)."""
    parsed = urllib.parse.urlsplit(seed)
    value = host_key(parsed.hostname or "website")
    if parsed.port:
        value += f"_{parsed.port}"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value)


def url_hash(url: str) -> str:
    """URL'ning SHA-256 hex digest'i (cache fayl nomlari uchun)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def date_from_url(url: str) -> str | None:
    """URL yo'lidagi /YYYY/MM/DD/ naqshidan ISO sana; topilmasa None."""
    path = urllib.parse.urlsplit(url).path
    match = re.search(r"/(20\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])(?:/|$)", path)
    if not match:
        return None
    try:
        return datetime(int(match[1]), int(match[2]), int(match[3]), tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None
