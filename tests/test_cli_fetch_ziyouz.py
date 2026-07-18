"""`ufl fetch-ziyouz` integratsiya testi — haqiqiy tarmoq so'rovisiz, soxta
WebClient orqali. `_build_web_client`ni monkeypatch qiladi.

`_write_test_config` — `tests/test_cli_fetch_hf.py`dagi bilan bir xil naqsh
(Config'ning barcha majburiy bo'limlari to'ldirilishi kerak, pydantic default'siz)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import ufl.cli as cli_module
from ufl.cli import app
from ufl.store.db import Store

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
education = 1000

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

_ROOT_HTML = """
<html><body>
<div class="pd-category"><h3>Ildiz</h3>
<a href="https://ziyouz.com/kutubxona/category/7-a">Kategoriya A</a>
</div>
</body></html>
"""

_CAT_A_HTML = """
<html><body>
<div class="pd-category"><h3>O'zbek zamonaviy she'riyati</h3>
<a href="https://ziyouz.com/kutubxona/category/7-a?download=10:kitob-a1">Kitob A1</a>
</div>
</body></html>
"""


class _FakeResponse:
    def __init__(self, url: str, content: bytes) -> None:
        self.url = url
        self.content = content
        self.text = content.decode("utf-8", errors="ignore")


class _FakeWebClient:
    """`_download_url`ga GET qilinganda haqiqiy .pdf faylga "redirect qilingan"
    deb, final .url'ni fayl-kengaytmali qilib qaytaradi."""

    def __init__(self, download_url: str, file_bytes: bytes, final_url: str) -> None:
        self._pages = {
            "https://ziyouz.com/kutubxona": _ROOT_HTML,
            "https://ziyouz.com/kutubxona/category/7-a": _CAT_A_HTML,
        }
        self._download_url = download_url
        self._file_bytes = file_bytes
        self._final_url = final_url

    def get(self, url: str):
        if url == self._download_url:
            return _FakeResponse(self._final_url, self._file_bytes)
        return _FakeResponse(url, self._pages[url].encode("utf-8"))

    def close(self) -> None:
        pass


def test_fetch_ziyouz_downloads_processes_and_records_one_item(tmp_path, monkeypatch):
    download_url = "https://ziyouz.com/kutubxona/category/7-a?download=10:kitob-a1"
    final_url = "https://ziyouz.com/books/uzbek_zamonaviy_sheriyati/Kitob A1.txt"
    file_bytes = "Bu sinov uchun yozilgan o'zbekcha matn kitobi.".encode("utf-8")

    fake_client = _FakeWebClient(download_url, file_bytes, final_url)
    monkeypatch.setattr(cli_module, "_build_web_client", lambda config: fake_client)
    # `walk_catalog`ning standart `start_url`i ("https://ziyouz.com/kutubxona") allaqachon
    # `_FakeWebClient._pages`dagi kalit bilan bir xil — qo'shimcha monkeypatch shart emas.

    config_path = _write_test_config(tmp_path)

    result = runner.invoke(app, ["fetch-ziyouz", "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    with Store(tmp_path / "ufl.db") as store:
        assert store.is_processed("ziyouz:10") is True
        books = store.list_books()
    assert len(books) == 1
    assert books[0].category == "books"
    assert (tmp_path / "output" / "books" / "10_kitob-a1.txt").exists()
