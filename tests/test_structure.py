from ufl.clean.structure import clean_structure
from ufl.ingest.base import Block, Document


def test_removes_repeated_running_header_and_page_numbers():
    blocks = []
    bodies = [
        "Birinchi sahifada asosiy voqealar boshlanadi va qahramon safarga chiqadi juda qiziqarli tarzda.",
        "Ikkinchi sahifada voqealar davom etib, yangi qahramonlar paydo bo'ladi va syujet chigallashadi.",
        "Uchinchi sahifada voqealar nihoyasiga yetib, yakuniy xulosalar chiqariladi va kitob tugaydi.",
    ]
    for page, body in enumerate(bodies, start=1):
        blocks.append(Block(text="IKKINCHI BOB", page=page))
        blocks.append(Block(text=body, page=page))
        blocks.append(Block(text=str(page), page=page))

    result = clean_structure(Document(blocks=blocks), header_footer_min_repeats=3)

    kept_texts = [b.text for b in result.kept_blocks]
    assert kept_texts == bodies
    dropped_reasons = {reason for _, reason in result.dropped}
    assert "kolontitul" in dropped_reasons
    assert "sahifa_raqami" in dropped_reasons


def test_removes_various_page_number_formats():
    document = Document(blocks=[
        Block(text="12", page=1),
        Block(text="- 12 -", page=2),
        Block(text="45-bet", page=3),
        Block(text="Bu haqiqiy matn 12 ta so'zdan iborat emas balki oddiy jumla.", page=4),
    ])
    result = clean_structure(document)
    kept_texts = [b.text for b in result.kept_blocks]
    assert kept_texts == ["Bu haqiqiy matn 12 ta so'zdan iborat emas balki oddiy jumla."]


def test_removes_toc_entries():
    document = Document(blocks=[
        Block(text="1-bob. Kirish ........................ 5", page=2),
        Block(text="Bu oddiy asosiy matn bo'lib, mundarijaga aloqasi yo'q va yetarlicha uzun.", page=5),
    ])
    result = clean_structure(document)
    kept_texts = [b.text for b in result.kept_blocks]
    assert kept_texts == ["Bu oddiy asosiy matn bo'lib, mundarijaga aloqasi yo'q va yetarlicha uzun."]


def test_can_disable_toc_detection():
    document = Document(blocks=[Block(text="1-bob. Kirish ........................ 5", page=2)])
    result = clean_structure(document, detect_toc=False)
    assert len(result.kept_blocks) == 1


def test_removes_front_matter_by_keyword():
    document = Document(blocks=[
        Block(text="ISBN 978-9943-01-234-5, Toshkent nashriyoti, 2020-yil.", page=1),
        Block(text="Bu kitobning asosiy matni bo'lib, hikoya shu yerdan boshlanadi va davom etadi.", page=1),
    ])
    result = clean_structure(document)
    kept_texts = [b.text for b in result.kept_blocks]
    assert kept_texts == ["Bu kitobning asosiy matni bo'lib, hikoya shu yerdan boshlanadi va davom etadi."]


def test_removes_bibliography_entries():
    document = Document(blocks=[
        Block(text="Rashidov, A., Til nazariyasi, Toshkent, 2015, 45-bet.", page=90),
        Block(text="Bu asosiy matn bo'lib, adabiyotlar ro'yxatiga aloqasi yo'q va yetarlicha uzun matn.", page=90),
    ])
    result = clean_structure(document)
    kept_texts = [b.text for b in result.kept_blocks]
    assert kept_texts == ["Bu asosiy matn bo'lib, adabiyotlar ro'yxatiga aloqasi yo'q va yetarlicha uzun matn."]


def test_can_disable_bibliography_detection():
    document = Document(blocks=[Block(text="Rashidov, A., Til nazariyasi, Toshkent, 2015, 45-bet.", page=90)])
    result = clean_structure(document, detect_bibliography=False)
    assert len(result.kept_blocks) == 1


def test_keeps_normal_body_text_untouched():
    text = "Bu oddiy asosiy matn bo'lib, hech qanday tuzilma shovqiniga ega emas va shunchaki hikoya davom etadi."
    document = Document(blocks=[Block(text=text, page=10)])
    result = clean_structure(document)
    assert len(result.kept_blocks) == 1
    assert result.kept_blocks[0].text == text
    assert result.dropped == []
