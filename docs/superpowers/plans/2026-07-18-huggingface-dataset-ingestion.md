# HuggingFace Dataset Ingestion (`ufl fetch-hf`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `ufl fetch-hf <dataset-id>` CLI command that streams rows from a HuggingFace dataset (no full download — local disk has only ~24GB free), runs each row through the existing language/quality/dedup/normalize pipeline, and writes shard-batched clean text output, with resumable progress tracking and a user-controlled `--stop-at-budget` flag.

**Architecture:** Three new small modules (`store/hf_state.py` for resumable progress, `ingest/hf_dataset.py` for streaming+sharding, `hf_pipeline.py` for the row-cleaning logic) plumbed into a new `cli.py` command. Maximally reuses existing code: `clean_paragraphs()` (unchanged), `ProcessResult`/`write_output()` (unchanged, reused by constructing a `ProcessResult` per shard), `Store`/`BookRecord` (unchanged, one record per shard). A local-only `docker-compose.override.yml` (gitignored) redirects `/app/data/output` to the external `UFL-Datas` folder — zero application code changes for that part.

**Tech Stack:** HuggingFace `datasets` library (streaming mode), existing UFL pipeline primitives, pytest, Docker.

**Spec:** `docs/superpowers/specs/2026-07-18-huggingface-dataset-ingestion-design.md`

---

## Task 1: Resumable progress state (`HFFetchState`)

**Files:**
- Create: `src/ufl/store/hf_state.py`
- Test: `tests/test_store_hf_state.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from project root, using the light local venv — no heavy deps needed for this module):
```bash
PYTHONPATH=src python -m pytest tests/test_store_hf_state.py -q
```
Expected: FAIL with `ModuleNotFoundError: No module named 'ufl.store.hf_state'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ufl/store/hf_state.py
"""HF fetch-hf progress holati — dataset+split bo'yicha oxirgi tugallangan shard raqami.

Byudjet DB (ufl.db)dan ALOHIDA: har dataset+split uchun alohida kichik SQLite fayl
(`data/hf_state/<slug>__<split>.sqlite3`), xuddi crawl uchun CrawlState kabi.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = "CREATE TABLE IF NOT EXISTS progress(key TEXT PRIMARY KEY, last_shard INTEGER NOT NULL);"


class HFFetchState:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "HFFetchState":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_last_shard(self, key: str) -> int:
        row = self._conn.execute("SELECT last_shard FROM progress WHERE key=?", (key,)).fetchone()
        return int(row[0]) if row else 0

    def set_last_shard(self, key: str, shard_index: int) -> None:
        self._conn.execute(
            "INSERT INTO progress(key,last_shard) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET last_shard=excluded.last_shard",
            (key, shard_index),
        )
        self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_store_hf_state.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ufl/store/hf_state.py tests/test_store_hf_state.py
git commit -m "HF fetch-hf uchun davom ettiriladigan progress holati (HFFetchState)"
```

---

## Task 2: Streaming + sharding (`ingest/hf_dataset.py`)

**Files:**
- Create: `src/ufl/ingest/hf_dataset.py`
- Test: `tests/test_ingest_hf_dataset.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_ingest_hf_dataset.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ufl.ingest.hf_dataset'` (note: this test file does NOT need the `datasets` package installed, since `load_dataset` is monkeypatched before it's ever called — but the module-level `from datasets import load_dataset` import in `hf_dataset.py` DOES require `datasets` to be importable. If running in the light local venv without `datasets` installed, this will instead fail with `ModuleNotFoundError: No module named 'datasets'` — that is also an acceptable RED result for this step, proving the module doesn't exist/work yet. If that happens, skip ahead and run this test suite for real inside Docker after Task 4 installs `datasets`.)

- [ ] **Step 3: Write minimal implementation**

```python
# src/ufl/ingest/hf_dataset.py
"""HuggingFace dataset'larni streaming rejimda o'qish (to'liq yuklab olmasdan) va
shard (guruh)larga bo'lish.

Diskda joy juda cheklangan (~24GB) — datasets kutubxonasining oddiy (to'liq yuklovchi)
rejimi HECH QACHON ishlatilmaydi, faqat streaming=True.
Qoidalar: docs/superpowers/specs/2026-07-18-huggingface-dataset-ingestion-design.md
"""

from __future__ import annotations

import os
from typing import Iterator

from datasets import load_dataset

SHARD_SIZE = 1000


def dataset_slug(dataset_id: str) -> str:
    return dataset_id.replace("/", "_")


def iter_shards(
    dataset_id: str,
    split: str,
    text_column: str,
    *,
    shard_size: int = SHARD_SIZE,
    skip_rows: int = 0,
    limit: int = 0,
) -> Iterator[list[str]]:
    """Dataset'ni streaming o'qiydi, har `shard_size` qatordan iborat matn-ro'yxatini
    qaytaradi. `skip_rows` — davom ettirish uchun (allaqachon ishlangan qatorlar).
    `limit` — 0 bo'lmasa, shuncha qatordan keyin (hatto shard o'rtasida bo'lsa ham) to'xtaydi.
    """
    stream = load_dataset(
        dataset_id, split=split, streaming=True, token=os.environ.get("HF_TOKEN") or None
    )
    if skip_rows:
        stream = stream.skip(skip_rows)

    batch: list[str] = []
    total = 0
    for row in stream:
        batch.append(row[text_column])
        total += 1
        if len(batch) >= shard_size:
            yield batch
            batch = []
        if limit and total >= limit:
            break
    if batch:
        yield batch
```

- [ ] **Step 4: Run tests to verify they pass**

This module imports `datasets` at module load time, so this step must run where `datasets` is installed. Run inside Docker:
```bash
docker compose run --rm ufl bash -c "pip install -q datasets && PYTHONPATH=src python -m pytest tests/test_ingest_hf_dataset.py -q"
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ufl/ingest/hf_dataset.py tests/test_ingest_hf_dataset.py
git commit -m "HF dataset streaming + shard-bo'lish (ingest/hf_dataset.py)"
```

---

## Task 3: Row-cleaning pipeline (`hf_pipeline.py`)

**Files:**
- Create: `src/ufl/hf_pipeline.py`
- Test: `tests/test_hf_pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hf_pipeline.py
from ufl.clean.dedup import DeduplicationStore
from ufl.hf_pipeline import process_hf_shard

_UZBEK = "Бу китоб жуда қизиқарли бўлиб, унда кўплаб воқеалар тасвирланган."
_ENGLISH = (
    "This is a purely English paragraph without any Uzbek words "
    "that should definitely be filtered out here."
)


def test_process_hf_shard_keeps_uzbek_drops_non_uzbek():
    result = process_hf_shard(
        [_UZBEK, _ENGLISH],
        shard_label="test__train__shard-000001",
        category="books",
        dedup_store=DeduplicationStore(),
    )

    assert result.category == "books"
    assert result.format == "hf-dataset"
    assert result.total_blocks == 2
    assert result.kept_blocks == 1
    assert "kitob" in result.kept_text.lower()
    assert any(d.reason == "til_ozbekcha_emas" for d in result.dropped)


def test_process_hf_shard_deduplicates_within_shard():
    result = process_hf_shard(
        [_UZBEK, _UZBEK],
        shard_label="test__train__shard-000001",
        category="books",
        dedup_store=DeduplicationStore(),
    )

    assert result.kept_blocks == 1
    assert any(d.reason == "takror" for d in result.dropped)


def test_process_hf_shard_source_path_matches_shard_label():
    result = process_hf_shard(
        [_UZBEK],
        shard_label="tahrirchi_uz-crawl__news__shard-000042",
        category="web_news",
        dedup_store=DeduplicationStore(),
    )

    assert result.source_path.name == "tahrirchi_uz-crawl__news__shard-000042"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_hf_pipeline.py -q` (light venv is fine — this module doesn't import `datasets`)
Expected: FAIL with `ModuleNotFoundError: No module named 'ufl.hf_pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ufl/hf_pipeline.py
"""HF dataset qator-shardlarini tozalash: bitta hujjat (fayl) o'rniga bitta shard
(N qatorlik matn-ro'yxati) `ProcessResult`ga aylantiradi — mavjud `pipeline.write_output()`
o'zgarishsiz qayta ishlatiladi (shard_label fayl nomiga aylanadi).
"""

from __future__ import annotations

from pathlib import Path

from ufl.clean.apply import clean_paragraphs
from ufl.clean.dedup import DeduplicationStore
from ufl.clean.language import FastTextPredictor
from ufl.pipeline import DroppedBlock, ProcessResult
from ufl.stats.tokens import TokenCounter, count_tokens


def process_hf_shard(
    texts: list[str],
    *,
    shard_label: str,
    category: str,
    dedup_store: DeduplicationStore,
    fasttext_predict: FastTextPredictor | None = None,
    exact_token_counter: TokenCounter | None = None,
    chars_per_token: float = 4.0,
    min_language_confidence: float = 0.65,
    min_heuristic_score: float = 0.20,
    apostrophe_mode: str = "ascii",
    quality_kwargs: dict | None = None,
) -> ProcessResult:
    dropped: list[DroppedBlock] = []

    def _record_drop(text: str, reason: str) -> None:
        dropped.append(DroppedBlock(text=text, page=0, reason=reason))

    kept = clean_paragraphs(
        texts,
        dedup_store=dedup_store,
        get_text=lambda t: t,
        fasttext_predict=fasttext_predict,
        min_language_confidence=min_language_confidence,
        min_heuristic_score=min_heuristic_score,
        apostrophe_mode=apostrophe_mode,
        quality_kwargs=quality_kwargs,
        on_drop=_record_drop,
    )
    kept_text = "\n\n".join(kept)
    token_counts = count_tokens(
        kept_text, chars_per_token=chars_per_token, exact_counter=exact_token_counter
    )

    return ProcessResult(
        source_path=Path(shard_label),
        category=category,
        format="hf-dataset",
        kept_text=kept_text,
        dropped=dropped,
        char_count=token_counts.char_count,
        estimated_tokens=token_counts.estimated_tokens,
        exact_tokens=token_counts.exact_tokens,
        total_blocks=len(texts),
        kept_blocks=len(kept),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_hf_pipeline.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ufl/hf_pipeline.py tests/test_hf_pipeline.py
git commit -m "HF shard-qatorlarni tozalash pipeline'i (hf_pipeline.py)"
```

---

## Task 4: Add `datasets` dependency, rebuild, verify no regressions

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the dependency**

Add this line to `requirements.txt`, in a new section after the tokenizer section:

```
# --- HuggingFace dataset streaming (fetch-hf) ---
datasets==5.0.0
```

- [ ] **Step 2: Rebuild the Docker image**

```bash
docker compose build
```
Expected: build succeeds (no dependency conflict errors — already verified compatible with `huggingface-hub==1.24.0`/`transformers==5.14.1` during design).

- [ ] **Step 3: Run the full test suite**

```bash
docker compose run --rm ufl python -m pytest tests/ -q
```
Expected: all tests pass, including the new `test_ingest_hf_dataset.py` (this time for real, since `datasets` is now baked into the image — no need for the ad-hoc `pip install` from Task 2 Step 4 anymore).

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "datasets kutubxonasi qo'shildi (HF streaming uchun)"
```

---

## Task 5: Wire the `ufl fetch-hf` CLI command

**Files:**
- Modify: `src/ufl/cli.py`
- Test: `tests/test_cli_fetch_hf.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_fetch_hf.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose run --rm ufl python -m pytest tests/test_cli_fetch_hf.py -q
```
Expected: FAIL — `fetch-hf` is not a registered command (typer will report "No such command 'fetch-hf'").

- [ ] **Step 3: Write minimal implementation**

In `src/ufl/cli.py`, add these imports near the top (alongside the existing `from ufl.pipeline import ...` line):

```python
from ufl.hf_pipeline import process_hf_shard
from ufl.ingest.hf_dataset import SHARD_SIZE, dataset_slug, iter_shards
from ufl.store.hf_state import HFFetchState
```

Then add this new command, placed after the `crawl` command function (end of file is fine too):

```python
@app.command("fetch-hf")
def fetch_hf(
    dataset_id: str = typer.Argument(..., help="HuggingFace dataset ID (masalan tahrirchi/uz-crawl)"),
    split: str = typer.Option(..., "--split", help="Dataset split nomi (masalan train, news, lat)"),
    category: str = typer.Option(..., "--category", help="8 kategoriyadan biri"),
    text_column: str = typer.Option("text", "--text-column", help="Matn ustuni nomi"),
    limit: int = typer.Option(0, "--limit", help="Shuncha qatordan keyin to'xtash (0 — cheklovsiz)"),
    stop_at_budget: bool = typer.Option(
        False, "--stop-at-budget",
        help="Kategoriya budjet-maqsadiga yetgach avtomatik to'xtash (standart: o'chiq — dataset oxirigacha ishlanadi)",
    ),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
    """HuggingFace dataset'dan qator-baqator (streaming) toza matn yig'ish."""
    setup_logging()
    if category not in CRAWL_CATEGORIES:
        console.print(
            f"[bold red]Xato:[/bold red] noto'g'ri kategoriya '{category}'. "
            f"Ruxsat etilgan: {', '.join(CRAWL_CATEGORIES)}."
        )
        raise typer.Exit(code=1)

    config = Config.load(config_path)
    slug = dataset_slug(dataset_id)
    state_path = config.paths.db.parent / "hf_state" / f"{slug}__{split}.sqlite3"
    fasttext_predict = load_fasttext_predictor(config.language.fasttext_model_path)
    exact_token_counter = load_tokenizer_counter(config.tokenizer.local_dir, config.tokenizer.model_id)
    quality_kwargs = {
        "min_chars": config.quality.min_chars,
        "min_words": config.quality.min_words,
        "max_non_letter_ratio": config.quality.max_non_letter_ratio,
        "max_repeated_ngram_ratio": config.quality.max_repeated_ngram_ratio,
        "max_upper_ratio": config.quality.max_upper_ratio,
        "max_url_ratio": config.quality.max_url_ratio,
    }
    dedup_store = DeduplicationStore()

    with HFFetchState(state_path) as state, Store(config.paths.db) as store:
        key = f"{dataset_id}::{split}"
        shard_index = state.get_last_shard(key)
        skip_rows = shard_index * SHARD_SIZE
        ok_shards = 0
        processed_rows = 0
        kept_total = 0

        for texts in iter_shards(dataset_id, split, text_column, skip_rows=skip_rows, limit=limit):
            shard_index += 1
            shard_label = f"{slug}__{split}__shard-{shard_index:06d}"
            result = process_hf_shard(
                texts,
                shard_label=shard_label,
                category=category,
                dedup_store=dedup_store,
                fasttext_predict=fasttext_predict,
                exact_token_counter=exact_token_counter,
                chars_per_token=config.tokenizer.chars_per_token,
                min_language_confidence=config.language.min_confidence,
                min_heuristic_score=config.language.min_heuristic_score,
                apostrophe_mode=config.normalize.apostrophe_mode,
                quality_kwargs=quality_kwargs,
            )
            write_output(
                result,
                output_dir=config.paths.output,
                rejected_dir=config.paths.rejected,
                reports_dir=config.paths.reports,
            )
            dropped_pct = (
                len(result.dropped) / result.total_blocks * 100 if result.total_blocks else 0.0
            )
            store.record_book(
                BookRecord(
                    path=f"hf:{dataset_id}:{split}:shard-{shard_index:06d}",
                    category=category,
                    format=result.format,
                    char_count=result.char_count,
                    estimated_tokens=result.estimated_tokens,
                    exact_tokens=result.exact_tokens,
                    total_blocks=result.total_blocks,
                    kept_blocks=result.kept_blocks,
                    dropped_pct=round(dropped_pct, 2),
                )
            )
            state.set_last_shard(key, shard_index)
            ok_shards += 1
            processed_rows += len(texts)
            kept_total += result.kept_blocks
            console.print(
                f"Shard {shard_index}: {result.kept_blocks}/{result.total_blocks} saqlandi "
                f"({result.exact_tokens or result.estimated_tokens:,} token)."
            )

            if stop_at_budget:
                collected = store.collected_tokens_by_category()
                target = config.budget.categories.get(category)
                if target and collected.get(category, 0) >= target:
                    console.print(
                        f"[green]Budjet maqsadiga yetildi[/green] "
                        f"({category}: {collected[category]:,}/{target:,}). To'xtatilmoqda."
                    )
                    break

    # `datasets` kutubxonasining ba'zi native (pyarrow) thread'lari interpreter
    # tugaganda tozalanmasdan xato berishi mumkin (kuzatilgan: PyGILState_Release
    # crash) — aniq tozalash bu holatni oldini oladi.
    import gc

    gc.collect()

    console.print(
        f"\n[bold green]Tugadi.[/bold green] {ok_shards} shard qayta ishlandi "
        f"({processed_rows:,} qator, {kept_total:,} saqlandi)."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose run --rm ufl python -m pytest tests/test_cli_fetch_hf.py -q
```
Expected: `7 passed`

- [ ] **Step 5: Run the full suite to confirm no regressions**

```bash
docker compose run --rm ufl python -m pytest tests/ -q
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/ufl/cli.py tests/test_cli_fetch_hf.py
git commit -m "ufl fetch-hf buyrug'i qo'shildi (streaming, resumable, --stop-at-budget)"
```

---

## Task 6: Local `UFL-Datas` output redirection (Docker Compose override)

**Files:**
- Create: `docker-compose.override.yml.example`
- Modify: `.gitignore`
- Create (local only, NOT committed): `docker-compose.override.yml`

This task has no tests (pure infrastructure config) — verification is a manual Docker check.

- [ ] **Step 1: Create the committed template file**

```yaml
# docker-compose.override.yml.example
#
# Lokal-only konfiguratsiya namunasi. Nusxalab `docker-compose.override.yml` deb
# saqlang va o'z "toza-data ombori" yo'lingizni yozing. Bu fayl .gitignore'da —
# hech qachon git'ga tushmaydi, VPS'ga ham umuman ta'sir qilmaydi (VPS'da bu fayl
# yo'q, shuning uchun oddiy data/output/ bilan davom etadi).
services:
  ufl:
    volumes:
      - "../UFL-Datas:/app/data/output"
  web:
    volumes:
      - "../UFL-Datas:/app/data/output"
```

- [ ] **Step 2: Add to .gitignore**

Add this line to `.gitignore` (near the top, in a sensible section):

```
docker-compose.override.yml
```

- [ ] **Step 3: Create the real local override file**

```yaml
# docker-compose.override.yml
services:
  ufl:
    volumes:
      - "../UFL-Datas:/app/data/output"
  web:
    volumes:
      - "../UFL-Datas:/app/data/output"
```

Save this as `docker-compose.override.yml` in the project root (same directory as `docker-compose.yml`).

- [ ] **Step 4: Verify the mount works**

```bash
docker compose run --rm ufl bash -c "touch data/output/_mount_test.txt && ls /app/data/output"
```
Expected: `_mount_test.txt` appears in the output listing. Then check on the Windows host:
```bash
ls "/c/Users/Oybek/Documents/Projects programming/StartUps/UFL-Datas/_mount_test.txt"
```
Expected: file exists there. Clean up afterward:
```bash
rm "/c/Users/Oybek/Documents/Projects programming/StartUps/UFL-Datas/_mount_test.txt"
```

- [ ] **Step 5: Commit (only the committed files)**

```bash
git add docker-compose.override.yml.example .gitignore
git commit -m "UFL-Datas'ga lokal chiqish uchun docker-compose.override.yml namunasi"
```

---

## Task 7: Documentation

**Files:**
- Modify: `docs/DOCKER.md`
- Modify: `README.md`

- [ ] **Step 1: Add a new section to `docs/DOCKER.md`**

Add this section after the existing "§7. Fayllardan (eBook/hujjat) data extract qilish" section (or after whatever is currently the last numbered section — check the file first and use the next number):

```markdown
---

## 8. HuggingFace dataset'lardan yig'ish (`fetch-hf`)

Ba'zi o'zbekcha matn dataset'lari HuggingFace'da allaqachon millionlab qator sifatida
tayyor turibdi (masalan `tahrirchi/uz-books-v2`, `tahrirchi/uz-crawl`, `yakhyo/uz-wiki`).
Bularni qo'lda yuklab olish/o'qish o'rniga, `ufl fetch-hf` streaming rejimda (diskka
to'liq nusxa saqlamasdan) qator-baqator o'qib, mavjud til/sifat/dedup pipeline'idan
o'tkazadi.

### 8.1 Foydalanish

```bash
docker compose run --rm ufl ufl fetch-hf tahrirchi/uz-books-v2 --split lat --category books
docker compose run --rm ufl ufl fetch-hf tahrirchi/uz-crawl --split news --category web_news
docker compose run --rm ufl ufl fetch-hf tahrirchi/uz-crawl --split telegram_blogs --category web_news
docker compose run --rm ufl ufl fetch-hf yakhyo/uz-wiki --split train --category reference
```

- `--limit N` — sinov uchun, faqat N qator (masalan `--limit 100`).
- `--stop-at-budget` — kategoriya budjet-maqsadiga yetgach avtomatik to'xtaydi.
  **Standart: o'chiq** — bayroqsiz dataset oxirigacha (yoki manba tugaguncha) ishlanadi,
  hatto budjetdan oshib ketsa ham (to'xtash-to'xtamaslik qarori foydalanuvchida).

### 8.2 Davom ettirish

Har `dataset-id + split` uchun progress alohida saqlanadi (`data/hf_state/`). Buyruq
uzilib qolsa (tarmoq, vaqt), qayta ishga tushirilganda oxirgi tugallangan shard'dan
davom etadi — boshidan boshlamaydi.

### 8.3 Chiqish

Har 1000 qator — bitta shard fayl: `<output>/<kategoriya>/<dataset-slug>__<split>__shard-NNNNNN.txt`.

### 8.4 Litsenziya eslatmasi

`tahrirchi/*` dataset'lari apache-2.0/mit litsenziyali. `yakhyo/uz-wiki` paketlanishi
mit, lekin tarkib Vikipediya matni (CC BY-SA) — foydalanishdan oldin o'z loyihangiz
uchun litsenziya mosligini tekshiring (§6.5'dagi kabi umumiy eslatma shu yerga ham
tegishli).
```

- [ ] **Step 2: Update `README.md`**

Add this bullet to the feature list (after the existing "Fayllardan (eBook/hujjat) extract" bullet):

```markdown
- ✅ HuggingFace dataset'lardan streaming yig'ish (`ufl fetch-hf`): millionlab qatorli
  tayyor dataset'larni (uz-books-v2, uz-crawl, uz-wiki) to'liq yuklab olmasdan,
  mavjud tozalash pipeline'i orqali o'tkazadi — davom ettiriladigan, ixtiyoriy
  `--stop-at-budget`
```

- [ ] **Step 3: Commit**

```bash
git add docs/DOCKER.md README.md
git commit -m "fetch-hf hujjatlari (DOCKER.md §8, README)"
```

---

## Task 8: Real-world verification against a real HuggingFace dataset

**Files:** none (verification only)

This is the acid-test step — per this project's established practice, synthetic unit
tests alone are not trusted for new ingestion paths; a small real run against the
actual HuggingFace dataset is required before considering this feature done.

- [ ] **Step 1: Run a small real fetch against `yakhyo/uz-wiki`**

```bash
docker compose run --rm ufl ufl fetch-hf yakhyo/uz-wiki --split train --category reference --limit 50
```
Expected: command completes, prints a "Shard 1: N/50 saqlandi" line and a final
"Tugadi." summary line, exit code 0 (no `PyGILState_Release` crash — the `gc.collect()`
mitigation from Task 5 should prevent it; if the crash still appears, note it but
confirm the exit code is still 0 and output files are correct before treating it as
non-blocking).

- [ ] **Step 2: Inspect the real output**

```bash
find data/output/reference -iname "yakhyo_uz-wiki*"
```
Read one of the resulting `.txt` files and confirm it contains real, clean Uzbek
Wikipedia prose (no HTML tags, no wikitext markup residue).

- [ ] **Step 3: Confirm resumability works**

Run the exact same command again:
```bash
docker compose run --rm ufl ufl fetch-hf yakhyo/uz-wiki --split train --category reference --limit 50
```
Expected: since `--limit 50` was already fully consumed and recorded as shard 1,
re-running with the same `--limit 50` should skip those same 50 rows (via the
recorded `last_shard` state) and immediately hit the limit with zero new rows
processed — verify by checking `data/hf_state/yakhyo_uz-wiki__train.sqlite3` shows
`last_shard >= 1` via:
```bash
docker compose run --rm ufl python -c "
from ufl.store.hf_state import HFFetchState
with HFFetchState('data/hf_state/yakhyo_uz-wiki__train.sqlite3') as s:
    print(s.get_last_shard('yakhyo/uz-wiki::train'))
"
```
Expected: `1`

- [ ] **Step 4: Clean up all test artifacts**

```bash
docker compose run --rm ufl ufl stats --list 2>&1 | grep "hf:yakhyo/uz-wiki"
```
For each printed path, remove it from the budget:
```bash
MSYS_NO_PATHCONV=1 docker compose run --rm ufl ufl stats --remove "hf:yakhyo/uz-wiki:train:shard-000001"
```
Then remove the output/report/state files:
```bash
rm -f data/output/reference/yakhyo_uz-wiki__train__shard-000001.txt
rm -f data/reports/yakhyo_uz-wiki__train__shard-000001.json
rm -rf data/hf_state
git status --short   # confirm clean — only intended code changes remain staged/committed
```

- [ ] **Step 5: If `UFL-Datas` override is active locally, verify output landed there instead**

```bash
ls "/c/Users/Oybek/Documents/Projects programming/StartUps/UFL-Datas/reference/"
```
If the override from Task 6 is in place, the shard file from Step 1 will have appeared
here instead of `data/output/reference/` — adjust the Step 4 cleanup paths accordingly
(clean up in whichever location the file actually landed).

---

## Task 9: Final full-suite check and push

**Files:** none

- [ ] **Step 1: Run the complete test suite one more time**

```bash
docker compose run --rm ufl python -m pytest tests/ -q
```
Expected: all tests pass (should now be the Task-4-baseline count + 4 (hf_state) +
4 (hf_dataset) + 3 (hf_pipeline) + 7 (cli_fetch_hf) = baseline + 18 new tests).

- [ ] **Step 2: Confirm working tree is clean**

```bash
git status --short
```
Expected: no output (everything committed across Tasks 1–7; Task 8 was
verification-only and already cleaned up in its own Step 4).

- [ ] **Step 3: Push**

```bash
git push origin main
```

- [ ] **Step 4: Report to the user (in Uzbek)**

Summarize: which 3 datasets are now fetchable, the exact commands to run each,
that `--stop-at-budget` is opt-in (off by default per their explicit request), and
that output now lands in `UFL-Datas` locally (category-subfoldered) once they've
copied `docker-compose.override.yml.example` to `docker-compose.override.yml`
(Task 6 already created the real one for them, so no action needed from them unless
they're on a different machine).
