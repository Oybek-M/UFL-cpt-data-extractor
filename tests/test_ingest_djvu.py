import subprocess

from PIL import Image, ImageDraw, ImageFont

from ufl.ingest.djvu import extract


def _encode_pbm_to_djvu(pbm_path, djvu_path) -> None:
    subprocess.run(["cjb2", str(pbm_path), str(djvu_path)], check=True, capture_output=True)


def _attach_text_layer(djvu_path, page_number: int, text: str, txt_file_path) -> None:
    sexp = f'(page 0 0 200 100 (line 0 0 200 20 (word 0 0 200 20 "{text}")))'
    txt_file_path.write_text(sexp, encoding="utf-8")
    subprocess.run(
        ["djvused", str(djvu_path), "-e", f"select {page_number}; set-txt {txt_file_path}", "-s"],
        check=True,
        capture_output=True,
    )


def test_djvu_extract_reads_text_layer(tmp_path):
    pbm_path = tmp_path / "blank.pbm"
    Image.new("1", (200, 100), color=1).save(pbm_path)
    djvu_path = tmp_path / "sample.djvu"
    _encode_pbm_to_djvu(pbm_path, djvu_path)
    _attach_text_layer(
        djvu_path, 1, "Bu djvu matn qatlamidagi yetarlicha uzun matn.", tmp_path / "text.sexp"
    )

    document = extract(djvu_path)

    assert len(document.blocks) == 1
    assert "djvu matn qatlamidagi" in document.blocks[0].text
    assert document.blocks[0].page == 1


def test_djvu_extract_uses_ocr_when_no_text_layer(tmp_path):
    image = Image.new("1", (600, 150), color=1)  # 1-bit: dithersiz toza bitonal
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    draw.text((20, 40), "Salom Dunyo", fill=0, font=font)
    pbm_path = tmp_path / "scanned.pbm"
    image.save(pbm_path)
    djvu_path = tmp_path / "scanned.djvu"
    _encode_pbm_to_djvu(pbm_path, djvu_path)
    # Matn qatlami biriktirilmagan -> OCR fallback ishga tushishi kerak

    document = extract(djvu_path)

    combined = " ".join(b.text for b in document.blocks)
    assert "Salom" in combined
    assert "Dunyo" in combined


def test_djvu_extract_drops_blank_page_without_text_layer(tmp_path):
    pbm_path = tmp_path / "blank2.pbm"
    Image.new("1", (200, 100), color=1).save(pbm_path)
    djvu_path = tmp_path / "blank.djvu"
    _encode_pbm_to_djvu(pbm_path, djvu_path)

    document = extract(djvu_path)

    assert document.blocks == []
