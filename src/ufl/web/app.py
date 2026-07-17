"""UFL Web UI — FastAPI. Auth yo'q (kichik jamoa, 2-3 kishi, ichki ishlatish uchun).

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §18
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ufl.clean.dedup import DeduplicationStore
from ufl.clean.language import load_fasttext_predictor
from ufl.config import Config
from ufl.crawl.state import CrawlState
from ufl.crawl.urls import domain_folder, prepare_url
from ufl.ingest import url as url_module
from ufl.pipeline import ProcessResult, process_file, write_output
from ufl.stats.budget import compute_budget, total_budget
from ufl.stats.tokens import load_tokenizer_counter
from ufl.store.db import BookRecord, Store

BASE_DIR = Path(__file__).parent
app = FastAPI(title="UFL — Uzbek CPT Data")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_config_path = Path(os.environ.get("UFL_CONFIG_PATH", "config/ufl.toml"))
_config = Config.load(_config_path)
_dedup_store = DeduplicationStore()
_fasttext_predict = load_fasttext_predictor(_config.language.fasttext_model_path)
_exact_token_counter = load_tokenizer_counter(_config.tokenizer.local_dir, _config.tokenizer.model_id)

CRAWL_CATEGORIES = [
    "web_news", "gov_legal", "education", "reference",
    "books", "conversations", "technical", "domain_haf",
]
# Har domen uchun bitta faol crawl jarayoni (bu web-server jarayoni ichida kuzatiladi).
_crawl_processes: dict[str, subprocess.Popen] = {}

_QUALITY_KWARGS = {
    "min_chars": _config.quality.min_chars,
    "min_words": _config.quality.min_words,
    "max_non_letter_ratio": _config.quality.max_non_letter_ratio,
    "max_repeated_ngram_ratio": _config.quality.max_repeated_ngram_ratio,
    "max_upper_ratio": _config.quality.max_upper_ratio,
    "max_url_ratio": _config.quality.max_url_ratio,
}


def _dashboard_context() -> dict:
    with Store(_config.paths.db) as store:
        collected = store.collected_tokens_by_category()
        book_count = store.book_count()
        books = store.list_books()
    budgets = compute_budget(_config.budget.categories, collected)
    return {
        "budgets": sorted(budgets, key=lambda b: b.category),
        "total": total_budget(budgets),
        "book_count": book_count,
        "categories": sorted(_config.budget.categories),
        "category_labels": _config.budget.category_labels,
        "books": sorted(books, key=lambda b: b.path),
    }


def _process_and_record(source_path: Path, category: str) -> ProcessResult:
    result = process_file(
        source_path,
        category=category,
        dedup_store=_dedup_store,
        fasttext_predict=_fasttext_predict,
        exact_token_counter=_exact_token_counter,
        chars_per_token=_config.tokenizer.chars_per_token,
        header_footer_min_repeats=_config.structure.header_footer_min_repeats,
        detect_toc=_config.structure.detect_toc,
        detect_bibliography=_config.structure.detect_bibliography,
        min_language_confidence=_config.language.min_confidence,
        min_heuristic_score=_config.language.min_heuristic_score,
        apostrophe_mode=_config.normalize.apostrophe_mode,
        quality_kwargs=_QUALITY_KWARGS,
    )
    write_output(
        result,
        output_dir=_config.paths.output,
        rejected_dir=_config.paths.rejected,
        reports_dir=_config.paths.reports,
    )
    dropped_pct = len(result.dropped) / result.total_blocks * 100 if result.total_blocks else 0.0
    with Store(_config.paths.db) as store:
        store.record_book(
            BookRecord(
                path=str(source_path),
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
    return result


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", _dashboard_context())


# /upload, /paste, /url qasddan "async def" emas, oddiy "def" — ular ichidagi
# pipeline (OCR, transliteratsiya va h.k.) sinxron va CPU bilan band bo'lishi
# mumkin. "async def" bo'lganda bu ish butun event loop'ni to'sib qo'yardi
# (bitta og'ir fayl butun ilovani hamma uchun muzlatib qo'yardi); oddiy "def"
# bilan FastAPI buni avtomatik alohida thread pool'da ishga tushiradi.
@app.post("/upload", response_class=HTMLResponse)
def upload(request: Request, file: UploadFile = File(...), category: str = Form(...)) -> HTMLResponse:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / file.filename
        with tmp_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            result = _process_and_record(tmp_path, category)
        except Exception as exc:  # noqa: BLE001
            return templates.TemplateResponse(
                request, "index.html", {**_dashboard_context(), "error": str(exc)}
            )
    return templates.TemplateResponse(request, "result.html", {"result": result})


@app.post("/paste", response_class=HTMLResponse)
def paste(
    request: Request,
    text: str = Form(...),
    category: str = Form(...),
    filename: str = Form("paste.txt"),
) -> HTMLResponse:
    if not filename.endswith(".txt"):
        filename = f"{filename}.txt"
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / filename
        tmp_path.write_text(text, encoding="utf-8")
        try:
            result = _process_and_record(tmp_path, category)
        except Exception as exc:  # noqa: BLE001
            return templates.TemplateResponse(
                "index.html", {"request": request, **_dashboard_context(), "error": str(exc)}
            )
    return templates.TemplateResponse(request, "result.html", {"result": result})


@app.post("/url", response_class=HTMLResponse)
def from_url(
    request: Request,
    url: str = Form(...),
    category: str = Form(...),
    filename: str = Form(""),
) -> HTMLResponse:
    safe_name = filename.strip() or _slug_from_url(url)
    if not safe_name.endswith(".html"):
        safe_name = f"{safe_name}.html"
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / safe_name
        try:
            html = url_module.fetch_html(url)
            tmp_path.write_text(html, encoding="utf-8")
            result = _process_and_record(tmp_path, category)
        except Exception as exc:  # noqa: BLE001
            return templates.TemplateResponse(
                request, "index.html", {**_dashboard_context(), "error": str(exc)}
            )
    return templates.TemplateResponse(request, "result.html", {"result": result})


def _slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    raw = f"{parsed.netloc}{parsed.path}".strip("/") or "sahifa"
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_")
    return slug or "sahifa"


@app.post("/books/remove")
def remove_book(path: str = Form(...)) -> RedirectResponse:
    with Store(_config.paths.db) as store:
        store.remove_book(path)
    return RedirectResponse("/", status_code=303)


@app.post("/books/clear-all")
def clear_all_books() -> RedirectResponse:
    with Store(_config.paths.db) as store:
        store.clear_all()
    return RedirectResponse("/", status_code=303)


def _launch_crawl_process(
    seed: str, category: str, max_articles: int, config_path: Path
) -> subprocess.Popen:
    args = [sys.executable, "-m", "ufl.cli", "crawl", seed, "--category", category, "--config", str(config_path)]
    if max_articles:
        args += ["--max-articles", str(max_articles)]
    # Web thread'ni bloklamaslik uchun mustaqil fon jarayoni (OCR-muzlash darsi —
    # bu ilgari butun ilovani muzlatgan xatoning aynan takrorlanishini oldini oladi).
    return subprocess.Popen(  # noqa: S603 — argumentlar forma qiymatlaridan, shell=False
        args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


@app.get("/crawl", response_class=HTMLResponse)
def crawl_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "crawl.html",
        {"categories": CRAWL_CATEGORIES, "category_labels": _config.budget.category_labels},
    )


@app.post("/crawl/start")
def crawl_start(
    url: str = Form(...), category: str = Form(...), max_articles: int = Form(0)
) -> RedirectResponse:
    seed = prepare_url(url)
    domain = domain_folder(seed)
    process = _crawl_processes.get(domain)
    if process is None or process.poll() is not None:
        _crawl_processes[domain] = _launch_crawl_process(seed, category, max_articles, _config_path)
    return RedirectResponse(f"/crawl/status/{domain}", status_code=303)


@app.get("/crawl/status/{domain}", response_class=HTMLResponse)
def crawl_status_page(request: Request, domain: str) -> HTMLResponse:
    state_dir = _config.crawl.output_dir / domain / "_state"
    counts: dict[str, int] = {}
    if (state_dir / "state.sqlite3").exists():
        with CrawlState(state_dir) as state:
            counts = state.counts()
    process = _crawl_processes.get(domain)
    running = process is not None and process.poll() is None
    return templates.TemplateResponse(
        request,
        "crawl_status.html",
        {"domain": domain, "counts": sorted(counts.items()), "running": running},
    )


@app.post("/crawl/stop/{domain}")
def crawl_stop(domain: str) -> RedirectResponse:
    process = _crawl_processes.get(domain)
    if process is not None and process.poll() is None:
        process.terminate()
    return RedirectResponse(f"/crawl/status/{domain}", status_code=303)


@app.get("/download/{category}/{filename}")
def download(category: str, filename: str) -> FileResponse:
    path = _config.paths.output / category / filename
    if not path.exists():
        return HTMLResponse("Fayl topilmadi", status_code=404)  # type: ignore[return-value]
    return FileResponse(path, filename=filename, media_type="text/plain")
