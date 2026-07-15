import io

import fitz
from PIL import Image, ImageDraw, ImageFont

from ufl.ingest.pdf import extract


def test_pdf_extract_reads_digital_text_layer(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Bu raqamli PDF sahifasining matni bo'lib, yetarlicha uzun.")
    path = tmp_path / "digital.pdf"
    doc.save(str(path))
    doc.close()

    document = extract(path)

    assert len(document.blocks) == 1
    assert "raqamli PDF" in document.blocks[0].text
    assert document.blocks[0].page == 1


def test_pdf_extract_uses_ocr_for_scanned_page(tmp_path):
    image = Image.new("RGB", (800, 200), color="white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    draw.text((20, 60), "Salom Dunyo", fill="black", font=font)
    img_bytes = io.BytesIO()
    image.save(img_bytes, format="PNG")

    doc = fitz.open()
    page = doc.new_page(width=800, height=200)
    page.insert_image(fitz.Rect(0, 0, 800, 200), stream=img_bytes.getvalue())
    path = tmp_path / "scanned.pdf"
    doc.save(str(path))
    doc.close()

    document = extract(path)

    combined = " ".join(b.text for b in document.blocks)
    assert "Salom" in combined
    assert "Dunyo" in combined


def test_pdf_extract_drops_blank_scanned_page(tmp_path):
    image = Image.new("RGB", (400, 200), color="white")  # bo'sh, matnsiz
    img_bytes = io.BytesIO()
    image.save(img_bytes, format="PNG")

    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    page.insert_image(fitz.Rect(0, 0, 400, 200), stream=img_bytes.getvalue())
    path = tmp_path / "blank_scan.pdf"
    doc.save(str(path))
    doc.close()

    document = extract(path)

    assert document.blocks == []
