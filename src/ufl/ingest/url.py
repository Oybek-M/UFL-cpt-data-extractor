"""Veb-sahifa URL'idan HTML yuklab olish (SSRF himoyasi bilan).

Ichki/xususiy tarmoq manzillariga (localhost, 127.0.0.1, bulut metadata
endpointlari va h.k.) so'rov yuborilishining oldi olinadi — ilova auth'siz,
istalgan foydalanuvchi URL kiritishi mumkin bo'lgani uchun.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

_TIMEOUT_SECONDS = 15.0


class UrlFetchError(Exception):
    pass


def fetch_html(url: str) -> str:
    _ensure_public_http_url(url)
    try:
        response = httpx.get(
            url,
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (UFL data-pipeline)"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise UrlFetchError(f"Sahifani yuklab bo'lmadi: {exc}") from exc
    _ensure_public_http_url(str(response.url))  # redirect ichki manzilga olib bormaganini tekshirish
    return response.text


def _ensure_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlFetchError("Faqat http(s) URL qo'llab-quvvatlanadi")
    hostname = parsed.hostname
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
