"""Pipeline: bitta hujjatni 10 bosqich orqali o'tkazadi va natijani diskka yozadi.

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §4
DETECT -> INGEST -> STRUCTURE -> TRANSLIT -> LANGUAGE -> QUALITY ->
NORMALIZE -> DEDUP -> WRITE -> STATS
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ufl.clean.apply import clean_paragraphs
from ufl.clean.dedup import DeduplicationStore
from ufl.clean.language import FastTextPredictor
from ufl.clean.structure import clean_structure, find_ambiguous_kept_blocks
from ufl.crawl.minimax import MiniMaxClient
from ufl.ingest import detect as detect_module
from ufl.ingest import djvu as djvu_module
from ufl.ingest import docx as docx_module
from ufl.ingest import epub as epub_module
from ufl.ingest import fb2 as fb2_module
from ufl.ingest import html as html_module
from ufl.ingest import pdf as pdf_module
from ufl.ingest import pptx as pptx_module
from ufl.ingest import txt as txt_module
from ufl.ingest.base import Document
from ufl.stats.tokens import TokenCounter, count_tokens

_EXTRACTORS = {
    "pdf": pdf_module.extract,
    "djvu": djvu_module.extract,
    "epub": epub_module.extract,
    "docx": docx_module.extract,
    "pptx": pptx_module.extract,
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
    minimax: MiniMaxClient | None = None,
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

    # Ixtiyoriy (opt-in): evristika "shubhali" deb qoldirgan bloklarni MiniMax'ga bitta
    # so'rovda tekshiradi (token-tejamkor — faqat shunday bloklar bo'lsagina chaqiriladi,
    # matnni hech qachon o'zi tahrirlamaydi, faqat qoldirish/tashlash qarori beradi).
    if minimax is not None:
        ambiguous_blocks = find_ambiguous_kept_blocks(structure_result.kept_blocks)
        if ambiguous_blocks:
            labeled = [(str(index), block.text) for index, block in enumerate(ambiguous_blocks)]
            drop_ids = minimax.arbitrate_noise_blocks(path.stem, labeled)
            if drop_ids:
                to_drop = {id(ambiguous_blocks[int(bid)]) for bid in drop_ids}
                for bid in drop_ids:
                    block = ambiguous_blocks[int(bid)]
                    dropped.append(
                        DroppedBlock(text=block.text, page=block.page, reason="minimax_shovqin")
                    )
                structure_result.kept_blocks = [
                    block for block in structure_result.kept_blocks if id(block) not in to_drop
                ]

    def _record_drop(block: object, reason: str) -> None:
        dropped.append(DroppedBlock(text=block.text, page=block.page, reason=reason))  # type: ignore[attr-defined]

    kept_paragraphs = clean_paragraphs(
        structure_result.kept_blocks,
        dedup_store=dedup_store,
        get_text=lambda block: block.text,
        fasttext_predict=fasttext_predict,
        min_language_confidence=min_language_confidence,
        min_heuristic_score=min_heuristic_score,
        apostrophe_mode=apostrophe_mode,
        quality_kwargs=quality_kwargs,
        on_drop=_record_drop,
    )

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
