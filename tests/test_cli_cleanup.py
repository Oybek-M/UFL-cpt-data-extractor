import os
import time
from pathlib import Path

from typer.testing import CliRunner

from ufl.cli import app

runner = CliRunner()


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


def _touch_with_age(path: Path, days_old: int) -> None:
    path.write_text("{}", encoding="utf-8")
    old_time = time.time() - days_old * 86400
    os.utime(path, (old_time, old_time))


def test_cleanup_removes_old_rejected_and_report_files(tmp_path):
    config_path = _write_test_config(tmp_path)
    rejected_dir = tmp_path / "rejected" / "books"
    reports_dir = tmp_path / "reports"
    rejected_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    old_rejected = rejected_dir / "old.jsonl"
    _touch_with_age(old_rejected, days_old=40)

    result = runner.invoke(app, ["cleanup", "--config", str(config_path), "--older-than-days", "30"])

    assert result.exit_code == 0
    assert not old_rejected.exists()
    assert "1 ta fayl o'chirildi" in result.stdout


def test_cleanup_dry_run_does_not_delete_and_reports_count(tmp_path):
    config_path = _write_test_config(tmp_path)
    rejected_dir = tmp_path / "rejected"
    rejected_dir.mkdir(parents=True)
    old_rejected = rejected_dir / "old.jsonl"
    _touch_with_age(old_rejected, days_old=40)

    result = runner.invoke(
        app, ["cleanup", "--config", str(config_path), "--older-than-days", "30", "--dry-run"]
    )

    assert result.exit_code == 0
    assert old_rejected.exists()
    assert "dry-run" in result.stdout
