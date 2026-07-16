from ufl.crawl.blocks import (
    clean_content_blocks,
    clean_lines,
    fragment_blocks,
    fragment_text,
    obvious_trash_block,
)


def test_clean_lines_collapses_whitespace_and_fixes_punctuation():
    assert clean_lines("Salom   dunyo ,  qalaysan ?") == "Salom dunyo, qalaysan?"


def test_clean_lines_unescapes_html_entities():
    assert clean_lines("Bir &amp; ikki") == "Bir & ikki"


def test_fragment_blocks_extracts_ordered_paragraphs():
    html = "<div><p>Birinchi paragraf.</p><p>Ikkinchi paragraf.</p></div>"
    assert fragment_blocks(html) == ["Birinchi paragraf.", "Ikkinchi paragraf."]


def test_fragment_blocks_drops_script_style_and_nav():
    html = (
        "<article>"
        "<script>var x = 1;</script>"
        "<nav>Menyu havolalari</nav>"
        "<p>Asosiy matn.</p>"
        "<style>.a{color:red}</style>"
        "</article>"
    )
    blocks = fragment_blocks(html)
    assert blocks == ["Asosiy matn."]


def test_fragment_text_joins_blocks_with_blank_line():
    html = "<div><p>Bir.</p><p>Ikki.</p></div>"
    assert fragment_text(html) == "Bir.\n\nIkki."


def test_obvious_trash_block_detects_ad_labels():
    assert obvious_trash_block("Reklama")
    assert obvious_trash_block("реклама")
    assert obvious_trash_block("Sponsored")
    assert obvious_trash_block("Homiylik materiali")
    assert not obvious_trash_block("Bu oddiy jumla, reklama emas.")


def test_obvious_trash_block_detects_short_captions():
    assert obvious_trash_block("Foto: KUN.UZ")
    assert obvious_trash_block("Video: youtube")
    assert not obvious_trash_block("Fotosurat san'ati haqida uzun maqola " * 20)


def test_clean_content_blocks_removes_ads_and_duplicates():
    blocks = [
        "Asosiy paragraf matni.",
        "Reklama",
        "Asosiy paragraf matni.",  # dublikat
        "Ikkinchi paragraf.",
    ]
    assert clean_content_blocks(blocks) == ["Asosiy paragraf matni.", "Ikkinchi paragraf."]
