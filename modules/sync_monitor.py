"""Synchronization service coordinating batches with Syncthing."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from utils.db_manager import DatabaseManager
from utils.syncthing_api import SyncthingAPI, SyncthingAPIError

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
    detail: Optional[str] = None


@dataclass(slots=True)
class SyncDiagnostics:
    """Debug payload describing the current Syncthing integration state."""

    batch_dir: str
    folder_id: Optional[str]
    device_id: Optional[str]
    last_error: Optional[str]
    syncthing_status: dict[str, Any]


class SyncService:
    """Service responsible for coordinating batch synchronization."""

    def __init__(
        self,
        db: DatabaseManager,
        batch_dir: Path,
        syncthing_api: SyncthingAPI,
        *,
        folder_id: str | None = None,
        device_id: str | None = None,
        rescan_delay: float | int = 0,
    ) -> None:
        self._db = db
        self._batch_dir = Path(batch_dir).expanduser().resolve()
        self._batch_dir.mkdir(parents=True, exist_ok=True)
        self._syncthing = syncthing_api
        self._folder_id = folder_id.strip() if folder_id else None
        self._device_id = device_id.strip() if device_id else None
        self._last_error: str | None = None
        try:
            delay_value = float(rescan_delay)
        except (TypeError, ValueError):
            delay_value = 0.0
        self._rescan_delay = max(0.0, delay_value)

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

        if self._rescan_delay > 0:
            time.sleep(self._rescan_delay)

        if self._folder_id:
            try:
                relative = str(batch_path.relative_to(self._batch_dir))
            except ValueError:
                relative = batch_name
            self._syncthing.trigger_rescan(
                folder=self._folder_id,
                subdirs=[relative],
            )
        else:
            self._syncthing.trigger_rescan(str(batch_path))

        self._last_error = None
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

        try:
            completion = self._syncthing.folder_completion(
                self._folder_id or batch_name,
                device=self._device_id,
            )
            progress = completion.completion
            self._last_error = None
            detail: str | None = None
        except SyncthingAPIError as exc:
            self._last_error = str(exc)
            progress = 0.0
            detail = str(exc)

        if progress >= 100.0:
            synced_at = self._mark_batch_synced(batch_name, record["id"])
            status = BATCH_STATUS_SYNCED
            progress = 100.0

        return SyncStatus(
            batch=batch_name,
            status=status,
            progress=progress,
            synced_at=synced_at,
            detail=detail,
        )

    # ------------------------------------------------------------------
    def diagnostics(self) -> SyncDiagnostics:
        """Expose troubleshooting details for Syncthing integration."""

        try:
            status_payload = dict(self._syncthing.system_status())
        except SyncthingAPIError as exc:  # pragma: no cover - network failures
            status_payload = {"error": str(exc)}

        return SyncDiagnostics(
            batch_dir=str(self._batch_dir),
            folder_id=self._folder_id,
            device_id=self._device_id,
            last_error=self._last_error,
            syncthing_status=status_payload,
        )

    def refresh_syncing_batches(self) -> list[dict[str, Any]]:
        """Poll all batches marked as ``SYNCING`` and update their status."""

        rows = self._db.fetchall(
            "SELECT id, name FROM batches WHERE status = ? ORDER BY datetime(created_at)",
            (BATCH_STATUS_SYNCING,),
        )

        refreshed: list[dict[str, Any]] = []
        for row in rows:
            batch_name = row["name"]
            try:
                status = self.status(batch_name)
            except ValueError:
                continue

            refreshed.append(
                {
                    "batch_id": int(row["id"]) if row["id"] is not None else None,
                    "batch": status.batch,
                    "status": status.status,
                    "progress": status.progress,
                    "synced_at": status.synced_at,
                    "detail": status.detail,
                }
            )

        return refreshed

    # ------------------------------------------------------------------
    @property
    def folder_id(self) -> str | None:
        return self._folder_id

    @property
    def device_id(self) -> str | None:
        return self._device_id

    @property
    def last_error(self) -> str | None:
        return self._last_error

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


__all__ = [
    "SyncDiagnostics",
    "SyncService",
    "SyncStartResult",
    "SyncStatus",
]
