from ufl.crawl.candidates import Candidate
from ufl.crawl.minimax import MiniMaxClient
from ufl.crawl.state import CrawlState

_VALID = [
    "web_news", "gov_legal", "education", "reference",
    "books", "conversations", "technical", "domain_haf",
]


class _FakeResponse:
    def __init__(self, status_code: int, body: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._body = body
        self.text = text or ""

    def json(self) -> dict:
        return self._body


def _chat_response(content: dict) -> _FakeResponse:
    import json

    return _FakeResponse(
        200, {"choices": [{"message": {"content": json.dumps(content)}}]}
    )


def _candidate(candidate_id="c1", method="nuxt", selector="", blocks=None):
    blocks = blocks or [
        "Birinchi blok matni bu yerda ancha uzun va toza bo'lishi kerak, kamida ikki yuz "
        "ellikta belgidan iborat bo'lishi uchun yetarlicha so'z qo'shildi shu qatorga.",
        "Ikkinchi blok matni ham yetarlicha uzun bo'lishi kerak, shuning uchun bu yerga "
        "yana bir nechta jumla qo'shildi va umumiy uzunlik minimal chegaradan oshsin.",
    ]
    text = "\n\n".join(blocks)
    return Candidate(
        candidate_id=candidate_id, method=method, selector=selector, text=text,
        score=100.0, paragraph_count=2, link_density=0.0, blocks=blocks,
    )


def test_minimax_selects_candidate_and_caches_adapter(tmp_path):
    state = CrawlState(tmp_path / "_state")
    candidate = _candidate()
    calls = []

    def fake_post(url, headers, body, timeout):
        calls.append(body)
        return _chat_response({
            "page_id": 1, "is_article": True, "candidate_id": "c1",
            "content_block_ids": ["c1_b0001", "c1_b0002"], "trash_block_ids": [],
            "complete": True, "confidence": 0.9, "reason": "ok",
        })

    client = MiniMaxClient("secret-key", state, post=fake_post)

    decision = client.select_candidate(
        domain="test.uz", page_id=1, url="https://test.uz/a", title="Sarlavha",
        published=None, reason="first_page_calibration", candidates=[candidate],
    )

    assert decision is not None
    assert decision.status == "accepted"
    assert decision.method == "nuxt"
    assert len(decision.blocks) == 2
    assert len(calls) == 1
    adapter = state.adapter("test.uz")
    assert adapter is not None
    assert adapter["method"] == "nuxt"


def test_minimax_rejects_low_confidence(tmp_path):
    state = CrawlState(tmp_path / "_state")
    candidate = _candidate()

    def fake_post(url, headers, body, timeout):
        return _chat_response({
            "page_id": 1, "is_article": True, "candidate_id": "c1",
            "content_block_ids": ["c1_b0001"], "trash_block_ids": [],
            "complete": True, "confidence": 0.2, "reason": "unsure",
        })

    client = MiniMaxClient("secret-key", state, post=fake_post)

    decision = client.select_candidate(
        domain="test.uz", page_id=1, url="https://test.uz/a", title="Sarlavha",
        published=None, reason="ambiguous", candidates=[candidate],
    )

    assert decision is not None
    assert decision.status == "manual_review"
    assert state.adapter("test.uz") is None


def test_minimax_rejects_incomplete(tmp_path):
    state = CrawlState(tmp_path / "_state")
    candidate = _candidate()

    def fake_post(url, headers, body, timeout):
        return _chat_response({
            "page_id": 1, "is_article": True, "candidate_id": "c1",
            "content_block_ids": ["c1_b0001"], "trash_block_ids": [],
            "complete": False, "confidence": 0.9, "reason": "truncated",
        })

    client = MiniMaxClient("secret-key", state, post=fake_post)

    decision = client.select_candidate(
        domain="test.uz", page_id=1, url="https://test.uz/a", title="Sarlavha",
        published=None, reason="ambiguous", candidates=[candidate],
    )

    assert decision is not None
    assert decision.status == "quality_rejected"
    assert state.adapter("test.uz") is None


def test_minimax_401_marks_blocked(tmp_path):
    state = CrawlState(tmp_path / "_state")
    candidate = _candidate()

    def fake_post(url, headers, body, timeout):
        return _FakeResponse(401, text="unauthorized")

    client = MiniMaxClient("bad-key", state, post=fake_post)

    decision = client.select_candidate(
        domain="test.uz", page_id=1, url="https://test.uz/a", title="Sarlavha",
        published=None, reason="ambiguous", candidates=[candidate],
    )

    assert decision is not None
    assert client.blocked
    # Bloklangandan keyin keyingi chaqiruv umuman API'ga bormaydi (None qaytadi).
    second = client.select_candidate(
        domain="test.uz", page_id=2, url="https://test.uz/b", title="B",
        published=None, reason="ambiguous", candidates=[candidate],
    )
    assert second is None


def test_minimax_batch_hash_skips_duplicate(tmp_path):
    state = CrawlState(tmp_path / "_state")
    candidate = _candidate()
    calls = []

    def fake_post(url, headers, body, timeout):
        calls.append(body)
        return _chat_response({
            "page_id": 1, "is_article": True, "candidate_id": "c1",
            "content_block_ids": ["c1_b0001", "c1_b0002"], "trash_block_ids": [],
            "complete": True, "confidence": 0.9, "reason": "ok",
        })

    client = MiniMaxClient("secret-key", state, post=fake_post)
    kwargs = dict(
        domain="test.uz", page_id=1, url="https://test.uz/a", title="Sarlavha",
        published=None, reason="first_page_calibration", candidates=[candidate],
    )

    first = client.select_candidate(**kwargs)
    second = client.select_candidate(**kwargs)

    assert first is not None and first.status == "accepted"
    assert second is None  # bir xil payload — batch_hash dedup, qayta yuborilmadi
    assert len(calls) == 1


def test_minimax_classify_falls_back_on_garbage(tmp_path):
    state = CrawlState(tmp_path / "_state")

    def fake_post(url, headers, body, timeout):
        return _chat_response({"choices": "garbage"})  # noto'g'ri shakl -> None

    client = MiniMaxClient("secret-key", state, post=fake_post)

    result = client.classify_category("Sarlavha", "Snippet matni", _VALID)

    assert result is None


def test_minimax_classify_returns_valid_category(tmp_path):
    state = CrawlState(tmp_path / "_state")

    def fake_post(url, headers, body, timeout):
        return _FakeResponse(200, {"choices": [{"message": {"content": "technical"}}]})

    client = MiniMaxClient("secret-key", state, post=fake_post)

    result = client.classify_category("IT yangiliklari", "Dasturlash haqida maqola", _VALID)

    assert result == "technical"


def test_crawl_works_without_key(tmp_path):
    state = CrawlState(tmp_path / "_state")
    client = MiniMaxClient("", state, post=lambda *a: (_ for _ in ()).throw(AssertionError("chaqirilmasligi kerak")))

    decision = client.select_candidate(
        domain="test.uz", page_id=1, url="https://test.uz/a", title="T",
        published=None, reason="ambiguous", candidates=[_candidate()],
    )

    assert decision is None
    assert client.classify_category("T", "S", _VALID) is None
