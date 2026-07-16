from ufl.crawl.state import CrawlState


def _state(tmp_path):
    return CrawlState(tmp_path / "_state")


def test_add_page_dedupes_by_url(tmp_path):
    state = _state(tmp_path)
    assert state.add_page("https://kun.uz/news/a") is True
    assert state.add_page("https://kun.uz/news/a") is False  # takror — qo'shilmaydi
    assert state.pending_page_count() == 1


def test_next_page_newest_first(tmp_path):
    state = _state(tmp_path)
    state.add_page("https://kun.uz/news/old", published_at="2026-07-01T00:00:00+00:00")
    state.add_page("https://kun.uz/news/new", published_at="2026-07-16T00:00:00+00:00")
    row = state.next_page()
    assert row["url"] == "https://kun.uz/news/new"


def test_recover_resets_processing_on_restart(tmp_path):
    root = tmp_path / "_state"
    state = CrawlState(root)
    state.add_page("https://kun.uz/news/x")
    state.conn.execute("UPDATE pages SET status='processing' WHERE url=?", ("https://kun.uz/news/x",))
    state.conn.commit()
    state.close()

    # Qayta ochilganda 'processing' -> 'discovered' (uzilgan ishni tiklaydi)
    state2 = CrawlState(root)
    assert state2.pending_page_count() == 1


def test_save_and_read_adapter(tmp_path):
    state = _state(tmp_path)
    state.save_adapter("kun.uz", method="nuxt", selector="", confidence=0.9, samples=1)
    row = state.adapter("kun.uz")
    assert row is not None
    assert row["method"] == "nuxt"


def test_counts_by_status(tmp_path):
    state = _state(tmp_path)
    state.add_page("https://kun.uz/a")
    state.add_page("https://kun.uz/b")
    counts = state.counts()
    assert counts.get("discovered") == 2


def test_median_clean_chars(tmp_path):
    state = _state(tmp_path)
    for i, chars in enumerate([100, 300, 500]):
        url = f"https://kun.uz/news/{i}"
        state.add_page(url)
        state.conn.execute(
            "UPDATE pages SET status='done', clean_chars=? WHERE url=?", (chars, url)
        )
    state.conn.commit()
    assert state.median_clean_chars() == 300.0
