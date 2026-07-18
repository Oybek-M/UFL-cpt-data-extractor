"""ziyouz.com "Kutubxona" HTML sahifalarini tahlil qilish: kategoriya nomi va
davom etiladigan/yuklab olinadigan havolalarni ajratish.

Pagination uchun maxsus parser YO'Q — Joomla pagination oddiy `<a href>` bo'lgani
uchun generic same-site link-yurish (bu modulning vazifasi) uni tabiiy ravishda
qamraydi (docs/superpowers/plans/2026-07-18-ziyouz-bulk-downloader.md).
"""

from __future__ import annotations

import re
import urllib.parse

from bs4 import BeautifulSoup

# `download`ning qiymati "id:slug" formatida — buni parse_qs bilan (regex bilan
# emas) o'qiymiz, chunki bitta-parametrli query'da ("?download=...") qiymatdan
# oldin '?' yoki '&' belgisi YO'Q — `[?&]download=` uslubidagi regex bunday
# holatni o'tkazib yuboradi (real HTML bilan tasdiqlangan xato).
_DOWNLOAD_VALUE_RE = re.compile(r"^(\d+):([\w-]+)$")
_TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "fbclid", "gclid"}


def _download_item(parsed: urllib.parse.SplitResult) -> tuple[str, str] | None:
    """`?download=<id>:<slug>` query-parametridan (id, slug) ajratadi; yo'q/mos
    kelmasa None."""
    values = urllib.parse.parse_qs(parsed.query).get("download")
    if not values:
        return None
    match = _DOWNLOAD_VALUE_RE.match(values[0])
    if not match:
        return None
    return match.group(1), match.group(2)


def extract_category_name(html: str) -> str | None:
    """`<div class="pd-category">` ichidagi `<h3>` matnini qaytaradi; topilmasa None."""
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one("div.pd-category h3")
    if heading is None:
        return None
    text = heading.get_text(strip=True)
    return text or None


def discover_links(html: str, page_url: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Sahifadagi havolalarni ikkiga ajratadi:
    - `pages`: davom etiladigan bir-xil-saytdagi `/kutubxona/*` HTML sahifa URL'lari
      (kuzatuv query-parametrlari olib tashlanadi, dublikat yo'q).
    - `items`: `(item_id, slug, absolute_download_url)` — yuklab olish havolalari,
      `item_id` bo'yicha dedup qilingan (bir xil kitobga ikkita havola — sarlavha
      va "Saqlash" tugmasi — bo'lishi mumkin).
    """
    soup = BeautifulSoup(html, "html.parser")
    base_host = urllib.parse.urlsplit(page_url).hostname

    pages: list[str] = []
    seen_pages: set[str] = set()
    items: list[tuple[str, str, str]] = []
    seen_items: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        absolute = urllib.parse.urljoin(page_url, href)
        parsed = urllib.parse.urlsplit(absolute)

        download_item = _download_item(parsed)
        if download_item:
            item_id, slug = download_item
            if item_id not in seen_items:
                seen_items.add(item_id)
                items.append((item_id, slug, absolute))
            continue

        if parsed.hostname != base_host:
            continue
        if not parsed.path.startswith("/kutubxona"):
            continue

        cleaned = _strip_tracking_params(parsed)
        if cleaned not in seen_pages:
            seen_pages.add(cleaned)
            pages.append(cleaned)

    return pages, items


def _strip_tracking_params(parsed: urllib.parse.SplitResult) -> str:
    pairs = [
        (key, value) for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_KEYS
    ]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(pairs), "")
    )
