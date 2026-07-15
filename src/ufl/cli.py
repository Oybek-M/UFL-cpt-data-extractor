"""UFL CLI — `ufl version|run|stats`."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table

from ufl import __version__
from ufl.clean.dedup import DeduplicationStore
from ufl.clean.language import load_fasttext_predictor
from ufl.config import Config
from ufl.logging_setup import setup_logging
from ufl.pipeline import process_file, write_output
from ufl.stats.budget import compute_budget, total_budget
from ufl.stats.tokens import load_tokenizer_counter
from ufl.store.db import BookRecord, Store

app = typer.Typer(name="ufl", help="Uzbek CPT data pipeline — kitoblardan toza matn ajratib olish.")
console = Console()


@app.command()
def version() -> None:
    """UFL versiyasini chiqarish."""
    console.print(f"ufl [bold green]{__version__}[/bold green]")


@app.command()
def run(
    input_path: Path = typer.Argument(..., help="Fayl yoki papka yo'li (masalan data/input)"),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
    force: bool = typer.Option(
        False, "--force", help="Allaqachon qayta ishlangan fayllarni ham qayta ishlash"
    ),
) -> None:
    """Berilgan papkadagi fayllarni pipeline orqali qayta ishlash."""
    setup_logging()
    config = Config.load(config_path)

    if not input_path.exists():
        console.print(f"[bold red]Xato:[/bold red] '{input_path}' topilmadi.")
        raise typer.Exit(code=1)

    files = _collect_files(input_path)
    if not files:
        console.print("[yellow]Hech qanday fayl topilmadi.[/yellow]")
        return

    console.print(f"[bold]{len(files)}[/bold] fayl topildi: {input_path}")

    fasttext_predict = load_fasttext_predictor(config.language.fasttext_model_path)
    exact_token_counter = load_tokenizer_counter(config.tokenizer.local_dir, config.tokenizer.model_id)
    if fasttext_predict is None:
        console.print("[yellow]fastText modeli topilmadi — faqat gevristika bilan davom etiladi.[/yellow]")
    if exact_token_counter is None:
        console.print("[yellow]Gemma tokenizer topilmadi — faqat taxminiy token hisobi ishlatiladi.[/yellow]")

    dedup_store = DeduplicationStore()
    quality_kwargs = {
        "min_chars": config.quality.min_chars,
        "min_words": config.quality.min_words,
        "max_non_letter_ratio": config.quality.max_non_letter_ratio,
        "max_repeated_ngram_ratio": config.quality.max_repeated_ngram_ratio,
        "max_upper_ratio": config.quality.max_upper_ratio,
        "max_url_ratio": config.quality.max_url_ratio,
    }

    ok_count = 0
    skip_count = 0
    error_count = 0
    total_estimated_tokens = 0

    with Store(config.paths.db) as store:
        for file_path in track(files, description="Qayta ishlanmoqda...", console=console):
            category = _infer_category(file_path, input_path)
            source_key = str(file_path)
            if store.is_processed(source_key) and not force:
                skip_count += 1
                continue

            try:
                result = process_file(
                    file_path,
                    category=category,
                    dedup_store=dedup_store,
                    fasttext_predict=fasttext_predict,
                    exact_token_counter=exact_token_counter,
                    chars_per_token=config.tokenizer.chars_per_token,
                    header_footer_min_repeats=config.structure.header_footer_min_repeats,
                    detect_toc=config.structure.detect_toc,
                    detect_bibliography=config.structure.detect_bibliography,
                    min_language_confidence=config.language.min_confidence,
                    min_heuristic_score=config.language.min_heuristic_score,
                    apostrophe_mode=config.normalize.apostrophe_mode,
                    quality_kwargs=quality_kwargs,
                )
                write_output(
                    result,
                    output_dir=config.paths.output,
                    rejected_dir=config.paths.rejected,
                    reports_dir=config.paths.reports,
                )
                dropped_pct = (
                    len(result.dropped) / result.total_blocks * 100 if result.total_blocks else 0.0
                )
                store.record_book(
                    BookRecord(
                        path=source_key,
                        category=category,
                        format=result.format,
                        char_count=result.char_count,
                        estimated_tokens=result.estimated_tokens,
                        exact_tokens=result.exact_tokens,
                        total_blocks=result.total_blocks,
                        kept_blocks=result.kept_blocks,
                        dropped_pct=round(dropped_pct, 2),
                    )
                )
            except Exception as exc:  # noqa: BLE001 — fayl izolyatsiyasi: batch to'xtamasin
                error_count += 1
                console.print(f"[red]Xato:[/red] {file_path} — {exc}")
                continue

            ok_count += 1
            total_estimated_tokens += result.estimated_tokens

    console.print(
        f"\n[bold green]Tugadi.[/bold green] Muvaffaqiyatli: {ok_count}, "
        f"O'tkazib yuborildi: {skip_count}, Xato: {error_count}. "
        f"Taxminiy yig'ilgan token: {total_estimated_tokens:,}"
    )


def _collect_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(p for p in input_path.rglob("*") if p.is_file() and not p.name.startswith("."))


def _infer_category(file_path: Path, root: Path) -> str:
    if root.is_file():
        return "uncategorized"
    try:
        relative = file_path.relative_to(root)
    except ValueError:
        return "uncategorized"
    return relative.parts[0] if len(relative.parts) > 1 else "uncategorized"


@app.command()
def stats(
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
    """Jamlanma statistika va byudjet progressni ko'rsatish."""
    setup_logging()
    config = Config.load(config_path)

    with Store(config.paths.db) as store:
        collected = store.collected_tokens_by_category()
        book_count = store.book_count()

    budgets = compute_budget(config.budget.categories, collected)
    total = total_budget(budgets)

    table = Table(title="UFL — Uzbek CPT byudjet progressi")
    table.add_column("Kategoriya", style="bold")
    table.add_column("Yig'ilgan", justify="right")
    table.add_column("Maqsad", justify="right")
    table.add_column("Progress", justify="right")

    for budget in sorted(budgets, key=lambda b: b.category):
        table.add_row(
            budget.category,
            f"{budget.collected_tokens:,}",
            f"{budget.target_tokens:,}",
            f"{budget.progress_pct:.1f}%",
        )
    table.add_section()
    table.add_row(
        f"[bold]{total.category}[/bold]",
        f"[bold]{total.collected_tokens:,}[/bold]",
        f"[bold]{total.target_tokens:,}[/bold]",
        f"[bold]{total.progress_pct:.1f}%[/bold]",
    )

    console.print(table)
    console.print(f"Jami qayta ishlangan kitob/hujjat: [bold]{book_count}[/bold]")


if __name__ == "__main__":
    app()
