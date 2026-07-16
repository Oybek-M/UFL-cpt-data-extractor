"""Foydalanuvchi talabi: MiniMax token sarfi maqolalar soniga emas, DOMENLAR soniga
proporsional bo'lishi kerak. Bu test 10 ta bir domen maqolasi uchun MiniMax
kalibratsiya (Rol A) va kategoriya-aniqlash (Rol B) chaqiruvlari <=1 martadan
oshmasligini isbotlaydi — soxta HTTP POST'ni sanash orqali.
"""

import json

from ufl.crawl.collector import Collector
from ufl.crawl.minimax import MiniMaxClient
from ufl.crawl.state import CrawlState

_VALID = [
    "web_news", "gov_legal", "education", "reference",
    "books", "conversations", "technical", "domain_haf",
]

_QUALITY = {
    "min_chars": 25, "min_words": 4, "max_non_letter_ratio": 0.40,
    "max_repeated_ngram_ratio": 0.30, "max_upper_ratio": 0.70, "max_url_ratio": 0.20,
}

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
        '<html><head><title>Sinov maqolasi</title>'
        '<meta property="og:title" content="Sinov maqolasi">'
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
    sitemaps: list[str] = []

    def allowed(self, url: str) -> bool:
        return True


class _FakeWriter:
    def __init__(self, state: CrawlState) -> None:
        self.state = state
        self.calls: list[dict] = []

    def write_article(self, page, *, title, published, method, category, blocks) -> None:
        self.calls.append({"url": page["url"], "category": category})
        self.state.conn.execute(
            "UPDATE pages SET status='done', updated_at=? WHERE id=?", (title, int(page["id"]))
        )
        self.state.conn.commit()


def _fake_post_counting(calls: dict):
    def fake_post(url, headers, body, timeout):
        payload = json.loads(body["messages"][1]["content"])
        if "candidates" in payload.get("page", {}):
            calls["calibration"] += 1
            candidates_payload = payload["page"]["candidates"]
            first = candidates_payload[0]
            block_ids = [b["block_id"] for b in first["blocks"]]
            content = json.dumps({
                "page_id": payload["page"]["page_id"], "is_article": True,
                "candidate_id": first["candidate_id"], "content_block_ids": block_ids,
                "trash_block_ids": [], "complete": True, "confidence": 0.9, "reason": "ok",
            })
        else:
            calls["category"] += 1
            content = "web_news"
        return _ChatResponse(content)

    return fake_post


class _ChatResponse:
    def __init__(self, content: str) -> None:
        self.status_code = 200
        self.text = content

    def json(self):
        return {"choices": [{"message": {"content": self.text}}]}


def test_collector_minimax_token_saving_scales_with_domains_not_articles(tmp_path):
    urls = [f"https://test.uz/news/2026/07/{16 + i}/maqola-{i}" for i in range(10)]
    # Har maqola matni betakror bo'lishi kerak — aks holda DeduplicationStore ularni
    # (to'g'ri ravishda) bir xil kontent deb, dublikat sifatida tashlab yuboradi.
    unique_suffix = (
        " Ушбу воқеа рақами {index} бўлиб, бошқа хабарлардан фарқли жузъиётларга эга."
    )
    pages = {
        url: _nuxt_html(_UZ1, _UZ2 + unique_suffix.format(index=i))
        for i, url in enumerate(urls)
    }
    state = CrawlState(tmp_path / "_state")
    web = _FakeWeb(pages)
    robots = _FakeRobots()
    writer = _FakeWriter(state)
    calls = {"calibration": 0, "category": 0}
    minimax = MiniMaxClient("secret-key", state, post=_fake_post_counting(calls))

    seed = urls[0]
    collector = Collector(
        seed, state=state, web=web, robots=robots, writer=writer,
        category_mode="auto", valid_categories=_VALID, minimax=minimax,
        quality_kwargs=_QUALITY, min_clean_chars=250, min_local_chars=300,
    )
    for url in urls[1:]:
        state.add_page(url)

    for _ in range(len(urls)):
        collector.process_page()

    assert len(writer.calls) == 10
    assert calls["calibration"] <= 1
    assert calls["category"] <= 1
