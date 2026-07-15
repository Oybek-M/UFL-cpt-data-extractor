from pathlib import Path

from typer.testing import CliRunner

from ufl.cli import app

runner = CliRunner()

_UZBEK_PARAGRAPH = "Бу китоб жуда қизиқарли бўлиб, унда кўплаб воқеалар тасвирланган."


def _write_test_config(tmp_path: Path) -> Path:
    config_content = f"""
[paths]
input = "{(tmp_path / "input").as_posix()}"
output = "{(tmp_path / "output").as_posix()}"
rejected = "{(tmp_path / "rejected").as_posix()}"
reports = "{(tmp_path / "reports").as_posix()}"
models_dir = "{(tmp_path / "models").as_posix()}"
db = "{(tmp_path / "ufl.db").as_posix()}"

[budget.categories]
books = 1000

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


def test_stats_shows_budget_progress_after_run(tmp_path):
    config_path = _write_test_config(tmp_path)
    input_dir = tmp_path / "input" / "books"
    input_dir.mkdir(parents=True)
    (input_dir / "sample.txt").write_text(_UZBEK_PARAGRAPH, encoding="utf-8")

    runner.invoke(app, ["run", str(tmp_path / "input"), "--config", str(config_path)])
    result = runner.invoke(app, ["stats", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "books" in result.stdout
    assert "JAMI" in result.stdout


def test_stats_works_with_empty_database(tmp_path):
    config_path = _write_test_config(tmp_path)

    result = runner.invoke(app, ["stats", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "0" in result.stdout
