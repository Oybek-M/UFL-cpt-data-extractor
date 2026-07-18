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


def test_get_shard_size_returns_none_when_not_set(tmp_path):
    with HFFetchState(tmp_path / "state.sqlite3") as state:
        assert state.get_shard_size("k") is None


def test_set_and_get_shard_size(tmp_path):
    with HFFetchState(tmp_path / "state.sqlite3") as state:
        state.set_shard_size("k", 20)
        assert state.get_shard_size("k") == 20


def test_set_last_shard_does_not_clear_shard_size(tmp_path):
    """shard_size va last_shard alohida yozilsa ham, bir-birini
    o'chirib yubormasligi kerak (bitta qatorda birga saqlanadi)."""
    with HFFetchState(tmp_path / "state.sqlite3") as state:
        state.set_shard_size("k", 20)
        state.set_last_shard("k", 3)
        assert state.get_shard_size("k") == 20
        assert state.get_last_shard("k") == 3


def test_migrates_existing_db_missing_shard_size_column(tmp_path):
    """Eski (production) hf_state fayllari shard_size ustunisiz yaratilgan —
    HFFetchState ularni ochganda buzmasdan ustunni qo'shishi kerak."""
    import sqlite3

    db_path = tmp_path / "state.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE progress(key TEXT PRIMARY KEY, last_shard INTEGER NOT NULL)")
    conn.execute("INSERT INTO progress(key, last_shard) VALUES ('k', 5)")
    conn.commit()
    conn.close()

    with HFFetchState(db_path) as state:
        assert state.get_last_shard("k") == 5  # eski qator saqlanib qolgan
        assert state.get_shard_size("k") is None  # eski qatorda hech qachon yozilmagan
