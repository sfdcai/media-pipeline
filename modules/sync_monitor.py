"""Synchronization service coordinating batches with Syncthing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from utils.db_manager import DatabaseManager
from utils.syncthing_api import SyncthingAPI

from .batch import (
    FILE_STATUS_BATCHED,
    FILE_STATUS_SYNCED,
    BATCH_STATUS_SYNCED,
    BATCH_STATUS_SYNCING,
)


@dataclass(slots=True)
class SyncStartResult:
    """Return type for :meth:`SyncService.start`."""

    batch: str
    started: bool
    status: str


@dataclass(slots=True)
class SyncStatus:
    """Represents synchronization progress for a batch."""

    batch: str
    status: str
    progress: float
    synced_at: Optional[str]


class SyncService:
    """Service responsible for coordinating batch synchronization."""

    def __init__(
        self,
        db: DatabaseManager,
        batch_dir: Path,
        syncthing_api: SyncthingAPI,
        *,
        folder_id: str | None = None,
    ) -> None:
        self._db = db
        self._batch_dir = Path(batch_dir).expanduser().resolve()
        self._batch_dir.mkdir(parents=True, exist_ok=True)
        self._syncthing = syncthing_api
        self._folder_id = folder_id.strip() if folder_id else None

    # ------------------------------------------------------------------
    def start(self, batch_name: str) -> SyncStartResult:
        """Mark the batch as syncing and trigger a Syncthing rescan."""

        record = self._get_batch(batch_name)
        if record is None:
            raise ValueError(f"Unknown batch '{batch_name}'")

        status = record["status"]
        if status == BATCH_STATUS_SYNCED:
            return SyncStartResult(batch=batch_name, started=False, status=status)
        if status == BATCH_STATUS_SYNCING:
            return SyncStartResult(batch=batch_name, started=False, status=status)

        batch_path = self._batch_dir / batch_name
        if not batch_path.exists():
            raise FileNotFoundError(f"Batch directory '{batch_path}' missing")

        self._db.execute(
            "UPDATE batches SET status = ?, synced_at = NULL WHERE name = ?",
            (BATCH_STATUS_SYNCING, batch_name),
        ).close()

        self._syncthing.trigger_rescan(str(batch_path))

        return SyncStartResult(batch=batch_name, started=True, status=BATCH_STATUS_SYNCING)

    # ------------------------------------------------------------------
    def status(self, batch_name: str) -> SyncStatus:
        """Fetch the latest synchronization status for *batch_name*."""

        record = self._get_batch(batch_name)
        if record is None:
            raise ValueError(f"Unknown batch '{batch_name}'")

        status = record["status"]
        synced_at = record["synced_at"]
        batch_path = self._batch_dir / batch_name

        if status == BATCH_STATUS_SYNCED:
            return SyncStatus(
                batch=batch_name,
                status=status,
                progress=100.0,
                synced_at=synced_at,
            )

        if not batch_path.exists():
            return SyncStatus(
                batch=batch_name,
                status=status,
                progress=0.0,
                synced_at=synced_at,
            )

        completion = self._syncthing.folder_completion(self._folder_id or batch_name)
        progress = completion.completion

        if progress >= 100.0:
            synced_at = self._mark_batch_synced(batch_name, record["id"])
            status = BATCH_STATUS_SYNCED
            progress = 100.0

        return SyncStatus(batch=batch_name, status=status, progress=progress, synced_at=synced_at)

    # ------------------------------------------------------------------
    def _get_batch(self, batch_name: str) -> Optional[dict[str, Optional[str]]]:
        row = self._db.fetchone(
            "SELECT id, name, status, synced_at FROM batches WHERE name = ?",
            (batch_name,),
        )
        if row is None:
            return None
        return {
            "id": int(row["id"]) if row["id"] is not None else None,
            "name": row["name"],
            "status": row["status"],
            "synced_at": row["synced_at"],
        }

    def _mark_batch_synced(self, batch_name: str, batch_id: int | None) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "UPDATE batches SET status = ?, synced_at = ? WHERE name = ?",
            (BATCH_STATUS_SYNCED, timestamp, batch_name),
        ).close()
        if batch_id is not None:
            self._db.execute(
                "UPDATE files SET status = ? WHERE batch_id = ? AND status IN (?, ?)",
                (FILE_STATUS_SYNCED, batch_id, FILE_STATUS_BATCHED, FILE_STATUS_SYNCED),
            ).close()
        return timestamp


__all__ = ["SyncService", "SyncStartResult", "SyncStatus"]
