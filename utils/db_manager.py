"""SQLite database helper utilities."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY,
        size INTEGER,
        sha256 TEXT,
        exif_datetime TEXT,
        ctime REAL,
        mtime REAL,
        status TEXT,
        batch_id INTEGER,
        target_path TEXT,
        error TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256)",
    "CREATE INDEX IF NOT EXISTS idx_files_status ON files(status)",
    """
    CREATE TABLE IF NOT EXISTS batches (
        name TEXT PRIMARY KEY,
        size_bytes INTEGER,
        file_count INTEGER,
        status TEXT,
        created_at TEXT,
        synced_at TEXT,
        sorted_at TEXT,
        manifest_path TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        ts TEXT,
        module TEXT,
        level TEXT,
        message TEXT,
        context TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS config_changes (
        ts TEXT,
        key TEXT,
        old_value TEXT,
        new_value TEXT,
        actor TEXT
    )
    """,
)


class DatabaseManager:
    """Thread-safe convenience wrapper around SQLite connections."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def _initialize_schema(self) -> None:
        with self._lock:
            cursor = self._connection.cursor()
            for statement in SCHEMA_STATEMENTS:
                cursor.execute(statement)
            cursor.close()

    def execute(
        self, query: str, parameters: Sequence[Any] | None = None
    ) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._connection.cursor()
            cursor.execute(query, parameters or [])
            return cursor

    def executemany(
        self, query: str, seq_of_parameters: Iterable[Sequence[Any]]
    ) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._connection.cursor()
            cursor.executemany(query, seq_of_parameters)
            return cursor

    def fetchone(
        self, query: str, parameters: Sequence[Any] | None = None
    ) -> Optional[sqlite3.Row]:
        cursor = self.execute(query, parameters)
        try:
            return cursor.fetchone()
        finally:
            cursor.close()

    def fetchall(
        self, query: str, parameters: Sequence[Any] | None = None
    ) -> list[sqlite3.Row]:
        cursor = self.execute(query, parameters)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

    def get_file(self, path: Path | str) -> Optional[dict[str, Any]]:
        row = self.fetchone("SELECT * FROM files WHERE path = ?", (str(Path(path)),))
        return dict(row) if row else None

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None  # type: ignore[assignment]

    def __del__(self) -> None:  # pragma: no cover - defensive clean-up
        try:
            self.close()
        except Exception:
            pass


__all__ = ["DatabaseManager"]
