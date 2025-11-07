from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.batch import (
    BATCH_STATUS_SORTED,
    BATCH_STATUS_SYNCED,
    FILE_STATUS_BATCHED,
    FILE_STATUS_SORTED,
)
from modules.dashboard import DashboardService
from utils.db_manager import DatabaseManager


def test_dashboard_summary_returns_totals(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "db.sqlite")
    batch_dir = tmp_path / "batches"
    sorted_dir = tmp_path / "sorted"
    batch_dir.mkdir()
    sorted_dir.mkdir()

    cursor = db.execute(
        """
        INSERT INTO batches(name, size_bytes, file_count, status, created_at, manifest_path)
        VALUES(?, ?, ?, ?, datetime('now'), ?)
        """,
        ("batch_001", 100, 2, BATCH_STATUS_SYNCED, "manifest.json"),
    )
    batch_id = cursor.lastrowid
    cursor.close()

    db.execute(
        """
        INSERT INTO files(path, size, status, batch_id)
        VALUES(?, ?, ?, ?)
        """,
        (str(batch_dir / "batch_001" / "one.jpg"), 50, FILE_STATUS_BATCHED, batch_id),
    ).close()
    db.execute(
        """
        INSERT INTO files(path, size, status, batch_id)
        VALUES(?, ?, ?, ?)
        """,
        (str(sorted_dir / "2021/05/04/photo.jpg"), 75, FILE_STATUS_SORTED, batch_id),
    ).close()

    (batch_dir / "batch_001").mkdir()
    (sorted_dir / "2021/05/04").mkdir(parents=True, exist_ok=True)
    (sorted_dir / "2021/05/04/photo.jpg").write_text("x" * 10, encoding="utf-8")

    service = DashboardService(db, batch_dir=batch_dir, sorted_dir=sorted_dir)

    summary = service.summary()

    assert summary.files["total"] == 2
    assert summary.files["total_size_bytes"] == 125
    assert summary.files["completion_percent"] >= 50
    assert summary.batches["total"] == 1
    assert summary.batches["completion_percent"] in {0.0, 100.0}
    assert summary.storage["sorted_dir_bytes"] >= 10
    assert summary.recent_batches
    assert summary.recent_batches[0]["id"] == batch_id
    assert summary.recent_batches[0]["status"] == BATCH_STATUS_SYNCED
    assert hasattr(summary, "generated_at")

    db.close()
