import os
import time
from pathlib import Path

from ufl.cleanup import cleanup_logs


def _touch_with_age(path: Path, days_old: int) -> None:
    path.write_text("{}", encoding="utf-8")
    old_time = time.time() - days_old * 86400
    os.utime(path, (old_time, old_time))


def test_cleanup_removes_old_files_but_keeps_recent(tmp_path):
    rejected = tmp_path / "rejected" / "books"
    reports = tmp_path / "reports"
    rejected.mkdir(parents=True)
    reports.mkdir(parents=True)

    old_file = rejected / "old.jsonl"
    _touch_with_age(old_file, days_old=40)
    recent_file = reports / "recent.json"
    _touch_with_age(recent_file, days_old=1)

    result = cleanup_logs(rejected_dir=tmp_path / "rejected", reports_dir=reports, older_than_days=30)

    assert not old_file.exists()
    assert recent_file.exists()
    assert old_file in result.removed_files


def test_cleanup_dry_run_does_not_delete(tmp_path):
    rejected = tmp_path / "rejected"
    rejected.mkdir()
    old_file = rejected / "old.jsonl"
    _touch_with_age(old_file, days_old=40)

    result = cleanup_logs(
        rejected_dir=rejected, reports_dir=tmp_path / "reports", older_than_days=30, dry_run=True
    )

    assert old_file.exists()
    assert old_file in result.removed_files


def test_cleanup_keeps_gitkeep_regardless_of_age(tmp_path):
    rejected = tmp_path / "rejected"
    rejected.mkdir()
    gitkeep = rejected / ".gitkeep"
    _touch_with_age(gitkeep, days_old=40)

    result = cleanup_logs(rejected_dir=rejected, reports_dir=tmp_path / "reports", older_than_days=30)

    assert gitkeep.exists()
    assert gitkeep not in result.removed_files


def test_cleanup_ignores_missing_directories(tmp_path):
    result = cleanup_logs(
        rejected_dir=tmp_path / "does_not_exist_rejected",
        reports_dir=tmp_path / "does_not_exist_reports",
        older_than_days=30,
    )

    assert result.removed_files == []
    assert result.freed_bytes == 0
