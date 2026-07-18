# tests/test_ingest_hf_dataset.py
import ufl.ingest.hf_dataset as hf_dataset
from ufl.ingest.hf_dataset import dataset_slug, iter_shards


class _FakeStream:
    def __init__(self, rows):
        self._rows = list(rows)

    def skip(self, n):
        return _FakeStream(self._rows[n:])

    def __iter__(self):
        return iter(self._rows)


def test_dataset_slug_replaces_slash_with_underscore():
    assert dataset_slug("tahrirchi/uz-crawl") == "tahrirchi_uz-crawl"


def test_iter_shards_batches_rows_by_shard_size(monkeypatch):
    rows = [{"text": f"matn-{i}"} for i in range(5)]
    monkeypatch.setattr(hf_dataset, "load_dataset", lambda *a, **k: _FakeStream(rows))

    shards = list(iter_shards("some/dataset", "train", "text", shard_size=2))

    assert shards == [["matn-0", "matn-1"], ["matn-2", "matn-3"], ["matn-4"]]


def test_iter_shards_skips_rows_when_resuming(monkeypatch):
    rows = [{"text": f"matn-{i}"} for i in range(5)]
    monkeypatch.setattr(hf_dataset, "load_dataset", lambda *a, **k: _FakeStream(rows))

    shards = list(iter_shards("some/dataset", "train", "text", shard_size=2, skip_rows=2))

    assert shards == [["matn-2", "matn-3"], ["matn-4"]]


def test_iter_shards_stops_at_limit_even_mid_shard(monkeypatch):
    rows = [{"text": f"matn-{i}"} for i in range(10)]
    monkeypatch.setattr(hf_dataset, "load_dataset", lambda *a, **k: _FakeStream(rows))

    shards = list(iter_shards("some/dataset", "train", "text", shard_size=1000, limit=3))

    assert shards == [["matn-0", "matn-1", "matn-2"]]
