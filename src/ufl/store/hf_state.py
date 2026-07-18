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
        self._migrate_schema()
        self._conn.commit()

    def _migrate_schema(self) -> None:
        """Eski (production) hf_state fayllari shard_size ustunisiz yaratilgan —
        buzmasdan qo'shib qo'yamiz (masalan tahrirchi/uz-crawl progressi)."""
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(progress)")}
        if "shard_size" not in columns:
            self._conn.execute("ALTER TABLE progress ADD COLUMN shard_size INTEGER")

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

    def get_shard_size(self, key: str) -> int | None:
        row = self._conn.execute("SELECT shard_size FROM progress WHERE key=?", (key,)).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def set_shard_size(self, key: str, shard_size: int) -> None:
        self._conn.execute(
            "INSERT INTO progress(key, last_shard, shard_size) VALUES(?, 0, ?) "
            "ON CONFLICT(key) DO UPDATE SET shard_size=excluded.shard_size",
            (key, shard_size),
        )
        self._conn.commit()
