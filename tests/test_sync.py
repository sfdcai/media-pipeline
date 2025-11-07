from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.batch import (
    BATCH_STATUS_PENDING,
    BATCH_STATUS_SYNCED,
    BATCH_STATUS_SYNCING,
    FILE_STATUS_BATCHED,
    FILE_STATUS_SYNCED,
)
from modules.sync_monitor import SyncService
from utils.db_manager import DatabaseManager
from utils.syncthing_api import SyncthingCompletion


def _insert_batch(db: DatabaseManager, batch_dir: Path, name: str) -> int:
    batch_path = batch_dir / name
    batch_path.mkdir(parents=True, exist_ok=True)
    manifest = batch_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    cursor = db.execute(
        """
        INSERT INTO batches(name, size_bytes, file_count, status, created_at, manifest_path)
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (name, 0, 1, BATCH_STATUS_PENDING, datetime.now(timezone.utc).isoformat(), str(manifest)),
    )
    try:
        batch_id = cursor.lastrowid
    finally:
        cursor.close()
    return int(batch_id)


def _insert_file(db: DatabaseManager, path: Path, batch_id: int) -> None:
    db.execute(
        """
        INSERT INTO files(path, size, status, batch_id)
        VALUES(?, ?, ?, ?)
        """,
        (str(path), 0, FILE_STATUS_BATCHED, batch_id),
    ).close()


class StubSyncthingAPI:
    def __init__(self) -> None:
        self.completion = 0.0
        self.scans: list[tuple[str | None, list[str] | None, str | None]] = []

    def trigger_rescan(
        self,
        path: str | None = None,
        *,
        folder: str | None = None,
        subdirs: list[str] | None = None,
    ) -> None:
        self.scans.append((folder, subdirs, path))

    def folder_completion(self, folder: str) -> SyncthingCompletion:
        return SyncthingCompletion(folder=folder, completion=self.completion)


def test_sync_service_transitions_status(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "db.sqlite")
    batch_dir = tmp_path / "batches"
    file_path = batch_dir / "batch_001" / "photo.jpg"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("content", encoding="utf-8")

    batch_id = _insert_batch(db, batch_dir, "batch_001")
    _insert_file(db, file_path, batch_id)

    api = StubSyncthingAPI()
    service = SyncService(db, batch_dir=batch_dir, syncthing_api=api)

    start_result = service.start("batch_001")
    assert start_result.started is True
    assert start_result.status == BATCH_STATUS_SYNCING
    assert api.scans == [(None, None, str(file_path.parent))]


def test_sync_service_respects_folder_id(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "db.sqlite")
    batch_dir = tmp_path / "syncthing" / "upload"
    batch_name = "batch_123"
    batch_path = batch_dir / batch_name
    batch_path.mkdir(parents=True, exist_ok=True)
    manifest = batch_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    cursor = db.execute(
        """
        INSERT INTO batches(name, size_bytes, file_count, status, created_at, manifest_path)
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (
            batch_name,
            0,
            0,
            BATCH_STATUS_PENDING,
            datetime.now(timezone.utc).isoformat(),
            str(manifest),
        ),
    )
    try:
        batch_id = int(cursor.lastrowid)
    finally:
        cursor.close()

    db.execute(
        """
        INSERT INTO files(path, size, status, batch_id)
        VALUES(?, ?, ?, ?)
        """,
        (str(batch_path / "file.jpg"), 0, FILE_STATUS_BATCHED, batch_id),
    ).close()

    api = StubSyncthingAPI()
    service = SyncService(
        db,
        batch_dir=batch_dir,
        syncthing_api=api,
        folder_id="media-folder",
    )

    service.start(batch_name)

    assert api.scans == [("media-folder", [batch_name], None)]

    db.close()
