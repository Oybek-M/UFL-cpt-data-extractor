import json
from pathlib import Path

from typer.testing import CliRunner

from ufl import cli
from ufl.cli import app

runner = CliRunner()

_UZ1 = (
    "Ўзбекистон Республикаси Президенти янги қарор имзолади ва ушбу ҳужжатга кўра "
    "мамлакатда таълим тизимини янада ривожлантириш борасида кенг кўламли ислоҳотлар "
    "амалга оширилиши белгиланди."
)
_UZ2 = (
    "Қарорга мувофиқ ёшларни қўллаб-қувватлаш, уларнинг билим олишлари учун зарур "
    "шароитларни яратиш ҳамда илмий тадқиқотларни рағбатлантириш чоралари кўрилади "
    "деб таъкидланди мажлисда."
)


def _nuxt_html(*paragraphs: str) -> bytes:
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    payload = json.dumps(["x", f'<div class="post-content">{body}</div>'])
    html = (
        '<html><head><title>Sinov</title>'
        '<meta property="og:title" content="Sinov maqola">'
        '</head><body><div id="app"></div>'
        f'<script id="__NUXT_DATA__">{payload}</script>'
        "</body></html>"
    )
    return html.encode("utf-8")


class _FakeResponse:
    def __init__(self, content: bytes, url: str) -> None:
        self.content = content
        self.text = content.decode("utf-8")
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.status_code = 200
        self.url = url


class _FakeWebClient:
    def __init__(self, pages: dict[str, bytes]) -> None:
        self.pages = pages

    def get(self, url: str) -> _FakeResponse:
        if url not in self.pages:
            raise RuntimeError(f"unexpected url {url}")
        return _FakeResponse(self.pages[url], url)

    def close(self) -> None:
        pass


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


def test_crawl_cli_local_mode_collects_from_fixture(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    seed = "https://test.uz/news/2026/07/16/maqola"
    fake_web = _FakeWebClient({seed: _nuxt_html(_UZ1, _UZ2)})
    monkeypatch.setattr(cli, "_build_web_client", lambda config: fake_web)

    result = runner.invoke(
        app, ["crawl", seed, "--category", "web_news", "--once", "--config", str(config_path)]
    )

    assert result.exit_code == 0, result.output
    text_files = list((tmp_path / "collected" / "test.uz" / "text_folder").glob("*.txt"))
    assert len(text_files) == 1
    assert "o'zbekiston" in text_files[0].read_text(encoding="utf-8").lower()


def test_crawl_cli_rejects_unknown_category(tmp_path):
    config_path = _write_test_config(tmp_path)

    result = runner.invoke(
        app,
        ["crawl", "https://test.uz", "--category", "notacategory", "--config", str(config_path)],
    )

    assert result.exit_code != 0


def test_crawl_status_shows_counts(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    seed = "https://test.uz/news/2026/07/16/maqola"
    fake_web = _FakeWebClient({seed: _nuxt_html(_UZ1, _UZ2)})
    monkeypatch.setattr(cli, "_build_web_client", lambda config: fake_web)
    runner.invoke(app, ["crawl", seed, "--category", "web_news", "--once", "--config", str(config_path)])

    result = runner.invoke(app, ["crawl-status", seed, "--config", str(config_path)])

    assert result.exit_code == 0
    assert "done" in result.output
