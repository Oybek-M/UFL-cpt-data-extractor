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


def test_store_persists_across_reconnects(tmp_path):
    db_path = tmp_path / "ufl.db"
    with Store(db_path) as store:
        store.record_book(_make_record())

    with Store(db_path) as store:
        assert store.is_processed("data/input/books/sample.txt") is True
        assert store.book_count() == 1
