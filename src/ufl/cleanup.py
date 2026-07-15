"""rejected/ va reports/ papkalaridagi eski diagnostika fayllarini tozalash.

Diqqat: bu FAQAT diagnostika loglariga (rejected/*.jsonl, reports/*.json)
tegadi. data/output/*.txt — yig'ilayotgan CPT ma'lumotining o'zi — bu yerda
HECH QACHON o'chirilmaydi.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CleanupResult:
    removed_files: list[Path] = field(default_factory=list)
    freed_bytes: int = 0


def cleanup_logs(
    *,
    rejected_dir: Path,
    reports_dir: Path,
    older_than_days: int,
    dry_run: bool = False,
) -> CleanupResult:
    cutoff = time.time() - older_than_days * 86400
    result = CleanupResult()

    for directory in (Path(rejected_dir), Path(reports_dir)):
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            if path.stat().st_mtime >= cutoff:
                continue
            result.freed_bytes += path.stat().st_size
            result.removed_files.append(path)
            if not dry_run:
                path.unlink()

    return result
