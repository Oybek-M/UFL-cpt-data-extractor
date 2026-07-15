from ufl.ingest.fb2 import extract

_FB2_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
  <body>
    <section>
      <p>Birinchi paragraf.</p>
      <p>Ikkinchi paragraf.</p>
    </section>
  </body>
</FictionBook>
"""


def test_fb2_extract_reads_paragraphs(tmp_path):
    path = tmp_path / "sample.fb2"
    path.write_text(_FB2_SAMPLE, encoding="utf-8")

    document = extract(path)

    assert [b.text for b in document.blocks] == ["Birinchi paragraf.", "Ikkinchi paragraf."]
