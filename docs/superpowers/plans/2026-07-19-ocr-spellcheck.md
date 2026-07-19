# OCR-manba imlo tuzatish (`finalize-corpus` 5-bosqich) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **MUHIM:** har bir task tugagach, faqat o'sha task fayllarini emas, **to'liq test suite'ni** (`docker compose run --rm ufl python -m pytest`, bayroqsiz) ishga tushiring — bu loyihada avval bir marta cheklangan test-fayl tekshiruvi haqiqiy regressiyani o'tkazib yuborgan edi.

**Goal:** "kayta" kabi shaklan to'g'ri, lekin harfiy OCR-xatosi bo'lgan so'zlarni (ishonchli
lug'at + 5 ta ma'lum chalkashlik juftligi orqali) yuqori-ishonch bilan avtomatik
to'g'irlash, `finalize-corpus`ning yangi 5-bosqichi sifatida.

**Architecture:** Yangi `src/ufl/finalize/spellcheck.py` moduli: ishonchli lug'atni
faqat HF-manba fayllardan quradi, HF-manba bo'lmagan (ziyouz + boshqa web-manba) har
bir faylning har so'zini tekshiradi, 5 ta chalkashlik juftligi bo'yicha yagona nomzod
topilsagina to'g'irlaydi. Ixtiyoriy (`--use-minimax`) ikkinchi bosqich: qoidaga
asoslangan usul hal qila olmagan noyob so'zlarni MiniMax'ga (bir marta har bir so'z
uchun) yuboradi.

**Tech Stack:** Python (mavjud loyiha stack'i), pytest, Typer CLI, `httpx` (MiniMax
so'rovlari uchun, mavjud `src/ufl/crawl/minimax.py`dagi naqshga mos, lekin alohida,
yengil, holatsiz funksiya — `CrawlState`/`ai_batches` infratuzilmasisiz, chunki bu
bir martalik finalize-corpus ishga tushirish doirasida ishlaydi, uzoq muddatli
davom ettirish kerak emas).

Dizayn: [2026-07-19-ocr-spellcheck-design.md](../specs/2026-07-19-ocr-spellcheck-design.md).

---

### Task 1: `is_hf_sourced_filename()` — `src/ufl/finalize/hf_rename.py`

**Files:**
- Modify: `src/ufl/finalize/hf_rename.py`
- Test: `tests/test_finalize_hf_rename.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_finalize_hf_rename.py`:

```python
def test_is_hf_sourced_filename_original_naming():
    assert is_hf_sourced_filename("tahrirchi_uz-crawl__news__shard-000001.txt") is True


def test_is_hf_sourced_filename_renamed_alias():
    assert is_hf_sourced_filename("corpus-a__news__shard-000001.txt") is True
    assert is_hf_sourced_filename("corpus-b__lat__shard-000001.txt") is True
    assert is_hf_sourced_filename("corpus-c__train__shard-000001.txt") is True


def test_is_hf_sourced_filename_ziyouz_style_returns_false():
    assert is_hf_sourced_filename("10763_hamza-hakimzoda-niyoziy.txt") is False


def test_is_hf_sourced_filename_unrecognized_slug_returns_false():
    assert is_hf_sourced_filename("boshqa_dataset__train__shard-000001.txt") is False
```

Update the import block at the top of the test file (lines 5-9 currently read):
```python
from ufl.finalize.hf_rename import (
    match_hf_shard_filename,
    renamed_filename,
    source_path_for_filename,
)
```
change to:
```python
from ufl.finalize.hf_rename import (
    is_hf_sourced_filename,
    match_hf_shard_filename,
    renamed_filename,
    source_path_for_filename,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose run --rm ufl python -m pytest tests/test_finalize_hf_rename.py -v`

Expected: `ImportError: cannot import name 'is_hf_sourced_filename'`.

- [ ] **Step 3: Write the implementation**

In `src/ufl/finalize/hf_rename.py`, append this function at the end of the file:

```python
def is_hf_sourced_filename(filename: str) -> bool:
    """Fayl HF dataset'dan kelib chiqqanmi — hali qayta nomlanmagan (masalan
    tahrirchi_uz-crawl__...) yoki qayta nomlangan (corpus-a__...) holatlarning
    ikkalasini ham tekshiradi."""
    match = _SHARD_FILENAME_RE.match(filename)
    if match is None:
        return False
    slug = match.group("slug")
    return slug in _SLUG_TO_DATASET_ID or slug in DATASET_ALIAS.values()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose run --rm ufl python -m pytest tests/test_finalize_hf_rename.py -v`

Expected: all tests pass (existing 10 + 4 new = 14).

- [ ] **Step 5: Run the FULL test suite**

Run: `docker compose run --rm ufl python -m pytest`

Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/ufl/finalize/hf_rename.py tests/test_finalize_hf_rename.py
git commit -m "finalize: is_hf_sourced_filename - HF-manba faylni aniqlash (asl yoki qayta nomlangan)"
```

---

### Task 2: `spellcheck.py` — ishonchli lug'at va qoidaga asoslangan tuzatish

**Files:**
- Create: `src/ufl/finalize/spellcheck.py`
- Test: `tests/test_finalize_spellcheck.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_finalize_spellcheck.py`:

```python
"""OCR-manba imlo tuzatish: ishonchli lug'at (faqat HF-manba fayllardan) va
5 ta ma'lum chalkashlik juftligi bo'yicha yuqori-ishonchli tuzatish."""

from pathlib import Path

from ufl.finalize.spellcheck import build_trusted_dictionary, correct_line, find_correction


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_trusted_dictionary_only_uses_hf_sourced_files(tmp_path):
    output_dir = tmp_path / "output"
    _write(output_dir / "web_news" / "corpus-a__news__shard-000001.txt", "qayta ishlash kerak.")
    _write(output_dir / "web_news" / "10763_kimdir.txt", "kayta ishlash kerak edi.")

    trusted = build_trusted_dictionary(output_dir)

    assert "qayta" in trusted
    assert "kayta" not in trusted  # ziyouz-manba, lug'atga qo'shilmaydi


def test_build_trusted_dictionary_lowercases_and_strips_trailing_punct(tmp_path):
    output_dir = tmp_path / "output"
    _write(output_dir / "reference" / "corpus-c__train__shard-000001.txt", "Kitob, juda qiziq!")

    trusted = build_trusted_dictionary(output_dir)

    assert "kitob" in trusted
    assert "qiziq" in trusted
    assert "Kitob," not in trusted


def test_find_correction_fixes_known_confusion():
    trusted = {"qayta", "kitob", "salom"}
    assert find_correction("kayta", trusted) == "qayta"


def test_find_correction_preserves_capitalization():
    trusted = {"qayta"}
    assert find_correction("Kayta", trusted) == "Qayta"


def test_find_correction_returns_none_when_word_already_trusted():
    trusted = {"kitob"}
    assert find_correction("kitob", trusted) is None


def test_find_correction_returns_none_when_no_candidate_found():
    trusted = {"salom"}
    assert find_correction("nomavjud", trusted) is None


def test_find_correction_returns_none_when_ambiguous():
    # "kaqta" -> ("q","k") almashtirilsa "kaqta"->"kaqta" (o'zgarmaydi, chunki "q"
    # so'zda bor, "k"ga almashtirilsa "kaqta"->"kaqta"): ikkita mustaqil trusted so'z
    # topiladigan sun'iy holat quramiz.
    trusted = {"kaqta", "qaqta"}
    # "kakta" so'zidan: (q,k) juftligi bo'yicha "k"->"q" almashtirilsa har ikki "k"
    # birdek almashadi -> "qaqta" (trusted'da bor). Alohida boshqa juftlik orqali
    # "kaqta" ham topilib qolishi mumkin emas shu misolda, shuning uchun oddiyroq
    # sun'iy holat: ikkita turli juftlik ikkita turli trusted so'zga olib kelsin.
    trusted_ambiguous = {"gakta", "haqta"}
    assert find_correction("gaxta", trusted_ambiguous) is None


def test_correct_line_applies_correction_and_calls_callback():
    trusted = {"qayta", "kitob"}
    calls = []
    result = correct_line(
        "kayta kitob o'qidim.", trusted, on_correction=lambda old, new: calls.append((old, new))
    )
    assert result == "qayta kitob o'qidim."
    assert calls == [("kayta", "qayta")]


def test_correct_line_calls_on_unresolved_for_unfixable_words():
    trusted = {"kitob"}
    unresolved = []
    result = correct_line(
        "gubla kitob.", trusted, on_unresolved=lambda word: unresolved.append(word)
    )
    assert result == "gubla kitob."
    assert unresolved == ["gubla"]


def test_correct_line_leaves_blank_line_unchanged():
    assert correct_line("", {"kitob"}) == ""
    assert correct_line("   ", {"kitob"}) == "   "
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose run --rm ufl python -m pytest tests/test_finalize_spellcheck.py -v`

Expected: `ModuleNotFoundError: No module named 'ufl.finalize.spellcheck'`.

- [ ] **Step 3: Write the implementation**

Create `src/ufl/finalize/spellcheck.py`:

```python
"""OCR-manba imlo tuzatish: "kayta" kabi shaklan to'g'ri, lekin harfiy OCR-xatosi
bo'lgan so'zlarni ishonchli lug'at + ma'lum chalkashlik juftliklari orqali
yuqori-ishonch bilan tuzatadi.

Manba: docs/superpowers/specs/2026-07-19-ocr-spellcheck-design.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ufl.finalize.hf_rename import is_hf_sourced_filename

_CONFUSION_PAIRS: list[tuple[str, str]] = [
    ("q", "k"), ("g'", "g"), ("h", "x"), ("o'", "u"), ("i", "y"),
]
_TRAILING_PUNCT_CHARS = ".,!?:;)\"»"


def _split_trailing_punct(token: str) -> tuple[str, str]:
    end = len(token)
    while end > 0 and token[end - 1] in _TRAILING_PUNCT_CHARS:
        end -= 1
    return token[:end], token[end:]


def build_trusted_dictionary(output_dir: Path) -> set[str]:
    """HF-manba fayllardagi barcha (kichik harfli, tinish-belgisiz) so'zlarni
    to'playdi. Ziyouz va boshqa web-manba fayllar hisobga olinmaydi."""
    trusted: set[str] = set()
    for txt_path in sorted(Path(output_dir).glob("*/*.txt")):
        if not is_hf_sourced_filename(txt_path.name):
            continue
        try:
            text = txt_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.split("\n"):
            for token in line.split():
                core, _ = _split_trailing_punct(token.lower())
                if core:
                    trusted.add(core)
    return trusted


def find_correction(word: str, trusted: set[str]) -> str | None:
    """5 ta chalkashlik juftligi bo'yicha yagona ishonchli nomzodni qidiradi.
    So'z allaqachon lug'atda bo'lsa, yoki 0/2+ nomzod topilsa — None."""
    lower = word.lower()
    if not lower or lower in trusted:
        return None
    candidates: set[str] = set()
    for a, b in _CONFUSION_PAIRS:
        for src, dst in ((a, b), (b, a)):
            if src in lower:
                candidate = lower.replace(src, dst)
                if candidate != lower and candidate in trusted:
                    candidates.add(candidate)
    if len(candidates) != 1:
        return None
    corrected = next(iter(candidates))
    if word[:1].isupper():
        return corrected[:1].upper() + corrected[1:]
    return corrected


def correct_line(
    line: str,
    trusted: set[str],
    *,
    on_correction: Callable[[str, str], None] | None = None,
    on_unresolved: Callable[[str], None] | None = None,
) -> str:
    """Qatordagi har so'zni tekshiradi: ishonchli lug'atda bo'lsa tegilmaydi,
    yagona nomzod topilsa to'g'irlanadi (on_correction chaqiriladi), aks holda
    o'zgarishsiz qoladi (on_unresolved chaqiriladi, agar berilgan bo'lsa)."""
    if not line.strip():
        return line
    result = []
    for token in line.split():
        core, suffix = _split_trailing_punct(token)
        if not core or core.lower() in trusted:
            result.append(token)
            continue
        correction = find_correction(core, trusted)
        if correction is not None:
            corrected_token = correction + suffix
            if on_correction:
                on_correction(token, corrected_token)
            result.append(corrected_token)
        else:
            if on_unresolved:
                on_unresolved(core.lower())
            result.append(token)
    return " ".join(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose run --rm ufl python -m pytest tests/test_finalize_spellcheck.py -v`

Expected: all 10 tests pass. If `test_find_correction_returns_none_when_ambiguous` fails,
double check the trusted-set arithmetic by hand (this test's fixture is synthetic, not
real Uzbek text — its only purpose is to verify the "2+ candidates -> None" branch).

- [ ] **Step 5: Run the FULL test suite**

Run: `docker compose run --rm ufl python -m pytest`

Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/ufl/finalize/spellcheck.py tests/test_finalize_spellcheck.py
git commit -m "finalize: spellcheck.py - ishonchli lug'at va chalkashlik-juftlik asosidagi tuzatish"
```

---

### Task 3: MiniMax ixtiyoriy fallback — `src/ufl/finalize/spellcheck.py`

**Files:**
- Modify: `src/ufl/finalize/spellcheck.py`
- Test: `tests/test_finalize_spellcheck.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_finalize_spellcheck.py`. First add these imports at the top
(alongside the existing ones):

```python
from ufl.finalize.spellcheck import apply_known_corrections, query_minimax_corrections
```

Then append:

```python
class _FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def _minimax_body(corrections: dict) -> dict:
    import json

    return {"choices": [{"message": {"content": json.dumps({"corrections": corrections})}}]}


def test_query_minimax_corrections_returns_empty_without_api_key():
    corrections, calls = query_minimax_corrections(["gubla"], api_key="")
    assert corrections == {}
    assert calls == 0


def test_query_minimax_corrections_returns_empty_for_empty_word_list():
    corrections, calls = query_minimax_corrections([], api_key="fake-key")
    assert corrections == {}
    assert calls == 0


def test_query_minimax_corrections_parses_response():
    def fake_post(url, headers, json_body, timeout):
        return _FakeResponse(200, _minimax_body({"gubla": "gulla", "xyzabc": None}))

    corrections, calls = query_minimax_corrections(
        ["gubla", "xyzabc"], api_key="fake-key", post=fake_post
    )
    assert corrections == {"gubla": "gulla"}
    assert calls == 1


def test_query_minimax_corrections_batches_large_word_lists():
    call_log = []

    def fake_post(url, headers, json_body, timeout):
        call_log.append(json_body)
        return _FakeResponse(200, _minimax_body({}))

    words = [f"word{i}" for i in range(5)]
    _, calls = query_minimax_corrections(words, api_key="fake-key", post=fake_post, batch_size=2)

    assert calls == 3  # 5 so'z, batch_size=2 -> 3 so'rov (2+2+1)


def test_query_minimax_corrections_returns_empty_on_network_error():
    def fake_post(url, headers, json_body, timeout):
        raise ConnectionError("network down")

    corrections, calls = query_minimax_corrections(["gubla"], api_key="fake-key", post=fake_post)
    assert corrections == {}
    assert calls == 1  # urinish qilindi, lekin xato bo'ldi


def test_query_minimax_corrections_returns_empty_on_bad_status():
    def fake_post(url, headers, json_body, timeout):
        return _FakeResponse(401, {})

    corrections, calls = query_minimax_corrections(["gubla"], api_key="fake-key", post=fake_post)
    assert corrections == {}
    assert calls == 1


def test_apply_known_corrections_replaces_matching_words():
    corrections = {"gubla": "gulla"}
    calls = []
    result = apply_known_corrections(
        "Bu gubla, chiroyli.", corrections, on_correction=lambda old, new: calls.append((old, new))
    )
    assert result == "Bu Gulla, chiroyli."
    assert calls == [("gubla,", "Gulla,")]


def test_apply_known_corrections_leaves_unmatched_words_unchanged():
    result = apply_known_corrections("Bu kitob edi.", {"gubla": "gulla"})
    assert result == "Bu kitob edi."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose run --rm ufl python -m pytest tests/test_finalize_spellcheck.py -v`

Expected: `ImportError: cannot import name 'apply_known_corrections'` (and
`query_minimax_corrections`) — the new tests error, the 10 from Task 2 still pass.

- [ ] **Step 3: Write the implementation**

Append to `src/ufl/finalize/spellcheck.py`. First add these imports at the top of the
file (alongside the existing `from __future__ import annotations` etc.):

```python
import json
from typing import Any, Protocol
```

(the file already has `from pathlib import Path` and `from typing import Callable` —
just add `Any` and `Protocol` to that same `typing` import line instead of a
duplicate line, and add the `import json` line near the top with the other imports)

Then append these constants near the top (after `_TRAILING_PUNCT_CHARS`):

```python
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7-highspeed"
DEFAULT_MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"


class _PostResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


def _default_post(url: str, headers: dict[str, str], json_body: dict[str, Any], timeout: float) -> _PostResponse:
    import httpx

    return httpx.post(url, headers=headers, json=json_body, timeout=timeout)


def _first_json_object(text: str) -> dict:
    start = text.find("{")
    if start == -1:
        raise ValueError("Javobda JSON obyekt topilmadi")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise ValueError("Javobda to'liq JSON obyekt topilmadi")
```

Then append at the end of the file:

```python
def query_minimax_corrections(
    words: list[str],
    *,
    api_key: str,
    model: str = DEFAULT_MINIMAX_MODEL,
    url: str = DEFAULT_MINIMAX_URL,
    batch_size: int = 200,
    post: Any = None,
) -> tuple[dict[str, str], int]:
    """Qoidaga asoslangan usul hal qila olmagan noyob so'zlarni MiniMax'ga yuboradi.

    Qaytaradi: ({asl_so'z: tuzatilgan_so'z} lug'ati, yuborilgan so'rovlar soni).
    Kalitsiz, bo'sh ro'yxat, tarmoq xatosi yoki javobni tahlil qilib bo'lmasa —
    bo'sh lug'at (xavfsiz standart, so'z tuzatilmagan holda qoladi)."""
    if not words or not api_key:
        return {}, 0
    post_fn = post or _default_post
    corrections: dict[str, str] = {}
    call_count = 0
    for start in range(0, len(words), batch_size):
        chunk = words[start : start + batch_size]
        call_count += 1
        request_body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You correct likely OCR letter-confusion errors in Uzbek words.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": (
                                "Each word below is NOT found in a trusted Uzbek dictionary "
                                "and could not be auto-corrected by a simple rule. For each "
                                "word, if you are confident it is a single-letter OCR misread "
                                "of a real Uzbek word, return the corrected word. If not "
                                "confident, or the word looks like a proper noun/loanword, "
                                "return null. Return one JSON object: "
                                '{"corrections": {"word1": "fix1_or_null", ...}}'
                            ),
                            "words": chunk,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "stream": False,
            "max_completion_tokens": 2000,
            "temperature": 0.1,
        }
        try:
            response = post_fn(
                url,
                {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                request_body,
                60.0,
            )
        except Exception:  # noqa: BLE001 — tarmoq xatosi: so'z tuzatilmagan qoladi
            continue
        if response.status_code != 200:
            continue
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            decision = _first_json_object(content)
            chunk_corrections = decision.get("corrections", {})
        except Exception:  # noqa: BLE001
            continue
        corrections.update(
            {word: fix for word, fix in chunk_corrections.items() if isinstance(fix, str) and fix}
        )
    return corrections, call_count


def apply_known_corrections(
    line: str,
    corrections: dict[str, str],
    *,
    on_correction: Callable[[str, str], None] | None = None,
) -> str:
    """Tashqi manbadan (masalan MiniMax) olingan {asl: tuzatilgan} lug'atini
    qatorga qo'llaydi — chalkashlik-juftlik mantig'isiz, to'g'ridan-to'g'ri qidiruv."""
    if not line.strip():
        return line
    result = []
    for token in line.split():
        core, suffix = _split_trailing_punct(token)
        fix = corrections.get(core.lower())
        if fix:
            corrected_token = (fix[:1].upper() + fix[1:] if token[:1].isupper() else fix) + suffix
            if on_correction:
                on_correction(token, corrected_token)
            result.append(corrected_token)
        else:
            result.append(token)
    return " ".join(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose run --rm ufl python -m pytest tests/test_finalize_spellcheck.py -v`

Expected: all 18 tests pass (10 from Task 2 + 8 new).

- [ ] **Step 5: Run the FULL test suite**

Run: `docker compose run --rm ufl python -m pytest`

Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/ufl/finalize/spellcheck.py tests/test_finalize_spellcheck.py
git commit -m "finalize: MiniMax ixtiyoriy fallback (query_minimax_corrections, apply_known_corrections)"
```

---

### Task 4: `finalize-corpus` 5-bosqich CLI integratsiyasi — `src/ufl/cli.py`

**Files:**
- Modify: `src/ufl/cli.py`
- Test: `tests/test_cli_finalize_corpus.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_finalize_corpus.py`:

```python
def test_apply_corrects_known_ocr_confusion(tmp_path):
    config_path = _write_test_config(tmp_path)
    output_dir = tmp_path / "output"
    _write(output_dir / "web_news" / "corpus-a__news__shard-000001.txt", "qayta ishlash kerak.\n")
    ziyouz_file = output_dir / "web_news" / "10763_kimdir.txt"
    _write(ziyouz_file, "Bu kayta ishlash kerak edi.\n")

    result = runner.invoke(app, ["finalize-corpus", "--apply", "--config", str(config_path)])

    assert result.exit_code == 0
    corrected = ziyouz_file.read_text(encoding="utf-8")
    assert "qayta" in corrected
    assert "kayta" not in corrected
    assert "Tuzatildi" in result.output


def test_dry_run_does_not_modify_spelling(tmp_path):
    config_path = _write_test_config(tmp_path)
    output_dir = tmp_path / "output"
    _write(output_dir / "web_news" / "corpus-a__news__shard-000001.txt", "qayta ishlash kerak.\n")
    ziyouz_file = output_dir / "web_news" / "10763_kimdir.txt"
    original = "Bu kayta ishlash kerak edi.\n"
    _write(ziyouz_file, original)

    result = runner.invoke(app, ["finalize-corpus", "--config", str(config_path)])

    assert result.exit_code == 0
    assert ziyouz_file.read_text(encoding="utf-8") == original


def test_apply_does_not_touch_hf_sourced_files(tmp_path):
    config_path = _write_test_config(tmp_path)
    output_dir = tmp_path / "output"
    hf_file = output_dir / "web_news" / "corpus-a__news__shard-000001.txt"
    original = "Bu kayta ishlanmagan HF matni (o'zgarishsiz qolishi kerak).\n"
    _write(hf_file, original)

    result = runner.invoke(app, ["finalize-corpus", "--apply", "--config", str(config_path)])

    assert result.exit_code == 0
    assert hf_file.read_text(encoding="utf-8") == original  # HF fayllarga tegilmaydi


def test_apply_without_minimax_flag_does_not_call_minimax(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    output_dir = tmp_path / "output"
    _write(output_dir / "web_news" / "corpus-a__news__shard-000001.txt", "kitob juda yaxshi.\n")
    _write(output_dir / "web_news" / "10763_kimdir.txt", "Bu nomavjudsoz.\n")

    called = []
    monkeypatch.setattr(
        cli_module, "query_minimax_corrections", lambda *a, **kw: called.append(1) or ({}, 0)
    )

    result = runner.invoke(app, ["finalize-corpus", "--apply", "--config", str(config_path)])

    assert result.exit_code == 0
    assert called == []  # --use-minimax berilmagani uchun chaqirilmagan
```

At the top of `tests/test_cli_finalize_corpus.py`, check the existing imports — if
`ufl.cli` is not already imported as `cli_module`, add this line alongside the
existing `from ufl.cli import app` line:
```python
import ufl.cli as cli_module
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose run --rm ufl python -m pytest tests/test_cli_finalize_corpus.py -v`

Expected: `test_apply_corrects_known_ocr_confusion` FAILS (no 5th stage exists yet, so
"kayta" is never corrected and "Tuzatildi" never appears in output). The other new
tests may pass vacuously (nothing to break yet) — that's fine, they're forward-looking
guards.

- [ ] **Step 3: Write the implementation**

In `src/ufl/cli.py`:

(a) Add these imports. `src/ufl/cli.py` line 18 currently reads:
```python
from ufl.clean.quality import strip_garbage_tokens
```
Leave that line untouched. `src/ufl/cli.py` line 27 currently reads:
```python
from ufl.finalize.hf_rename import match_hf_shard_filename, renamed_filename
```
Replace that ONE line with:
```python
from ufl.finalize.hf_rename import is_hf_sourced_filename, match_hf_shard_filename, renamed_filename
```
Then add a new import line right after it (there is no existing
`from ufl.finalize.spellcheck import ...` line — this is a brand new module):
```python
from ufl.finalize.spellcheck import (
    apply_known_corrections,
    build_trusted_dictionary,
    correct_line,
    query_minimax_corrections,
)
```

(b) Add a new CLI option to the `finalize_corpus` function signature. This exact
`config_path` line appears multiple times in the file (once per CLI command), so
anchor on the full `finalize_corpus` signature, which is unique. Find (currently
lines 688-694):
```python
@app.command("finalize-corpus")
def finalize_corpus(
    apply: bool = typer.Option(
        False, "--apply", help="Haqiqiy o'zgarish qilish (standart: faqat hisobot, dry-run)"
    ),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
```
Change to:
```python
@app.command("finalize-corpus")
def finalize_corpus(
    apply: bool = typer.Option(
        False, "--apply", help="Haqiqiy o'zgarish qilish (standart: faqat hisobot, dry-run)"
    ),
    use_minimax: bool = typer.Option(
        False, "--use-minimax",
        help="Qoidaga asoslangan usul hal qila olmagan so'zlar uchun MiniMax'dan ham foydalanish (standart: o'chiq, xarajat uchun)",
    ),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
```

(c) Add the new 5th stage. Find the existing 4th stage block (OCR-chiqindi
tokenlarni tozalash) and its closing `console.print(f"[bold]OCR-chiqindi tozalash:..."`
line, then find the `if not apply:` block that follows it (still OUTSIDE the
`with Store(...) as store:` block). Insert the new stage AFTER the stage-4
`console.print` call and BEFORE the `if not apply:` line (i.e. still INSIDE the
`with Store(...) as store:` block):

```python
        # 5. OCR-manba imlo tuzatish (ishonchli lug'at, faqat HF-manba BO'LMAGAN fayllar)
        trusted = build_trusted_dictionary(output_dir)
        spell_files = 0
        spell_corrections = 0
        unresolved_words: set[str] = set()

        def _log_spell_correction(original: str, corrected: str, txt_path: Path, line_number: int) -> None:
            console.print(
                f"[bold]Tuzatildi:[/bold] {original} -> {corrected} "
                f"(fayl: {txt_path}, qator: {line_number})"
            )

        file_new_lines: dict[Path, list[str]] = {}
        for txt_path in output_dir.glob("*/*.txt"):
            if is_hf_sourced_filename(txt_path.name):
                continue
            try:
                text = txt_path.read_text(encoding="utf-8")
            except OSError as exc:
                console.print(f"[red]O'qib bo'lmadi:[/red] {txt_path} — {exc}")
                continue
            lines = text.split("\n")
            new_lines: list[str] = []
            file_had_correction = False
            for line_number, line in enumerate(lines, start=1):
                correction_count_before = spell_corrections

                def _on_correction(original: str, corrected: str, _path=txt_path, _line_number=line_number) -> None:
                    nonlocal spell_corrections
                    spell_corrections += 1
                    _log_spell_correction(original, corrected, _path, _line_number)

                new_line = correct_line(
                    line,
                    trusted,
                    on_correction=_on_correction,
                    on_unresolved=unresolved_words.add,
                )
                if spell_corrections != correction_count_before:
                    file_had_correction = True
                new_lines.append(new_line)
            if file_had_correction:
                spell_files += 1
                file_new_lines[txt_path] = new_lines
                if apply:
                    try:
                        txt_path.write_text("\n".join(new_lines), encoding="utf-8")
                    except OSError as exc:
                        console.print(f"[red]Yozib bo'lmadi:[/red] {txt_path} — {exc}")

        minimax_calls = 0
        if use_minimax and unresolved_words:
            api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
            minimax_corrections, minimax_calls = query_minimax_corrections(
                sorted(unresolved_words), api_key=api_key
            )
            if minimax_corrections:
                for txt_path in output_dir.glob("*/*.txt"):
                    if is_hf_sourced_filename(txt_path.name):
                        continue
                    try:
                        text = txt_path.read_text(encoding="utf-8")
                    except OSError as exc:
                        console.print(f"[red]O'qib bo'lmadi:[/red] {txt_path} — {exc}")
                        continue
                    lines = text.split("\n")
                    new_lines = []
                    file_had_correction = False
                    for line_number, line in enumerate(lines, start=1):
                        correction_count_before = spell_corrections

                        def _on_minimax_correction(
                            original: str, corrected: str, _path=txt_path, _line_number=line_number
                        ) -> None:
                            nonlocal spell_corrections
                            spell_corrections += 1
                            console.print(
                                f"[bold]Tuzatildi (MiniMax):[/bold] {original} -> {corrected} "
                                f"(fayl: {_path}, qator: {_line_number})"
                            )

                        new_line = apply_known_corrections(
                            line, minimax_corrections, on_correction=_on_minimax_correction
                        )
                        if spell_corrections != correction_count_before:
                            file_had_correction = True
                        new_lines.append(new_line)
                    if file_had_correction:
                        spell_files += 1
                        if apply:
                            try:
                                txt_path.write_text("\n".join(new_lines), encoding="utf-8")
                            except OSError as exc:
                                console.print(f"[red]Yozib bo'lmadi:[/red] {txt_path} — {exc}")

        console.print(
            f"[bold]Imlo tuzatish:[/bold] {spell_corrections} ta so'z tuzatil"
            f"{'di' if apply else 'adi'} ({spell_files} faylda). "
            f"Qoldiq (hal qilinmagan) noyob so'z: {len(unresolved_words)}."
        )
        if use_minimax:
            console.print(f"[bold]MiniMax so'rovlari:[/bold] {minimax_calls} ta.")
```

(d) Update the function's docstring once more to mention the 5th stage — find:
```python
    """Yig'ilgan korpusni jamoaga topshirishdan oldin tayyorlaydi: global dedup,
    PII tozalash, HF dataset manbasini fayl nomidan yashirish, OCR-chiqindi
    tokenlarni tozalash.
```
change to:
```python
    """Yig'ilgan korpusni jamoaga topshirishdan oldin tayyorlaydi: global dedup,
    PII tozalash, HF dataset manbasini fayl nomidan yashirish, OCR-chiqindi
    tokenlarni tozalash, OCR-manba imlo xatolarini tuzatish.
```

**Muhim eslatma implementatorga**: yuqoridagi kod ichma-ich `for txt_path in
output_dir.glob(...)` tsiklini ikki marta (rule-based bosqich + ixtiyoriy MiniMax
bosqichi) takrorlaydi — bu qasddan, MiniMax faqat kamdan-kam holatlarda (bayroq
yoqilganda va hal qilinmagan so'z bo'lganda) ishlaydi, shuning uchun ikkinchi marta
korpusni skanerlash faqat shu holatlarda sodir bo'ladi (odatiy holatda faqat bitta
skanerlash). Bu darajada murakkablikni soddalashtirishga urinmang — testlar aynan
shu ikki bosqichli xatti-harakatni tekshiradi.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose run --rm ufl python -m pytest tests/test_cli_finalize_corpus.py -v`

Expected: all tests pass (previous 7 + 4 new = 11).

- [ ] **Step 5: Run the FULL test suite**

Run: `docker compose run --rm ufl python -m pytest`

Expected: no new failures. Pay special attention to `tests/test_cli_fetch_hf.py` and
any other test files NOT directly related to this change — this project has already
had one real regression slip through task-scoped testing once this session; do not
skip this step.

- [ ] **Step 6: Commit**

```bash
git add src/ufl/cli.py tests/test_cli_finalize_corpus.py
git commit -m "cli: finalize-corpus'ga 5-bosqich - OCR-manba imlo tuzatish (+ ixtiyoriy MiniMax)"
```

---

### Task 5: Hujjatlash — `docs/DOCKER.md`

**Files:**
- Modify: `docs/DOCKER.md`

- [ ] **Step 1: Update the finalize-corpus section**

In `docs/DOCKER.md`, find (the intro paragraph updated by the previous OCR-denoise
feature):

```markdown
Yig'ilgan korpusni (`UFL-Datas`) jamoaning umumiy training bazasiga topshirishdan oldin
ishga tushiriladi. To'rt bosqich: global (korpus-bo'ylab) dedup, PII (email/telefon)
tozalash, HF dataset manbasini fayl nomidan yashirish, OCR-chiqindi tokenlarni tozalash.
Dizayn: [2026-07-18-finalize-corpus-design.md](superpowers/specs/2026-07-18-finalize-corpus-design.md),
[2026-07-19-ocr-garbage-token-scrub-design.md](superpowers/specs/2026-07-19-ocr-garbage-token-scrub-design.md).
```

Replace with:

```markdown
Yig'ilgan korpusni (`UFL-Datas`) jamoaning umumiy training bazasiga topshirishdan oldin
ishga tushiriladi. Besh bosqich: global (korpus-bo'ylab) dedup, PII (email/telefon)
tozalash, HF dataset manbasini fayl nomidan yashirish, OCR-chiqindi tokenlarni tozalash,
OCR-manba imlo xatolarini tuzatish.
Dizayn: [2026-07-18-finalize-corpus-design.md](superpowers/specs/2026-07-18-finalize-corpus-design.md),
[2026-07-19-ocr-garbage-token-scrub-design.md](superpowers/specs/2026-07-19-ocr-garbage-token-scrub-design.md),
[2026-07-19-ocr-spellcheck-design.md](superpowers/specs/2026-07-19-ocr-spellcheck-design.md).
```

- [ ] **Step 2: Document the --use-minimax flag**

In the same file, find the `### 10.1 Ishlatish` section's code block:

```markdown
**Haqiqiy o'zgarish qilish uchun:**

```bash
docker compose run --rm ufl ufl finalize-corpus --apply
```
```

Add right after it:

```markdown
**MiniMax bilan birga (ixtiyoriy, qoldiq imlo-xatolarini ham tekshirish uchun):**

```bash
docker compose run --rm ufl ufl finalize-corpus --apply --use-minimax
```

(`MINIMAX_API_KEY` muhit o'zgaruvchisi kerak. Standart holatda o'chiq — faqat
qoidaga asoslangan tuzatish yetarli bo'lmagan qoldiq so'zlar uchun, har bir noyob
so'z faqat bir marta so'raladi, xarajatni tejash uchun.)
```

- [ ] **Step 3: Document the 5th stage**

In the same file, find the `### 10.2 Bosqichlar va xavfsizlik` section's paragraph
about the OCR-chiqindi tozalash stage (added by the previous feature) and append,
right after that paragraph, a new paragraph:

```markdown
**OCR-manba imlo tuzatish** (`spellcheck.py`) — "kayta" kabi shaklan to'g'ri, lekin
harfiy OCR-xatosi bo'lgan so'zlarni tuzatadi. Ishonchli lug'at **faqat HF-manba
fayllardan** quriladi (web-crawl va ziyouz — ikkalasida ham ekstraksiya/OCR muammosi
bo'lishi mumkin, shuning uchun lug'atga qo'shilmaydi). Tekshirish/tuzatish esa **HF-manba
bo'lmagan barcha fayllarga** qo'llanadi. Faqat 5 ta ma'lum chalkashlik juftligi
(`q↔k`, `g'↔g`, `h↔x`, `o'↔u`, `i↔y`) bo'yicha **yagona nomzod** topilsagina
to'g'irlanadi — noaniq holatlarda so'zga tegilmaydi.
```

- [ ] **Step 4: Commit**

```bash
git add docs/DOCKER.md
git commit -m "docs: finalize-corpus'ga OCR-manba imlo tuzatish (5-bosqich) hujjati"
```

---

### Yakuniy tekshiruv (barcha tasklardan keyin)

```bash
docker compose run --rm ufl python -m pytest
```

Expected: barcha testlar o'tadi (avvalgi + yangi ~27 test), regressiya yo'q.
