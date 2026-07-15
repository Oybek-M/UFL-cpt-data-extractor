"""Pipeline: bitta hujjatni 10 bosqich orqali o'tkazadi va natijani diskka yozadi.

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §4
DETECT -> INGEST -> STRUCTURE -> TRANSLIT -> LANGUAGE -> QUALITY ->
NORMALIZE -> DEDUP -> WRITE -> STATS
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ufl.clean.dedup import DeduplicationStore
from ufl.clean.language import FastTextPredictor, is_uzbek
from ufl.clean.normalize import normalize
from ufl.clean.quality import assess
from ufl.clean.structure import clean_structure
from ufl.clean.transliterate import to_latin
from ufl.ingest import detect as detect_module
from ufl.ingest import djvu as djvu_module
from ufl.ingest import docx as docx_module
from ufl.ingest import epub as epub_module
from ufl.ingest import fb2 as fb2_module
from ufl.ingest import html as html_module
from ufl.ingest import pdf as pdf_module
from ufl.ingest import txt as txt_module
from ufl.ingest.base import Document
from ufl.stats.tokens import TokenCounter, count_tokens

_EXTRACTORS = {
    "pdf": pdf_module.extract,
    "djvu": djvu_module.extract,
    "epub": epub_module.extract,
    "docx": docx_module.extract,
    "fb2": fb2_module.extract,
    "html": html_module.extract,
    "txt": txt_module.extract,
}


@dataclass
class DroppedBlock:
    text: str
    page: int
    reason: str


@dataclass
class ProcessResult:
    source_path: Path
    category: str
    format: str
    kept_text: str
    dropped: list[DroppedBlock] = field(default_factory=list)
    char_count: int = 0
    estimated_tokens: int = 0
    exact_tokens: int | None = None
    total_blocks: int = 0
    kept_blocks: int = 0


def process_file(
    path: Path,
    *,
    category: str,
    dedup_store: DeduplicationStore,
    fasttext_predict: FastTextPredictor | None = None,
    exact_token_counter: TokenCounter | None = None,
    chars_per_token: float = 4.0,
    header_footer_min_repeats: int = 3,
    detect_toc: bool = True,
    detect_bibliography: bool = True,
    min_language_confidence: float = 0.65,
    min_heuristic_score: float = 0.20,
    apostrophe_mode: str = "ascii",
    quality_kwargs: dict | None = None,
) -> ProcessResult:
    file_format = detect_module.detect_format(path)
    extractor = _EXTRACTORS.get(file_format)
    if extractor is None:
        raise ValueError(f"Qo'llab-quvvatlanmaydigan format: {file_format} ({path})")

    document: Document = extractor(path)

    structure_result = clean_structure(
        document,
        header_footer_min_repeats=header_footer_min_repeats,
        detect_toc=detect_toc,
        detect_bibliography=detect_bibliography,
    )

    dropped: list[DroppedBlock] = [
        DroppedBlock(text=block.text, page=block.page, reason=reason)
        for block, reason in structure_result.dropped
    ]

    kept_paragraphs: list[str] = []

    for block in structure_result.kept_blocks:
        latin_text = to_latin(block.text)

        lang_result = is_uzbek(
            latin_text,
            fasttext_predict=fasttext_predict,
            min_confidence=min_language_confidence,
            min_heuristic_score=min_heuristic_score,
        )
        if not lang_result.is_uzbek:
            dropped.append(DroppedBlock(text=block.text, page=block.page, reason="til_ozbekcha_emas"))
            continue

        quality_result = assess(latin_text, **(quality_kwargs or {}))
        if not quality_result.keep:
            reason = quality_result.reason or "sifat"
            dropped.append(DroppedBlock(text=block.text, page=block.page, reason=reason))
            continue

        normalized_text = normalize(latin_text, apostrophe_mode=apostrophe_mode)
        if not normalized_text:
            dropped.append(DroppedBlock(text=block.text, page=block.page, reason="normalizatsiyadan_song_bosh"))
            continue

        if dedup_store.check_and_add(normalized_text):
            dropped.append(DroppedBlock(text=block.text, page=block.page, reason="takror"))
            continue

        kept_paragraphs.append(normalized_text)

    kept_text = "\n\n".join(kept_paragraphs)
    token_counts = count_tokens(
        kept_text, chars_per_token=chars_per_token, exact_counter=exact_token_counter
    )

    return ProcessResult(
        source_path=path,
        category=category,
        format=file_format,
        kept_text=kept_text,
        dropped=dropped,
        char_count=token_counts.char_count,
        estimated_tokens=token_counts.estimated_tokens,
        exact_tokens=token_counts.exact_tokens,
        total_blocks=len(document.blocks),
        kept_blocks=len(kept_paragraphs),
    )


def write_output(
    result: ProcessResult, *, output_dir: Path, rejected_dir: Path, reports_dir: Path
) -> Path:
    """Natijalarni diskka yozadi: .txt, rejected/*.jsonl, reports/*.json. .txt yo'lini qaytaradi."""
    category_output_dir = Path(output_dir) / result.category
    category_output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = category_output_dir / f"{result.source_path.stem}.txt"
    txt_path.write_text(result.kept_text, encoding="utf-8")

    if result.dropped:
        rejected_category_dir = Path(rejected_dir) / result.category
        rejected_category_dir.mkdir(parents=True, exist_ok=True)
        rejected_path = rejected_category_dir / f"{result.source_path.stem}.jsonl"
        with rejected_path.open("w", encoding="utf-8") as f:
            for item in result.dropped:
                f.write(
                    json.dumps(
                        {"text": item.text, "page": item.page, "reason": item.reason},
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    reports_path = Path(reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)
    report_path = reports_path / f"{result.source_path.stem}.json"
    dropped_count = len(result.dropped)
    report = {
        "source": str(result.source_path),
        "category": result.category,
        "format": result.format,
        "char_count": result.char_count,
        "estimated_tokens": result.estimated_tokens,
        "exact_tokens": result.exact_tokens,
        "total_blocks": result.total_blocks,
        "kept_blocks": result.kept_blocks,
        "dropped_blocks": dropped_count,
        "dropped_pct": round(dropped_count / result.total_blocks * 100, 2) if result.total_blocks else 0.0,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return txt_path
