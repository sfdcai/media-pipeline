"""Deduplication service responsible for hashing media files."""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from utils.db_manager import DatabaseManager
from utils.hash_tools import HashAlgorithm, compute_file_hash

LOGGER = logging.getLogger(__name__)

FILE_STATUS_NEW = "NEW"
FILE_STATUS_UNIQUE = "UNIQUE"
FILE_STATUS_DUPLICATE = "DUPLICATE"
FILE_STATUS_ERROR = "ERROR"
HASHED_STATUSES = {FILE_STATUS_UNIQUE, FILE_STATUS_DUPLICATE}


@dataclass
class DedupState:
    running: bool = False
    total_files: int = 0
    processed_files: int = 0
    duplicate_files: int = 0
    error: Optional[str] = None
    last_processed: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[int | str | bool]]:
        return {
            "running": self.running,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "duplicate_files": self.duplicate_files,
            "error": self.error,
            "last_processed": self.last_processed,
        }


class DedupService:
    """Service that manages deduplication runs."""

    def __init__(
        self,
        db: DatabaseManager,
        source_dir: Path,
        duplicates_dir: Path,
        hash_algorithm: HashAlgorithm = "sha256",
    ) -> None:
        self._db = db
        self._source_dir = Path(source_dir).expanduser().resolve()
        self._duplicates_dir = Path(duplicates_dir).expanduser().resolve()
        self._duplicates_dir.mkdir(parents=True, exist_ok=True)
        self._hash_algorithm = hash_algorithm

        self._state = DedupState()
        self._state_lock = threading.Lock()
        self._task_lock = asyncio.Lock()
        self._task: Optional[asyncio.Task[None]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def start(self) -> bool:
        """Start a deduplication run. Returns ``False`` if already running."""

        async with self._task_lock:
            if self._task and not self._task.done():
                return False
            self._task = asyncio.create_task(self._run())
        return True

    def status(self) -> Dict[str, Optional[int | str | bool]]:
        with self._state_lock:
            return self._state.to_dict()

    async def wait_for_completion(self) -> None:
        async with self._task_lock:
            task = self._task
        if task:
            await task

    # ------------------------------------------------------------------
    async def _run(self) -> None:
        self._set_state(running=True, error=None, last_processed=None)
        try:
            await asyncio.to_thread(self._process_files)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Dedup run failed")
            self._set_state(error=str(exc))
        finally:
            self._set_state(running=False)
            async with self._task_lock:
                self._task = None

    # ------------------------------------------------------------------
    def _process_files(self) -> None:
        files = self._discover_files()
        total_files = len(files)

        processed = 0
        duplicates = 0

        for file_path in files:
            record = self._db.get_file(file_path)
            if record and record.get("status") in HASHED_STATUSES:
                processed += 1
                if record.get("status") == FILE_STATUS_DUPLICATE:
                    duplicates += 1
                continue

        self._set_state(
            total_files=total_files,
            processed_files=processed,
            duplicate_files=duplicates,
        )

        for file_path in files:
            record = self._db.get_file(file_path)
            if record and record.get("status") in HASHED_STATUSES:
                continue

            try:
                stat_result = file_path.stat()
            except FileNotFoundError:
                LOGGER.warning(
                    "File vanished before hashing", extra={"path": str(file_path)}
                )
                continue

            metadata = {
                "size": stat_result.st_size,
                "ctime": stat_result.st_ctime,
                "mtime": stat_result.st_mtime,
            }

            if record is None:
                self._db.execute(
                    """
                    INSERT INTO files(path, size, ctime, mtime, status)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        str(file_path),
                        metadata["size"],
                        metadata["ctime"],
                        metadata["mtime"],
                        FILE_STATUS_NEW,
                    ),
                ).close()
            else:
                self._db.execute(
                    """
                    UPDATE files SET size = ?, ctime = ?, mtime = ?, status = ?, error = NULL
                    WHERE path = ?
                    """,
                    (
                        metadata["size"],
                        metadata["ctime"],
                        metadata["mtime"],
                        FILE_STATUS_NEW,
                        str(file_path),
                    ),
                ).close()

            try:
                digest = compute_file_hash(file_path, algorithm=self._hash_algorithm)
            except Exception as exc:  # pragma: no cover - error path exercised in tests
                LOGGER.exception("Failed to hash file", extra={"path": str(file_path)})
                self._db.execute(
                    "UPDATE files SET status = ?, error = ? WHERE path = ?",
                    (FILE_STATUS_ERROR, str(exc), str(file_path)),
                ).close()
                self._increment_processed()
                continue

            duplicate = self._db.fetchone(
                "SELECT path, status FROM files WHERE sha256 = ? AND path != ? ORDER BY path LIMIT 1",
                (digest, str(file_path)),
            )

            if duplicate:
                status = FILE_STATUS_DUPLICATE
                duplicates += 1
                if duplicate["status"] != FILE_STATUS_UNIQUE:
                    self._db.execute(
                        "UPDATE files SET status = ? WHERE path = ?",
                        (FILE_STATUS_UNIQUE, duplicate["path"]),
                    ).close()
            else:
                status = FILE_STATUS_UNIQUE

            self._db.execute(
                """
                UPDATE files
                SET sha256 = ?, size = ?, ctime = ?, mtime = ?, status = ?, error = NULL
                WHERE path = ?
                """,
                (
                    digest,
                    metadata["size"],
                    metadata["ctime"],
                    metadata["mtime"],
                    status,
                    str(file_path),
                ),
            ).close()

            processed += 1
            self._set_state(
                processed_files=processed,
                duplicate_files=duplicates,
                last_processed=str(file_path),
            )

    # ------------------------------------------------------------------
    def _discover_files(self) -> list[Path]:
        if not self._source_dir.exists():
            LOGGER.warning(
                "Source directory missing", extra={"path": str(self._source_dir)}
            )
            return []

        return sorted(
            (path for path in self._source_dir.rglob("*") if path.is_file()),
            key=lambda p: str(p),
        )

    def _set_state(self, **updates: Optional[int | str | bool]) -> None:
        with self._state_lock:
            for key, value in updates.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)

    def _increment_processed(self) -> None:
        with self._state_lock:
            self._state.processed_files += 1


__all__ = ["DedupService", "DedupState", "FILE_STATUS_DUPLICATE", "FILE_STATUS_UNIQUE"]
