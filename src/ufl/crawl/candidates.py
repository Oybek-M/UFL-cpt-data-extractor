"""Ko'p-strategiyali maqola-tana nomzodlarini ajratish (crawler tojli qismi).

Manba: website-to-txt-collector/continuous_collector.py (313-868) — UFL uslubida port.
Strategiyalar: JSON-LD `articleBody`, Nuxt `__NUXT_DATA__`, Next.js `__NEXT_DATA__`,
DOM selektorlar + evristik skorlash (link-zichlik, POSITIVE/NEGATIVE ishoralar,
sarlavha-so'z bonusi, boilerplate jarima).
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Iterable

from bs4 import BeautifulSoup, Tag

from ufl.crawl._time import normalized_time as _normalized_time
from ufl.crawl.blocks import clean_lines, fragment_text
from ufl.crawl.urls import date_from_url

NEGATIVE_HINTS = {
    "advert", "banner", "breadcrumb", "comment", "cookie", "footer", "header", "menu",
    "modal", "navbar", "newsletter", "promo", "recommend", "related", "share", "sidebar",
    "social", "subscribe", "tag-list", "toolbar",
}

POSITIVE_HINTS = {
    "article", "body", "content", "entry", "news", "post", "story", "text",
}

# (method, selector, text, score, paragraphs, link_density)
_RawCandidate = tuple[str, str, str, float, int, float]


@dataclass
class Candidate:
    candidate_id: str
    method: str
    selector: str
    text: str
    score: float
    paragraph_count: int
    link_density: float
    blocks: list[str] = field(default_factory=list)

    def block_payload(self, character_budget: int = 70000) -> list[dict[str, str]]:
        payload: list[dict[str, str]] = []
        used = 0
        source = self.blocks or [part for part in self.text.split("\n\n") if part.strip()]
        for index, value in enumerate(source, 1):
            if used + len(value) > character_budget and payload:
                break
            block_id = f"{self.candidate_id}_b{index:04d}"
            payload.append({"block_id": block_id, "text": value})
            used += len(value)
        return payload


def recursive_json_values(value: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from recursive_json_values(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from recursive_json_values(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def extract_metadata(soup: BeautifulSoup, url: str) -> tuple[str, str | None]:
    title = ""
    for selector, attribute in (
        ('meta[property="og:title"]', "content"),
        ('meta[name="twitter:title"]', "content"),
    ):
        node = soup.select_one(selector)
        if node and node.get(attribute):
            title = str(node.get(attribute)).strip()
            break
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    published: str | None = None
    for selector, attribute in (
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ("time[datetime]", "datetime"),
    ):
        node = soup.select_one(selector)
        if node and node.get(attribute):
            published = _normalized_time(str(node.get(attribute)))
            if published:
                break
    if not published:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.string or script.get_text())
            except (json.JSONDecodeError, TypeError):
                continue
            for path, value in recursive_json_values(payload):
                if path.lower().endswith(("datepublished", "uploaddate")):
                    published = _normalized_time(value)
                    if published:
                        break
            if published:
                break
    return clean_lines(title)[:1000], published or date_from_url(url)


def candidates_from_page(soup: BeautifulSoup, title: str = "") -> list[Candidate]:
    raw: list[_RawCandidate] = []

    # JSON-LD — articleBody eng aniq manba.
    for index, script in enumerate(soup.select('script[type="application/ld+json"]')):
        try:
            payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for path, value in recursive_json_values(payload):
            if path.lower().endswith(("articlebody", ".text", ".content")) and len(value) >= 300:
                text = fragment_text(value)
                if len(text) >= 250:
                    raw.append(
                        ("jsonld", f"jsonld:{index}:{path}", text, 10000 + len(text),
                         text.count("\n\n") + 1, 0.0)
                    )

    # Nuxt — tekislangan JSON massiv; kontent HTML-string sifatida qoladi.
    nuxt = soup.select_one("script#__NUXT_DATA__")
    if nuxt and nuxt.string:
        try:
            payload = json.loads(nuxt.string)
            for index, item in enumerate(payload if isinstance(payload, list) else []):
                if not isinstance(item, str) or len(item) < 300:
                    continue
                lower = item.lower()
                if not re.search(r"<(p|div|blockquote|h2)\b", lower):
                    continue
                text = fragment_text(item)
                if len(text) < 250:
                    continue
                bonus = 6000 if "post-content" in lower else 2000
                paragraphs = len(re.findall(r"<(p|div|blockquote)\b", lower))
                raw.append(
                    ("nuxt", f"nuxt:{index}", text, bonus + len(text) + paragraphs * 100,
                     paragraphs, 0.0)
                )
        except (json.JSONDecodeError, TypeError):
            pass

    # Next.js — ichma-ich JSON; body/content/text nomli maydonlar afzal.
    next_data = soup.select_one("script#__NEXT_DATA__")
    if next_data and next_data.string:
        try:
            payload = json.loads(next_data.string)
            for path, value in recursive_json_values(payload):
                key = path.rsplit(".", 1)[-1].lower()
                if len(value) < 300 or not any(
                    word in key for word in ("body", "content", "article", "text")
                ):
                    continue
                text = fragment_text(value)
                if len(text) >= 250:
                    raw.append(
                        ("next", f"next:{path}", text, 5000 + len(text),
                         text.count("\n\n") + 1, 0.0)
                    )
        except (json.JSONDecodeError, TypeError):
            pass

    selectors = [
        '[itemprop="articleBody"]', "article", "main article", ".article-body",
        ".article-content", ".post-content", ".entry-content", ".story-body", ".news-content",
    ]
    seen_nodes: set[int] = set()
    for selector in selectors:
        try:
            nodes = soup.select(selector)
        except Exception:  # noqa: BLE001 — noto'g'ri selektorni o'tkazib yubor
            continue
        for node in nodes[:20]:
            seen_nodes.add(id(node))
            raw.extend(dom_candidate(node, selector))

    pattern = re.compile(r"article|content|entry|news|post|story", re.I)
    for node in soup.find_all(["div", "section", "main"], limit=5000):
        if id(node) in seen_nodes:
            continue
        identity = " ".join(node.get("class", [])) + " " + str(node.get("id", ""))
        if pattern.search(identity):
            selector = simple_selector(node)
            raw.extend(dom_candidate(node, selector))

    title_words = {
        word for word in re.findall(r"[\wʻʼ‘’'-]+", title.casefold(), flags=re.UNICODE)
        if len(word) >= 4
    }
    reranked: list[_RawCandidate] = []
    for method, selector, text, score, paragraphs, link_density in raw:
        opening_words = set(re.findall(r"[\wʻʼ‘’'-]+", text[:1600].casefold(), flags=re.UNICODE))
        if title_words:
            score += (len(title_words & opening_words) / len(title_words)) * 14000
        boilerplate = text[:1200].casefold()
        if any(phrase in boilerplate for phrase in (
            "shaxsiy ma’lumot", "maxfiylik siyosat", "privacy policy",
            "terms and conditions", "cookie policy", "foydalanish shartlari",
        )):
            score -= 16000
        reranked.append((method, selector, text, score, paragraphs, link_density))

    deduped: list[Candidate] = []
    hashes: set[str] = set()
    reranked.sort(key=lambda item: item[3], reverse=True)
    for method, selector, text, score, paragraphs, link_density in reranked:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in hashes:
            continue
        hashes.add(digest)
        deduped.append(
            Candidate(f"c{len(deduped)+1:03d}", method, selector, text, score, paragraphs, link_density)
        )
        if len(deduped) >= 12:
            break
    return deduped


def probable_article_page(soup: BeautifulSoup, url: str) -> bool:
    og_type = soup.select_one('meta[property="og:type"]')
    if og_type and str(og_type.get("content", "")).casefold() == "article":
        return True
    for script in soup.select('script[type="application/ld+json"]'):
        value = (script.string or script.get_text()).casefold()
        if any(kind in value for kind in (
            '"@type":"article"', '"@type": "article"',
            '"@type":"newsarticle"', '"@type": "newsarticle"',
        )):
            return True
    path = urllib.parse.urlsplit(url).path.strip("/")
    return bool(date_from_url(url) and path.count("/") >= 3)


def simple_selector(node: Tag) -> str:
    if node.get("id"):
        return f"#{node.get('id')}"
    classes = [re.sub(r"[^a-zA-Z0-9_-]", "", value) for value in node.get("class", [])[:3]]
    classes = [value for value in classes if value]
    return node.name + "".join(f".{value}" for value in classes)


def dom_candidate(node: Tag, selector: str) -> list[_RawCandidate]:
    clone = BeautifulSoup(str(node), "html.parser")
    for bad in clone.select("script,style,noscript,svg,form,button,nav,footer,header,aside"):
        bad.decompose()
    root = clone.find()
    if not root:
        return []
    text = fragment_text(str(root))
    if len(text) < 250:
        return []
    links = sum(len(a.get_text(" ", strip=True)) for a in root.find_all("a"))
    visible = max(1, len(root.get_text(" ", strip=True)))
    link_density = links / visible
    paragraphs = len(root.find_all(["p", "blockquote", "li"]))
    identity = (selector + " " + " ".join(root.get("class", []))).lower()
    positive = sum(1 for hint in POSITIVE_HINTS if hint in identity)
    negative = sum(1 for hint in NEGATIVE_HINTS if hint in identity)
    score = len(text) + paragraphs * 180 + positive * 800 - negative * 2500 - link_density * 5000
    return [("dom", selector, text, score, paragraphs, link_density)]


def title_with_punctuation(title: str) -> str:
    value = clean_lines(title).strip()
    if value and value[-1] not in ".!?…":
        value += "."
    return value
