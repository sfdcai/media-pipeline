"""File sorting service that organises media into date-based directories."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from utils.db_manager import DatabaseManager
from utils.exif_tools import extract_capture_datetime

from .batch import (
    BATCH_STATUS_SORTED,
    BATCH_STATUS_SORTING,
    FILE_STATUS_BATCHED,
    FILE_STATUS_SORTED,
    FILE_STATUS_SYNCED,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SortResult:
    """Result returned when starting a sort run."""

    batch: str
    sorted_files: int
    skipped_files: int
    started: bool


@dataclass(slots=True)
class SortStatus:
    """Current progress snapshot for a batch sort run."""

    batch: str
    status: str
    total_files: int
    sorted_files: int


class SortService:
    """Move synced files into their final sorted destination."""

    def __init__(
        self,
        db: DatabaseManager,
        batch_dir: Path,
        sorted_dir: Path,
        *,
        folder_pattern: str = "{year}/{month:02d}/{day:02d}",
        exif_fallback: bool = True,
    ) -> None:
        self._db = db
        self._batch_dir = Path(batch_dir).expanduser().resolve()
        self._sorted_dir = Path(sorted_dir).expanduser().resolve()
        self._sorted_dir.mkdir(parents=True, exist_ok=True)
        self._folder_pattern = folder_pattern
        self._exif_fallback = exif_fallback

    # ------------------------------------------------------------------
    def start(self, batch_name: str) -> SortResult:
        record = self._get_batch(batch_name)
        if record is None:
            raise ValueError(f"Unknown batch '{batch_name}'")

        if record["status"] == BATCH_STATUS_SORTED:
            return SortResult(batch=batch_name, sorted_files=0, skipped_files=0, started=False)

        self._db.execute(
            "UPDATE batches SET status = ?, sorted_at = NULL WHERE name = ?",
            (BATCH_STATUS_SORTING, batch_name),
        ).close()

        files = self._db.fetchall(
            "SELECT rowid, path, target_path, status, exif_datetime FROM files WHERE batch_id = ?",
            (record["id"],),
        )

        sorted_count = 0
        skipped = 0

        for row in files:
            record = dict(row)
            path = Path(record["path"])
            status_value = record["status"]
            if status_value not in {FILE_STATUS_BATCHED, FILE_STATUS_SYNCED, FILE_STATUS_SORTED}:
                LOGGER.debug(
                    "Skipping file not ready for sorting",
                    extra={"path": str(path), "status": status_value},
                )
                skipped += 1
                continue
            if not path.exists():
                LOGGER.warning("Skipping missing file during sort", extra={"path": str(path)})
                skipped += 1
                continue

            resolved = self._determine_destination(path, record)
            if resolved is None:
                skipped += 1
                continue

            destination, capture = resolved

            destination.parent.mkdir(parents=True, exist_ok=True)

            if destination.exists():
                LOGGER.info(
                    "Destination already exists during sort", extra={"path": str(destination)}
                )
                if path.resolve() != destination.resolve():
                    destination = self._resolve_collision(destination)

            shutil.move(str(path), str(destination))
            sorted_count += 1

            capture_iso = capture.isoformat()

            self._db.execute(
                """
                UPDATE files
                SET path = ?, target_path = ?, status = ?, exif_datetime = COALESCE(exif_datetime, ?)
                WHERE rowid = ?
                """,
                (
                    str(destination),
                    str(destination),
                    FILE_STATUS_SORTED,
                    capture_iso,
                    record["rowid"],
                ),
            ).close()

        sorted_at = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "UPDATE batches SET status = ?, sorted_at = ? WHERE name = ?",
            (BATCH_STATUS_SORTED, sorted_at, batch_name),
        ).close()

        return SortResult(
            batch=batch_name,
            sorted_files=sorted_count,
            skipped_files=skipped,
            started=True,
        )

    # ------------------------------------------------------------------
    def status(self, batch_name: str) -> SortStatus:
        record = self._get_batch(batch_name)
        if record is None:
            raise ValueError(f"Unknown batch '{batch_name}'")

        files = self._db.fetchall(
            "SELECT status FROM files WHERE batch_id = ?",
            (record["id"],),
        )
        total = len(files)
        sorted_count = sum(1 for row in files if row["status"] == FILE_STATUS_SORTED)

        return SortStatus(
            batch=batch_name,
            status=record["status"],
            total_files=total,
            sorted_files=sorted_count,
        )

    # ------------------------------------------------------------------
    def _get_batch(self, batch_name: str) -> Optional[dict[str, str]]:
        row = self._db.fetchone(
            "SELECT id, status FROM batches WHERE name = ?",
            (batch_name,),
        )
        if row is None:
            return None
        return {"id": int(row["id"]), "status": row["status"]}

    def _determine_destination(
        self, path: Path, row: dict[str, object]
    ) -> Optional[tuple[Path, datetime]]:
        capture = self._capture_datetime(path, row)
        if capture is None:
            LOGGER.warning("Unable to determine capture date", extra={"path": str(path)})
            return None

        relative = self._folder_pattern.format(
            year=capture.year,
            month=capture.month,
            day=capture.day,
        )
        destination = self._sorted_dir / relative / path.name
        return destination, capture

    def _capture_datetime(self, path: Path, row: dict[str, object]) -> Optional[datetime]:
        if row.get("exif_datetime"):
            try:
                parsed = datetime.fromisoformat(str(row["exif_datetime"]))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                LOGGER.debug("Invalid stored EXIF timestamp", extra={"value": row["exif_datetime"]})

        capture = extract_capture_datetime(path)
        if capture:
            return capture

        if not self._exif_fallback:
            return None

        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    def _resolve_collision(self, destination: Path) -> Path:
        index = 1
        while True:
            candidate = destination.with_stem(f"{destination.stem}_{index}")
            if not candidate.exists():
                return candidate
            index += 1

__all__ = ["SortService", "SortResult", "SortStatus"]
