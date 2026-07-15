import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_UZBEK_TEXT = "Бу китоб жуда қизиқарли бўлиб, унда кўплаб воқеалар тасвирланган."


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

[budget.category_labels]
books = "Kitoblar va adabiyot"

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


@pytest.fixture()
def client(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    monkeypatch.setenv("UFL_CONFIG_PATH", str(config_path))
    import ufl.web.app as web_app

    importlib.reload(web_app)  # UFL_CONFIG_PATH o'qib, modul-darajasidagi holatni qayta yaratish
    return TestClient(web_app.app)


def test_index_shows_budget_dashboard(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "books" in response.text
    assert "JAMI" in response.text


def test_index_shows_human_readable_category_label(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Kitoblar va adabiyot" in response.text


def test_books_remove_endpoint_removes_book_and_redirects_to_index(client):
    client.post("/paste", data={"text": _UZBEK_TEXT, "category": "books", "filename": "sinov"})
    assert "sinov.txt" in client.get("/").text

    response = client.post(
        "/books/remove", data={"path": [line for line in _find_book_paths(client) if "sinov" in line][0]}
    )

    assert response.status_code == 200  # TestClient follows the 303 redirect
    assert "sinov.txt" not in response.text


def test_books_clear_all_removes_every_record(client):
    client.post("/paste", data={"text": _UZBEK_TEXT, "category": "books", "filename": "sinov"})

    response = client.post("/books/clear-all")

    assert response.status_code == 200
    assert "Hali hech narsa qayta ishlanmagan" in response.text


def _find_book_paths(client) -> list[str]:
    import re

    html = client.get("/").text
    return re.findall(r'name="path" value="([^"]+)"', html)


def test_paste_processes_uzbek_text_and_shows_result(client):
    response = client.post(
        "/paste", data={"text": _UZBEK_TEXT, "category": "books", "filename": "sinov"}
    )
    assert response.status_code == 200
    assert "kitob" in response.text.lower()
    assert "/download/books/sinov.txt" in response.text


def test_download_serves_processed_txt(client):
    client.post("/paste", data={"text": _UZBEK_TEXT, "category": "books", "filename": "sinov"})
    response = client.get("/download/books/sinov.txt")
    assert response.status_code == 200
    assert "kitob" in response.text.lower()


def test_url_endpoint_fetches_and_processes_page(client, monkeypatch):
    import ufl.web.app as web_app

    fake_html = f"<html><body><article><p>{_UZBEK_TEXT}</p></article></body></html>"
    monkeypatch.setattr(web_app.url_module, "fetch_html", lambda url: fake_html)

    response = client.post(
        "/url", data={"url": "https://misol.uz/maqola", "category": "books", "filename": ""}
    )

    assert response.status_code == 200
    assert "kitob" in response.text.lower()


def test_url_endpoint_shows_error_on_fetch_failure(client, monkeypatch):
    import ufl.web.app as web_app
    from ufl.ingest.url import UrlFetchError

    def fail(url):
        raise UrlFetchError("ichki manzilga ruxsat yo'q")

    monkeypatch.setattr(web_app.url_module, "fetch_html", fail)

    response = client.post(
        "/url", data={"url": "http://127.0.0.1/", "category": "books", "filename": ""}
    )

    assert response.status_code == 200
    assert "ichki manzilga ruxsat yo" in response.text
