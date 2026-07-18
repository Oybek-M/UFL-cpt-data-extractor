"""HF fetch-hf progress holati — dataset+split bo'yicha oxirgi tugallangan shard raqami.

Byudjet DB (ufl.db)dan ALOHIDA: har dataset+split uchun alohida kichik SQLite fayl
(`data/hf_state/<slug>__<split>.sqlite3`), xuddi crawl uchun CrawlState kabi.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = "CREATE TABLE IF NOT EXISTS progress(key TEXT PRIMARY KEY, last_shard INTEGER NOT NULL);"


class HFFetchState:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "HFFetchState":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_last_shard(self, key: str) -> int:
        row = self._conn.execute("SELECT last_shard FROM progress WHERE key=?", (key,)).fetchone()
        return int(row[0]) if row else 0

    def set_last_shard(self, key: str, shard_index: int) -> None:
        self._conn.execute(
            "INSERT INTO progress(key,last_shard) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET last_shard=excluded.last_shard",
            (key, shard_index),
        )
        self._conn.commit()
