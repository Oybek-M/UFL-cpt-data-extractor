"""Crawl holati (per-domen SQLite) — resumable, crash-safe.

Manba: website-to-txt-collector/continuous_collector.py (337-603) — UFL uslubida port.
UFL byudjet DB'sidan (`ufl.db`) ALOHIDA: har domen uchun
`data/collected/<domain>/_state/state.sqlite3`. Jadvallar: meta, sitemaps, pages,
adapters, ai_batches (+ writer 4.5 uchun output_bundles/output_items).
"""

from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

from ufl.crawl._time import normalized_time, utc_now
from ufl.crawl.urls import date_from_url

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sitemaps(
  url TEXT PRIMARY KEY, depth INTEGER NOT NULL, source_lastmod TEXT,
  status TEXT NOT NULL DEFAULT 'pending', cursor INTEGER NOT NULL DEFAULT 0,
  error TEXT, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sitemaps_status ON sitemaps(status, source_lastmod);
CREATE TABLE IF NOT EXISTS pages(
  id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, title TEXT,
  published_at TEXT, sitemap_lastmod TEXT, status TEXT NOT NULL DEFAULT 'discovered',
  attempts INTEGER NOT NULL DEFAULT 0, error TEXT, http_status INTEGER,
  cache_file TEXT, candidates_file TEXT, selected_method TEXT,
  discovered_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  clean_chars INTEGER, dataset_id INTEGER,
  text_path TEXT, text_offset INTEGER, text_length INTEGER,
  table_path TEXT, table_offset INTEGER, table_length INTEGER, text_sha256 TEXT
);
CREATE INDEX IF NOT EXISTS pages_queue ON pages(status, published_at DESC, discovered_at DESC);
CREATE TABLE IF NOT EXISTS adapters(
  domain TEXT PRIMARY KEY, method TEXT NOT NULL, selector TEXT,
  confidence REAL NOT NULL, samples INTEGER NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_batches(
  batch_hash TEXT PRIMARY KEY, domain TEXT NOT NULL, page_ids TEXT NOT NULL,
  status TEXT NOT NULL, request_file TEXT NOT NULL, response_file TEXT,
  attempts INTEGER NOT NULL DEFAULT 0, http_status INTEGER, error TEXT,
  retry_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS output_bundles(
  id INTEGER PRIMARY KEY, start_date TEXT NOT NULL, end_date TEXT NOT NULL DEFAULT '',
  text_path TEXT NOT NULL UNIQUE, table_path TEXT NOT NULL UNIQUE,
  text_size INTEGER NOT NULL DEFAULT 0, table_size INTEGER NOT NULL DEFAULT 0,
  documents INTEGER NOT NULL DEFAULT 0, open INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS output_items(
  page_id INTEGER PRIMARY KEY, dataset_id INTEGER NOT NULL UNIQUE,
  bundle_id INTEGER NOT NULL, text_offset INTEGER NOT NULL,
  text_length INTEGER NOT NULL, clean_chars INTEGER NOT NULL DEFAULT 0,
  text_sha256 TEXT NOT NULL, table_offset INTEGER NOT NULL, table_length INTEGER NOT NULL,
  table_sha256 TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


class CrawlState:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.cache = self.root / "cache"
        self.candidates = self.root / "candidates"
        self.ai_dir = self.root / "ai_batches"
        for folder in (self.cache, self.candidates, self.ai_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.root / "state.sqlite3")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()
        self._recover_statuses()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "CrawlState":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _recover_statuses(self) -> None:
        stamp = utc_now()
        for src, dst in (
            ("processing", "discovered"),
            ("ai_processing", "ai_pending"),
            ("writing", "discovered"),
        ):
            self.conn.execute(
                "UPDATE pages SET status=?, updated_at=? WHERE status=?", (dst, stamp, src)
            )
        self.conn.execute(
            "UPDATE pages SET status='discovered', updated_at=? "
            "WHERE status='download_failed' AND attempts < 5",
            (stamp,),
        )
        self.conn.execute(
            "UPDATE sitemaps SET status='pending', updated_at=? WHERE status='processing'", (stamp,)
        )
        self.conn.execute(
            "UPDATE ai_batches SET status='retry', updated_at=? WHERE status='processing'", (stamp,)
        )
        self.conn.commit()

    # --- meta ---
    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    # --- pages ---
    def add_page(
        self, url: str, published_at: str | None = None, sitemap_lastmod: str | None = None
    ) -> bool:
        stamp = utc_now()
        published = normalized_time(published_at) or date_from_url(url)
        cursor = self.conn.execute(
            """INSERT OR IGNORE INTO pages
               (url,published_at,sitemap_lastmod,status,discovered_at,updated_at)
               VALUES(?,?,?,'discovered',?,?)""",
            (url, published, sitemap_lastmod, stamp, stamp),
        )
        if cursor.rowcount == 0 and published:
            self.conn.execute(
                "UPDATE pages SET published_at=COALESCE(published_at,?), "
                "sitemap_lastmod=COALESCE(?,sitemap_lastmod) WHERE url=?",
                (published, sitemap_lastmod, url),
            )
        self.conn.commit()
        return cursor.rowcount == 1

    def next_page(self) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT * FROM pages WHERE status='discovered'
               ORDER BY COALESCE(published_at,sitemap_lastmod,'1970-01-01') DESC,
                        discovered_at DESC LIMIT 1"""
        ).fetchone()

    def pending_page_count(self) -> int:
        return int(
            self.conn.execute("SELECT COUNT(*) FROM pages WHERE status='discovered'").fetchone()[0]
        )

    # --- sitemaps ---
    def upsert_sitemap(self, url: str, depth: int, source_lastmod: str | None) -> None:
        row = self.conn.execute(
            "SELECT source_lastmod,status FROM sitemaps WHERE url=?", (url,)
        ).fetchone()
        stamp = utc_now()
        if not row:
            self.conn.execute(
                "INSERT INTO sitemaps(url,depth,source_lastmod,status,cursor,updated_at) "
                "VALUES(?,?,?,'pending',0,?)",
                (url, depth, source_lastmod, stamp),
            )
        elif source_lastmod and source_lastmod != row["source_lastmod"]:
            self.conn.execute(
                "UPDATE sitemaps SET depth=?,source_lastmod=?,status='pending',cursor=0,"
                "error=NULL,updated_at=? WHERE url=?",
                (depth, source_lastmod, stamp, url),
            )
        self.conn.commit()

    def next_sitemap(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM sitemaps WHERE status='pending' "
            "ORDER BY COALESCE(source_lastmod,'') DESC, depth, url LIMIT 1"
        ).fetchone()

    # --- adapters ---
    def adapter(self, domain: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM adapters WHERE domain=?", (domain,)).fetchone()

    def save_adapter(
        self, domain: str, method: str, selector: str, confidence: float, samples: int
    ) -> None:
        self.conn.execute(
            """INSERT INTO adapters(domain,method,selector,confidence,samples,updated_at)
               VALUES(?,?,?,?,?,?) ON CONFLICT(domain) DO UPDATE SET
               method=excluded.method,selector=excluded.selector,confidence=excluded.confidence,
               samples=adapters.samples+excluded.samples,updated_at=excluded.updated_at""",
            (domain, method, selector, confidence, samples, utc_now()),
        )
        self.conn.commit()

    # --- ai (MiniMax, Faza 4.7) ---
    def ai_pages(self, domain: str, limit: int = 1) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM pages WHERE status='ai_pending' AND url LIKE ? "
            "ORDER BY COALESCE(published_at,'') DESC LIMIT ?",
            (f"%://%{domain}%", limit),
        ).fetchall()

    # --- stats ---
    def counts(self) -> dict[str, int]:
        return {
            row["status"]: int(row["count"])
            for row in self.conn.execute(
                "SELECT status,COUNT(*) AS count FROM pages GROUP BY status"
            )
        }

    def median_clean_chars(self, limit: int = 100) -> float | None:
        rows = self.conn.execute(
            """SELECT clean_chars FROM pages WHERE status='done' AND clean_chars IS NOT NULL
               ORDER BY updated_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        values = [int(row["clean_chars"]) for row in rows if int(row["clean_chars"]) > 0]
        return float(statistics.median(values)) if values else None
