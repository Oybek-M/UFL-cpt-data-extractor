"""Bundled writer — crash-safe juftlik chiqish (.txt + .jsonl) + UFL byudjetiga yozish.

Manba: website-to-txt-collector/continuous_collector.py (878-1120) — UFL uslubida port.
Farq: `blocks` collector.py orqali UFL `clean_paragraphs`dan allaqachon tozalangan holda
keladi — bu yerda faqat formatlash, crash-safe saqlash va `Store.record_book` orqali
byudjetga token qo'shish bajariladi.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Iterable

from ufl.crawl._time import normalized_time, utc_now
from ufl.crawl.blocks import clean_lines
from ufl.crawl.candidates import title_with_punctuation
from ufl.crawl.state import CrawlState
from ufl.stats.tokens import TokenCounter, count_tokens
from ufl.store.db import BookRecord, Store

DEFAULT_SHARD_LIMIT_BYTES = 50 * 1024 * 1024


class BundledWriter:
    def __init__(
        self,
        output_root: Path,
        *,
        state: CrawlState,
        domain: str,
        store: Store | None = None,
        shard_limit_bytes: int = DEFAULT_SHARD_LIMIT_BYTES,
        exact_token_counter: TokenCounter | None = None,
        chars_per_token: float = 4.0,
    ) -> None:
        self.output_root = Path(output_root)
        self.state = state
        self.domain = domain
        self.store = store
        self.shard_limit_bytes = shard_limit_bytes
        self.exact_token_counter = exact_token_counter
        self.chars_per_token = chars_per_token
        self.site_root = self.output_root / domain
        self.text_folder = self.site_root / "text_folder"
        self.table_folder = self.site_root / "table_folder"
        self.text_folder.mkdir(parents=True, exist_ok=True)
        self.table_folder.mkdir(parents=True, exist_ok=True)
        self.recover()

    # --- crash-tiklash ---
    @staticmethod
    def _segment_valid(path: Path, offset: int, length: int, digest: str) -> bool:
        if not path.exists() or path.stat().st_size < offset + length:
            return False
        with path.open("rb") as handle:
            handle.seek(offset)
            payload = handle.read(length)
        return hashlib.sha256(payload).hexdigest() == digest

    def recover(self) -> None:
        rows = self.state.conn.execute(
            """SELECT i.*, b.text_path, b.table_path FROM output_items i
               JOIN output_bundles b ON b.id = i.bundle_id WHERE i.status='writing'"""
        ).fetchall()
        for row in rows:
            text_path = Path(row["text_path"])
            table_path = Path(row["table_path"])
            text_ok = self._segment_valid(
                text_path, int(row["text_offset"]), int(row["text_length"]), row["text_sha256"]
            )
            table_ok = self._segment_valid(
                table_path, int(row["table_offset"]), int(row["table_length"]), row["table_sha256"]
            )
            if text_ok and table_ok:
                self._commit(row)
                continue
            for path, offset in (
                (text_path, int(row["text_offset"])),
                (table_path, int(row["table_offset"])),
            ):
                if path.exists() and path.stat().st_size > offset:
                    with path.open("r+b") as handle:
                        handle.truncate(offset)
            self.state.conn.execute("DELETE FROM output_items WHERE page_id=?", (row["page_id"],))
            self.state.conn.execute(
                "UPDATE output_bundles SET text_size=?,table_size=? WHERE id=?",
                (row["text_offset"], row["table_offset"], row["bundle_id"]),
            )
            self.state.conn.execute(
                "UPDATE pages SET status='discovered',error='Uzilgan yozuv tiklandi' WHERE id=?",
                (row["page_id"],),
            )
            self.state.conn.commit()

    # --- formatlash ---
    def compose(self, title: str, blocks: Iterable[str]) -> tuple[str, str, list[str]]:
        clean_title = clean_lines(title).strip()
        content = [block for block in blocks if block.strip()]
        title_key = re.sub(r"\W+", "", clean_title.casefold(), flags=re.UNICODE)
        if content and title_key:
            first_key = re.sub(r"\W+", "", content[0].casefold(), flags=re.UNICODE)
            if first_key == title_key:
                content = content[1:]
        body = "\n\n".join(content).strip()
        heading = title_with_punctuation(clean_title)
        combined = f"{heading}\n\n{body}".strip() if heading else body
        return combined, clean_title, content

    # --- yozish ---
    def write_article(
        self,
        page: sqlite3.Row,
        *,
        title: str,
        published: str | None,
        method: str,
        category: str,
        blocks: list[str],
    ) -> None:
        combined, clean_title, clean_blocks = self.compose(title, blocks)
        page_id = int(page["id"])
        existing = self.state.conn.execute(
            "SELECT dataset_id FROM output_items WHERE page_id=?", (page_id,)
        ).fetchone()
        if existing:
            dataset_id = int(existing["dataset_id"])
        else:
            dataset_id = int(
                self.state.conn.execute(
                    "SELECT COALESCE(MAX(dataset_id),0)+1 FROM output_items"
                ).fetchone()[0]
            )
        parsed_date = normalized_time(published or page["published_at"])
        date = parsed_date[:10] if parsed_date else utc_now()[:10]
        record = {
            "id": dataset_id,
            "text": combined,
            "title": clean_title,
            "date": date,
            "source_website": self.domain,
            "source_url": page["url"],
        }
        text_payload = (combined.rstrip() + "\n\n\n").encode("utf-8")
        table_payload = (
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        bundle = self._open_bundle(date, len(text_payload), len(table_payload))
        text_path = Path(bundle["text_path"])
        table_path = Path(bundle["table_path"])
        text_offset = text_path.stat().st_size if text_path.exists() else 0
        table_offset = table_path.stat().st_size if table_path.exists() else 0
        text_digest = hashlib.sha256(text_payload).hexdigest()
        table_digest = hashlib.sha256(table_payload).hexdigest()
        self.state.conn.execute(
            """INSERT OR REPLACE INTO output_items
               (page_id,dataset_id,bundle_id,text_offset,text_length,clean_chars,text_sha256,
                table_offset,table_length,table_sha256,status,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,'writing',?)""",
            (
                page_id, dataset_id, bundle["id"], text_offset, len(text_payload), len(combined),
                text_digest, table_offset, len(table_payload), table_digest, utc_now(),
            ),
        )
        self.state.conn.execute(
            "UPDATE pages SET status='writing',selected_method=?,title=?,"
            "published_at=COALESCE(?,published_at) WHERE id=?",
            (method, clean_title, parsed_date, page_id),
        )
        self.state.conn.commit()
        for path, payload in ((text_path, text_payload), (table_path, table_payload)):
            with path.open("ab") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        item = self.state.conn.execute(
            """SELECT i.*, b.text_path, b.table_path FROM output_items i
               JOIN output_bundles b ON b.id = i.bundle_id WHERE i.page_id=?""",
            (page_id,),
        ).fetchone()
        self._commit(item)
        self._record_budget(category, combined, page)

    def _record_budget(self, category: str, combined: str, page: sqlite3.Row) -> None:
        if self.store is None:
            return
        counts = count_tokens(
            combined, chars_per_token=self.chars_per_token, exact_counter=self.exact_token_counter
        )
        self.store.record_book(
            BookRecord(
                path=str(page["url"]),
                category=category,
                format="web",
                char_count=counts.char_count,
                estimated_tokens=counts.estimated_tokens,
                exact_tokens=counts.exact_tokens,
                total_blocks=1,
                kept_blocks=1,
                dropped_pct=0.0,
            )
        )

    # --- bundle/shard boshqaruvi ---
    def _open_bundle(self, start_date: str, incoming_text: int, incoming_table: int) -> sqlite3.Row:
        safe_date = start_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_date) else utc_now()[:10]
        row = self.state.conn.execute(
            "SELECT * FROM output_bundles WHERE open=1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row and (
            safe_date[:7] <= str(row["end_date"] or row["start_date"])[:7]
            and int(row["text_size"]) + incoming_text <= self.shard_limit_bytes
            and int(row["table_size"]) + incoming_table <= self.shard_limit_bytes
        ):
            return self._extend_bundle_month_range(row, safe_date)
        if row:
            self.state.conn.execute("UPDATE output_bundles SET open=0 WHERE id=?", (row["id"],))
        bundle_id = int(
            self.state.conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM output_bundles").fetchone()[0]
        )
        month = safe_date[5:7]
        text_path = self.text_folder / f"{bundle_id:06d}_{month}.txt"
        table_path = self.table_folder / f"{bundle_id:06d}_{month}.jsonl"
        self.state.conn.execute(
            """INSERT INTO output_bundles
               (id,start_date,end_date,text_path,table_path,text_size,table_size,documents,open)
               VALUES(?,?,?,?,?,0,0,0,1)""",
            (bundle_id, safe_date, safe_date, str(text_path), str(table_path)),
        )
        self.state.conn.commit()
        return self.state.conn.execute(
            "SELECT * FROM output_bundles WHERE id=?", (bundle_id,)
        ).fetchone()

    def _extend_bundle_month_range(self, row: sqlite3.Row, end_date: str) -> sqlite3.Row:
        start_month = str(row["start_date"])[5:7]
        end_month = end_date[5:7]
        old_end_month = str(row["end_date"] or row["start_date"])[5:7]
        if end_month == old_end_month:
            return row
        suffix = start_month if end_date[:7] == str(row["start_date"])[:7] else f"{start_month}_{end_month}"
        new_text = self.text_folder / f"{int(row['id']):06d}_{suffix}.txt"
        new_table = self.table_folder / f"{int(row['id']):06d}_{suffix}.jsonl"
        old_text = Path(row["text_path"])
        old_table = Path(row["table_path"])
        if old_text.exists() and old_text != new_text:
            old_text.replace(new_text)
        if old_table.exists() and old_table != new_table:
            old_table.replace(new_table)
        self.state.conn.execute(
            "UPDATE output_bundles SET end_date=?,text_path=?,table_path=? WHERE id=?",
            (end_date, str(new_text), str(new_table), row["id"]),
        )
        self.state.conn.execute(
            """UPDATE pages SET text_path=?,table_path=? WHERE id IN
               (SELECT page_id FROM output_items WHERE bundle_id=?)""",
            (str(new_text), str(new_table), row["id"]),
        )
        self.state.conn.commit()
        return self.state.conn.execute("SELECT * FROM output_bundles WHERE id=?", (row["id"],)).fetchone()

    def _commit(self, item: sqlite3.Row) -> None:
        self.state.conn.execute(
            "UPDATE output_items SET status='committed' WHERE page_id=?", (item["page_id"],)
        )
        self.state.conn.execute(
            """UPDATE output_bundles SET
               text_size=MAX(text_size,?),table_size=MAX(table_size,?),documents=documents+1
               WHERE id=?""",
            (
                int(item["text_offset"]) + int(item["text_length"]),
                int(item["table_offset"]) + int(item["table_length"]),
                item["bundle_id"],
            ),
        )
        self.state.conn.execute(
            """UPDATE pages SET status='done',dataset_id=?,clean_chars=?,
               text_path=?,text_offset=?,text_length=?,table_path=?,table_offset=?,table_length=?,
               text_sha256=?,updated_at=?,error=NULL
               WHERE id=?""",
            (
                item["dataset_id"], item["clean_chars"],
                item["text_path"], item["text_offset"], item["text_length"],
                item["table_path"], item["table_offset"], item["table_length"],
                item["text_sha256"], utc_now(), item["page_id"],
            ),
        )
        self.state.conn.commit()
