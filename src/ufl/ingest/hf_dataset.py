"""HuggingFace dataset'larni streaming rejimda o'qish (to'liq yuklab olmasdan) va
shard (guruh)larga bo'lish.

Diskda joy juda cheklangan (~24GB) — datasets kutubxonasining oddiy (to'liq yuklovchi)
rejimi HECH QACHON ishlatilmaydi, faqat streaming=True.
Qoidalar: docs/superpowers/specs/2026-07-18-huggingface-dataset-ingestion-design.md
"""

from __future__ import annotations

import os
from typing import Iterator

from datasets import load_dataset

SHARD_SIZE = 1000


def dataset_slug(dataset_id: str) -> str:
    return dataset_id.replace("/", "_")


def iter_shards(
    dataset_id: str,
    split: str,
    text_column: str,
    *,
    shard_size: int = SHARD_SIZE,
    skip_rows: int = 0,
    limit: int = 0,
) -> Iterator[list[str]]:
    """Dataset'ni streaming o'qiydi, har `shard_size` qatordan iborat matn-ro'yxatini
    qaytaradi. `skip_rows` — davom ettirish uchun (allaqachon ishlangan qatorlar).
    `limit` — 0 bo'lmasa, shuncha qatordan keyin (hatto shard o'rtasida bo'lsa ham) to'xtaydi.
    """
    stream = load_dataset(
        dataset_id, split=split, streaming=True, token=os.environ.get("HF_TOKEN") or None
    )
    if skip_rows:
        stream = stream.skip(skip_rows)

    batch: list[str] = []
    total = 0
    for row in stream:
        batch.append(row[text_column])
        total += 1
        if len(batch) >= shard_size:
            yield batch
            batch = []
        if limit and total >= limit:
            break
    if batch:
        yield batch
