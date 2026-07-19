# OCR-chiqindi token tozalash (`strip_garbage_tokens`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qator ichidagi OCR-chiqindi tokenlarni (obyektiv struktura-belgilarga asoslangan)
butun blokni tashlamasdan, faqat chiqindi qismini olib tashlash orqali tozalash — ham
kelajakdagi yig'ish (ingestion), ham mavjud korpusni retroaktiv (finalize-corpus).

**Architecture:** Yangi `strip_garbage_tokens(line: str) -> str` funksiyasi
`src/ufl/clean/quality.py`da. Ikki integratsiya nuqtasi: (1) `src/ufl/clean/apply.py`ning
`clean_paragraphs()` ichida, `to_latin`dan keyin va `is_uzbek`/`assess`dan oldin; (2)
`src/ufl/cli.py`ning `finalize-corpus` buyrug'iga 4-bosqich sifatida (dedup→PII→rename'dan
keyin), mavjud `.txt` fayllarni qatorma-qator tozalab qayta yozadi.

**Tech Stack:** Python (mavjud loyiha stack'i), pytest, Typer CLI, mavjud regex-asoslangan
heuristik uslub (`src/ufl/clean/quality.py`dagi `assess()` bilan bir xil falsafa).

Dizayn: [2026-07-19-ocr-garbage-token-scrub-design.md](../specs/2026-07-19-ocr-garbage-token-scrub-design.md).

---

### Task 1: `strip_garbage_tokens()` — `src/ufl/clean/quality.py`

**Files:**
- Modify: `src/ufl/clean/quality.py`
- Test: `tests/test_quality.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_quality.py` (append at end of file, update the import at top):

```python
from ufl.clean.quality import assess, strip_garbage_tokens
```

(replace the existing `from ufl.clean.quality import assess` line with the line above)

```python
def test_strip_garbage_tokens_removes_symbol_and_isolated_letters():
    line = "• kayta nshlaga1^ K r k -^."
    assert strip_garbage_tokens(line) == "kayta"


def test_strip_garbage_tokens_keeps_legit_digit_suffix_words():
    line = "Voqea 5-bet va 1991-yil haqida."
    assert strip_garbage_tokens(line) == "Voqea 5-bet va 1991-yil haqida."


def test_strip_garbage_tokens_keeps_apostrophe_words():
    line = "o'zbek tug'ilgan kitobxon."
    assert strip_garbage_tokens(line) == "o'zbek tug'ilgan kitobxon."


def test_strip_garbage_tokens_keeps_normal_punctuation():
    line = "Salom, do'stim! Qandaysiz? Yaxshi: rahmat."
    assert strip_garbage_tokens(line) == line


def test_strip_garbage_tokens_leaves_blank_line_unchanged():
    assert strip_garbage_tokens("") == ""
    assert strip_garbage_tokens("   ") == "   "


def test_strip_garbage_tokens_returns_empty_when_all_garbage():
    assert strip_garbage_tokens("• ^") == ""


def test_strip_garbage_tokens_removes_digit_letter_fusion_without_hyphen():
    line = "Bu nshlaga1 xato edi."
    assert strip_garbage_tokens(line) == "Bu xato edi."


def test_strip_garbage_tokens_keeps_standalone_numbers():
    line = "1. Birinchi band va 2. ikkinchi band."
    assert strip_garbage_tokens(line) == line
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose run --rm ufl python -m pytest tests/test_quality.py -v`

Expected: `ImportError: cannot import name 'strip_garbage_tokens' from 'ufl.clean.quality'`
(all 8 new tests error/fail for this reason; the 9 pre-existing `assess` tests still pass
once the import line itself doesn't crash collection — if the import error prevents the whole
file from collecting, ALL tests in the file will show as errored, which is still the correct
RED state for this step: it confirms the function doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Add to `src/ufl/clean/quality.py`, after the existing `assess()` function (at the end of the
file):

```python
_DIGIT_SUFFIX_WORDS = {
    "bet", "yil", "son", "hafta", "kun", "soat", "minut", "sekund",
    "yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
    "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
}
_ALLOWED_EXTRA_CHARS = set("'-.,!?:;()\"«»–—…")
_DIGIT_WORD_RE = re.compile(r"^(\d+)-([^\W\d_]+)$", re.UNICODE)


def _is_garbage_token(token: str) -> bool:
    if any(not (ch.isalpha() or ch.isdigit() or ch in _ALLOWED_EXTRA_CHARS) for ch in token):
        return True
    if len(token) == 1 and token.isalpha():
        return True
    has_digit = any(ch.isdigit() for ch in token)
    has_letter = any(ch.isalpha() for ch in token)
    if has_digit and has_letter:
        match = _DIGIT_WORD_RE.match(token)
        if match and match.group(2).lower() in _DIGIT_SUFFIX_WORDS:
            return False
        return True
    return False


def strip_garbage_tokens(line: str) -> str:
    """OCR-chiqindi tokenlarni (g'ayrioddiy ramz, izolyatsiyalangan yakka harf,
    raqam-harf yopishish) qatordan olib tashlaydi, qolganlarini bo'shliq bilan
    qayta birlashtiradi. Bo'sh/faqat-bo'shliq qator o'zgarishsiz qaytariladi."""
    if not line.strip():
        return line
    kept = [token for token in line.split() if not _is_garbage_token(token)]
    return " ".join(kept)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose run --rm ufl python -m pytest tests/test_quality.py -v`

Expected: all 17 tests pass (9 pre-existing `assess` tests + 8 new `strip_garbage_tokens`
tests).

- [ ] **Step 5: Commit**

```bash
git add src/ufl/clean/quality.py tests/test_quality.py
git commit -m "clean: strip_garbage_tokens - OCR-chiqindi tokenlarni qator darajasida tozalash"
```

---

### Task 2: `clean_paragraphs()` integratsiyasi — `src/ufl/clean/apply.py`

**Files:**
- Modify: `src/ufl/clean/apply.py`
- Test: `tests/test_clean_apply.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_clean_apply.py` (append at end of file):

```python
def test_clean_paragraphs_strips_ocr_garbage_but_keeps_paragraph():
    text = _UZBEK + "\n• kayta nshlaga1^ K r k -^."
    kept = _clean([text])
    assert len(kept) == 1
    assert "nshlaga1" not in kept[0]
    assert "•" not in kept[0]
    assert "kayta" in kept[0].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm ufl python -m pytest tests/test_clean_apply.py -v -k ocr_garbage`

Expected: FAIL — `assert "nshlaga1" not in kept[0]` fails because `nshlaga1^` (with the `^`
stripped only by nothing yet — the whole garbage line currently passes through unchanged
inside the kept block).

- [ ] **Step 3: Write the implementation**

In `src/ufl/clean/apply.py`, update the import line:

```python
from ufl.clean.quality import assess, strip_garbage_tokens
```

Then in `clean_paragraphs()`, change:

```python
        raw = get_text(item)
        latin = to_latin(raw)

        if not is_uzbek(
```

to:

```python
        raw = get_text(item)
        latin = to_latin(raw)
        latin = "\n".join(strip_garbage_tokens(line) for line in latin.split("\n"))

        if not is_uzbek(
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose run --rm ufl python -m pytest tests/test_clean_apply.py -v`

Expected: all 5 tests pass (4 pre-existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add src/ufl/clean/apply.py tests/test_clean_apply.py
git commit -m "clean: clean_paragraphs endi strip_garbage_tokens'ni translitdan keyin chaqiradi"
```

---

### Task 3: `finalize-corpus` 4-bosqich (retroaktiv tozalash) — `src/ufl/cli.py`

**Files:**
- Modify: `src/ufl/cli.py`
- Test: `tests/test_cli_finalize_corpus.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli_finalize_corpus.py` (append at end of file):

```python
def test_apply_strips_ocr_garbage_tokens(tmp_path):
    config_path = _write_test_config(tmp_path)
    output_dir = tmp_path / "output"
    garbage_file = output_dir / "web_news" / "3_c.txt"
    _write(garbage_file, "Yaxshi gap bu yerda.\n• kayta nshlaga1^ K r k -^.\n")

    result = runner.invoke(app, ["finalize-corpus", "--apply", "--config", str(config_path)])

    assert result.exit_code == 0
    cleaned_text = garbage_file.read_text(encoding="utf-8")
    assert "nshlaga1" not in cleaned_text
    assert "•" not in cleaned_text
    assert "kayta" in cleaned_text
    assert "Yaxshi gap bu yerda." in cleaned_text


def test_dry_run_does_not_modify_ocr_garbage(tmp_path):
    config_path = _write_test_config(tmp_path)
    output_dir = tmp_path / "output"
    garbage_file = output_dir / "web_news" / "3_c.txt"
    original = "Yaxshi gap bu yerda.\n• kayta nshlaga1^ K r k -^.\n"
    _write(garbage_file, original)

    result = runner.invoke(app, ["finalize-corpus", "--config", str(config_path)])

    assert result.exit_code == 0
    assert garbage_file.read_text(encoding="utf-8") == original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose run --rm ufl python -m pytest tests/test_cli_finalize_corpus.py -v`

Expected: `test_apply_strips_ocr_garbage_tokens` FAILS (`nshlaga1` still present, since no
4th stage exists yet) — the CLI runs but only performs the existing 3 stages.
`test_dry_run_does_not_modify_ocr_garbage` PASSES already (nothing modifies the file in
dry-run today) — this is fine, it's a guard test for after the new stage is added.

- [ ] **Step 3: Write the implementation**

In `src/ufl/cli.py`, update the import line that currently reads:

```python
from ufl.clean.dedup import DeduplicationStore
```

to add the new import alongside it (insert a new line, keep existing alphabetical-ish
grouping):

```python
from ufl.clean.dedup import DeduplicationStore
from ufl.clean.quality import strip_garbage_tokens
```

Then in the `finalize_corpus` function, after the existing stage-3 block (HF nomini
yashirish) and its `unknown_datasets` warning loop, and BEFORE the final
`if not apply:` dry-run message, insert:

```python
        # 4. OCR-chiqindi tokenlarni tozalash (qator darajasida)
        denoise_files = 0
        denoise_lines = 0
        for txt_path in output_dir.glob("*/*.txt"):
            try:
                text = txt_path.read_text(encoding="utf-8")
            except OSError as exc:
                console.print(f"[red]O'qib bo'lmadi:[/red] {txt_path} — {exc}")
                continue
            lines = text.split("\n")
            cleaned_lines = [strip_garbage_tokens(line) for line in lines]
            changed_count = sum(1 for old, new in zip(lines, cleaned_lines) if old != new)
            if changed_count:
                denoise_files += 1
                denoise_lines += changed_count
                if apply:
                    try:
                        txt_path.write_text("\n".join(cleaned_lines), encoding="utf-8")
                    except OSError as exc:
                        console.print(f"[red]Yozib bo'lmadi:[/red] {txt_path} — {exc}")
        console.print(
            f"[bold]OCR-chiqindi tozalash:[/bold] {denoise_lines} qatordan chiqindi token "
            f"olib tashlan{'di' if apply else 'adi'} ({denoise_files} faylda)."
        )
```

Also update the function's docstring to mention the 4th stage:

```python
    """Yig'ilgan korpusni jamoaga topshirishdan oldin tayyorlaydi: global dedup,
    PII tozalash, HF dataset manbasini fayl nomidan yashirish, OCR-chiqindi
    tokenlarni tozalash.

    Bosqich tartibi muhim: dedup va PII HF fayllarni asl (dataset_slug asosidagi)
    nomi bilan aniqlaydi, shuning uchun rename doim OXIRIDA (3-bosqich) ishlaydi.
    OCR-chiqindi tozalash (4-bosqich) fayl nomiga bog'liq emas, shuning uchun
    rename'dan keyin yoki oldin ishlashi farqi yo'q — soddalik uchun oxirida."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose run --rm ufl python -m pytest tests/test_cli_finalize_corpus.py -v`

Expected: all 5 tests pass (3 pre-existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/ufl/cli.py tests/test_cli_finalize_corpus.py
git commit -m "cli: finalize-corpus'ga 4-bosqich - OCR-chiqindi tokenlarni retroaktiv tozalash"
```

---

### Task 4: Hujjatlash — `docs/DOCKER.md`

**Files:**
- Modify: `docs/DOCKER.md`

- [ ] **Step 1: Update the finalize-corpus section**

In `docs/DOCKER.md`, find this text (around line 447-452):

```markdown
## 10. Korpusni yakunlash (finalize-corpus)

Yig'ilgan korpusni (`UFL-Datas`) jamoaning umumiy training bazasiga topshirishdan oldin
ishga tushiriladi. Uch bosqich: global (korpus-bo'ylab) dedup, PII (email/telefon)
tozalash, HF dataset manbasini fayl nomidan yashirish. Dizayn:
[2026-07-18-finalize-corpus-design.md](superpowers/specs/2026-07-18-finalize-corpus-design.md).
```

Replace with:

```markdown
## 10. Korpusni yakunlash (finalize-corpus)

Yig'ilgan korpusni (`UFL-Datas`) jamoaning umumiy training bazasiga topshirishdan oldin
ishga tushiriladi. To'rt bosqich: global (korpus-bo'ylab) dedup, PII (email/telefon)
tozalash, HF dataset manbasini fayl nomidan yashirish, OCR-chiqindi tokenlarni tozalash.
Dizayn: [2026-07-18-finalize-corpus-design.md](superpowers/specs/2026-07-18-finalize-corpus-design.md),
[2026-07-19-ocr-garbage-token-scrub-design.md](superpowers/specs/2026-07-19-ocr-garbage-token-scrub-design.md).
```

Then find this text (around line 468-472):

```markdown
### 10.2 Bosqichlar va xavfsizlik

Bosqich tartibi qat'iy: **dedup → PII → HF nomini yashirish**. Rename doim oxirida
ishlaydi, chunki dedup va PII bosqichlari HF fayllarni asl (dataset_slug asosidagi)
nomi orqali aniqlaydi.
```

Replace with:

```markdown
### 10.2 Bosqichlar va xavfsizlik

Bosqich tartibi qat'iy: **dedup → PII → HF nomini yashirish → OCR-chiqindi tozalash**.
Rename dedup/PII'dan keyin ishlaydi, chunki ular HF fayllarni asl (dataset_slug asosidagi)
nomi orqali aniqlaydi. OCR-chiqindi tozalash fayl nomiga bog'liq emas (faqat kontentga
ishlaydi), shuning uchun oxirida turadi.

**OCR-chiqindi tozalash** (`strip_garbage_tokens`) — ziyouz/ziyonet'dan OCR orqali olingan
fayllarda uchraydigan qator ichidagi alohida chiqindi tokenlarni (g'ayrioddiy ramz,
izolyatsiyalangan yakka harf, raqam-harf yopishish) olib tashlaydi, butun qatorni/blokni
tashlamasdan. **Bilingan cheklov**: "so'zga o'xshab qolgan, lekin noto'g'ri harfli"
chiqindi (masalan `ertaklashvj`, `xapk`) bu usul bilan tutilmaydi — lug'at yoki til
modeli talab qiladi, hozircha qamrovdan tashqarida.
```

- [ ] **Step 2: Commit**

```bash
git add docs/DOCKER.md
git commit -m "docs: finalize-corpus'ga OCR-chiqindi tozalash (4-bosqich) hujjati"
```

---

### Yakuniy tekshiruv (barcha tasklardan keyin)

Barcha tasklar tugagach, to'liq test suite'ni ishga tushirish:

```bash
docker compose run --rm ufl python -m pytest
```

Expected: barcha testlar o'tadi (avvalgi + yangi ~15 test), regressiya yo'q.
