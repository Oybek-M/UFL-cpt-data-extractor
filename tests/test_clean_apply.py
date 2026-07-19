from ufl.clean.apply import clean_paragraphs
from ufl.clean.dedup import DeduplicationStore

_UZBEK = "Бу гап тўлиқ ўзбек тилида ёзилган ва етарлича узун бўлиши керак, шунда сифат гейти ундан ўтади."
_ENGLISH = "This paragraph is written entirely in English and should be dropped by the language filter."

_QUALITY = {
    "min_chars": 25,
    "min_words": 4,
    "max_non_letter_ratio": 0.40,
    "max_repeated_ngram_ratio": 0.30,
    "max_upper_ratio": 0.70,
    "max_url_ratio": 0.20,
}


def _clean(texts, dedup=None, on_drop=None):
    return clean_paragraphs(
        texts,
        dedup_store=dedup or DeduplicationStore(),
        min_language_confidence=0.65,
        min_heuristic_score=0.20,
        apostrophe_mode="ascii",
        quality_kwargs=_QUALITY,
        on_drop=on_drop,
    )


def test_clean_paragraphs_keeps_uzbek_transliterated():
    kept = _clean([_UZBEK])
    assert len(kept) == 1
    assert "o'zbek" in kept[0].lower()  # kirill -> lotin


def test_clean_paragraphs_drops_english():
    drops = []
    kept = _clean([_ENGLISH], on_drop=lambda item, reason: drops.append(reason))
    assert kept == []
    assert "til_ozbekcha_emas" in drops


def test_clean_paragraphs_dedupes_within_store():
    store = DeduplicationStore()
    first = _clean([_UZBEK], dedup=store)
    second = _clean([_UZBEK], dedup=store)
    assert len(first) == 1
    assert second == []  # dedup store bir xil matnni ikkinchi marta olmaydi


def test_clean_paragraphs_supports_custom_get_text_and_on_drop():
    items = [{"t": _UZBEK}, {"t": _ENGLISH}]
    drops = []
    kept = clean_paragraphs(
        items,
        get_text=lambda d: d["t"],
        dedup_store=DeduplicationStore(),
        quality_kwargs=_QUALITY,
        on_drop=lambda item, reason: drops.append((item["t"][:5], reason)),
    )
    assert len(kept) == 1
    assert drops and drops[0][1] == "til_ozbekcha_emas"


def test_clean_paragraphs_strips_ocr_garbage_but_keeps_paragraph():
    text = _UZBEK + "\n• kayta nshlaga1^ K r k -^."
    kept = _clean([text])
    assert len(kept) == 1
    assert "nshlaga1" not in kept[0]
    assert "•" not in kept[0]
    assert "kayta" in kept[0].lower()
