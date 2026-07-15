from ufl.ingest.detect import detect_format


def test_detect_format_by_extension(tmp_path):
    cases = [
        (".pdf", "pdf"),
        (".djvu", "djvu"),
        (".epub", "epub"),
        (".docx", "docx"),
        (".fb2", "fb2"),
        (".html", "html"),
        (".htm", "html"),
        (".txt", "txt"),
    ]
    for ext, expected in cases:
        path = tmp_path / f"sample{ext}"
        path.write_bytes(b"placeholder")
        assert detect_format(path) == expected


def test_detect_format_falls_back_to_pdf_magic_bytes(tmp_path):
    path = tmp_path / "noext"
    path.write_bytes(b"%PDF-1.4 rest of file")
    assert detect_format(path) == "pdf"


def test_detect_format_falls_back_to_html_when_content_starts_with_tag(tmp_path):
    path = tmp_path / "noext2"
    path.write_bytes(b"<!DOCTYPE html><html><body>Salom</body></html>")
    assert detect_format(path) == "html"


def test_detect_format_falls_back_to_txt_for_plain_content(tmp_path):
    path = tmp_path / "noext3"
    path.write_bytes(b"Oddiy matn hech qanday belgisiz.")
    assert detect_format(path) == "txt"
