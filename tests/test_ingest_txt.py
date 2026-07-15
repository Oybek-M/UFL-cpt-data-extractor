from ufl.ingest.txt import extract


def test_txt_extract_splits_into_paragraphs(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("Birinchi paragraf.\n\nIkkinchi paragraf.\n\n\nUchinchi.", encoding="utf-8")

    document = extract(path)

    assert [b.text for b in document.blocks] == [
        "Birinchi paragraf.",
        "Ikkinchi paragraf.",
        "Uchinchi.",
    ]
