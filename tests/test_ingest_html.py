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


# Yaxshilanish A: kontent faqat __NUXT_DATA__ ichida (o'qiladigan DOM'da yo'q) —
# trafilatura yolg'iz o'zi ushlamaydi, ko'p-strategiyali ekstraktor ushlaydi.
_NUXT_BODY = (
    "<p>Nuxt payload ichidagi maqola tanasi yetarlicha uzun bo'lishi kerak, "
    "chunki ekstraktor qisqa nomzodlarni rad etadi va jiddiy matnni oladi.</p>"
    "<p>Ikkinchi paragraf qo'shimcha jumlalar bilan uzaytiriladi va tabiiy nasr bo'ladi. "
    "Yana bir necha so'z qo'shamiz, toki chegaradan oshsin.</p>"
)


def test_html_ingest_uses_multistrategy_for_nuxt(tmp_path):
    import json

    payload = json.dumps(["x", f'<div class="post-content">{_NUXT_BODY}</div>'])
    html = (
        "<html><head><title>Nuxt sahifa</title></head><body>"
        '<div id="app"></div>'  # o'qiladigan DOM bo'sh
        f'<script id="__NUXT_DATA__">{payload}</script>'
        "</body></html>"
    )
    path = tmp_path / "nuxt.html"
    path.write_text(html, encoding="utf-8")

    document = extract(path)

    combined = " ".join(b.text for b in document.blocks)
    assert "Nuxt payload ichidagi maqola" in combined
