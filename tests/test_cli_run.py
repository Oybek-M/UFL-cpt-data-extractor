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


def test_run_processes_txt_file_and_writes_output(tmp_path):
    config_path = _write_test_config(tmp_path)
    input_dir = tmp_path / "input" / "books"
    input_dir.mkdir(parents=True)
    (input_dir / "sample.txt").write_text(_UZBEK_PARAGRAPH, encoding="utf-8")

    result = runner.invoke(app, ["run", str(tmp_path / "input"), "--config", str(config_path)])

    assert result.exit_code == 0
    output_txt = tmp_path / "output" / "books" / "sample.txt"
    assert output_txt.exists()
    assert "kitob" in output_txt.read_text(encoding="utf-8").lower()


def test_run_skips_already_processed_file_without_force(tmp_path):
    config_path = _write_test_config(tmp_path)
    input_dir = tmp_path / "input" / "books"
    input_dir.mkdir(parents=True)
    (input_dir / "sample.txt").write_text(_UZBEK_PARAGRAPH, encoding="utf-8")

    runner.invoke(app, ["run", str(tmp_path / "input"), "--config", str(config_path)])
    output_txt = tmp_path / "output" / "books" / "sample.txt"
    first_mtime = output_txt.stat().st_mtime

    result = runner.invoke(app, ["run", str(tmp_path / "input"), "--config", str(config_path)])

    assert result.exit_code == 0
    assert output_txt.stat().st_mtime == first_mtime  # qayta yozilmagan


def test_run_isolates_failures_and_continues_batch(tmp_path):
    config_path = _write_test_config(tmp_path)
    input_dir = tmp_path / "input" / "books"
    input_dir.mkdir(parents=True)
    (input_dir / "good.txt").write_text(_UZBEK_PARAGRAPH, encoding="utf-8")
    (input_dir / "broken.pdf").write_bytes(b"bu haqiqiy PDF fayl emas")

    result = runner.invoke(app, ["run", str(tmp_path / "input"), "--config", str(config_path)])

    assert result.exit_code == 0
    assert (tmp_path / "output" / "books" / "good.txt").exists()
    assert not (tmp_path / "output" / "books" / "broken.txt").exists()


def test_run_never_touches_minimax_when_all_files_have_folder_category(tmp_path, monkeypatch):
    """Kategoriya papka-nomidan aniqlansa, MiniMax umuman quril(may)maydi (token tejash)."""
    config_path = _write_test_config(tmp_path)
    input_dir = tmp_path / "input" / "books"
    input_dir.mkdir(parents=True)
    (input_dir / "sample.txt").write_text(_UZBEK_PARAGRAPH, encoding="utf-8")
    import ufl.cli as cli

    def _fail(*args, **kwargs):
        raise AssertionError("MiniMax chaqirilmasligi kerak edi")

    monkeypatch.setattr(cli, "_build_minimax", _fail)

    result = runner.invoke(app, ["run", str(tmp_path / "input"), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "output" / "books" / "sample.txt").exists()


def test_run_flat_file_without_minimax_falls_back_to_books(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "erkin.txt").write_text(_UZBEK_PARAGRAPH, encoding="utf-8")
    import ufl.cli as cli

    monkeypatch.setattr(cli, "_build_minimax", lambda *a, **k: None)

    result = runner.invoke(app, ["run", str(input_dir), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "output" / "books" / "erkin.txt").exists()


def test_run_flat_file_uses_minimax_category_when_available(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "maqola.txt").write_text(_UZBEK_PARAGRAPH, encoding="utf-8")
    import ufl.cli as cli

    class _FakeMiniMax:
        def classify_category(self, title, snippet, valid_categories):
            assert title == "maqola"
            return "education"

    monkeypatch.setattr(cli, "_build_minimax", lambda *a, **k: _FakeMiniMax())

    result = runner.invoke(app, ["run", str(input_dir), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "output" / "education" / "maqola.txt").exists()


def test_run_verify_with_minimax_drops_flagged_ambiguous_block(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    input_dir = tmp_path / "input" / "books"
    input_dir.mkdir(parents=True)
    bibliography_like = "Rashidov, Karimova, Yusupova, Alimov birgalikda ishladi."
    (input_dir / "sample.txt").write_text(
        _UZBEK_PARAGRAPH + "\n\n" + bibliography_like, encoding="utf-8"
    )
    import ufl.cli as cli

    class _FakeMiniMax:
        def arbitrate_noise_blocks(self, title, blocks):
            return {block_id for block_id, text in blocks if "Rashidov" in text}

    monkeypatch.setattr(cli, "_build_minimax", lambda *a, **k: _FakeMiniMax())

    result = runner.invoke(
        app,
        ["run", str(tmp_path / "input"), "--config", str(config_path), "--verify-with-minimax"],
    )

    assert result.exit_code == 0, result.output
    output_text = (tmp_path / "output" / "books" / "sample.txt").read_text(encoding="utf-8")
    assert "Rashidov" not in output_text
    assert "qiziqarli" in output_text.lower() or "kitob" in output_text.lower()


def test_run_summary_uses_exact_token_count_when_tokenizer_available(tmp_path, monkeypatch):
    """Gemma tokenizer topilganda, yakuniy xulosa taxminiy emas, ANIQ tokenni ko'rsatishi kerak."""
    config_path = _write_test_config(tmp_path)
    input_dir = tmp_path / "input" / "books"
    input_dir.mkdir(parents=True)
    (input_dir / "sample.txt").write_text(_UZBEK_PARAGRAPH, encoding="utf-8")
    import ufl.cli as cli

    monkeypatch.setattr(cli, "load_tokenizer_counter", lambda *a, **k: (lambda text: 12345))

    result = runner.invoke(app, ["run", str(tmp_path / "input"), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert "Aniq yig'ilgan token" in result.output
    assert "12,345" in result.output
    assert "Taxminiy" not in result.output


def test_run_without_flag_never_touches_minimax_for_structure(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    input_dir = tmp_path / "input" / "books"
    input_dir.mkdir(parents=True)
    (input_dir / "sample.txt").write_text(_UZBEK_PARAGRAPH, encoding="utf-8")
    import ufl.cli as cli

    def _fail(*args, **kwargs):
        raise AssertionError("MiniMax chaqirilmasligi kerak edi")

    monkeypatch.setattr(cli, "_build_minimax", _fail)

    result = runner.invoke(app, ["run", str(tmp_path / "input"), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
