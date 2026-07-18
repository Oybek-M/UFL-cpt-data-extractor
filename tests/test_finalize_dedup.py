"""Global (korpus-bo'ylab) exact-hash dedup — ingestion paytidagi dedup
(clean/dedup.py) faqat bitta CLI ishga tushirish doirasida ishlaydi; bu modul
butun data/output/ papkasi bo'ylab (turli sanalar/manbalardan) takrorlarni
topadi."""

from pathlib import Path

import pytest

from ufl.finalize.dedup import find_duplicate_groups, infer_source_path, quarantine_duplicates
from ufl.store.db import BookRecord, Store


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_find_duplicate_groups_detects_identical_content_across_categories(tmp_path):
    output_dir = tmp_path / "output"
    _write(output_dir / "books" / "1_kitob-a.txt", "Bir xil matn shu yerda.")
    _write(output_dir / "reference" / "2_kitob-b.txt", "Bir xil matn shu yerda.")
    _write(output_dir / "books" / "3_boshqa.txt", "Butunlay boshqa matn.")

    groups = find_duplicate_groups(output_dir)

    assert len(groups) == 1
    assert groups[0].kept.name == "1_kitob-a.txt"
    assert [p.name for p in groups[0].duplicates] == ["2_kitob-b.txt"]


def test_find_duplicate_groups_ignores_whitespace_case_differences(tmp_path):
    output_dir = tmp_path / "output"
    _write(output_dir / "books" / "1_a.txt", "Salom   Dunyo")
    _write(output_dir / "books" / "2_b.txt", "salom dunyo")

    groups = find_duplicate_groups(output_dir)

    assert len(groups) == 1


def test_find_duplicate_groups_returns_empty_when_no_duplicates(tmp_path):
    output_dir = tmp_path / "output"
    _write(output_dir / "books" / "1_a.txt", "Birinchi matn.")
    _write(output_dir / "books" / "2_b.txt", "Ikkinchi matn.")

    assert find_duplicate_groups(output_dir) == []


def test_infer_source_path_ziyouz_style_filename():
    assert infer_source_path("10763_hamza-hakimzoda-niyoziy.txt") == "ziyouz:10763"


def test_infer_source_path_hf_style_filename():
    assert (
        infer_source_path("tahrirchi_uz-crawl__news__shard-000001.txt")
        == "hf:tahrirchi/uz-crawl:news:shard-000001"
    )


def test_infer_source_path_unrecognized_filename_returns_none():
    assert infer_source_path("random-file-name.txt") is None


def test_quarantine_duplicates_moves_files_and_marks_store(tmp_path):
    output_dir = tmp_path / "output"
    rejected_dir = tmp_path / "rejected"
    kept = output_dir / "books" / "10763_kitob-a.txt"
    dup = output_dir / "books" / "10764_kitob-a-copy.txt"
    _write(kept, "Bir xil matn.")
    _write(dup, "Bir xil matn.")

    with Store(tmp_path / "ufl.db") as store:
        store.record_book(BookRecord(
            path="ziyouz:10764", category="books", format="txt", char_count=12,
            estimated_tokens=3, exact_tokens=None, total_blocks=1, kept_blocks=1, dropped_pct=0.0,
        ))
        groups = find_duplicate_groups(output_dir)

        moved = quarantine_duplicates(groups, rejected_dir=rejected_dir, store=store)

        assert moved == 1
        assert not dup.exists()
        assert (rejected_dir / "duplicates" / "books" / "10764_kitob-a-copy.txt").exists()
        assert kept.exists()  # birinchisi qoladi
        cur = store._conn.execute(
            "SELECT dedup_status FROM books WHERE path = ?", ("ziyouz:10764",)
        )
        assert cur.fetchone()[0] == "duplicate"


def test_quarantine_duplicates_skips_store_update_when_source_unrecognized(tmp_path):
    output_dir = tmp_path / "output"
    rejected_dir = tmp_path / "rejected"
    _write(output_dir / "books" / "random-a.txt", "Bir xil matn.")
    _write(output_dir / "books" / "random-b.txt", "Bir xil matn.")

    with Store(tmp_path / "ufl.db") as store:
        groups = find_duplicate_groups(output_dir)
        moved = quarantine_duplicates(groups, rejected_dir=rejected_dir, store=store)

    assert moved == 1  # DB yozuvi topilmasa ham fayl baribir ko'chiriladi


def test_quarantine_duplicates_succeeds_across_different_filesystems(tmp_path, monkeypatch):
    """output/ va rejected/ turli Docker bind-mountlarda (masalan UFL-Datas vs
    data/) bo'lganda os.rename EXDEV bilan xato beradi — shunday holatda ham
    fayl ko'chirilishi kerak (nusxalab-o'chirish orqali)."""
    output_dir = tmp_path / "output"
    rejected_dir = tmp_path / "rejected"
    kept = output_dir / "books" / "10763_kitob-a.txt"
    dup = output_dir / "books" / "10764_kitob-a-copy.txt"
    _write(kept, "Bir xil matn.")
    _write(dup, "Bir xil matn.")

    def _raise_exdev(self, target):
        raise OSError(18, "Invalid cross-device link")  # errno.EXDEV

    monkeypatch.setattr(Path, "replace", _raise_exdev)

    with Store(tmp_path / "ufl.db") as store:
        groups = find_duplicate_groups(output_dir)
        moved = quarantine_duplicates(groups, rejected_dir=rejected_dir, store=store)

    assert moved == 1
    assert not dup.exists()
    assert (rejected_dir / "duplicates" / "books" / "10764_kitob-a-copy.txt").read_text(
        encoding="utf-8"
    ) == "Bir xil matn."
