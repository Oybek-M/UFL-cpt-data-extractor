from PIL import Image, ImageDraw, ImageFont

from ufl.ingest.ocr import run_ocr


def _make_text_image(text: str) -> Image.Image:
    image = Image.new("RGB", (600, 100), color="white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    draw.text((20, 20), text, fill="black", font=font)
    return image


def test_run_ocr_recognizes_simple_latin_text():
    image = _make_text_image("Salom Dunyo")

    result = run_ocr(image, languages="uzb+uzb_cyrl")

    assert "Salom" in result.text
    assert "Dunyo" in result.text
    assert result.confidence > 50


def test_run_ocr_returns_empty_for_blank_image():
    blank = Image.new("RGB", (300, 100), color="white")

    result = run_ocr(blank, languages="uzb+uzb_cyrl")

    assert result.text.strip() == ""
    assert result.confidence == 0.0
