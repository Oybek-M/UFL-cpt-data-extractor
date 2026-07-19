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
from ufl.clean.quality import strip_garbage_tokens
from ufl.config import Config
from ufl.crawl.collector import Collector
from ufl.crawl.minimax import InMemoryMetaState, MiniMaxClient
from ufl.crawl.state import CrawlState
from ufl.crawl.urls import domain_folder, prepare_url
from ufl.crawl.web_client import RobotsPolicy, WebClient
from ufl.crawl.writer import BundledWriter
from ufl.finalize.dedup import find_duplicate_groups, quarantine_duplicates
from ufl.finalize.hf_rename import match_hf_shard_filename, renamed_filename
from ufl.finalize.pii import scrub_pii
from ufl.hf_pipeline import process_hf_shard
from ufl.ingest.hf_dataset import SHARD_SIZE, dataset_slug, iter_shards
from ufl.logging_setup import setup_logging
from ufl.pipeline import process_file, write_output
from ufl.stats.budget import compute_budget, total_budget
from ufl.stats.tokens import load_tokenizer_counter
from ufl.store.db import BookRecord, Store
from ufl.store.hf_state import HFFetchState
from ufl.ziyouz.catalog import walk_catalog
from ufl.ziyouz.category_map import resolve_ufl_category

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
    verify_with_minimax: bool = typer.Option(
        False,
        "--verify-with-minimax",
        help=(
            "Evristika 'shubhali' deb qoldirgan bloklarni (front-matter/kolontitul/"
            "bibliografiyaga o'xshash) MiniMax'ga tekshirtirish (ixtiyoriy, bitta "
            "hujjat uchun bitta so'rov — token-tejamkor, matnni tahrirlamaydi)"
        ),
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
    total_exact_tokens = 0
    minimax_dropped_count = 0
    valid_categories = list(config.budget.categories)
    # MiniMax faqat kategoriya-papkasiz (tekis joylashtirilgan) fayl uchraganda, birinchi
    # marta kerak bo'lganda quriladi — barcha fayl to'g'ri papkalarda bo'lsa, umuman
    # chaqirilmaydi/prompt qilinmaydi (token va UX tejash).
    minimax_holder: dict[str, MiniMaxClient | None] = {}

    def _minimax_for_run() -> MiniMaxClient | None:
        if "client" not in minimax_holder:
            minimax_holder["client"] = _build_minimax(config, InMemoryMetaState())
        return minimax_holder["client"]

    with Store(config.paths.db) as store:
        for file_path in track(files, description="Qayta ishlanmoqda...", console=console):
            folder_category = _infer_category(file_path, input_path)
            source_key = str(file_path)
            if store.is_processed(source_key) and not force:
                skip_count += 1
                continue

            try:
                result = process_file(
                    file_path,
                    category=folder_category,
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
                    minimax=_minimax_for_run() if verify_with_minimax else None,
                )
                category = folder_category
                if folder_category == "uncategorized":
                    category = _resolve_file_category(
                        file_path, result.kept_text[:400], valid_categories, _minimax_for_run()
                    )
                    result.category = category
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
            total_exact_tokens += (
                result.exact_tokens if result.exact_tokens is not None else result.estimated_tokens
            )
            minimax_dropped_count += sum(1 for d in result.dropped if d.reason == "minimax_shovqin")

    if exact_token_counter is not None:
        token_summary = f"Aniq yig'ilgan token: {total_exact_tokens:,}"
    else:
        token_summary = f"Taxminiy yig'ilgan token: {total_estimated_tokens:,}"
    console.print(
        f"\n[bold green]Tugadi.[/bold green] Muvaffaqiyatli: {ok_count}, "
        f"O'tkazib yuborildi: {skip_count}, Xato: {error_count}. {token_summary}"
    )
    if verify_with_minimax:
        console.print(f"MiniMax orqali qo'shimcha olib tashlangan shubhali bloklar: {minimax_dropped_count}")


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


def _resolve_file_category(
    file_path: Path,
    snippet: str,
    valid_categories: list[str],
    minimax: MiniMaxClient | None,
) -> str:
    """Papka-kategoriyasi bo'lmagan (tekis joylashtirilgan) fayllar uchun: MiniMax bilan
    urinib ko'radi (ixtiyoriy, faqat shu holatda chaqiriladi — token tejash), topolmasa
    yoki kalitsiz bo'lsa "books"ga tushadi (fayllar odatda kitob/hujjat-tipidagi manba)."""
    if minimax is not None:
        guess = minimax.classify_category(file_path.stem, snippet, valid_categories)
        if guess:
            return guess
    return "books" if "books" in valid_categories else "uncategorized"


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
                tokens = book.exact_tokens if book.exact_tokens is not None else book.estimated_tokens
                console.print(f"  [{book.category}] {book.path} — {tokens:,} token")

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


def _build_minimax(config: Config, state: CrawlState | InMemoryMetaState) -> MiniMaxClient | None:
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


@app.command("fetch-hf")
def fetch_hf(
    dataset_id: str = typer.Argument(..., help="HuggingFace dataset ID (masalan tahrirchi/uz-crawl)"),
    split: str = typer.Option(..., "--split", help="Dataset split nomi (masalan train, news, lat)"),
    category: str = typer.Option(..., "--category", help="8 kategoriyadan biri"),
    text_column: str = typer.Option("text", "--text-column", help="Matn ustuni nomi"),
    limit: int = typer.Option(0, "--limit", help="Shuncha qatordan keyin to'xtash (0 — cheklovsiz)"),
    stop_at_budget: bool = typer.Option(
        False, "--stop-at-budget",
        help="Kategoriya budjet-maqsadiga yetgach avtomatik to'xtash (standart: o'chiq — dataset oxirigacha ishlanadi)",
    ),
    shard_size: int = typer.Option(
        0, "--shard-size",
        help="Har shardning qator soni (0 — global standart yoki bu dataset+split uchun saqlangan qiymat)",
    ),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
    """HuggingFace dataset'dan qator-baqator (streaming) toza matn yig'ish."""
    setup_logging()
    if category not in CRAWL_CATEGORIES:
        console.print(
            f"[bold red]Xato:[/bold red] noto'g'ri kategoriya '{category}'. "
            f"Ruxsat etilgan: {', '.join(CRAWL_CATEGORIES)}."
        )
        raise typer.Exit(code=1)

    config = Config.load(config_path)
    slug = dataset_slug(dataset_id)
    state_path = config.paths.db.parent / "hf_state" / f"{slug}__{split}.sqlite3"
    fasttext_predict = load_fasttext_predictor(config.language.fasttext_model_path)
    exact_token_counter = load_tokenizer_counter(config.tokenizer.local_dir, config.tokenizer.model_id)
    quality_kwargs = {
        "min_chars": config.quality.min_chars,
        "min_words": config.quality.min_words,
        "max_non_letter_ratio": config.quality.max_non_letter_ratio,
        "max_repeated_ngram_ratio": config.quality.max_repeated_ngram_ratio,
        "max_upper_ratio": config.quality.max_upper_ratio,
        "max_url_ratio": config.quality.max_url_ratio,
    }
    dedup_store = DeduplicationStore()

    with HFFetchState(state_path) as state, Store(config.paths.db) as store:
        key = f"{dataset_id}::{split}"
        stored_shard_size = state.get_shard_size(key)
        if stored_shard_size is not None:
            if shard_size and shard_size != stored_shard_size:
                console.print(
                    f"[bold red]Xato:[/bold red] '{key}' uchun avval --shard-size "
                    f"{stored_shard_size} bilan progress saqlangan, lekin {shard_size} berildi. "
                    f"Resumability'ni buzmaslik uchun --shard-size {stored_shard_size} ishlating "
                    "yoki uni butunlay tashlab qo'ying."
                )
                raise typer.Exit(code=1)
            effective_shard_size = stored_shard_size
        else:
            effective_shard_size = shard_size or SHARD_SIZE
            state.set_shard_size(key, effective_shard_size)

        shard_index = state.get_last_shard(key)
        skip_rows = shard_index * effective_shard_size
        ok_shards = 0
        processed_rows = 0
        kept_total = 0

        for texts in iter_shards(
            dataset_id, split, text_column,
            shard_size=effective_shard_size, skip_rows=skip_rows, limit=limit,
        ):
            shard_index += 1
            shard_label = f"{slug}__{split}__shard-{shard_index:06d}"
            result = process_hf_shard(
                texts,
                shard_label=shard_label,
                category=category,
                dedup_store=dedup_store,
                fasttext_predict=fasttext_predict,
                exact_token_counter=exact_token_counter,
                chars_per_token=config.tokenizer.chars_per_token,
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
                    path=f"hf:{dataset_id}:{split}:shard-{shard_index:06d}",
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
            state.set_last_shard(key, shard_index)
            ok_shards += 1
            processed_rows += len(texts)
            kept_total += result.kept_blocks
            console.print(
                f"Shard {shard_index}: {result.kept_blocks}/{result.total_blocks} saqlandi "
                f"({result.exact_tokens or result.estimated_tokens:,} token)."
            )

            if stop_at_budget:
                collected = store.collected_tokens_by_category()
                target = config.budget.categories.get(category)
                if target and collected.get(category, 0) >= target:
                    console.print(
                        f"[green]Budjet maqsadiga yetildi[/green] "
                        f"({category}: {collected[category]:,}/{target:,}). To'xtatilmoqda."
                    )
                    break

    # `datasets` kutubxonasining ba'zi native (pyarrow) thread'lari interpreter
    # tugaganda tozalanmasdan xato berishi mumkin (kuzatilgan: PyGILState_Release
    # crash) — aniq tozalash bu holatni oldini oladi.
    import gc

    gc.collect()

    console.print(
        f"\n[bold green]Tugadi.[/bold green] {ok_shards} shard qayta ishlandi "
        f"({processed_rows:,} qator, {kept_total:,} saqlandi)."
    )


ZIYOUZ_SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".docx", ".doc", ".fb2", ".djvu", ".txt", ".html"}
ZIYOUZ_MAX_FILE_BYTES = 200 * 1024 * 1024


@app.command("fetch-ziyouz")
def fetch_ziyouz(
    category: str = typer.Option(
        None, "--category", help="Faqat shu UFL kategoriyasidagi elementlarni yuklash (bo'sh — hammasi)"
    ),
    limit: int = typer.Option(0, "--limit", help="Shuncha elementdan keyin to'xtash (0 — cheklovsiz)"),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
    """ziyouz.com "Kutubxona" bo'limidan ommaviy fayl yuklab, UFL pipeline'idan o'tkazish."""
    setup_logging()
    if category is not None and category not in CRAWL_CATEGORIES:
        console.print(
            f"[bold red]Xato:[/bold red] noto'g'ri kategoriya '{category}'. "
            f"Ruxsat etilgan: {', '.join(CRAWL_CATEGORIES)}."
        )
        raise typer.Exit(code=1)

    config = Config.load(config_path)
    web = _build_web_client(config)
    fasttext_predict = load_fasttext_predictor(config.language.fasttext_model_path)
    exact_token_counter = load_tokenizer_counter(config.tokenizer.local_dir, config.tokenizer.model_id)
    quality_kwargs = {
        "min_chars": config.quality.min_chars,
        "min_words": config.quality.min_words,
        "max_non_letter_ratio": config.quality.max_non_letter_ratio,
        "max_repeated_ngram_ratio": config.quality.max_repeated_ngram_ratio,
        "max_upper_ratio": config.quality.max_upper_ratio,
        "max_url_ratio": config.quality.max_url_ratio,
    }
    dedup_store = DeduplicationStore()
    tmp_dir = config.paths.db.parent / "tmp_ziyouz"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    skip_count = 0
    error_count = 0
    unmapped_categories: set[str] = set()

    try:
        with Store(config.paths.db) as store:
            for item_id, slug, joomla_category, download_url in walk_catalog(web):
                if limit and ok_count >= limit:
                    break

                source_key = f"ziyouz:{item_id}"
                if store.is_processed(source_key):
                    skip_count += 1
                    continue

                ufl_category = resolve_ufl_category(joomla_category)
                if ufl_category is None:
                    if joomla_category not in unmapped_categories:
                        unmapped_categories.add(joomla_category)
                        console.print(
                            f"[yellow]Noma'lum kategoriya:[/yellow] '{joomla_category}' — "
                            "o'tkazib yuborilmoqda (category_map.py ga qo'shish mumkin)."
                        )
                    skip_count += 1
                    continue
                if category is not None and ufl_category != category:
                    skip_count += 1
                    continue

                try:
                    response = web.get(download_url)
                except Exception as exc:  # noqa: BLE001 — bitta faylni izolyatsiya qilish
                    error_count += 1
                    console.print(f"[red]Yuklab olishda xato:[/red] {download_url} — {exc}")
                    continue

                final_url = str(getattr(response, "url", download_url))
                extension = Path(final_url.split("?")[0]).suffix.lower()
                if extension not in ZIYOUZ_SUPPORTED_EXTENSIONS:
                    skip_count += 1
                    continue
                if len(response.content) > ZIYOUZ_MAX_FILE_BYTES:
                    skip_count += 1
                    continue

                tmp_path = tmp_dir / f"{item_id}_{slug}{extension}"
                tmp_path.write_bytes(response.content)
                try:
                    result = process_file(
                        tmp_path,
                        category=ufl_category,
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
                            category=ufl_category,
                            format=result.format,
                            char_count=result.char_count,
                            estimated_tokens=result.estimated_tokens,
                            exact_tokens=result.exact_tokens,
                            total_blocks=result.total_blocks,
                            kept_blocks=result.kept_blocks,
                            dropped_pct=round(dropped_pct, 2),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 — bitta faylni izolyatsiya qilish
                    error_count += 1
                    console.print(f"[red]Qayta ishlashda xato:[/red] {download_url} — {exc}")
                    continue
                finally:
                    tmp_path.unlink(missing_ok=True)

                ok_count += 1
                console.print(f"[green]OK[/green] {ufl_category}: {joomla_category} — {item_id}")
    finally:
        web.close()

    console.print(
        f"\n[bold green]Tugadi.[/bold green] Muvaffaqiyatli: {ok_count}, "
        f"O'tkazib yuborildi: {skip_count}, Xato: {error_count}."
    )


@app.command("finalize-corpus")
def finalize_corpus(
    apply: bool = typer.Option(
        False, "--apply", help="Haqiqiy o'zgarish qilish (standart: faqat hisobot, dry-run)"
    ),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
    """Yig'ilgan korpusni jamoaga topshirishdan oldin tayyorlaydi: global dedup,
    PII tozalash, HF dataset manbasini fayl nomidan yashirish, OCR-chiqindi
    tokenlarni tozalash.

    Bosqich tartibi muhim: dedup va PII HF fayllarni asl (dataset_slug asosidagi)
    nomi bilan aniqlaydi, shuning uchun rename doim OXIRIDA (3-bosqich) ishlaydi.
    OCR-chiqindi tozalash (4-bosqich) fayl nomiga bog'liq emas, shuning uchun
    rename'dan keyin yoki oldin ishlashi farqi yo'q — soddalik uchun oxirida."""
    setup_logging()
    config = Config.load(config_path)
    output_dir = config.paths.output
    rejected_dir = config.paths.rejected

    with Store(config.paths.db) as store:
        # 1. Global dedup
        groups = find_duplicate_groups(output_dir)
        dup_file_count = sum(len(g.duplicates) for g in groups)
        console.print(
            f"[bold]Dedup:[/bold] {len(groups)} guruh, {dup_file_count} dublikat fayl topildi."
        )
        if apply and groups:
            moved = quarantine_duplicates(groups, rejected_dir=rejected_dir, store=store)
            console.print(f"  -> {moved} fayl {rejected_dir}/duplicates/ ga ko'chirildi.")

        # 2. PII tozalash
        pii_files = 0
        pii_hits = 0
        for txt_path in output_dir.glob("*/*.txt"):
            try:
                text = txt_path.read_text(encoding="utf-8")
            except OSError as exc:
                console.print(f"[red]O'qib bo'lmadi:[/red] {txt_path} — {exc}")
                continue
            cleaned, count = scrub_pii(text)
            if count:
                pii_files += 1
                pii_hits += count
                if apply:
                    try:
                        txt_path.write_text(cleaned, encoding="utf-8")
                    except OSError as exc:
                        console.print(f"[red]Yozib bo'lmadi:[/red] {txt_path} — {exc}")
        console.print(f"[bold]PII:[/bold] {pii_hits} ta topildi ({pii_files} faylda).")

        # 3. HF nomini yashirish (doim OXIRGI bosqich)
        renamed = 0
        unknown_datasets: set[str] = set()
        for txt_path in output_dir.glob("*/*.txt"):
            match = match_hf_shard_filename(txt_path.name)
            if match is None:
                continue
            if match.dataset_id is None:
                unknown_datasets.add(match.slug)
                continue
            new_name = renamed_filename(txt_path.name)
            if new_name is None:
                continue
            if apply:
                try:
                    txt_path.replace(txt_path.parent / new_name)
                except OSError as exc:
                    console.print(f"[red]Qayta nomlab bo'lmadi:[/red] {txt_path} — {exc}")
                    continue
            renamed += 1
        console.print(f"[bold]HF nomini yashirish:[/bold] {renamed} fayl qayta nomlan{'di' if apply else 'adi'}.")
        for slug in sorted(unknown_datasets):
            console.print(
                f"[yellow]Noma'lum dataset:[/yellow] '{slug}' — hf_rename.py DATASET_ALIAS'ga qo'shing."
            )

        # 4. OCR-chiqindi tokenlarni tozalash (qator darajasida)
        denoise_files = 0
        denoise_lines = 0
        for txt_path in output_dir.glob("*/*.txt"):
            try:
                text = txt_path.read_text(encoding="utf-8")
            except OSError as exc:
                console.print(f"[red]O'qib bo'lmadi:[/red] {txt_path} — {exc}")
                continue
            lines = text.split("\n")
            cleaned_lines = [strip_garbage_tokens(line) for line in lines]
            changed_count = sum(1 for old, new in zip(lines, cleaned_lines) if old != new)
            if changed_count:
                denoise_files += 1
                denoise_lines += changed_count
                if apply:
                    try:
                        txt_path.write_text("\n".join(cleaned_lines), encoding="utf-8")
                    except OSError as exc:
                        console.print(f"[red]Yozib bo'lmadi:[/red] {txt_path} — {exc}")
        console.print(
            f"[bold]OCR-chiqindi tozalash:[/bold] {denoise_lines} qatordan chiqindi token "
            f"olib tashlan{'di' if apply else 'adi'} ({denoise_files} faylda)."
        )

    if not apply:
        console.print(
            "\n[yellow]Bu dry-run edi — hech narsa o'zgartirilmadi. "
            "--apply bilan qayta ishga tushiring.[/yellow]"
        )


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
