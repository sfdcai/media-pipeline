"""Database manager regression tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from utils.db_manager import DatabaseManager


def _create_legacy_batches_table(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE batches (
                name TEXT PRIMARY KEY,
                size_bytes INTEGER,
                file_count INTEGER,
                status TEXT,
                created_at TEXT,
                synced_at TEXT,
                sorted_at TEXT,
                manifest_path TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO batches (
                name,
                size_bytes,
                file_count,
                status,
                created_at,
                synced_at,
                sorted_at,
                manifest_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "batch_001",
                512,
                3,
                "PENDING",
                "2024-01-01T00:00:00Z",
                None,
                None,
                "/tmp/manifest.json",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_database_manager_migrates_batches_table(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    _create_legacy_batches_table(db_path)

    manager = DatabaseManager(db_path)
    try:
        rows = manager.fetchall("SELECT id, name, status FROM batches")
    finally:
        manager.close()

    assert rows[0]["id"] == 1
    assert rows[0]["name"] == "batch_001"
    assert rows[0]["status"] == "PENDING"
