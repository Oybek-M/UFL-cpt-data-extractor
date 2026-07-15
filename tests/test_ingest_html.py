from ufl.ingest.html import extract

_HTML_SAMPLE = """
<html>
  <head><title>Sinov sahifasi</title></head>
  <body>
    <nav>Bosh sahifa | Kontakt | Biz haqimizda</nav>
    <article>
      <h1>Maqola sarlavhasi</h1>
      <p>Bu maqolaning asosiy matni bo'lib, juda muhim va qiziqarli ma'lumotlarni o'z ichiga oladi.</p>
      <p>Bu ikkinchi paragraf bo'lib, mavzuni yanada chuqurroq yoritadi va aniq tushuntiradi.</p>
    </article>
    <footer>Barcha huquqlar himoyalangan 2024. Aloqa uchun email yozing.</footer>
  </body>
</html>
"""


def test_html_extract_keeps_main_article_content(tmp_path):
    path = tmp_path / "sample.html"
    path.write_text(_HTML_SAMPLE, encoding="utf-8")

    document = extract(path)

    combined = " ".join(b.text for b in document.blocks)
    assert "asosiy matni" in combined
    assert "chuqurroq yoritadi" in combined


def test_html_extract_produces_nonempty_blocks(tmp_path):
    path = tmp_path / "sample.html"
    path.write_text(_HTML_SAMPLE, encoding="utf-8")

    document = extract(path)

    assert len(document.blocks) > 0
    assert all(b.text.strip() for b in document.blocks)
