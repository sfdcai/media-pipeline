from datetime import datetime, timezone
from pathlib import Path
from typing import Any
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
from utils.syncthing_api import SyncthingAPIError, SyncthingCompletion


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
        self.completion_requests: list[tuple[str, str | None]] = []
        self.raise_completion: SyncthingAPIError | None = None
        self.status_payload: dict[str, Any] = {"myID": "DEVICE", "state": "idle"}

    def trigger_rescan(
        self,
        path: str | None = None,
        *,
        folder: str | None = None,
        subdirs: list[str] | None = None,
    ) -> None:
        self.scans.append((folder, subdirs, path))

    def folder_completion(
        self, folder: str, *, device: str | None = None
    ) -> SyncthingCompletion:
        if self.raise_completion is not None:
            raise self.raise_completion
        self.completion_requests.append((folder, device))
        return SyncthingCompletion(folder=folder, completion=self.completion)

    def system_status(self) -> dict[str, Any]:
        return self.status_payload


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
    service.status(batch_name)
    assert api.completion_requests[-1] == ("media-folder", None)

    db.close()


def test_sync_service_uses_device_id(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "db.sqlite")
    batch_dir = tmp_path / "syncthing" / "upload"
    batch_name = "batch_456"
    batch_path = batch_dir / batch_name
    batch_path.mkdir(parents=True, exist_ok=True)
    (batch_path / "manifest.json").write_text("{}", encoding="utf-8")

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
            str(batch_path / "manifest.json"),
        ),
    )
    cursor.close()

    api = StubSyncthingAPI()
    service = SyncService(
        db,
        batch_dir=batch_dir,
        syncthing_api=api,
        folder_id="folder-a",
        device_id="DEVICE42",
    )

    service.status(batch_name)
    assert api.completion_requests[-1] == ("folder-a", "DEVICE42")


def test_sync_service_reports_detail_on_error(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "db.sqlite")
    batch_dir = tmp_path / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_name = "batch_789"
    (batch_dir / batch_name).mkdir(parents=True, exist_ok=True)
    (batch_dir / batch_name / "manifest.json").write_text("{}", encoding="utf-8")

    cursor = db.execute(
        """
        INSERT INTO batches(name, size_bytes, file_count, status, created_at, manifest_path)
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (
            batch_name,
            0,
            0,
            BATCH_STATUS_SYNCING,
            datetime.now(timezone.utc).isoformat(),
            str(batch_dir / batch_name / "manifest.json"),
        ),
    )
    cursor.close()

    api = StubSyncthingAPI()
    api.raise_completion = SyncthingAPIError("Syncthing request failed (403 Forbidden - unauthorized)")
    service = SyncService(db, batch_dir=batch_dir, syncthing_api=api)

    status = service.status(batch_name)
    assert status.detail
    assert "403" in status.detail
    assert service.last_error == status.detail


def test_sync_diagnostics_include_last_error(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "db.sqlite")
    batch_dir = tmp_path / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "batch_001").mkdir(parents=True, exist_ok=True)

    api = StubSyncthingAPI()
    api.status_payload = {"myID": "DEVICE", "state": "idle"}
    service = SyncService(
        db,
        batch_dir=batch_dir,
        syncthing_api=api,
        folder_id="folder-a",
        device_id="device-a",
    )

    service._last_error = "Syncthing request failed (403 Forbidden)"  # type: ignore[attr-defined]
    diagnostics = service.diagnostics()
    assert diagnostics.folder_id == "folder-a"
    assert diagnostics.device_id == "device-a"
    assert diagnostics.last_error == "Syncthing request failed (403 Forbidden)"
    assert diagnostics.syncthing_status == api.status_payload


def test_refresh_syncing_batches_marks_completion(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "db.sqlite")
    batch_dir = tmp_path / "batches"
    batch_name = "batch_refresh"
    batch_path = batch_dir / batch_name
    batch_path.mkdir(parents=True, exist_ok=True)
    (batch_path / "manifest.json").write_text("{}", encoding="utf-8")

    cursor = db.execute(
        """
        INSERT INTO batches(name, size_bytes, file_count, status, created_at, manifest_path)
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (
            batch_name,
            0,
            1,
            BATCH_STATUS_SYNCING,
            datetime.now(timezone.utc).isoformat(),
            str(batch_path / "manifest.json"),
        ),
    )
    batch_id = int(cursor.lastrowid)
    cursor.close()

    file_path = batch_path / "photo.jpg"
    file_path.write_text("x", encoding="utf-8")
    db.execute(
        """
        INSERT INTO files(path, size, status, batch_id)
        VALUES(?, ?, ?, ?)
        """,
        (str(file_path), 1, FILE_STATUS_BATCHED, batch_id),
    ).close()

    api = StubSyncthingAPI()
    api.completion = 100.0

    service = SyncService(db, batch_dir=batch_dir, syncthing_api=api)

    refreshed = service.refresh_syncing_batches()

    assert refreshed
    assert refreshed[0]["status"] == BATCH_STATUS_SYNCED
    assert refreshed[0]["progress"] == 100.0

    row = db.fetchone("SELECT status FROM batches WHERE id = ?", (batch_id,))
    assert row["status"] == BATCH_STATUS_SYNCED

    db.close()
