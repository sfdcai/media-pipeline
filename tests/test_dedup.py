from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.dedup_router import dedup_status, start_dedup
from modules.dedup import DedupService, FILE_STATUS_DUPLICATE, FILE_STATUS_UNIQUE
from utils.db_manager import DatabaseManager


def test_dedup_service_hashes_and_detects_duplicates(tmp_path: Path) -> None:
    asyncio.run(_run_dedup_service(tmp_path))


async def _run_dedup_service(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    duplicates_dir = tmp_path / "duplicates"
    duplicates_dir.mkdir()
    db_path = tmp_path / "db.sqlite"

    (source_dir / "file1.txt").write_text("hello world", encoding="utf-8")
    (source_dir / "file2.txt").write_text("hello world", encoding="utf-8")
    (source_dir / "file3.txt").write_text("unique", encoding="utf-8")

    db = DatabaseManager(db_path)
    service = DedupService(db, source_dir=source_dir, duplicates_dir=duplicates_dir)

    started = await service.start()
    assert started is True
    await service.wait_for_completion()

    status = service.status()
    assert status["running"] is False
    assert status["total_files"] == 3
    assert status["processed_files"] == 3
    assert status["duplicate_files"] == 1

    file1 = db.get_file(source_dir / "file1.txt")
    file2 = db.get_file(source_dir / "file2.txt")
    file3 = db.get_file(source_dir / "file3.txt")

    assert file1 is not None and file1["status"] == FILE_STATUS_UNIQUE
    assert file2 is not None and file2["status"] == FILE_STATUS_DUPLICATE
    assert file3 is not None and file3["status"] == FILE_STATUS_UNIQUE

    (source_dir / "file4.txt").write_text("later", encoding="utf-8")
    started_again = await service.start()
    assert started_again is True
    await service.wait_for_completion()

    status_after = service.status()
    assert status_after["total_files"] == 4
    assert status_after["processed_files"] == 4
    assert status_after["duplicate_files"] == 1


def test_dedup_router_start_and_status(tmp_path: Path) -> None:
    asyncio.run(_run_router_scenario(tmp_path))


async def _run_router_scenario(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    duplicates_dir = tmp_path / "duplicates"
    source_dir.mkdir()
    duplicates_dir.mkdir()
    db_path = tmp_path / "db.sqlite"

    (source_dir / "one.txt").write_text("same", encoding="utf-8")
    (source_dir / "two.txt").write_text("same", encoding="utf-8")

    db = DatabaseManager(db_path)
    service = DedupService(db, source_dir=source_dir, duplicates_dir=duplicates_dir)

    response = await start_dedup(service=service)
    assert response.started is True

    await service.wait_for_completion()

    status_response = await dedup_status(service=service)
    assert status_response.total_files == 2
    assert status_response.processed_files == 2
    assert status_response.duplicate_files == 1

    response_second = await start_dedup(service=service)
    assert response_second.started is True
