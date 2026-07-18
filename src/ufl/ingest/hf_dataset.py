"""HuggingFace dataset'larni to'g'ridan-to'g'ri parquet fayllarni yuklab
o'qish va shard (guruh)larga bo'lish.

`datasets.load_dataset(..., streaming=True)` HF'ning Xet (hf_xet) tezlashtirish
tizimi orqali ishlaydi — real crawl'da (2026-07-18) `tahrirchi/uz-books-v2`
uchun bu yo'l abadiy osilib qolgani tasdiqlangan: bir xil parquet faylni oddiy
`curl` bilan 28 soniyada to'liq yuklab bo'lingan, lekin `datasets` orqali
100% CPU band bo'lgan holda soatlab hech qanday progress bo'lmagan (na yangi
tarmoq so'rovi, na yangi log qatori). Shuning uchun bu modul Xet'ni butunlay
chetlab o'tadi: parquet fayllar ro'yxati `HfApi.list_repo_files` orqali
olinadi, har biri oddiy HTTP (httpx) orqali vaqtinchalik yuklanadi, `pyarrow`
bilan mahalliy o'qiladi, so'ng darhol o'chiriladi.

Diskda joy juda cheklangan (~24GB) — datasets kutubxonasining oddiy (to'liq
avvaldan yuklovchi) rejimi HECH QACHON ishlatilmaydi, bir vaqtda faqat bitta
parquet fayl saqlanadi.
Qoidalar: docs/superpowers/specs/2026-07-18-huggingface-dataset-ingestion-design.md
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Iterator

import httpx
import pyarrow.parquet as pq
from huggingface_hub import HfApi

SHARD_SIZE = 1000


def dataset_slug(dataset_id: str) -> str:
    return dataset_id.replace("/", "_")


def _list_split_parquet_files(dataset_id: str, split: str, token: str | None) -> list[str]:
    """Berilgan split uchun parquet fayllar ro'yxatini (repo ichidagi yo'l,
    masalan "data/lat-00000-of-00026.parquet") shard raqami bo'yicha
    tartiblangan holda qaytaradi."""
    api = HfApi(token=token)
    files = api.list_repo_files(dataset_id, repo_type="dataset")
    pattern = re.compile(rf"^{re.escape(split)}-(\d+)-of-(\d+)\.parquet$")
    matched: list[tuple[int, str]] = []
    for path in files:
        basename = path.rsplit("/", 1)[-1]
        match = pattern.match(basename)
        if match:
            matched.append((int(match.group(1)), path))
    matched.sort(key=lambda pair: pair[0])
    return [path for _, path in matched]


def _download_parquet(dataset_id: str, path_in_repo: str, dest: Path, token: str | None) -> None:
    """Parquet faylni to'g'ridan-to'g'ri (Xet'siz, oddiy HTTP) yuklaydi."""
    url = f"https://huggingface.co/datasets/{dataset_id}/resolve/main/{path_in_repo}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=120.0) as response:
        response.raise_for_status()
        with dest.open("wb") as f:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                f.write(chunk)


def _iter_rows(
    parquet_files: list[str], dataset_id: str, text_column: str, token: str | None, tmp_dir: Path
) -> Iterator[str]:
    """Barcha parquet fayllarni ketma-ket yuklab, matn qatorlarini bitta
    uzluksiz oqim sifatida beradi (fayl chegarasi chaqiruvchi uchun ko'rinmas).
    Har bir fayl o'qib bo'lingach (yoki iterator erta to'xtatilsa ham,
    generator yopilganda) darhol o'chiriladi — disk joyi cheklangan."""
    for path_in_repo in parquet_files:
        local_path = tmp_dir / Path(path_in_repo).name
        _download_parquet(dataset_id, path_in_repo, local_path, token)
        try:
            parquet_file = pq.ParquetFile(local_path)
            for record_batch in parquet_file.iter_batches(columns=[text_column]):
                yield from record_batch.column(text_column).to_pylist()
        finally:
            local_path.unlink(missing_ok=True)


def iter_shards(
    dataset_id: str,
    split: str,
    text_column: str,
    *,
    shard_size: int = SHARD_SIZE,
    skip_rows: int = 0,
    limit: int = 0,
) -> Iterator[list[str]]:
    """Dataset'ni parquet fayl-fayl yuklab o'qiydi, har `shard_size` qatordan
    iborat matn-ro'yxatini qaytaradi. `skip_rows` — davom ettirish uchun
    (allaqachon ishlangan qatorlar, fayl chegaralaridan qat'i nazar butun
    split bo'yicha uzluksiz hisoblanadi). `limit` — 0 bo'lmasa, shuncha
    qatordan keyin (hatto shard o'rtasida bo'lsa ham) to'xtaydi."""
    token = os.environ.get("HF_TOKEN") or None
    parquet_files = _list_split_parquet_files(dataset_id, split, token)

    batch: list[str] = []
    total = 0
    rows_to_skip = skip_rows

    with tempfile.TemporaryDirectory(prefix="ufl_hf_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        for text in _iter_rows(parquet_files, dataset_id, text_column, token, tmp_dir):
            if rows_to_skip > 0:
                rows_to_skip -= 1
                continue
            batch.append(text)
            total += 1
            if len(batch) >= shard_size:
                yield batch
                batch = []
            if limit and total >= limit:
                break
    if batch:
        yield batch
