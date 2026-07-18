"""HF dataset qator-shardlarini tozalash: bitta hujjat (fayl) o'rniga bitta shard
(N qatorlik matn-ro'yxati) `ProcessResult`ga aylantiradi — mavjud `pipeline.write_output()`
o'zgarishsiz qayta ishlatiladi (shard_label fayl nomiga aylanadi).
"""

from __future__ import annotations

from pathlib import Path

from ufl.clean.apply import clean_paragraphs
from ufl.clean.dedup import DeduplicationStore
from ufl.clean.language import FastTextPredictor
from ufl.pipeline import DroppedBlock, ProcessResult
from ufl.stats.tokens import TokenCounter, count_tokens


def process_hf_shard(
    texts: list[str],
    *,
    shard_label: str,
    category: str,
    dedup_store: DeduplicationStore,
    fasttext_predict: FastTextPredictor | None = None,
    exact_token_counter: TokenCounter | None = None,
    chars_per_token: float = 4.0,
    min_language_confidence: float = 0.65,
    min_heuristic_score: float = 0.20,
    apostrophe_mode: str = "ascii",
    quality_kwargs: dict | None = None,
) -> ProcessResult:
    dropped: list[DroppedBlock] = []

    def _record_drop(text: str, reason: str) -> None:
        dropped.append(DroppedBlock(text=text, page=0, reason=reason))

    kept = clean_paragraphs(
        texts,
        dedup_store=dedup_store,
        get_text=lambda t: t,
        fasttext_predict=fasttext_predict,
        min_language_confidence=min_language_confidence,
        min_heuristic_score=min_heuristic_score,
        apostrophe_mode=apostrophe_mode,
        quality_kwargs=quality_kwargs,
        on_drop=_record_drop,
    )
    kept_text = "\n\n".join(kept)
    token_counts = count_tokens(
        kept_text, chars_per_token=chars_per_token, exact_counter=exact_token_counter
    )

    return ProcessResult(
        source_path=Path(shard_label),
        category=category,
        format="hf-dataset",
        kept_text=kept_text,
        dropped=dropped,
        char_count=token_counts.char_count,
        estimated_tokens=token_counts.estimated_tokens,
        exact_tokens=token_counts.exact_tokens,
        total_blocks=len(texts),
        kept_blocks=len(kept),
    )
