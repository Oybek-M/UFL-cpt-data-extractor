"""PII (email, telefon) tozalash — CPT sifatiga tayyorlash uchun standart
qadam (Dolma/FineWeb amaliyoti)."""

from ufl.finalize.pii import scrub_pii


def test_scrub_pii_removes_email():
    cleaned, count = scrub_pii("Bog'lanish uchun: aliyev@example.com yozing.")
    assert "aliyev@example.com" not in cleaned
    assert count == 1


def test_scrub_pii_removes_international_uzbek_phone():
    cleaned, count = scrub_pii("Tel: +998 90 123 45 67 raqamiga qo'ng'iroq qiling.")
    assert "+998 90 123 45 67" not in cleaned
    assert count == 1


def test_scrub_pii_removes_local_uzbek_phone():
    cleaned, count = scrub_pii("Tel: 090 123 45 67.")
    assert "090 123 45 67" not in cleaned
    assert count == 1


def test_scrub_pii_removes_multiple_matches():
    cleaned, count = scrub_pii("a@b.com va +998901234567 va yana c@d.com")
    assert count == 3


def test_scrub_pii_leaves_normal_uzbek_text_untouched():
    text = "Bu oddiy o'zbekcha matn, hech qanday shaxsiy ma'lumot yo'q."
    cleaned, count = scrub_pii(text)
    assert cleaned == text
    assert count == 0
