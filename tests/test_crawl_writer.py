import json

from ufl.crawl.state import CrawlState
from ufl.crawl.writer import BundledWriter
from ufl.store.db import Store


def _page(state: CrawlState, url: str, published: str | None = "2026-07-16"):
    state.add_page(url, published_at=published)
    return state.conn.execute("SELECT * FROM pages WHERE url=?", (url,)).fetchone()


def test_writer_pairs_txt_and_jsonl(tmp_path):
    state = CrawlState(tmp_path / "_state")
    page = _page(state, "https://test.uz/a")
    writer = BundledWriter(tmp_path / "out", state=state, domain="test.uz")

    writer.write_article(
        page, title="Sarlavha", published="2026-07-16", method="jsonld",
        category="web_news", blocks=["Birinchi paragraf matni.", "Ikkinchi paragraf matni."],
    )

    text_files = list((tmp_path / "out" / "test.uz" / "text_folder").glob("*.txt"))
    table_files = list((tmp_path / "out" / "test.uz" / "table_folder").glob("*.jsonl"))
    assert len(text_files) == 1
    assert len(table_files) == 1
    text_content = text_files[0].read_text(encoding="utf-8")
    assert "Sarlavha." in text_content
    assert "Birinchi paragraf matni." in text_content
    lines = table_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["title"] == "Sarlavha"
    assert record["date"] == "2026-07-16"
    assert record["source_website"] == "test.uz"
    assert record["source_url"] == "https://test.uz/a"
    assert "Birinchi paragraf matni." in record["text"]

    row = state.conn.execute("SELECT status FROM pages WHERE url=?", ("https://test.uz/a",)).fetchone()
    assert row["status"] == "done"


def test_writer_atomic_recover_after_interrupt(tmp_path):
    state = CrawlState(tmp_path / "_state")
    page = _page(state, "https://test.uz/crash")
    page_id = int(page["id"])

    text_path = tmp_path / "out" / "test.uz" / "text_folder" / "000001_07.txt"
    table_path = tmp_path / "out" / "test.uz" / "table_folder" / "000001_07.jsonl"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    table_path.parent.mkdir(parents=True, exist_ok=True)
    # Faqat qisman yozilgan (crash simulyatsiyasi) — deklaratsiya qilingan uzunlikdan qisqa.
    text_path.write_bytes(b"partial")
    table_path.write_bytes(b"partial")

    state.conn.execute(
        """INSERT INTO output_bundles
           (id,start_date,end_date,text_path,table_path,text_size,table_size,documents,open)
           VALUES(1,'2026-07-16','2026-07-16',?,?,0,0,0,1)""",
        (str(text_path), str(table_path)),
    )
    state.conn.execute(
        """INSERT INTO output_items
           (page_id,dataset_id,bundle_id,text_offset,text_length,clean_chars,text_sha256,
            table_offset,table_length,table_sha256,status,created_at)
           VALUES(?,1,1,0,100,50,'deadbeef',0,50,'deadbeef','writing','2026-07-16T00:00:00+00:00')""",
        (page_id,),
    )
    state.conn.execute("UPDATE pages SET status='writing' WHERE id=?", (page_id,))
    state.conn.commit()

    BundledWriter(tmp_path / "out", state=state, domain="test.uz")

    assert text_path.read_bytes() == b""
    assert table_path.read_bytes() == b""
    item = state.conn.execute("SELECT * FROM output_items WHERE page_id=?", (page_id,)).fetchone()
    assert item is None
    row = state.conn.execute("SELECT status,error FROM pages WHERE id=?", (page_id,)).fetchone()
    assert row["status"] == "discovered"
    assert row["error"]


def test_writer_rolls_shard_at_limit(tmp_path):
    state = CrawlState(tmp_path / "_state")
    writer = BundledWriter(tmp_path / "out", state=state, domain="test.uz", shard_limit_bytes=200)

    page1 = _page(state, "https://test.uz/one")
    writer.write_article(
        page1, title="Birinchi", published="2026-07-16", method="jsonld",
        category="web_news", blocks=["X" * 150],
    )
    page2 = _page(state, "https://test.uz/two")
    writer.write_article(
        page2, title="Ikkinchi", published="2026-07-16", method="jsonld",
        category="web_news", blocks=["Y" * 150],
    )

    bundles = state.conn.execute("SELECT id FROM output_bundles ORDER BY id").fetchall()
    assert len(bundles) == 2


def test_writer_records_tokens_to_budget(tmp_path):
    state = CrawlState(tmp_path / "_state")
    store = Store(tmp_path / "ufl.db")
    writer = BundledWriter(tmp_path / "out", state=state, domain="test.uz", store=store)
    page = _page(state, "https://test.uz/budget")

    writer.write_article(
        page, title="Sarlavha", published="2026-07-16", method="jsonld",
        category="web_news", blocks=["Bu maqola matni byudjetga yozilishi kerak."],
    )

    assert store.book_count() == 1
    tokens = store.collected_tokens_by_category()
    assert tokens.get("web_news", 0) > 0


def test_writer_never_splits_article_between_shards(tmp_path):
    state = CrawlState(tmp_path / "_state")
    writer = BundledWriter(tmp_path / "out", state=state, domain="test.uz", shard_limit_bytes=200)

    page1 = _page(state, "https://test.uz/near-limit")
    writer.write_article(
        page1, title="Birinchi", published="2026-07-16", method="jsonld",
        category="web_news", blocks=["X" * 150],
    )
    bundle1 = state.conn.execute("SELECT * FROM output_bundles WHERE id=1").fetchone()

    page2 = _page(state, "https://test.uz/overflow")
    writer.write_article(
        page2, title="Ikkinchi", published="2026-07-16", method="jsonld",
        category="web_news", blocks=["Y" * 150],
    )

    from pathlib import Path

    text1 = Path(bundle1["text_path"])
    content1 = text1.read_text(encoding="utf-8")
    assert "Y" * 150 not in content1  # ikkinchi maqola birinchi shard fayliga sizib kirmadi

    bundle2 = state.conn.execute("SELECT * FROM output_bundles WHERE id=2").fetchone()
    assert bundle2 is not None
    text2 = Path(bundle2["text_path"])
    content2 = text2.read_text(encoding="utf-8")
    assert "Y" * 150 in content2
    assert "X" * 150 not in content2
