# tests/test_store_hf_state.py
from ufl.store.hf_state import HFFetchState


def test_get_last_shard_returns_zero_when_not_set(tmp_path):
    with HFFetchState(tmp_path / "state.sqlite3") as state:
        assert state.get_last_shard("tahrirchi/uz-crawl::news") == 0


def test_set_and_get_last_shard(tmp_path):
    with HFFetchState(tmp_path / "state.sqlite3") as state:
        state.set_last_shard("tahrirchi/uz-crawl::news", 42)
        assert state.get_last_shard("tahrirchi/uz-crawl::news") == 42


def test_set_last_shard_upserts_existing_key(tmp_path):
    with HFFetchState(tmp_path / "state.sqlite3") as state:
        state.set_last_shard("k", 5)
        state.set_last_shard("k", 10)
        assert state.get_last_shard("k") == 10


def test_state_persists_across_reconnects(tmp_path):
    path = tmp_path / "state.sqlite3"
    with HFFetchState(path) as state:
        state.set_last_shard("k", 7)
    with HFFetchState(path) as state:
        assert state.get_last_shard("k") == 7
