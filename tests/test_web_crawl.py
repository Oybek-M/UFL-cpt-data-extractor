import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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
web_news = 1000

[budget.category_labels]
web_news = "Umumiy veb, yangiliklar"

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

[crawl]
output_dir = "{(tmp_path / "collected").as_posix()}"
request_timeout = 60
request_delay = 0
root_refresh_seconds = 300
idle_sleep_seconds = 10
shard_limit_bytes = 52428800
user_agent = "UFL-Test/1.0"
min_local_chars = 700
min_clean_chars = 250
"""
    config_path = tmp_path / "test_ufl.toml"
    config_path.write_text(config_content, encoding="utf-8")
    return config_path


@pytest.fixture()
def client(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    monkeypatch.setenv("UFL_CONFIG_PATH", str(config_path))
    import ufl.web.app as web_app

    importlib.reload(web_app)
    return TestClient(web_app.app)


class _FakeProcess:
    def __init__(self) -> None:
        self.terminated = False

    def poll(self):
        return None if not self.terminated else 0

    def terminate(self) -> None:
        self.terminated = True


def test_crawl_form_renders(client):
    response = client.get("/crawl")

    assert response.status_code == 200
    assert "Auto" in response.text or "auto" in response.text
    assert 'name="url"' in response.text


def test_crawl_start_launches_background_and_redirects_to_status(client, monkeypatch):
    import ufl.web.app as web_app

    launched = {}

    def fake_launch(seed, category, max_articles, config_path):
        launched["seed"] = seed
        launched["category"] = category
        return _FakeProcess()

    monkeypatch.setattr(web_app, "_launch_crawl_process", fake_launch)

    response = client.post(
        "/crawl/start", data={"url": "https://test.uz", "category": "web_news", "max_articles": "5"}
    )

    assert response.status_code == 200  # TestClient follows the 303 redirect
    assert launched["seed"] == "https://test.uz/"
    assert launched["category"] == "web_news"
    assert "test.uz" in response.text


def test_crawl_start_does_not_launch_second_process_for_same_domain(client, monkeypatch):
    import ufl.web.app as web_app

    calls = []

    def fake_launch(seed, category, max_articles, config_path):
        calls.append(seed)
        return _FakeProcess()

    monkeypatch.setattr(web_app, "_launch_crawl_process", fake_launch)

    client.post("/crawl/start", data={"url": "https://test.uz", "category": "web_news", "max_articles": "0"})
    client.post("/crawl/start", data={"url": "https://test.uz", "category": "web_news", "max_articles": "0"})

    assert len(calls) == 1


def test_crawl_status_reads_state_db(client, monkeypatch):
    import ufl.web.app as web_app
    from ufl.crawl.state import CrawlState

    state_dir = web_app._config.crawl.output_dir / "test.uz" / "_state"
    with CrawlState(state_dir) as state:
        state.add_page("https://test.uz/a")
        state.conn.execute("UPDATE pages SET status='done' WHERE url=?", ("https://test.uz/a",))
        state.conn.commit()

    response = client.get("/crawl/status/test.uz")

    assert response.status_code == 200
    assert "done" in response.text


def test_crawl_stop_terminates_tracked_process(client, monkeypatch):
    import ufl.web.app as web_app

    fake_process = _FakeProcess()
    monkeypatch.setattr(web_app, "_launch_crawl_process", lambda *a, **k: fake_process)
    client.post("/crawl/start", data={"url": "https://test.uz", "category": "web_news", "max_articles": "0"})

    response = client.post("/crawl/stop/test.uz")

    assert response.status_code == 200
    assert fake_process.terminated
