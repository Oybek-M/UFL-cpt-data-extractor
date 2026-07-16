"""Crawl uchun vaqt yordamchilari (UTC, ISO normalizatsiya).

Manba: website-to-txt-collector/continuous_collector.py (71-93).
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            parsed = datetime.strptime(cleaned[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalized_time(value: str | None) -> str | None:
    parsed = parse_time(value)
    return parsed.isoformat(timespec="seconds") if parsed else None
