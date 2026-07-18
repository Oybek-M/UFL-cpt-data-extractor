# tests/test_hf_pipeline.py
from ufl.clean.dedup import DeduplicationStore
from ufl.hf_pipeline import process_hf_shard

_UZBEK = "Бу китоб жуда қизиқарли бўлиб, унда кўплаб воқеалар тасвирланган."
_ENGLISH = (
    "This is a purely English paragraph without any Uzbek words "
    "that should definitely be filtered out here."
)


def test_process_hf_shard_keeps_uzbek_drops_non_uzbek():
    result = process_hf_shard(
        [_UZBEK, _ENGLISH],
        shard_label="test__train__shard-000001",
        category="books",
        dedup_store=DeduplicationStore(),
    )

    assert result.category == "books"
    assert result.format == "hf-dataset"
    assert result.total_blocks == 2
    assert result.kept_blocks == 1
    assert "kitob" in result.kept_text.lower()
    assert any(d.reason == "til_ozbekcha_emas" for d in result.dropped)


def test_process_hf_shard_deduplicates_within_shard():
    result = process_hf_shard(
        [_UZBEK, _UZBEK],
        shard_label="test__train__shard-000001",
        category="books",
        dedup_store=DeduplicationStore(),
    )

    assert result.kept_blocks == 1
    assert any(d.reason == "takror" for d in result.dropped)


def test_process_hf_shard_source_path_matches_shard_label():
    result = process_hf_shard(
        [_UZBEK],
        shard_label="tahrirchi_uz-crawl__news__shard-000042",
        category="web_news",
        dedup_store=DeduplicationStore(),
    )

    assert result.source_path.name == "tahrirchi_uz-crawl__news__shard-000042"
