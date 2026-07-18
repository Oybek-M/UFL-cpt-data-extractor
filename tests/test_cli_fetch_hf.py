from pathlib import Path

from typer.testing import CliRunner

from ufl.cli import app

runner = CliRunner()

_UZBEK_PARAGRAPH = "Бу китоб жуда қизиқарли бўлиб, унда кўплаб воқеалар тасвирланган."


class _FakeStream:
    def __init__(self, rows):
        self._rows = list(rows)

    def skip(self, n):
        return _FakeStream(self._rows[n:])

    def __iter__(self):
        return iter(self._rows)


def _write_test_config(tmp_path: Path, books_budget: int = 1000) -> Path:
    config_content = f"""
[paths]
input = "{(tmp_path / "input").as_posix()}"
output = "{(tmp_path / "output").as_posix()}"
rejected = "{(tmp_path / "rejected").as_posix()}"
reports = "{(tmp_path / "reports").as_posix()}"
models_dir = "{(tmp_path / "models").as_posix()}"
db = "{(tmp_path / "ufl.db").as_posix()}"

[budget.categories]
books = {books_budget}
education = 1000

[tokenizer]
model_id = "bu-yerda-mavjud-bolmagan/model-id-xyz"
local_dir = "{(tmp_path / "models" / "tokenizer").as_posix()}"
chars_per_token = 4.0

[normalize]
apostrophe_mode = "ascii"
quote_style = "straight"

[quality]
min_chars = 25
min_words = 4
max_non_letter_ratio = 0.40
max_repeated_ngram_ratio = 0.30
max_upper_ratio = 0.70
max_url_ratio = 0.20

[language]
min_confidence = 0.65
min_heuristic_score = 0.20
fasttext_model_path = "{(tmp_path / "models" / "lid.176.ftz").as_posix()}"

[ocr]
languages = "uzb+uzb_cyrl"
min_confidence = 60
dpi = 300

[structure]
header_footer_min_repeats = 3
detect_toc = true
detect_bibliography = true

[dedup]
enabled = true
near_dup_enabled = false
"""
    config_path = tmp_path / "test_ufl.toml"
    config_path.write_text(config_content, encoding="utf-8")
    return config_path


def test_fetch_hf_processes_dataset_and_writes_shard_output(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    import ufl.ingest.hf_dataset as hf_dataset

    rows = [{"text": _UZBEK_PARAGRAPH} for _ in range(3)]
    monkeypatch.setattr(hf_dataset, "load_dataset", lambda *a, **k: _FakeStream(rows))

    result = runner.invoke(
        app,
        ["fetch-hf", "test/dataset", "--split", "train", "--category", "books",
         "--config", str(config_path)],
    )

    assert result.exit_code == 0, result.output
    output_files = list((tmp_path / "output" / "books").glob("*.txt"))
    assert len(output_files) == 1
    assert "kitob" in output_files[0].read_text(encoding="utf-8").lower()


def test_fetch_hf_rejects_invalid_category(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    import ufl.ingest.hf_dataset as hf_dataset

    monkeypatch.setattr(hf_dataset, "load_dataset", lambda *a, **k: _FakeStream([]))

    result = runner.invoke(
        app,
        ["fetch-hf", "test/dataset", "--split", "train", "--category", "notacategory",
         "--config", str(config_path)],
    )

    assert result.exit_code == 1


def test_fetch_hf_records_resumable_progress(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    import ufl.ingest.hf_dataset as hf_dataset
    from ufl.store.hf_state import HFFetchState

    rows = [{"text": _UZBEK_PARAGRAPH}]
    monkeypatch.setattr(hf_dataset, "load_dataset", lambda *a, **k: _FakeStream(rows))

    result = runner.invoke(
        app,
        ["fetch-hf", "test/dataset", "--split", "train", "--category", "books",
         "--config", str(config_path)],
    )

    assert result.exit_code == 0, result.output
    state_file = tmp_path / "hf_state" / "test_dataset__train.sqlite3"
    with HFFetchState(state_file) as state:
        assert state.get_last_shard("test/dataset::train") == 1


def test_fetch_hf_respects_limit_option(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    import ufl.ingest.hf_dataset as hf_dataset

    rows = [{"text": _UZBEK_PARAGRAPH + f" nashr-{i}."} for i in range(5)]
    monkeypatch.setattr(hf_dataset, "load_dataset", lambda *a, **k: _FakeStream(rows))

    result = runner.invoke(
        app,
        ["fetch-hf", "test/dataset", "--split", "train", "--category", "books",
         "--limit", "2", "--config", str(config_path)],
    )

    assert result.exit_code == 0, result.output
    output_files = list((tmp_path / "output" / "books").glob("*.txt"))
    assert len(output_files) == 1
    text = output_files[0].read_text(encoding="utf-8")
    assert text.count("nashr-0") + text.count("nashr-1") == 2
    assert "nashr-2" not in text


def test_fetch_hf_stops_at_budget_when_flag_set(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path, books_budget=50)
    import ufl.ingest.hf_dataset as hf_dataset

    rows = [{"text": _UZBEK_PARAGRAPH + f" nashr-{i}."} for i in range(1001)]
    monkeypatch.setattr(hf_dataset, "load_dataset", lambda *a, **k: _FakeStream(rows))

    result = runner.invoke(
        app,
        ["fetch-hf", "test/dataset", "--split", "train", "--category", "books",
         "--stop-at-budget", "--config", str(config_path)],
    )

    assert result.exit_code == 0, result.output
    output_files = list((tmp_path / "output" / "books").glob("*.txt"))
    assert len(output_files) == 1  # faqat 1-shard (1000 qator); budjetga yetgach 2-shard ishlanmadi


def test_fetch_hf_without_flag_ignores_budget_and_processes_all_shards(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path, books_budget=50)
    import ufl.ingest.hf_dataset as hf_dataset

    rows = [{"text": _UZBEK_PARAGRAPH + f" nashr-{i}."} for i in range(1001)]
    monkeypatch.setattr(hf_dataset, "load_dataset", lambda *a, **k: _FakeStream(rows))

    result = runner.invoke(
        app,
        ["fetch-hf", "test/dataset", "--split", "train", "--category", "books",
         "--config", str(config_path)],
    )

    assert result.exit_code == 0, result.output
    output_files = list((tmp_path / "output" / "books").glob("*.txt"))
    assert len(output_files) == 2  # ikkala shard ham ishlandi (1000 + 1 qator), budjet e'tiborsiz
