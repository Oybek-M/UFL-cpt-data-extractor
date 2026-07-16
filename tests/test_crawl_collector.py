import json

from ufl.crawl.collector import Collector
from ufl.crawl.state import CrawlState

_VALID = [
    "web_news", "gov_legal", "education", "reference",
    "books", "conversations", "technical", "domain_haf",
]

_QUALITY = {
    "min_chars": 25, "min_words": 4, "max_non_letter_ratio": 0.40,
    "max_repeated_ngram_ratio": 0.30, "max_upper_ratio": 0.70, "max_url_ratio": 0.20,
}

# Uzun o'zbek-kirill paragraflari (translit + til-filtr + min_clean_chars>=250 dan o'tadi).
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
_EN = (
    "This paragraph is written entirely in English and must be dropped by the Uzbek "
    "only language filter because it does not belong to the target corpus at all."
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


class _FakeWeb:
    def __init__(self, pages: dict[str, bytes]) -> None:
        self.pages = pages

    def get(self, url: str) -> _FakeResponse:
        if url not in self.pages:
            raise RuntimeError(f"unexpected url {url}")
        return _FakeResponse(self.pages[url], url)


class _FakeRobots:
    def __init__(self, allow: bool = True) -> None:
        self._allow = allow
        self.sitemaps: list[str] = []

    def allowed(self, url: str) -> bool:
        return self._allow


class _FakeWriter:
    def __init__(self, state: CrawlState) -> None:
        self.state = state
        self.calls: list[dict] = []

    def write_article(self, page, *, title, published, method, category, blocks) -> None:
        self.calls.append(
            {"url": page["url"], "title": title, "category": category, "blocks": list(blocks)}
        )
        body = "\n\n".join(blocks)
        self.state.conn.execute(
            "UPDATE pages SET status='done', clean_chars=?, selected_method=?, updated_at=? WHERE id=?",
            (len(body), method, title, int(page["id"])),
        )
        self.state.conn.commit()


def _collector(tmp_path, url, html_by_url, *, allow=True, mode="web_news", minimax=None, min_clean_chars=250):
    state = CrawlState(tmp_path / "_state")
    web = _FakeWeb(html_by_url)
    robots = _FakeRobots(allow=allow)
    writer = _FakeWriter(state)
    collector = Collector(
        url, state=state, web=web, robots=robots, writer=writer,
        category_mode=mode, valid_categories=_VALID, minimax=minimax,
        quality_kwargs=_QUALITY, min_clean_chars=min_clean_chars, min_local_chars=300,
    )
    return collector, writer, state


def test_collector_processes_uzbek_article_through_pipeline(tmp_path):
    url = "https://test.uz/news/2026/07/16/maqola"
    collector, writer, state = _collector(tmp_path, url, {url: _nuxt_html(_UZ1, _UZ2)})

    collector.process_page()

    assert len(writer.calls) == 1
    call = writer.calls[0]
    assert call["category"] == "web_news"
    combined = " ".join(call["blocks"]).lower()
    assert "o'zbekiston" in combined  # kirill -> lotin
    assert state.counts().get("done") == 1


def test_collector_drops_non_uzbek_blocks(tmp_path):
    url = "https://test.uz/news/2026/07/16/aralash"
    collector, writer, _ = _collector(tmp_path, url, {url: _nuxt_html(_UZ1, _EN, _UZ2)})

    collector.process_page()

    assert len(writer.calls) == 1
    combined = " ".join(writer.calls[0]["blocks"]).lower()
    assert "english" not in combined  # ingliz bloki tashlandi
    assert "o'zbekiston" in combined


def test_collector_rejects_short_after_language_filter(tmp_path):
    url = "https://test.uz/news/2026/07/16/qisqa"
    # min_clean_chars juda baland — normal o'zbek tana ham qisqa hisoblanadi
    collector, writer, state = _collector(
        tmp_path, url, {url: _nuxt_html(_UZ1, _UZ2)}, min_clean_chars=100000
    )

    collector.process_page()

    assert writer.calls == []
    row = state.conn.execute("SELECT status FROM pages WHERE url=?", (url,)).fetchone()
    assert row["status"] == "quality_rejected"


def test_collector_discovers_links_into_queue(tmp_path):
    url = "https://test.uz/news/2026/07/16/asosiy"
    body = "".join(f"<p>{p}</p>" for p in (_UZ1, _UZ2))
    payload = json.dumps(["x", f'<div class="post-content">{body}</div>'])
    html = (
        "<html><head><title>T</title></head><body>"
        '<a href="/news/2026/07/15/boshqa-maqola">Boshqa</a>'
        f'<script id="__NUXT_DATA__">{payload}</script>'
        "</body></html>"
    ).encode("utf-8")
    collector, _, state = _collector(tmp_path, url, {url: html})

    collector.process_page()

    urls = [r["url"] for r in state.conn.execute("SELECT url FROM pages").fetchall()]
    assert any("boshqa-maqola" in u for u in urls)


def test_collector_respects_robots_disallow(tmp_path):
    url = "https://test.uz/news/2026/07/16/taqiq"
    collector, writer, state = _collector(
        tmp_path, url, {url: _nuxt_html(_UZ1, _UZ2)}, allow=False
    )

    collector.process_page()

    assert writer.calls == []
    row = state.conn.execute("SELECT status FROM pages WHERE url=?", (url,)).fetchone()
    assert row["status"] == "access_denied"
