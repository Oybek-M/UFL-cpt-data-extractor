"""Veb-sahifa URL'idan HTML yuklab olish (SSRF himoyasi bilan).

Ikki qatlamli himoya:
1. `ufl.crawl.urls.canonical_url` — string darajasi: sxema, credential, localhost,
   literal ichki IP, ortiqcha query, uzun URL rad etiladi + normalizatsiya.
2. Bu yerdagi DNS-guard — host haqiqatda xususiy/loopback/link-local IP'ga resolve
   bo'lsa rad etiladi (crawl.urls string-tekshiruvi ushlamaydigan holat).

Ilova auth'siz — istalgan foydalanuvchi URL kiritishi mumkin bo'lgani uchun ikkalasi ham kerak.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from ufl.crawl.urls import canonical_url

_TIMEOUT_SECONDS = 15.0


class UrlFetchError(Exception):
    pass


def fetch_html(url: str) -> str:
    safe_url = _guard(url)
    try:
        response = httpx.get(
            safe_url,
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (UFL data-pipeline)"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise UrlFetchError(f"Sahifani yuklab bo'lmadi: {exc}") from exc
    _guard(str(response.url))  # redirect ichki manzilga olib bormaganini tekshirish
    return response.text


def _guard(url: str) -> str:
    """Kanonizatsiya (string SSRF) + DNS-guard. Xавfli/yaroqsiz bo'lsa UrlFetchError."""
    try:
        safe = canonical_url(url)
    except ValueError as exc:
        raise UrlFetchError(str(exc)) from exc
    _ensure_public_host(safe)
    return safe


def _ensure_public_host(url: str) -> None:
    hostname = urlparse(url).hostname
    if not hostname:
        raise UrlFetchError("URL noto'g'ri")
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UrlFetchError(f"Hostni aniqlab bo'lmadi: {hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UrlFetchError("Ichki/xususiy tarmoq manzillariga so'rov yuborish taqiqlangan")
