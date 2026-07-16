import pytest

from ufl.crawl import web_client
from ufl.crawl.web_client import RobotsPolicy, WebClient


class _FakeResponse:
    def __init__(self, text: str = "", status: int = 200) -> None:
        self.text = text
        self.status_code = status

    def raise_for_status(self) -> None:
        return None


class _FakeHttpxClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[str] = []

    def get(self, url: str, **kwargs) -> _FakeResponse:
        self.calls.append(url)
        return self.response


def test_web_client_enforces_delay_between_same_host(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(web_client.time, "sleep", lambda s: sleeps.append(s))
    ticks = iter([100.0, 100.0, 100.1, 100.1])
    monkeypatch.setattr(web_client.time, "monotonic", lambda: next(ticks))

    fake = _FakeHttpxClient(_FakeResponse("ok"))
    wc = WebClient(user_agent="X", request_delay=0.6, timeout=10, client=fake)

    wc.get("https://kun.uz/a")  # birinchi so'rov: kechikish yo'q
    wc.get("https://kun.uz/b")  # 0.1s o'tdi → 0.5s kutish kerak

    assert sleeps == [pytest.approx(0.5, abs=1e-6)]
    assert fake.calls == ["https://kun.uz/a", "https://kun.uz/b"]


def test_robots_policy_parses_sitemaps_and_disallow():
    robots_txt = (
        "User-agent: *\n"
        "Disallow: /private/\n"
        "Sitemap: https://kun.uz/sitemap-news.xml\n"
    )

    class _Web:
        def get(self, url):
            return _FakeResponse(robots_txt)

    policy = RobotsPolicy("https://kun.uz", _Web(), user_agent="UFL")
    assert "https://kun.uz/sitemap-news.xml" in policy.sitemaps
    assert policy.allowed("https://kun.uz/news/1") is True
    assert policy.allowed("https://kun.uz/private/secret") is False


def test_robots_policy_defaults_sitemap_when_missing():
    class _Web:
        def get(self, url):
            raise RuntimeError("no robots.txt")

    policy = RobotsPolicy("https://kun.uz", _Web(), user_agent="UFL")
    assert policy.sitemaps == ["https://kun.uz/sitemap.xml"]
    assert policy.allowed("https://kun.uz/anything") is True
