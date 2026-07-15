import pytest

from ufl.ingest.url import UrlFetchError, fetch_html


@pytest.mark.parametrize("bad_url", ["ftp://example.com/x", "not-a-url", ""])
def test_fetch_html_rejects_non_http_scheme(bad_url):
    with pytest.raises(UrlFetchError):
        fetch_html(bad_url)


@pytest.mark.parametrize(
    "internal_url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://0.0.0.0/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
    ],
)
def test_fetch_html_rejects_internal_addresses(internal_url):
    with pytest.raises(UrlFetchError):
        fetch_html(internal_url)


def test_fetch_html_returns_response_text_for_public_url(monkeypatch):
    class FakeResponse:
        text = "<html><body>Salom Dunyo</body></html>"
        url = "https://example.com/sahifa"

        def raise_for_status(self) -> None:
            return None

    def fake_get(url, **kwargs):
        return FakeResponse()

    def fake_getaddrinfo(host, port):
        return [(None, None, None, None, ("93.184.216.34", 0))]  # ommaviy (misol) IP

    monkeypatch.setattr("ufl.ingest.url.httpx.get", fake_get)
    monkeypatch.setattr("ufl.ingest.url.socket.getaddrinfo", fake_getaddrinfo)

    html = fetch_html("https://example.com/sahifa")

    assert "Salom Dunyo" in html


def test_fetch_html_raises_on_http_error(monkeypatch):
    import httpx

    def fake_get(url, **kwargs):
        request = httpx.Request("GET", url)
        raise httpx.ConnectError("boglanib bolmadi", request=request)

    def fake_getaddrinfo(host, port):
        return [(None, None, None, None, ("93.184.216.34", 0))]

    monkeypatch.setattr("ufl.ingest.url.httpx.get", fake_get)
    monkeypatch.setattr("ufl.ingest.url.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(UrlFetchError):
        fetch_html("https://example.com/")
