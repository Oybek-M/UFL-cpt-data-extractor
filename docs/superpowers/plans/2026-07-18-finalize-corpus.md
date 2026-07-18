# `ufl finalize-corpus` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `ufl finalize-corpus` CLI command that prepares the collected corpus in
`UFL-Datas` (mounted as `data/output` inside the container) for handoff to the team's shared
training dataset: global (cross-run) exact-hash deduplication, PII scrubbing, and hiding the
HuggingFace dataset origin from filenames.

**Architecture:** Three independent modules under a new `src/ufl/finalize/` package
(`dedup.py`, `pii.py`, `hf_rename.py`), wired together by one new Typer command in `cli.py`.
Default is dry-run (report only); `--apply` performs the actual file moves/edits/renames.
Stage order is fixed: dedup → PII → rename (rename must run last because dedup and PII need
the original HF shard filename pattern to still be present to identify files).

**Tech Stack:** Python 3.11+, existing `ufl` package conventions (Typer CLI, pydantic Config,
SQLite `Store`), pytest with `tmp_path` fixtures — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-18-finalize-corpus-design.md`

---

### Task 1: `Store` — `dedup_status` column + `mark_duplicate`

**Files:**
- Modify: `src/ufl/store/db.py`
- Test: `tests/test_store_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store_db.py`:

```python
def test_migrates_existing_db_missing_dedup_status_column(tmp_path):
    """Production ufl.db fayllari dedup_status ustunisiz yaratilgan — Store
    ularni ochganda buzmasdan ustunni qo'shishi kerak."""
    import sqlite3

    db_path = tmp_path / "ufl.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            format TEXT NOT NULL,
            char_count INTEGER NOT NULL DEFAULT 0,
            estimated_tokens INTEGER NOT NULL DEFAULT 0,
            exact_tokens INTEGER,
            total_blocks INTEGER NOT NULL DEFAULT 0,
            kept_blocks INTEGER NOT NULL DEFAULT 0,
            dropped_pct REAL NOT NULL DEFAULT 0.0,
            processed_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO books (path, category, format, char_count, estimated_tokens, "
        "total_blocks, kept_blocks, dropped_pct, processed_at) "
        "VALUES ('a.txt', 'books', 'txt', 10, 5, 1, 1, 0.0, '2026-01-01')"
    )
    conn.commit()
    conn.close()

    with Store(db_path) as store:
        assert store.book_count() == 1  # eski qator saqlanib qolgan
        columns = {row[1] for row in store._conn.execute("PRAGMA table_info(books)")}
        assert "dedup_status" in columns


def test_mark_duplicate_sets_status(tmp_path):
    with Store(tmp_path / "ufl.db") as store:
        store.record_book(_make_record(path="a.txt"))
        store.mark_duplicate("a.txt")
        cur = store._conn.execute("SELECT dedup_status FROM books WHERE path = ?", ("a.txt",))
        assert cur.fetchone()[0] == "duplicate"


def test_collected_tokens_by_category_excludes_duplicates(tmp_path):
    with Store(tmp_path / "ufl.db") as store:
        store.record_book(_make_record(path="a.txt", category="books"))
        store.record_book(_make_record(path="b.txt", category="books"))
        store.mark_duplicate("b.txt")

        totals = store.collected_tokens_by_category()

        assert totals["books"] == 110  # faqat a.txt (b.txt dublikat deb belgilangan)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_store_db.py -v -k "migrates_existing or mark_duplicate or excludes_duplicates"`
Expected: FAIL — `AttributeError: 'Store' object has no attribute 'mark_duplicate'` (first two),
and the third fails because `dedup_status` filter doesn't exist yet so `b.txt`'s tokens are
still counted.

- [ ] **Step 3: Implement the migration and new method**

In `src/ufl/store/db.py`, modify `__init__` and add methods:

```python
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # WAL: bir nechta jarayon (masalan parallel `ufl fetch-hf`) bir vaqtda
        # yozganda "database is locked" xatosini kamaytiradi (o'qish yozishni bloklamaydi).
        self._conn = sqlite3.connect(str(self._db_path), timeout=30.0)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)
        self._migrate_schema()
        self._conn.commit()

    def _migrate_schema(self) -> None:
        """Eski (production) ufl.db fayllari dedup_status ustunisiz yaratilgan —
        buzmasdan qo'shib qo'yamiz."""
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(books)")}
        if "dedup_status" not in columns:
            self._conn.execute("ALTER TABLE books ADD COLUMN dedup_status TEXT")
```

Add a new method (place after `record_book`):

```python
    def mark_duplicate(self, path: str) -> None:
        self._conn.execute(
            "UPDATE books SET dedup_status = 'duplicate' WHERE path = ?", (path,)
        )
        self._conn.commit()
```

Modify `collected_tokens_by_category`:

```python
    def collected_tokens_by_category(self) -> dict[str, int]:
        cur = self._conn.execute(
            "SELECT category, SUM(COALESCE(exact_tokens, estimated_tokens)) FROM books "
            "WHERE dedup_status IS NULL GROUP BY category"
        )
        return {category: total or 0 for category, total in cur.fetchall()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_store_db.py -v`
Expected: All PASS (including pre-existing tests — migration must not break them).

- [ ] **Step 5: Commit**

```bash
git add src/ufl/store/db.py tests/test_store_db.py
git commit -m "store: dedup_status ustuni va mark_duplicate (finalize-corpus uchun)"
```

---

### Task 2: `src/ufl/finalize/hf_rename.py` — HF dataset alias va fayl nomi hisoblash

**Files:**
- Create: `src/ufl/finalize/__init__.py` (bo'sh package marker)
- Create: `src/ufl/finalize/hf_rename.py`
- Test: `tests/test_finalize_hf_rename.py`

- [ ] **Step 1: Create the empty package marker**

```bash
touch "src/ufl/finalize/__init__.py"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_finalize_hf_rename.py`:

```python
"""HF dataset manbasini fayl nomidan yashirish — dataset_slug (masalan
'tahrirchi_uz-crawl') o'rniga generic alias ('corpus-a') qo'yiladi, split va
shard raqami saqlanib qoladi."""

from ufl.finalize.hf_rename import (
    match_hf_shard_filename,
    renamed_filename,
    source_path_for_filename,
)


def test_match_recognizes_known_dataset_shard_filename():
    match = match_hf_shard_filename("tahrirchi_uz-crawl__news__shard-000001.txt")
    assert match is not None
    assert match.dataset_id == "tahrirchi/uz-crawl"
    assert match.split == "news"
    assert match.shard == "000001"


def test_match_handles_split_names_containing_underscores():
    """'telegram_blogs' split nomining o'zida bitta pastki chiziq bor —
    slug/split/shard ajratish shu holatda ham to'g'ri ishlashi kerak."""
    match = match_hf_shard_filename("tahrirchi_uz-crawl__telegram_blogs__shard-000242.txt")
    assert match is not None
    assert match.dataset_id == "tahrirchi/uz-crawl"
    assert match.split == "telegram_blogs"
    assert match.shard == "000242"


def test_match_returns_none_for_unknown_dataset_but_reports_slug():
    match = match_hf_shard_filename("boshqa_dataset__train__shard-000001.txt")
    assert match is not None
    assert match.dataset_id is None
    assert match.slug == "boshqa_dataset"


def test_match_returns_none_for_non_shard_filename():
    """ziyouz uslubidagi fayl (id_slug.txt) HF shard naqshiga mos kelmaydi."""
    assert match_hf_shard_filename("10763_hamza-hakimzoda-niyoziy.txt") is None


def test_source_path_for_filename_known_dataset():
    path = source_path_for_filename("tahrirchi_uz-books-v2__lat__shard-000003.txt")
    assert path == "hf:tahrirchi/uz-books-v2:lat:shard-000003"


def test_source_path_for_filename_unknown_dataset_returns_none():
    assert source_path_for_filename("boshqa_dataset__train__shard-000001.txt") is None


def test_source_path_for_filename_non_shard_returns_none():
    assert source_path_for_filename("10763_hamza-hakimzoda-niyoziy.txt") is None


def test_renamed_filename_strips_dataset_name_keeps_split_and_shard():
    assert (
        renamed_filename("tahrirchi_uz-crawl__news__shard-000001.txt")
        == "corpus-a__news__shard-000001.txt"
    )


def test_renamed_filename_unknown_dataset_returns_none():
    assert renamed_filename("boshqa_dataset__train__shard-000001.txt") is None


def test_renamed_filename_non_shard_returns_none():
    assert renamed_filename("10763_hamza-hakimzoda-niyoziy.txt") is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_finalize_hf_rename.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ufl.finalize.hf_rename'`

- [ ] **Step 4: Implement**

Create `src/ufl/finalize/hf_rename.py`:

```python
"""HF (HuggingFace) dataset manbasini fayl nomidan yashirish.

fetch-hf shardlarni `{dataset_slug}__{split}__shard-{N}.txt` nomida yozadi
(masalan "tahrirchi_uz-crawl__news__shard-000001.txt") — bu HF va tashkilot
nomini fosh qiladi. Bu modul dataset_slug qismini generic alias bilan
almashtiradi, split va shard raqamini saqlab qoladi.

Manba: docs/superpowers/specs/2026-07-18-finalize-corpus-design.md
Xaritada yo'q dataset uchun None qaytariladi (chaqiruvchi tomon o'tkazib
yuborishi va ogohlantirishi kerak — hech qachon taxminiy alias yaratilmaydi,
"shubha bo'lsa tashla" tamoyili, xuddi ziyouz/category_map.py'dagi kabi).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ufl.ingest.hf_dataset import dataset_slug

DATASET_ALIAS: dict[str, str] = {
    "tahrirchi/uz-crawl": "corpus-a",
    "tahrirchi/uz-books-v2": "corpus-b",
    "yakhyo/uz-wiki": "corpus-c",
}

_SLUG_TO_DATASET_ID: dict[str, str] = {
    dataset_slug(dataset_id): dataset_id for dataset_id in DATASET_ALIAS
}

_SHARD_FILENAME_RE = re.compile(r"^(?P<slug>.+)__(?P<split>.+)__shard-(?P<shard>\d+)\.txt$")


@dataclass
class HfShardMatch:
    dataset_id: str | None  # None — slug DATASET_ALIAS'da topilmadi
    slug: str
    split: str
    shard: str


def match_hf_shard_filename(filename: str) -> HfShardMatch | None:
    """Fayl nomi HF shard naqshiga (`{slug}__{split}__shard-{N}.txt`) mos
    kelmasa None. Mos kelsa, lekin slug noma'lum bo'lsa dataset_id=None
    (chaqiruvchi `match.slug` orqali ogohlantirishi mumkin)."""
    match = _SHARD_FILENAME_RE.match(filename)
    if match is None:
        return None
    slug = match.group("slug")
    return HfShardMatch(
        dataset_id=_SLUG_TO_DATASET_ID.get(slug),
        slug=slug,
        split=match.group("split"),
        shard=match.group("shard"),
    )


def source_path_for_filename(filename: str) -> str | None:
    """Fayl nomidan ufl.db'dagi `path` qiymatini (`hf:{dataset_id}:{split}:
    shard-{N}`) hisoblaydi. Mos kelmasa yoki dataset noma'lum bo'lsa None."""
    match = match_hf_shard_filename(filename)
    if match is None or match.dataset_id is None:
        return None
    return f"hf:{match.dataset_id}:{match.split}:shard-{match.shard}"


def renamed_filename(filename: str) -> str | None:
    """De-branded fayl nomini qaytaradi (dataset_slug o'rniga alias, split va
    shard saqlanadi). Mos kelmasa yoki dataset noma'lum bo'lsa None."""
    match = match_hf_shard_filename(filename)
    if match is None or match.dataset_id is None:
        return None
    alias = DATASET_ALIAS[match.dataset_id]
    return f"{alias}__{match.split}__shard-{match.shard}.txt"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_finalize_hf_rename.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/ufl/finalize/__init__.py src/ufl/finalize/hf_rename.py tests/test_finalize_hf_rename.py
git commit -m "finalize: HF dataset alias va fayl nomi hisoblash (hf_rename.py)"
```

---

### Task 3: `src/ufl/finalize/dedup.py` — global (korpus-bo'ylab) dedup

**Files:**
- Create: `src/ufl/finalize/dedup.py`
- Test: `tests/test_finalize_dedup.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_finalize_dedup.py`:

```python
"""Global (korpus-bo'ylab) exact-hash dedup — ingestion paytidagi dedup
(clean/dedup.py) faqat bitta CLI ishga tushirish doirasida ishlaydi; bu modul
butun data/output/ papkasi bo'ylab (turli sanalar/manbalardan) takrorlarni
topadi."""

from pathlib import Path

from ufl.finalize.dedup import find_duplicate_groups, infer_source_path, quarantine_duplicates
from ufl.store.db import BookRecord, Store


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_find_duplicate_groups_detects_identical_content_across_categories(tmp_path):
    output_dir = tmp_path / "output"
    _write(output_dir / "books" / "1_kitob-a.txt", "Bir xil matn shu yerda.")
    _write(output_dir / "reference" / "2_kitob-b.txt", "Bir xil matn shu yerda.")
    _write(output_dir / "books" / "3_boshqa.txt", "Butunlay boshqa matn.")

    groups = find_duplicate_groups(output_dir)

    assert len(groups) == 1
    assert groups[0].kept.name == "1_kitob-a.txt"
    assert [p.name for p in groups[0].duplicates] == ["2_kitob-b.txt"]


def test_find_duplicate_groups_ignores_whitespace_case_differences(tmp_path):
    output_dir = tmp_path / "output"
    _write(output_dir / "books" / "1_a.txt", "Salom   Dunyo")
    _write(output_dir / "books" / "2_b.txt", "salom dunyo")

    groups = find_duplicate_groups(output_dir)

    assert len(groups) == 1


def test_find_duplicate_groups_returns_empty_when_no_duplicates(tmp_path):
    output_dir = tmp_path / "output"
    _write(output_dir / "books" / "1_a.txt", "Birinchi matn.")
    _write(output_dir / "books" / "2_b.txt", "Ikkinchi matn.")

    assert find_duplicate_groups(output_dir) == []


def test_infer_source_path_ziyouz_style_filename():
    assert infer_source_path("10763_hamza-hakimzoda-niyoziy.txt") == "ziyouz:10763"


def test_infer_source_path_hf_style_filename():
    assert (
        infer_source_path("tahrirchi_uz-crawl__news__shard-000001.txt")
        == "hf:tahrirchi/uz-crawl:news:shard-000001"
    )


def test_infer_source_path_unrecognized_filename_returns_none():
    assert infer_source_path("random-file-name.txt") is None


def test_quarantine_duplicates_moves_files_and_marks_store(tmp_path):
    output_dir = tmp_path / "output"
    rejected_dir = tmp_path / "rejected"
    kept = output_dir / "books" / "10763_kitob-a.txt"
    dup = output_dir / "books" / "10764_kitob-a-copy.txt"
    _write(kept, "Bir xil matn.")
    _write(dup, "Bir xil matn.")

    with Store(tmp_path / "ufl.db") as store:
        store.record_book(BookRecord(
            path="ziyouz:10764", category="books", format="txt", char_count=12,
            estimated_tokens=3, exact_tokens=None, total_blocks=1, kept_blocks=1, dropped_pct=0.0,
        ))
        groups = find_duplicate_groups(output_dir)

        moved = quarantine_duplicates(groups, rejected_dir=rejected_dir, store=store)

        assert moved == 1
        assert not dup.exists()
        assert (rejected_dir / "duplicates" / "books" / "10764_kitob-a-copy.txt").exists()
        assert kept.exists()  # birinchisi qoladi
        cur = store._conn.execute(
            "SELECT dedup_status FROM books WHERE path = ?", ("ziyouz:10764",)
        )
        assert cur.fetchone()[0] == "duplicate"


def test_quarantine_duplicates_skips_store_update_when_source_unrecognized(tmp_path):
    output_dir = tmp_path / "output"
    rejected_dir = tmp_path / "rejected"
    _write(output_dir / "books" / "random-a.txt", "Bir xil matn.")
    _write(output_dir / "books" / "random-b.txt", "Bir xil matn.")

    with Store(tmp_path / "ufl.db") as store:
        groups = find_duplicate_groups(output_dir)
        moved = quarantine_duplicates(groups, rejected_dir=rejected_dir, store=store)

    assert moved == 1  # DB yozuvi topilmasa ham fayl baribir ko'chiriladi
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_finalize_dedup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ufl.finalize.dedup'`

- [ ] **Step 3: Implement**

Create `src/ufl/finalize/dedup.py`:

```python
"""Global (korpus-bo'ylab) exact-hash deduplikatsiya.

Ingestion paytidagi dedup (`clean/dedup.py`) faqat bitta CLI ishga tushirish
doirasida ishlaydi. Bu modul butun `data/output/` papkasi bo'ylab (turli
sanalarda/manbalardan yig'ilgan fayllar orasida ham) aynan bir xil matnli
fayllarni topib, takrorlanganlarini `data/rejected/duplicates/`ga ko'chiradi
(o'chirilmaydi — qaytarib olish mumkin).

Manba: docs/superpowers/specs/2026-07-18-finalize-corpus-design.md
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ufl.finalize.hf_rename import source_path_for_filename
from ufl.store.db import Store

_WHITESPACE_RE = re.compile(r"\s+")
_ZIYOUZ_ID_RE = re.compile(r"^(\d+)_")


@dataclass
class DuplicateGroup:
    kept: Path
    duplicates: list[Path]


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def _hash_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return hashlib.sha1(_normalize(text).encode("utf-8")).hexdigest()


def find_duplicate_groups(output_dir: Path) -> list[DuplicateGroup]:
    """`output_dir`dagi barcha kategoriya papkalarida (`*/*.txt`) bir xil
    (normallashtirilgan) matnli fayllarni topadi. Har guruhda birinchi fayl
    (nomi bo'yicha saralangan) saqlanadi, qolganlari 'duplicates' hisoblanadi.
    O'qib bo'lmagan fayllar jim o'tkazib yuboriladi."""
    by_hash: dict[str, list[Path]] = {}
    for txt_path in sorted(Path(output_dir).glob("*/*.txt")):
        try:
            file_hash = _hash_file(txt_path)
        except OSError:
            continue
        by_hash.setdefault(file_hash, []).append(txt_path)

    return [
        DuplicateGroup(kept=paths[0], duplicates=paths[1:])
        for paths in by_hash.values()
        if len(paths) > 1
    ]


def infer_source_path(filename: str) -> str | None:
    """Fayl nomidan ufl.db'dagi `path` qiymatini taxmin qiladi (ziyouz yoki
    HF naqshi). Mos kelmasa None (chaqiruvchi DB yozuvini yangilamasdan
    o'tkazib yuborishi kerak)."""
    hf_path = source_path_for_filename(filename)
    if hf_path is not None:
        return hf_path
    match = _ZIYOUZ_ID_RE.match(filename)
    if match is not None:
        return f"ziyouz:{match.group(1)}"
    return None


def quarantine_duplicates(
    groups: list[DuplicateGroup], *, rejected_dir: Path, store: Store
) -> int:
    """Har bir guruhdagi dublikatlarni `rejected_dir/duplicates/{category}/`ga
    ko'chiradi va DB'da (topilsa) dedup_status='duplicate' deb belgilaydi.
    Ko'chirilgan fayllar sonini qaytaradi."""
    moved = 0
    for group in groups:
        for dup_path in group.duplicates:
            category = dup_path.parent.name
            dest_dir = Path(rejected_dir) / "duplicates" / category
            dest_dir.mkdir(parents=True, exist_ok=True)
            try:
                dup_path.replace(dest_dir / dup_path.name)
            except OSError:
                continue
            moved += 1
            source_path = infer_source_path(dup_path.name)
            if source_path is not None:
                store.mark_duplicate(source_path)
    return moved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_finalize_dedup.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ufl/finalize/dedup.py tests/test_finalize_dedup.py
git commit -m "finalize: global (korpus-bo'ylab) exact-hash dedup"
```

---

### Task 4: `src/ufl/finalize/pii.py` — PII (email/telefon) tozalash

**Files:**
- Create: `src/ufl/finalize/pii.py`
- Test: `tests/test_finalize_pii.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_finalize_pii.py`:

```python
"""PII (email, telefon) tozalash — CPT sifatiga tayyorlash uchun standart
qadam (Dolma/FineWeb amaliyoti)."""

from ufl.finalize.pii import scrub_pii


def test_scrub_pii_removes_email():
    cleaned, count = scrub_pii("Bog'lanish uchun: aliyev@example.com yozing.")
    assert "aliyev@example.com" not in cleaned
    assert count == 1


def test_scrub_pii_removes_international_uzbek_phone():
    cleaned, count = scrub_pii("Tel: +998 90 123 45 67 raqamiga qo'ng'iroq qiling.")
    assert "+998 90 123 45 67" not in cleaned
    assert count == 1


def test_scrub_pii_removes_local_uzbek_phone():
    cleaned, count = scrub_pii("Tel: 090 123 45 67.")
    assert "090 123 45 67" not in cleaned
    assert count == 1


def test_scrub_pii_removes_multiple_matches():
    cleaned, count = scrub_pii("a@b.com va +998901234567 va yana c@d.com")
    assert count == 3


def test_scrub_pii_leaves_normal_uzbek_text_untouched():
    text = "Bu oddiy o'zbekcha matn, hech qanday shaxsiy ma'lumot yo'q."
    cleaned, count = scrub_pii(text)
    assert cleaned == text
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_finalize_pii.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ufl.finalize.pii'`

- [ ] **Step 3: Implement**

Create `src/ufl/finalize/pii.py`:

```python
"""PII (shaxsiy ma'lumot: email, telefon) tozalash.

CPT (Continued Pre-Training) uchun standart amaliyot (Dolma, FineWeb — regex
asosida email/telefon maskalash). Kitob/gazeta/davlat hujjatlari kabi
user-generated bo'lmagan matnlarda kamdan-kam uchraydi (masalan kitob kolofoni
yoki gazeta muharriri aloqasi), lekin arzon va standart himoya qatlami.

Manba: docs/superpowers/specs/2026-07-18-finalize-corpus-design.md
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"\+998[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"
    r"|\b0\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b"
)


def scrub_pii(text: str) -> tuple[str, int]:
    """Email va telefon raqamlarini matndan olib tashlaydi. (tozalangan matn,
    olib tashlangan mosliklar soni) qaytaradi."""
    count = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return ""

    cleaned = _EMAIL_RE.sub(_replace, text)
    cleaned = _PHONE_RE.sub(_replace, cleaned)
    return cleaned, count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_finalize_pii.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ufl/finalize/pii.py tests/test_finalize_pii.py
git commit -m "finalize: PII (email/telefon) tozalash"
```

---

### Task 5: `ufl finalize-corpus` CLI buyrug'i

**Files:**
- Modify: `src/ufl/cli.py`
- Test: `tests/test_cli_finalize_corpus.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_finalize_corpus.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_finalize_corpus.py -v`
Expected: FAIL — `finalize-corpus` buyrug'i mavjud emas (Typer "No such command" xatosi).

- [ ] **Step 3: Implement the CLI command**

In `src/ufl/cli.py`, add imports (near existing finalize/ziyouz imports):

```python
from ufl.finalize.dedup import find_duplicate_groups, quarantine_duplicates
from ufl.finalize.hf_rename import match_hf_shard_filename, renamed_filename
from ufl.finalize.pii import scrub_pii
```

Add the new command (place after `fetch_ziyouz`):

```python
@app.command("finalize-corpus")
def finalize_corpus(
    apply: bool = typer.Option(
        False, "--apply", help="Haqiqiy o'zgarish qilish (standart: faqat hisobot, dry-run)"
    ),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
    """Yig'ilgan korpusni jamoaga topshirishdan oldin tayyorlaydi: global dedup,
    PII tozalash, HF dataset manbasini fayl nomidan yashirish.

    Bosqich tartibi muhim: dedup va PII HF fayllarni asl (dataset_slug asosidagi)
    nomi bilan aniqlaydi, shuning uchun rename doim OXIRIDA ishlaydi."""
    setup_logging()
    config = Config.load(config_path)
    output_dir = config.paths.output
    rejected_dir = config.paths.rejected

    with Store(config.paths.db) as store:
        # 1. Global dedup
        groups = find_duplicate_groups(output_dir)
        dup_file_count = sum(len(g.duplicates) for g in groups)
        console.print(
            f"[bold]Dedup:[/bold] {len(groups)} guruh, {dup_file_count} dublikat fayl topildi."
        )
        if apply and groups:
            moved = quarantine_duplicates(groups, rejected_dir=rejected_dir, store=store)
            console.print(f"  -> {moved} fayl {rejected_dir}/duplicates/ ga ko'chirildi.")

        # 2. PII tozalash
        pii_files = 0
        pii_hits = 0
        for txt_path in output_dir.glob("*/*.txt"):
            try:
                text = txt_path.read_text(encoding="utf-8")
            except OSError as exc:
                console.print(f"[red]O'qib bo'lmadi:[/red] {txt_path} — {exc}")
                continue
            cleaned, count = scrub_pii(text)
            if count:
                pii_files += 1
                pii_hits += count
                if apply:
                    try:
                        txt_path.write_text(cleaned, encoding="utf-8")
                    except OSError as exc:
                        console.print(f"[red]Yozib bo'lmadi:[/red] {txt_path} — {exc}")
        console.print(f"[bold]PII:[/bold] {pii_hits} ta topildi ({pii_files} faylda).")

        # 3. HF nomini yashirish (doim OXIRGI bosqich)
        renamed = 0
        unknown_datasets: set[str] = set()
        for txt_path in output_dir.glob("*/*.txt"):
            match = match_hf_shard_filename(txt_path.name)
            if match is None:
                continue
            if match.dataset_id is None:
                unknown_datasets.add(match.slug)
                continue
            new_name = renamed_filename(txt_path.name)
            if apply:
                try:
                    txt_path.replace(txt_path.parent / new_name)
                except OSError as exc:
                    console.print(f"[red]Qayta nomlab bo'lmadi:[/red] {txt_path} — {exc}")
                    continue
            renamed += 1
        console.print(f"[bold]HF nomini yashirish:[/bold] {renamed} fayl qayta nomlan{'di' if apply else 'adi'}.")
        for slug in sorted(unknown_datasets):
            console.print(
                f"[yellow]Noma'lum dataset:[/yellow] '{slug}' — hf_rename.py DATASET_ALIAS'ga qo'shing."
            )

    if not apply:
        console.print(
            "\n[yellow]Bu dry-run edi — hech narsa o'zgartirilmadi. "
            "--apply bilan qayta ishga tushiring.[/yellow]"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_finalize_corpus.py -v`
Expected: All PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest -q`
Expected: All PASS (no regressions in existing tests).

- [ ] **Step 6: Commit**

```bash
git add src/ufl/cli.py tests/test_cli_finalize_corpus.py
git commit -m "cli: ufl finalize-corpus buyrug'i (dedup + PII + HF nomini yashirish)"
```

---

### Task 6: Hujjatlar — `docs/DOCKER.md`

**Files:**
- Modify: `docs/DOCKER.md`

- [ ] **Step 1: Add a new section**

Append after the existing "## 9. ziyouz.com Kutubxonasidan ommaviy yig'ish" section:

```markdown
## 10. Korpusni yakunlash (finalize-corpus)

Yig'ilgan korpusni (`UFL-Datas`) jamoaning umumiy training bazasiga topshirishdan oldin
ishga tushiriladi. Uch bosqich: global (korpus-bo'ylab) dedup, PII (email/telefon)
tozalash, HF dataset manbasini fayl nomidan yashirish.

**Avval hisobot ko'rish uchun (hech narsa o'zgarmaydi):**

```bash
docker compose run --rm ufl ufl finalize-corpus
```

**Haqiqiy o'zgarish qilish uchun:**

```bash
docker compose run --rm ufl ufl finalize-corpus --apply
```

Yangi HF dataset qo'shilganda (masalan yangi `tahrirchi/...` yoki boshqa manba), uni
`src/ufl/finalize/hf_rename.py`dagi `DATASET_ALIAS` xaritasiga qo'shish kerak — aks holda
o'sha dataset fayllari "Noma'lum dataset" deb ogohlantiriladi va qayta nomlanmaydi
(xavfsizlik uchun — hech qachon taxminiy alias yaratilmaydi).

Dublikat fayllar o'chirilmaydi — `data/rejected/duplicates/{category}/`ga ko'chiriladi
(repo ichida, gitignored, kerak bo'lsa qaytarib olish mumkin).
```

- [ ] **Step 2: Commit**

```bash
git add docs/DOCKER.md
git commit -m "docs: finalize-corpus foydalanish qo'llanmasi"
```

---

## Yakuniy tekshiruv (implementatsiyadan keyin)

Barcha tasklar tugagach, real `UFL-Datas` ustida **faqat dry-run** bilan sinab ko'rish
(hech qachon avtomatik `--apply` bilan ishga tushirilmasin — foydalanuvchi o'zi ko'rib,
roziligini bergandan keyin):

```bash
docker compose run --rm ufl ufl finalize-corpus
```

Natijani foydalanuvchiga ko'rsatib, `--apply` bilan davom etish kerakligini so'rash kerak.
