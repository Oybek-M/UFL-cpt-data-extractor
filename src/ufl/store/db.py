"""SQLite store: qayta ishlangan kitoblar va byudjet progressini saqlaydi.

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §15
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    format TEXT NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    estimated_tokens INTEGER NOT NULL DEFAULT 0,
    exact_tokens INTEGER,
    total_blocks INTEGER NOT NULL DEFAULT 0,
    kept_blocks INTEGER NOT NULL DEFAULT 0,
    dropped_pct REAL NOT NULL DEFAULT 0.0,
    processed_at TEXT NOT NULL
);
"""


@dataclass
class BookRecord:
    path: str
    category: str
    format: str
    char_count: int
    estimated_tokens: int
    exact_tokens: int | None
    total_blocks: int
    kept_blocks: int
    dropped_pct: float


class Store:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def is_processed(self, path: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM books WHERE path = ?", (path,))
        return cur.fetchone() is not None

    def record_book(self, record: BookRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO books (path, category, format, char_count, estimated_tokens,
                                exact_tokens, total_blocks, kept_blocks, dropped_pct, processed_at)
            VALUES (:path, :category, :format, :char_count, :estimated_tokens,
                    :exact_tokens, :total_blocks, :kept_blocks, :dropped_pct, :processed_at)
            ON CONFLICT(path) DO UPDATE SET
                category=excluded.category, format=excluded.format,
                char_count=excluded.char_count, estimated_tokens=excluded.estimated_tokens,
                exact_tokens=excluded.exact_tokens, total_blocks=excluded.total_blocks,
                kept_blocks=excluded.kept_blocks, dropped_pct=excluded.dropped_pct,
                processed_at=excluded.processed_at
            """,
            {
                "path": record.path,
                "category": record.category,
                "format": record.format,
                "char_count": record.char_count,
                "estimated_tokens": record.estimated_tokens,
                "exact_tokens": record.exact_tokens,
                "total_blocks": record.total_blocks,
                "kept_blocks": record.kept_blocks,
                "dropped_pct": record.dropped_pct,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._conn.commit()

    def collected_tokens_by_category(self) -> dict[str, int]:
        cur = self._conn.execute("SELECT category, SUM(estimated_tokens) FROM books GROUP BY category")
        return {category: total or 0 for category, total in cur.fetchall()}

    def book_count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM books")
        return cur.fetchone()[0]
