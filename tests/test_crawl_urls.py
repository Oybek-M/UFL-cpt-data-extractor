import pytest

from ufl.crawl.urls import (
    belongs_to_site,
    canonical_url,
    collectable_url,
    date_from_url,
    domain_folder,
    host_key,
    prepare_url,
    url_hash,
)


# --- canonical_url ---

@pytest.mark.parametrize(
    "bad",
    [
        "http://127.0.0.1/x",
        "http://10.0.0.5/x",
        "http://192.168.1.1/",
        "http://[::1]/",
        "https://localhost/x",
        "https://sub.localhost/x",
    ],
)
def test_canonical_url_rejects_private_and_localhost(bad):
    with pytest.raises(ValueError):
        canonical_url(bad)


def test_canonical_url_rejects_credentials():
    with pytest.raises(ValueError):
        canonical_url("https://user:pass@example.com/")


def test_canonical_url_rejects_non_http_scheme():
    with pytest.raises(ValueError):
        canonical_url("ftp://example.com/file")


def test_canonical_url_strips_tracking_params():
    result = canonical_url("https://example.com/a?utm_source=x&id=7&fbclid=abc&gclid=z")
    assert "utm_source" not in result
    assert "fbclid" not in result
    assert "gclid" not in result
    assert "id=7" in result


def test_canonical_url_lowercases_host_and_strips_trailing_slash():
    assert canonical_url("https://Example.COM/Path/") == "https://example.com/Path"


def test_canonical_url_rejects_too_long():
    with pytest.raises(ValueError):
        canonical_url("https://example.com/" + "a" * 2100)


def test_canonical_url_rejects_too_many_query_params():
    query = "&".join(f"k{i}=v{i}" for i in range(8))
    with pytest.raises(ValueError):
        canonical_url(f"https://example.com/?{query}")


# --- host_key / belongs_to_site ---

def test_host_key_strips_www():
    assert host_key("www.Example.com") == "example.com"


def test_belongs_to_site_handles_www_and_subdomains():
    seed = "https://kun.uz"
    assert belongs_to_site("https://www.kun.uz/news/1", seed)
    assert belongs_to_site("https://kun.uz/a", seed)
    assert not belongs_to_site("https://other.com/a", seed)


# --- collectable_url ---

def test_collectable_url_rejects_binary_extensions():
    seed = "https://kun.uz"
    assert not collectable_url("https://kun.uz/photo.jpg", seed)
    assert not collectable_url("https://kun.uz/doc.pdf", seed)
    assert collectable_url("https://kun.uz/news/article", seed)


def test_collectable_url_rejects_other_domain():
    assert not collectable_url("https://other.com/news", "https://kun.uz")


# --- date_from_url ---

def test_date_from_url_extracts_yyyy_mm_dd():
    got = date_from_url("https://kun.uz/news/2026/07/16/some-slug")
    assert got is not None and got.startswith("2026-07-16")


def test_date_from_url_returns_none_without_date():
    assert date_from_url("https://kun.uz/about") is None


# --- misc helpers ---

def test_domain_folder_is_filesystem_safe():
    assert domain_folder("https://www.kun.uz") == "kun.uz"


def test_url_hash_is_stable_hex():
    h = url_hash("https://example.com/a")
    assert h == url_hash("https://example.com/a")
    assert len(h) == 64


def test_prepare_url_adds_https_scheme():
    assert prepare_url("kun.uz").startswith("https://kun.uz")
