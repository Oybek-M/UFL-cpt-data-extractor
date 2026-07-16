"""UFL CLI — `ufl version|run|stats`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table

from ufl import __version__
from ufl.cleanup import cleanup_logs
from ufl.clean.dedup import DeduplicationStore
from ufl.clean.language import load_fasttext_predictor
from ufl.config import Config
from ufl.crawl.collector import Collector
from ufl.crawl.minimax import MiniMaxClient
from ufl.crawl.state import CrawlState
from ufl.crawl.urls import domain_folder, prepare_url
from ufl.crawl.web_client import RobotsPolicy, WebClient
from ufl.crawl.writer import BundledWriter
from ufl.logging_setup import setup_logging
from ufl.pipeline import process_file, write_output
from ufl.stats.budget import compute_budget, total_budget
from ufl.stats.tokens import load_tokenizer_counter
from ufl.store.db import BookRecord, Store

app = typer.Typer(name="ufl", help="Uzbek CPT data pipeline — kitoblardan toza matn ajratib olish.")
console = Console()

CRAWL_CATEGORIES = [
    "web_news", "gov_legal", "education", "reference",
    "books", "conversations", "technical", "domain_haf",
]


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
    list_books: bool = typer.Option(False, "--list", help="Barcha qayta ishlangan hujjatlarni ro'yxatlash"),
    remove: str = typer.Option(None, "--remove", help="Ko'rsatilgan path bo'yicha yozuvni o'chirish (byudjetdan chiqarish)"),
    clear_category: str = typer.Option(None, "--clear-category", help="Kategoriyadagi barcha yozuvlarni o'chirish"),
    clear_all: bool = typer.Option(False, "--clear-all", help="Butun byudjetni (barcha yozuvlarni) tozalash"),
) -> None:
    """Jamlanma statistika va byudjet progressni ko'rsatish, yoki byudjetni qo'lda boshqarish."""
    setup_logging()
    config = Config.load(config_path)

    with Store(config.paths.db) as store:
        if remove:
            removed = store.remove_book(remove)
            console.print(f"[green]O'chirildi[/green]" if removed else "[yellow]Topilmadi[/yellow]", remove)
        if clear_category:
            n = store.clear_category(clear_category)
            console.print(f"[green]{n} ta yozuv o'chirildi[/green] (kategoriya: {clear_category})")
        if clear_all:
            n = store.clear_all()
            console.print(f"[green]{n} ta yozuv o'chirildi[/green] (butun byudjet tozalandi)")
        if list_books:
            for book in store.list_books():
                console.print(f"  [{book.category}] {book.path} — {book.estimated_tokens:,} token")

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


def _build_web_client(config: Config) -> WebClient:
    return WebClient(
        user_agent=config.crawl.user_agent,
        request_delay=config.crawl.request_delay,
        timeout=config.crawl.request_timeout,
    )


def _resolve_minimax_key() -> str:
    """MINIMAX_API_KEY env'dan; topilmasa va terminal interaktiv bo'lsa, foydalanuvchidan
    qo'lda so'raladi (na'munaviy loyihadagi kabi). Kalit hech qachon log/DB'ga yozilmaydi."""
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if key or not sys.stdin.isatty():
        return key
    entered = typer.prompt(
        "MiniMax API kaliti (ixtiyoriy; faqat local ekstraksiya uchun bo'sh qoldiring)",
        default="",
        show_default=False,
        hide_input=True,
    )
    return entered.strip()


def _build_minimax(config: Config, state: CrawlState) -> MiniMaxClient | None:
    key = _resolve_minimax_key()
    if not key:
        return None
    return MiniMaxClient(
        key,
        state,
        model=config.minimax.model,
        url=config.minimax.url,
        min_confidence=config.minimax.min_confidence,
    )


@app.command()
def crawl(
    url: str = typer.Argument(..., help="Crawl qilinadigan sayt manzili (masalan https://kun.uz)"),
    category: str = typer.Option(
        ..., "--category", help="8 kategoriyadan biri yoki 'auto' (MiniMax kalibrlash — Faza 4.7)"
    ),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
    max_articles: int = typer.Option(
        0, "--max-articles", help="Shuncha maqola yig'ilgandan keyin to'xtash (0 — cheklovsiz)"
    ),
    once: bool = typer.Option(
        False, "--once", help="Navbat bo'shaguncha ishlab, keyin to'xtash (uzluksiz emas)"
    ),
    max_steps: int = typer.Option(0, "--max-steps", help="Shuncha qadamdan keyin to'xtash (0 — cheklovsiz)"),
) -> None:
    """Sayt/blog/portaldan toza o'zbekcha matn yig'ish (resumable, newest-first)."""
    setup_logging()
    if category != "auto" and category not in CRAWL_CATEGORIES:
        console.print(
            f"[bold red]Xato:[/bold red] noto'g'ri kategoriya '{category}'. "
            f"Ruxsat etilgan: {', '.join(CRAWL_CATEGORIES)} yoki 'auto'."
        )
        raise typer.Exit(code=1)

    config = Config.load(config_path)
    seed = prepare_url(url)
    domain = domain_folder(seed)

    state = CrawlState(config.crawl.output_dir / domain / "_state")
    web = _build_web_client(config)
    robots = RobotsPolicy(seed, web, user_agent=config.crawl.user_agent)
    store = Store(config.paths.db)
    exact_token_counter = load_tokenizer_counter(config.tokenizer.local_dir, config.tokenizer.model_id)
    writer = BundledWriter(
        config.crawl.output_dir,
        state=state,
        domain=domain,
        store=store,
        shard_limit_bytes=config.crawl.shard_limit_bytes,
        exact_token_counter=exact_token_counter,
        chars_per_token=config.tokenizer.chars_per_token,
    )
    fasttext_predict = load_fasttext_predictor(config.language.fasttext_model_path)
    quality_kwargs = {
        "min_chars": config.quality.min_chars,
        "min_words": config.quality.min_words,
        "max_non_letter_ratio": config.quality.max_non_letter_ratio,
        "max_repeated_ngram_ratio": config.quality.max_repeated_ngram_ratio,
        "max_upper_ratio": config.quality.max_upper_ratio,
        "max_url_ratio": config.quality.max_url_ratio,
    }

    minimax = _build_minimax(config, state)
    if minimax is not None:
        console.print("[green]MiniMax AI yoqildi[/green] (faqat ambigu sahifalar uchun ishlatiladi).")

    collector = Collector(
        seed,
        state=state,
        web=web,
        robots=robots,
        writer=writer,
        category_mode=category,
        valid_categories=CRAWL_CATEGORIES,
        minimax=minimax,
        fasttext_predict=fasttext_predict,
        min_language_confidence=config.language.min_confidence,
        min_heuristic_score=config.language.min_heuristic_score,
        apostrophe_mode=config.normalize.apostrophe_mode,
        quality_kwargs=quality_kwargs,
        min_clean_chars=config.crawl.min_clean_chars,
        min_local_chars=config.crawl.min_local_chars,
    )

    console.print(f"[bold]Crawl boshlandi:[/bold] {seed} (domen: {domain}, kategoriya: {category})")
    try:
        collector.run(once=once, max_steps=max_steps, max_articles=max_articles)
        final_counts = state.counts()
    finally:
        store.close()
        web.close()
        state.close()

    console.print(f"[bold green]Tugadi.[/bold green] Holat: {final_counts}")


@app.command(name="crawl-status")
def crawl_status(
    url: str = typer.Argument(..., help="Holatini ko'rish uchun sayt manzili"),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
    """Berilgan domen uchun crawl holatini (yig'ilgan/kutayotgan/rad) ko'rsatish."""
    setup_logging()
    config = Config.load(config_path)
    seed = prepare_url(url)
    domain = domain_folder(seed)

    with CrawlState(config.crawl.output_dir / domain / "_state") as state:
        counts = state.counts()

    table = Table(title=f"Crawl holati — {domain}")
    table.add_column("Status", style="bold")
    table.add_column("Soni", justify="right")
    for status, count in sorted(counts.items()):
        table.add_row(status, str(count))
    console.print(table)


@app.command()
def cleanup(
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
    older_than_days: int = typer.Option(
        30, "--older-than-days", help="Shu kundan eski rejected/reports fayllari o'chiriladi"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Faqat qaysi fayllar o'chirilishini ko'rsatadi, o'chirmaydi"
    ),
) -> None:
    """rejected/ va reports/ diagnostika loglarini tozalash (data/output/*.txt'ga tegilmaydi)."""
    setup_logging()
    config = Config.load(config_path)
    result = cleanup_logs(
        rejected_dir=config.paths.rejected,
        reports_dir=config.paths.reports,
        older_than_days=older_than_days,
        dry_run=dry_run,
    )
    if dry_run:
        for path in result.removed_files:
            console.print(f"  {path}")
        console.print(
            f"[yellow]{len(result.removed_files)} ta fayl o'chirilishi mumkin[/yellow] "
            f"({result.freed_bytes:,} bayt) — dry-run, hech narsa o'chirilmadi"
        )
    else:
        console.print(
            f"[green]{len(result.removed_files)} ta fayl o'chirildi[/green] "
            f"({result.freed_bytes:,} bayt bo'shatildi)"
        )


if __name__ == "__main__":
    app()
