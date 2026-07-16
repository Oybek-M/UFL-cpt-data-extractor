"""Crawl orkestratsiyasi — kashfiyot → ekstraksiya → UFL clean pipeline → yozish.

Manba: website-to-txt-collector/continuous_collector.py (1385-1657) — UFL uslubida port.
Farq: nomzod tanlangandan keyin UFL'ning `clean_paragraphs` (transliteratsiya → faqat-
o'zbekcha til-filtri → sifat → normalizatsiya → dedup) chaqiriladi. Chiqish `writer` DI
orqali (Faza 4.5 BundledWriter). MiniMax ixtiyoriy (Faza 4.7); None bo'lsa local rejim.
"""

from __future__ import annotations

import time
import urllib.parse
from typing import Protocol

from bs4 import BeautifulSoup

from ufl.clean.apply import clean_paragraphs
from ufl.clean.dedup import DeduplicationStore
from ufl.clean.language import FastTextPredictor
from ufl.crawl._time import utc_now
from ufl.crawl.candidates import candidates_from_page, extract_metadata, probable_article_page
from ufl.crawl.categorize import resolve_category
from ufl.crawl.sitemap import parse_sitemap
from ufl.crawl.state import CrawlState
from ufl.crawl.urls import (
    belongs_to_site,
    canonical_url,
    collectable_url,
    date_from_url,
    domain_folder,
)

_IDLE_SLEEP_SECONDS = 10
_ROOT_REFRESH_SECONDS = 300
_STRUCTURED_METHODS = {"jsonld", "nuxt", "next"}


class ArticleWriter(Protocol):
    def write_article(
        self,
        page: object,
        *,
        title: str,
        published: str | None,
        method: str,
        category: str,
        blocks: list[str],
    ) -> None:
        ...


class Collector:
    def __init__(
        self,
        seed: str,
        *,
        state: CrawlState,
        web: object,
        robots: object,
        writer: ArticleWriter,
        category_mode: str,
        valid_categories: list[str],
        minimax: object | None = None,
        fasttext_predict: FastTextPredictor | None = None,
        min_language_confidence: float = 0.65,
        min_heuristic_score: float = 0.20,
        apostrophe_mode: str = "ascii",
        quality_kwargs: dict | None = None,
        min_clean_chars: int = 250,
        min_local_chars: int = 700,
    ) -> None:
        self.seed = seed
        self.domain = domain_folder(seed)
        self.state = state
        self.web = web
        self.robots = robots
        self.writer = writer
        self.category_mode = category_mode
        self.valid_categories = valid_categories
        self.minimax = minimax
        self.fasttext_predict = fasttext_predict
        self.min_language_confidence = min_language_confidence
        self.min_heuristic_score = min_heuristic_score
        self.apostrophe_mode = apostrophe_mode
        self.quality_kwargs = quality_kwargs or {}
        self.min_clean_chars = min_clean_chars
        self.min_local_chars = min_local_chars
        self.dedup = DeduplicationStore()
        self.state.add_page(seed, published_at=utc_now())

    # --- kashfiyot ---
    def refresh_roots(self, force: bool = False) -> bool:
        from ufl.crawl._time import parse_time

        last = parse_time(self.state.get_meta("last_root_refresh"))
        from datetime import datetime, timezone

        if not force and last and (datetime.now(timezone.utc) - last).total_seconds() < _ROOT_REFRESH_SECONDS:
            return False
        for location in getattr(self.robots, "sitemaps", []):
            try:
                normalized = canonical_url(location)
            except ValueError:
                continue
            if belongs_to_site(normalized, self.seed):
                self.state.upsert_sitemap(normalized, 0, utc_now())
        self.state.set_meta("last_root_refresh", utc_now())
        return True

    def process_sitemap(self) -> bool:
        row = self.state.next_sitemap()
        if not row:
            return False
        self.state.conn.execute(
            "UPDATE sitemaps SET status='processing',error=NULL,updated_at=? WHERE url=?",
            (utc_now(), row["url"]),
        )
        self.state.conn.commit()
        try:
            response = self.web.get(row["url"])
            kind, entries = parse_sitemap(response.content)
            for location, modified in entries:
                try:
                    normalized = canonical_url(location)
                except ValueError:
                    continue
                if not belongs_to_site(normalized, self.seed):
                    continue
                if kind == "sitemapindex":
                    self.state.upsert_sitemap(normalized, int(row["depth"]) + 1, modified)
                elif collectable_url(normalized, self.seed):
                    self.state.add_page(normalized, published_at=modified, sitemap_lastmod=modified)
            self.state.conn.execute(
                "UPDATE sitemaps SET status='done',cursor=0,error=NULL,updated_at=? WHERE url=?",
                (utc_now(), row["url"]),
            )
            self.state.conn.commit()
        except Exception as exc:  # noqa: BLE001
            self.state.conn.execute(
                "UPDATE sitemaps SET status='failed',error=?,updated_at=? WHERE url=?",
                (f"{type(exc).__name__}: {exc}"[:2000], utc_now(), row["url"]),
            )
            self.state.conn.commit()
        return True

    def _discover_links(self, soup: BeautifulSoup, base_url: str) -> None:
        for link in soup.find_all("a", href=True, limit=10000):
            absolute = urllib.parse.urljoin(base_url, str(link.get("href")))
            try:
                normalized = canonical_url(absolute)
            except ValueError:
                continue
            if collectable_url(normalized, self.seed):
                self.state.add_page(normalized, published_at=date_from_url(normalized))

    # --- sahifa ---
    def process_page(self) -> bool:
        page = self.state.next_page()
        if not page:
            return False
        page_id = int(page["id"])
        url = str(page["url"])
        if not self.robots.allowed(url):
            self._page_error(page_id, "access_denied", "robots.txt disallows this URL", None)
            return True
        self.state.conn.execute(
            "UPDATE pages SET status='processing',attempts=attempts+1,error=NULL,updated_at=? WHERE id=?",
            (utc_now(), page_id),
        )
        self.state.conn.commit()
        try:
            response = self.web.get(url)
            content_type = str(response.headers.get("Content-Type", "")).lower()
            if "html" not in content_type:
                self._page_error(
                    page_id, "extraction_failed", f"Not an HTML page: {content_type}",
                    getattr(response, "status_code", None),
                )
                return True
            soup = BeautifulSoup(response.content, "html.parser")
            title, published = extract_metadata(soup, url)
            self._discover_links(soup, str(getattr(response, "url", url)))
            candidates = candidates_from_page(soup, title)
            if not candidates:
                self._page_error(
                    page_id, "extraction_failed", "No plausible article-body candidate",
                    getattr(response, "status_code", None),
                )
                return True
            self.state.conn.execute(
                "UPDATE pages SET title=?,published_at=COALESCE(?,published_at),http_status=?,updated_at=? WHERE id=?",
                (title, published, getattr(response, "status_code", None), utc_now(), page_id),
            )
            self.state.conn.commit()
            page = self.state.conn.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()

            if urllib.parse.urlsplit(url).path.strip("/") == "":
                self._page_error(page_id, "non_article", "Website root page", None)
                return True

            adapter = self.state.adapter(self.domain)
            chosen = None
            if adapter:
                chosen = next(
                    (c for c in candidates if c.method == adapter["method"]
                     and (not adapter["selector"] or c.selector == adapter["selector"])),
                    None,
                )
            if chosen is not None:
                self._finalize(page, chosen, title, published, soup)
            elif self.minimax is not None and getattr(self.minimax, "api_key", None):
                reason = "first_page_calibration" if not adapter else "ambiguous_layout"
                self._process_with_minimax(page, candidates, title, published, soup, reason)
            else:
                strongest = candidates[0]
                locally_safe = (
                    (probable_article_page(soup, url) or len(strongest.text) >= self.min_local_chars)
                    and strongest.method in _STRUCTURED_METHODS
                )
                if locally_safe:
                    self._finalize(page, strongest, title, published, soup)
                else:
                    self._queue_ai(page_id, "MiniMax key required for uncertain layout")
        except Exception as exc:  # noqa: BLE001
            self._page_error(page_id, "extraction_failed", f"{type(exc).__name__}: {exc}", None)
        return True

    def _finalize(self, page: object, candidate: object, title: str, published: str | None, soup: BeautifulSoup) -> None:
        raw_blocks = candidate.blocks or [  # type: ignore[attr-defined]
            part for part in candidate.text.split("\n\n") if part.strip()  # type: ignore[attr-defined]
        ]
        self._finalize_blocks(page, candidate.method, title, published, raw_blocks, soup)  # type: ignore[attr-defined]

    def _finalize_blocks(
        self,
        page: object,
        method: str,
        title: str,
        published: str | None,
        raw_blocks: list[str],
        soup: BeautifulSoup,
    ) -> None:
        page_id = int(page["id"])  # type: ignore[index]
        clean_blocks = clean_paragraphs(
            raw_blocks,
            dedup_store=self.dedup,
            fasttext_predict=self.fasttext_predict,
            min_language_confidence=self.min_language_confidence,
            min_heuristic_score=self.min_heuristic_score,
            apostrophe_mode=self.apostrophe_mode,
            quality_kwargs=self.quality_kwargs,
        )
        body = "\n\n".join(clean_blocks)
        if len(body) < self.min_clean_chars:
            self._page_error(page_id, "quality_rejected", f"Toza tana qisqa: {len(body)}", None)
            return
        category = resolve_category(
            self.category_mode,
            url=str(page["url"]),  # type: ignore[index]
            valid_categories=self.valid_categories,
            section=self._section_hint(soup),
            title=title,
            snippet=body[:400],
            minimax=self.minimax,
            state=self.state,
            domain=self.domain,
        )
        self.writer.write_article(
            page,
            title=title,
            published=published,
            method=method,
            category=category,
            blocks=clean_blocks,
        )

    def _process_with_minimax(
        self,
        page: object,
        candidates: list,
        title: str,
        published: str | None,
        soup: BeautifulSoup,
        reason: str,
    ) -> None:
        page_id = int(page["id"])  # type: ignore[index]
        decision = self.minimax.select_candidate(  # type: ignore[union-attr]
            domain=self.domain,
            page_id=page_id,
            url=str(page["url"]),  # type: ignore[index]
            title=title,
            published=published,
            reason=reason,
            candidates=candidates,
        )
        if decision is None:
            self._queue_ai(page_id, reason)
            return
        if decision.status == "accepted":
            self._finalize_blocks(page, decision.method, title, published, decision.blocks, soup)
        else:
            self._page_error(page_id, decision.status, decision.reason or "MiniMax rad etdi", None)

    @staticmethod
    def _section_hint(soup: BeautifulSoup) -> str | None:
        for selector, attribute in (
            ('meta[property="article:section"]', "content"),
            ('meta[property="og:section"]', "content"),
        ):
            node = soup.select_one(selector)
            if node and node.get(attribute):
                return str(node.get(attribute))
        return None

    def _queue_ai(self, page_id: int, reason: str) -> None:
        self.state.conn.execute(
            "UPDATE pages SET status='ai_pending',error=?,updated_at=? WHERE id=?",
            (reason[:2000], utc_now(), page_id),
        )
        self.state.conn.commit()

    def _page_error(self, page_id: int, status: str, error: str, http_status: int | None) -> None:
        self.state.conn.execute(
            "UPDATE pages SET status=?,error=?,http_status=?,updated_at=? WHERE id=?",
            (status, error[:3000], http_status, utc_now(), page_id),
        )
        self.state.conn.commit()

    # --- asosiy sikl ---
    def run(self, once: bool = False, max_steps: int = 0, max_articles: int = 0) -> None:
        self.refresh_roots(force=True)
        steps = 0
        while True:
            did_work = False
            self.refresh_roots()
            if self.state.pending_page_count() < 100:
                did_work = self.process_sitemap() or did_work
            did_work = self.process_page() or did_work
            steps += 1
            if max_articles and int(self.state.counts().get("done", 0)) >= max_articles:
                break
            if max_steps and steps >= max_steps:
                break
            if once and not did_work:
                break
            if not did_work:
                time.sleep(_IDLE_SLEEP_SECONDS)
