from ufl.store.db import BookRecord, Store


def _make_record(path: str = "data/input/books/sample.txt", category: str = "books") -> BookRecord:
    return BookRecord(
        path=path,
        category=category,
        format="txt",
        char_count=439,
        estimated_tokens=110,
        exact_tokens=None,
        total_blocks=4,
        kept_blocks=3,
        dropped_pct=25.0,
    )


def test_store_uses_wal_mode_for_concurrent_writer_safety(tmp_path):
    """Bir nechta jarayon (masalan bir nechta `ufl fetch-hf`) bir vaqtda bitta
    ufl.db'ga yozganda "database is locked" xatosi kamayishi uchun WAL rejimi."""
    with Store(tmp_path / "ufl.db") as store:
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"


def test_is_processed_false_before_recording(tmp_path):
    with Store(tmp_path / "ufl.db") as store:
        assert store.is_processed("data/input/books/sample.txt") is False


def test_record_book_makes_it_processed(tmp_path):
    with Store(tmp_path / "ufl.db") as store:
        store.record_book(_make_record())
        assert store.is_processed("data/input/books/sample.txt") is True


def test_record_book_upserts_on_same_path(tmp_path):
    with Store(tmp_path / "ufl.db") as store:
        store.record_book(_make_record())
        store.record_book(_make_record())  # ikkinchi marta — yangilanishi kerak, ikki qator emas
        assert store.book_count() == 1


def test_collected_tokens_by_category_sums_across_books(tmp_path):
    with Store(tmp_path / "ufl.db") as store:
        store.record_book(_make_record(path="a.txt", category="books"))
        store.record_book(_make_record(path="b.txt", category="books"))
        store.record_book(_make_record(path="c.txt", category="education"))

        totals = store.collected_tokens_by_category()

        assert totals["books"] == 220
        assert totals["education"] == 110


def test_collected_tokens_by_category_prefers_exact_tokens_when_available(tmp_path):
    """Aniq Gemma-4 tokenizer mavjud bo'lganda, byudjet aniq hisobga tayanishi kerak —
    taxminiy (belgi-nisbati) emas."""
    with Store(tmp_path / "ufl.db") as store:
        record_estimated_only = _make_record(path="a.txt", category="books")  # exact_tokens=None
        record_with_exact = _make_record(path="b.txt", category="books")
        record_with_exact.exact_tokens = 150
        record_with_exact.estimated_tokens = 90  # atayin farqli — exact ustunlik qilishi kerak
        store.record_book(record_estimated_only)
        store.record_book(record_with_exact)

        totals = store.collected_tokens_by_category()

        assert totals["books"] == 110 + 150  # 110 (estimated, chunki exact yo'q) + 150 (exact)


def test_store_persists_across_reconnects(tmp_path):
    db_path = tmp_path / "ufl.db"
    with Store(db_path) as store:
        store.record_book(_make_record())

    with Store(db_path) as store:
        assert store.is_processed("data/input/books/sample.txt") is True
        assert store.book_count() == 1


def test_migrates_existing_db_missing_dedup_status_column(tmp_path):
    """Production ufl.db fayllari dedup_status ustunisiz yaratilgan — Store
    ularni ochganda buzmasdan ustunni qo'shishi kerak."""
    import sqlite3

    db_path = tmp_path / "ufl.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE books (
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
        )
        """
    )
    conn.execute(
        "INSERT INTO books (path, category, format, char_count, estimated_tokens, "
        "total_blocks, kept_blocks, dropped_pct, processed_at) "
        "VALUES ('a.txt', 'books', 'txt', 10, 5, 1, 1, 0.0, '2026-01-01')"
    )
    conn.commit()
    conn.close()

    with Store(db_path) as store:
        assert store.book_count() == 1  # eski qator saqlanib qolgan
        columns = {row[1] for row in store._conn.execute("PRAGMA table_info(books)")}
        assert "dedup_status" in columns


def test_mark_duplicate_sets_status(tmp_path):
    with Store(tmp_path / "ufl.db") as store:
        store.record_book(_make_record(path="a.txt"))
        store.mark_duplicate("a.txt")
        cur = store._conn.execute("SELECT dedup_status FROM books WHERE path = ?", ("a.txt",))
        assert cur.fetchone()[0] == "duplicate"


def test_collected_tokens_by_category_excludes_duplicates(tmp_path):
    with Store(tmp_path / "ufl.db") as store:
        store.record_book(_make_record(path="a.txt", category="books"))
        store.record_book(_make_record(path="b.txt", category="books"))
        store.mark_duplicate("b.txt")

        totals = store.collected_tokens_by_category()

        assert totals["books"] == 110  # faqat a.txt (b.txt dublikat deb belgilangan)
