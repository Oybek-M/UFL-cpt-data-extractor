# tests/test_ingest_hf_dataset.py
"""`iter_shards` endi `datasets.load_dataset(streaming=True)` (Xet orqali)
o'rniga parquet fayllarni to'g'ridan-to'g'ri (Xet'siz, oddiy HTTP) yuklab
o'qiydi — real crawl'da `datasets`+Xet ba'zi datasetlarda (tahrirchi/uz-books-v2)
abadiy osilib qolgani tasdiqlangan (xuddi shu faylni oddiy curl 28 soniyada
yuklagan, lekin datasets orqali cheksiz 100% CPU bilan progress bo'lmagan)."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

import ufl.ingest.hf_dataset as hf_dataset
from ufl.ingest.hf_dataset import _list_split_parquet_files, dataset_slug, iter_shards


def test_dataset_slug_replaces_slash_with_underscore():
    assert dataset_slug("tahrirchi/uz-crawl") == "tahrirchi_uz-crawl"


def test_list_split_parquet_files_filters_and_sorts_by_shard_index(monkeypatch):
    class _FakeApi:
        def __init__(self, token=None):
            pass

        def list_repo_files(self, dataset_id, repo_type):
            return [
                "README.md",
                "data/lat-00001-of-00003.parquet",
                "data/lat-00000-of-00003.parquet",
                "data/other-00000-of-00001.parquet",
                "data/lat-00002-of-00003.parquet",
            ]

    monkeypatch.setattr(hf_dataset, "HfApi", _FakeApi)

    files = _list_split_parquet_files("some/dataset", "lat", token=None)

    assert files == [
        "data/lat-00000-of-00003.parquet",
        "data/lat-00001-of-00003.parquet",
        "data/lat-00002-of-00003.parquet",
    ]


def _write_parquet_fixture(path: Path, texts: list[str]) -> None:
    table = pa.table({"text": texts})
    pq.write_table(table, path)


def test_iter_shards_batches_rows_by_shard_size(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture.parquet"
    _write_parquet_fixture(fixture, [f"matn-{i}" for i in range(5)])

    monkeypatch.setattr(
        hf_dataset, "_list_split_parquet_files",
        lambda *a, **k: ["data/train-00000-of-00001.parquet"],
    )
    monkeypatch.setattr(
        hf_dataset, "_download_parquet",
        lambda dataset_id, path_in_repo, dest, token: dest.write_bytes(fixture.read_bytes()),
    )

    shards = list(iter_shards("some/dataset", "train", "text", shard_size=2))

    assert shards == [["matn-0", "matn-1"], ["matn-2", "matn-3"], ["matn-4"]]


def test_iter_shards_skips_rows_when_resuming(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture.parquet"
    _write_parquet_fixture(fixture, [f"matn-{i}" for i in range(5)])

    monkeypatch.setattr(
        hf_dataset, "_list_split_parquet_files",
        lambda *a, **k: ["data/train-00000-of-00001.parquet"],
    )
    monkeypatch.setattr(
        hf_dataset, "_download_parquet",
        lambda dataset_id, path_in_repo, dest, token: dest.write_bytes(fixture.read_bytes()),
    )

    shards = list(iter_shards("some/dataset", "train", "text", shard_size=2, skip_rows=2))

    assert shards == [["matn-2", "matn-3"], ["matn-4"]]


def test_iter_shards_stops_at_limit_even_mid_shard(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture.parquet"
    _write_parquet_fixture(fixture, [f"matn-{i}" for i in range(10)])

    monkeypatch.setattr(
        hf_dataset, "_list_split_parquet_files",
        lambda *a, **k: ["data/train-00000-of-00001.parquet"],
    )
    monkeypatch.setattr(
        hf_dataset, "_download_parquet",
        lambda dataset_id, path_in_repo, dest, token: dest.write_bytes(fixture.read_bytes()),
    )

    shards = list(iter_shards("some/dataset", "train", "text", shard_size=1000, limit=3))

    assert shards == [["matn-0", "matn-1", "matn-2"]]


def test_iter_shards_spans_multiple_parquet_files(tmp_path, monkeypatch):
    """Split bir nechta parquet faylga bo'lingan bo'lsa ham, qatorlar fayl
    chegarasidan qat'i nazar uzluksiz hisoblanishi kerak (skip/shard mantig'i
    butun split bo'yicha, alohida fayl emas)."""
    fixture_a = tmp_path / "a.parquet"
    fixture_b = tmp_path / "b.parquet"
    _write_parquet_fixture(fixture_a, ["matn-0", "matn-1", "matn-2"])
    _write_parquet_fixture(fixture_b, ["matn-3", "matn-4"])

    monkeypatch.setattr(
        hf_dataset, "_list_split_parquet_files",
        lambda *a, **k: [
            "data/train-00000-of-00002.parquet",
            "data/train-00001-of-00002.parquet",
        ],
    )

    def _fake_download(dataset_id, path_in_repo, dest, token):
        source = fixture_a if "00000" in path_in_repo else fixture_b
        dest.write_bytes(source.read_bytes())

    monkeypatch.setattr(hf_dataset, "_download_parquet", _fake_download)

    shards = list(iter_shards("some/dataset", "train", "text", shard_size=3))

    assert shards == [["matn-0", "matn-1", "matn-2"], ["matn-3", "matn-4"]]


def test_iter_shards_deletes_temp_file_after_each_parquet_file(tmp_path, monkeypatch):
    """Disk joyi juda cheklangan (~24GB) — bir vaqtda faqat bitta parquet
    fayl saqlanib, ishlov tugagach darhol o'chirilishi kerak."""
    fixture = tmp_path / "fixture.parquet"
    _write_parquet_fixture(fixture, [f"matn-{i}" for i in range(3)])

    seen_paths: list[Path] = []

    monkeypatch.setattr(
        hf_dataset, "_list_split_parquet_files",
        lambda *a, **k: ["data/train-00000-of-00001.parquet"],
    )

    def _fake_download(dataset_id, path_in_repo, dest, token):
        seen_paths.append(dest)
        dest.write_bytes(fixture.read_bytes())

    monkeypatch.setattr(hf_dataset, "_download_parquet", _fake_download)

    list(iter_shards("some/dataset", "train", "text", shard_size=1000))

    assert len(seen_paths) == 1
    assert not seen_paths[0].exists()  # ishlov tugagach o'chirilgan bo'lishi kerak
