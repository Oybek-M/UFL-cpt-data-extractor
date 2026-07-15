from ebooklib import epub as epub_lib

from ufl.ingest.epub import extract


def _make_sample_epub(path) -> None:
    book = epub_lib.EpubBook()
    book.set_identifier("id123")
    book.set_title("Sinov kitobi")
    book.set_language("uz")

    chapter = epub_lib.EpubHtml(title="Bob 1", file_name="chap1.xhtml", lang="uz")
    chapter.content = "<html><body><p>Birinchi paragraf.</p><p>Ikkinchi paragraf.</p></body></html>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.add_item(epub_lib.EpubNcx())
    book.add_item(epub_lib.EpubNav())
    book.spine = ["nav", chapter]

    epub_lib.write_epub(str(path), book)


def test_epub_extract_reads_paragraphs(tmp_path):
    path = tmp_path / "sample.epub"
    _make_sample_epub(path)

    document = extract(path)

    assert [b.text for b in document.blocks] == ["Birinchi paragraf.", "Ikkinchi paragraf."]
