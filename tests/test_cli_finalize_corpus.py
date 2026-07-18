"""`ufl finalize-corpus` integratsiya testi — vaqtinchalik output/db papkalarda,
haqiqiy UFL-Datas'ga tegmasdan."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ufl.cli import app
from ufl.store.db import BookRecord, Store

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
web_news = 1000

[tokenizer]
model_id = "bu-yerda-mavjud-bolmagan/model-id-xyz"
local_dir = "{(tmp_path / "models" / "tokenizer").as_posix()}"
chars_per_token = 4.0

[normalize]
apostrophe_mode = "ascii"
quote_style = "straight"

[quality]
min_chars = 10
min_words = 2
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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_dry_run_makes_no_changes(tmp_path):
    config_path = _write_test_config(tmp_path)
    output_dir = tmp_path / "output"
    dup_a = output_dir / "books" / "1_a.txt"
    dup_b = output_dir / "books" / "2_b.txt"
    hf_file = output_dir / "web_news" / "tahrirchi_uz-crawl__news__shard-000001.txt"
    _write(dup_a, "Bir xil matn.")
    _write(dup_b, "Bir xil matn.")
    _write(hf_file, "Email: a@b.com bilan bog'laning.")

    result = runner.invoke(app, ["finalize-corpus", "--config", str(config_path)])

    assert result.exit_code == 0
    assert dup_a.exists() and dup_b.exists()  # hech narsa ko'chirilmagan
    assert hf_file.exists()  # hali qayta nomlanmagan
    assert "a@b.com" in hf_file.read_text(encoding="utf-8")  # PII hali tozalanmagan
    assert "dry-run" in result.output.lower() or "--apply" in result.output


def test_apply_runs_all_three_stages(tmp_path):
    config_path = _write_test_config(tmp_path)
    output_dir = tmp_path / "output"
    rejected_dir = tmp_path / "rejected"
    dup_a = output_dir / "books" / "1_a.txt"
    dup_b = output_dir / "books" / "2_b.txt"
    hf_file = output_dir / "web_news" / "tahrirchi_uz-crawl__news__shard-000001.txt"
    _write(dup_a, "Bir xil matn.")
    _write(dup_b, "Bir xil matn.")
    _write(hf_file, "Email: a@b.com bilan bog'laning.")

    with Store(tmp_path / "ufl.db") as store:
        store.record_book(BookRecord(
            path="ziyouz:2", category="books", format="txt", char_count=12,
            estimated_tokens=3, exact_tokens=None, total_blocks=1, kept_blocks=1, dropped_pct=0.0,
        ))

    result = runner.invoke(app, ["finalize-corpus", "--apply", "--config", str(config_path)])

    assert result.exit_code == 0
    assert dup_a.exists()
    assert not dup_b.exists()
    assert (rejected_dir / "duplicates" / "books" / "2_b.txt").exists()

    renamed_hf = output_dir / "web_news" / "corpus-a__news__shard-000001.txt"
    assert not hf_file.exists()
    assert renamed_hf.exists()
    assert "a@b.com" not in renamed_hf.read_text(encoding="utf-8")


def test_apply_warns_on_unknown_hf_dataset(tmp_path):
    config_path = _write_test_config(tmp_path)
    output_dir = tmp_path / "output"
    _write(output_dir / "web_news" / "boshqa_dataset__train__shard-000001.txt", "Matn.")

    result = runner.invoke(app, ["finalize-corpus", "--apply", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "boshqa_dataset" in result.output
