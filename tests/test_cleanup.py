from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.cleanup import CleanupService


def test_cleanup_service_removes_stale_artifacts(tmp_path: Path) -> None:
    batch_dir = tmp_path / "batches"
    batch_dir.mkdir()
    empty_batch = batch_dir / "batch_001"
    empty_batch.mkdir()

    non_empty_batch = batch_dir / "keep_me"
    non_empty_batch.mkdir()
    (non_empty_batch / "file.txt").write_text("keep", encoding="utf-8")

    protected_dir = batch_dir / ".stfolder"
    protected_dir.mkdir()

    external_dir = batch_dir / "USB"
    external_dir.mkdir()

    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    stale_file = temp_dir / "old.txt"
    stale_file.write_text("old", encoding="utf-8")
    stale_time = datetime.now(timezone.utc) - timedelta(days=10)
    os.utime(stale_file, (stale_time.timestamp(), stale_time.timestamp()))

    fresh_file = temp_dir / "fresh.txt"
    fresh_file.write_text("fresh", encoding="utf-8")

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "app.log"
    log_file.write_text("a" * (1024 * 1024 * 2), encoding="utf-8")

    service = CleanupService(
        batch_dir=batch_dir,
        temp_dir=temp_dir,
        log_dir=log_dir,
        temp_retention_days=7,
        log_max_bytes=1024 * 1024,
        batch_pattern="batch_{index:03d}",
    )

    report = service.run()

    assert str(empty_batch) in report.removed_batch_dirs
    assert empty_batch.exists() is False
    assert protected_dir.exists()
    assert external_dir.exists()
    assert str(stale_file) in report.deleted_temp_files
    assert fresh_file.exists()
    assert report.rotated_logs
    rotated_path = Path(report.rotated_logs[0])
    assert rotated_path.exists()
    assert log_file.exists()
