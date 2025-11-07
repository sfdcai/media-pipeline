"""Batch creation service for preparing files for synchronization."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional

from modules.dedup import FILE_STATUS_UNIQUE
from utils.db_manager import DatabaseManager

LOGGER = logging.getLogger(__name__)

FILE_STATUS_BATCHED = "BATCHED"
FILE_STATUS_SYNCED = "SYNCED"
FILE_STATUS_SORTED = "SORTED"

BATCH_STATUS_PENDING = "PENDING"
BATCH_STATUS_SYNCING = "SYNCING"
BATCH_STATUS_SYNCED = "SYNCED"
BATCH_STATUS_SORTING = "SORTING"
BATCH_STATUS_SORTED = "SORTED"
BATCH_STATUS_ERROR = "ERROR"


@dataclass(slots=True)
class BatchFileRecord:
    """Represents a single file entry within a batch manifest."""

    source_path: str
    batch_path: str
    relative_path: str
    size: int
    sha256: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "batch_path": self.batch_path,
            "relative_path": self.relative_path,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(slots=True)
class BatchCreationResult:
    """Result returned after attempting to create a batch."""

    created: bool
    batch_id: Optional[int] = None
    batch_name: Optional[str] = None
    file_count: int = 0
    size_bytes: int = 0
    manifest_path: Optional[str] = None
    created_at: Optional[str] = None
    files: List[BatchFileRecord] = field(default_factory=list)
    reason: Optional[str] = None
    blocking_batch: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "batch_id": self.batch_id,
            "batch_name": self.batch_name,
            "file_count": self.file_count,
            "size_bytes": self.size_bytes,
            "manifest_path": self.manifest_path,
            "created_at": self.created_at,
            "files": [record.to_dict() for record in self.files],
            "reason": self.reason,
            "blocking_batch": self.blocking_batch,
        }


class BatchService:
    """Service responsible for selecting unique files and creating batches."""

    def __init__(
        self,
        db: DatabaseManager,
        source_dir: Path,
        batch_dir: Path,
        max_size_gb: float = 15,
        naming_pattern: str = "batch_{index:03d}",
        *,
        selection_mode: str = "size",
        max_files: int | None = None,
        allow_parallel: bool = False,
    ) -> None:
        self._db = db
        self._source_dir = Path(source_dir).expanduser().resolve()
        self._batch_dir = Path(batch_dir).expanduser().resolve()
        self._batch_dir.mkdir(parents=True, exist_ok=True)
        self._naming_pattern = naming_pattern
        self._max_size_bytes = self._to_bytes(max_size_gb)
        mode = (selection_mode or "size").strip().lower()
        self._selection_mode = mode if mode in {"size", "files", "count"} else "size"
        self._max_files = self._to_int(max_files)
        self._allow_parallel = bool(allow_parallel)

    # ------------------------------------------------------------------
    def create_batch(self) -> BatchCreationResult:
        if not self._allow_parallel:
            guard = self._active_batch_guard()
            if guard is not None:
                name, status = guard
                message = (
                    f"Batch '{name}' is still {status.lower()}"
                    if status
                    else "Another batch is still in progress"
                )
                return BatchCreationResult(
                    created=False,
                    reason=message,
                    blocking_batch=name,
                )

        candidates = self._fetch_candidates()
        selected = self._select_within_limit(candidates)

        if not selected:
            return BatchCreationResult(created=False)

        batch_name = self._generate_batch_name()
        batch_path = self._batch_dir / batch_name
        batch_path.mkdir(parents=True, exist_ok=True)

        moved_records: list[BatchFileRecord] = []
        total_size = 0

        for row in selected:
            source_path = Path(row["path"])
            if not source_path.exists():
                LOGGER.warning(
                    "Skipping missing file during batch creation",
                    extra={"path": str(source_path)},
                )
                continue

            size = row["size"]
            if size is None:
                try:
                    size = source_path.stat().st_size
                except FileNotFoundError:
                    LOGGER.warning(
                        "File vanished before measuring size",
                        extra={"path": str(source_path)},
                    )
                    continue

            relative = self._relative_path(source_path)
            destination = batch_path / relative
            destination.parent.mkdir(parents=True, exist_ok=True)

            shutil.move(str(source_path), str(destination))

            moved_records.append(
                BatchFileRecord(
                    source_path=str(source_path),
                    batch_path=str(destination),
                    relative_path=str(relative),
                    size=int(size),
                    sha256=row.get("sha256"),
                )
            )
            total_size += int(size)

        if not moved_records:
            # No files successfully moved; remove directory if empty and return.
            try:
                batch_path.rmdir()
            except OSError:
                LOGGER.debug(
                    "Batch directory not empty during cleanup",
                    extra={"path": str(batch_path)},
                )
            return BatchCreationResult(created=False)

        created_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "batch": batch_name,
            "created_at": created_at,
            "file_count": len(moved_records),
            "size_bytes": total_size,
            "files": [record.to_dict() for record in moved_records],
        }
        manifest_path = batch_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

        batch_rowid = self._insert_batch(
            batch_name=batch_name,
            size_bytes=total_size,
            file_count=len(moved_records),
            created_at=created_at,
            manifest_path=manifest_path,
        )

        self._update_files(moved_records, batch_rowid)

        return BatchCreationResult(
            created=True,
            batch_id=batch_rowid,
            batch_name=batch_name,
            file_count=len(moved_records),
            size_bytes=total_size,
            manifest_path=str(manifest_path),
            created_at=created_at,
            files=moved_records,
        )

    # ------------------------------------------------------------------
    def _fetch_candidates(self) -> list[dict[str, Any]]:
        rows = self._db.fetchall(
            """
            SELECT path, size, sha256
            FROM files
            WHERE status = ? AND (batch_id IS NULL OR batch_id = 0)
            ORDER BY path
            """,
            (FILE_STATUS_UNIQUE,),
        )
        return [dict(row) for row in rows]

    def _select_within_limit(
        self, candidates: Iterable[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        running_size = 0
        limit_bytes = self._max_size_bytes if self._selection_mode == "size" else 0
        limit_files = self._max_files if self._selection_mode in {"files", "count"} else 0

        for row in candidates:
            normalized = self._normalize_candidate(row)
            if normalized is None:
                continue

            if limit_files and len(selected) >= limit_files:
                break

            size_int = normalized["size"]

            if limit_bytes and running_size + size_int > limit_bytes:
                if selected:
                    break
                if size_int > limit_bytes:
                    LOGGER.warning(
                        "Skipping file larger than batch limit",
                        extra={"path": normalized.get("path"), "size": size_int},
                    )
                    continue

            selected.append(normalized)
            running_size += size_int

            if limit_files and len(selected) >= limit_files:
                break

        return selected

    def _normalize_candidate(self, row: dict[str, Any]) -> dict[str, Any] | None:
        size_value = row.get("size")
        if size_value is None or int(size_value) <= 0:
            path_str = row.get("path")
            if not path_str:
                return None
            try:
                size_value = Path(path_str).stat().st_size
            except FileNotFoundError:
                LOGGER.warning(
                    "Skipping file missing during size check",
                    extra={"path": path_str},
                )
                return None

        row["size"] = int(size_value)
        return row

    def _active_batch_guard(self) -> tuple[str, str] | None:
        row = self._db.fetchone(
            """
            SELECT name, status
            FROM batches
            WHERE status IN (?, ?, ?, ?, ?)
            ORDER BY datetime(created_at) ASC
            LIMIT 1
            """,
            (
                BATCH_STATUS_PENDING,
                BATCH_STATUS_SYNCING,
                BATCH_STATUS_SYNCED,
                BATCH_STATUS_SORTING,
                BATCH_STATUS_ERROR,
            ),
        )
        if row is None:
            return None
        return str(row["name"]), str(row["status"])

    def _generate_batch_name(self) -> str:
        index = 1
        while True:
            try:
                candidate = self._naming_pattern.format(index=index)
            except KeyError as exc:  # pragma: no cover - misconfigured pattern
                raise ValueError("Batch naming pattern requires 'index' placeholder") from exc

            if not self._batch_exists(candidate):
                return candidate
            index += 1

    def _batch_exists(self, name: str) -> bool:
        existing = self._db.fetchone(
            "SELECT 1 FROM batches WHERE name = ?", (name,)
        )
        if existing:
            return True
        return (self._batch_dir / name).exists()

    def _insert_batch(
        self,
        *,
        batch_name: str,
        size_bytes: int,
        file_count: int,
        created_at: str,
        manifest_path: Path,
    ) -> int:
        cursor = self._db.execute(
            """
            INSERT INTO batches (name, size_bytes, file_count, status, created_at, synced_at, sorted_at, manifest_path)
            VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)
            """,
            (
                batch_name,
                size_bytes,
                file_count,
                BATCH_STATUS_PENDING,
                created_at,
                str(manifest_path),
            ),
        )
        try:
            rowid = cursor.lastrowid
        finally:
            cursor.close()
        return int(rowid)

    def _update_files(self, records: Iterable[BatchFileRecord], batch_id: int) -> None:
        for record in records:
            self._db.execute(
                """
                UPDATE files
                SET path = ?, size = ?, status = ?, batch_id = ?, target_path = NULL
                WHERE path = ?
                """,
                (
                    record.batch_path,
                    record.size,
                    FILE_STATUS_BATCHED,
                    batch_id,
                    record.source_path,
                ),
            ).close()

    def _relative_path(self, path: Path) -> Path:
        try:
            return path.relative_to(self._source_dir)
        except ValueError:
            return Path(path.name)

    @staticmethod
    def _to_bytes(max_size_gb: float) -> int:
        try:
            size_float = float(max_size_gb)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            size_float = 0.0
        if size_float <= 0:
            return 0
        return int(size_float * (1024 ** 3))

    @staticmethod
    def _to_int(value: int | float | str | None) -> int:
        if value is None:
            return 0
        try:
            number = int(value)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return 0
        return max(0, number)


__all__ = [
    "BatchService",
    "BatchCreationResult",
    "BatchFileRecord",
    "FILE_STATUS_BATCHED",
    "FILE_STATUS_SYNCED",
    "FILE_STATUS_SORTED",
    "BATCH_STATUS_PENDING",
    "BATCH_STATUS_SYNCING",
    "BATCH_STATUS_SYNCED",
    "BATCH_STATUS_SORTING",
    "BATCH_STATUS_SORTED",
    "BATCH_STATUS_ERROR",
]
