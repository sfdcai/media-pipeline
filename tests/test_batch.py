import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.batch_router import create_batch
from modules.batch import (
    BatchService,
    FILE_STATUS_ARCHIVED,
    FILE_STATUS_BATCHED,
    BATCH_STATUS_PENDING,
)
from modules.dedup import FILE_STATUS_UNIQUE
from utils.db_manager import DatabaseManager


def _insert_file(db: DatabaseManager, path: Path, size: int, sha: str) -> None:
    db.execute(
        """
        INSERT INTO files(path, size, status, sha256)
        VALUES(?, ?, ?, ?)
        """,
        (str(path), size, FILE_STATUS_UNIQUE, sha),
    ).close()


def test_batch_service_creates_manifest_and_moves_files(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    nested_dir = source_dir / "nested"
    nested_dir.mkdir()
    batch_dir = tmp_path / "batches"
    db = DatabaseManager(tmp_path / "db.sqlite")

    file_one = source_dir / "one.txt"
    file_two = nested_dir / "two.txt"
    file_one.write_text("alpha", encoding="utf-8")
    file_two.write_text("beta", encoding="utf-8")

    size_one = file_one.stat().st_size
    size_two = file_two.stat().st_size

    _insert_file(db, file_one, size_one, "sha-one")
    _insert_file(db, file_two, size_two, "sha-two")

    service = BatchService(
        db,
        source_dir=source_dir,
        batch_dir=batch_dir,
        max_size_gb=1,
        naming_pattern="batch_{index:02d}",
    )

    result = service.create_batch()

    assert result.created is True
    assert result.batch_name is not None
    assert result.file_count == 2
    assert result.size_bytes == size_one + size_two
    assert result.manifest_path is not None

    manifest_path = Path(result.manifest_path)
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["file_count"] == 2
    batch_paths = {entry["batch_path"] for entry in manifest["files"]}
    assert all(Path(path).exists() for path in batch_paths)
    assert not file_one.exists()
    assert not file_two.exists()

    rows = db.fetchall("SELECT path, status, batch_id FROM files ORDER BY path")
    assert all(row["status"] == FILE_STATUS_BATCHED for row in rows)
    assert all(row["batch_id"] for row in rows)

    batch_record = db.fetchone(
        "SELECT name, file_count, size_bytes, status, manifest_path FROM batches WHERE name = ?",
        (result.batch_name,),
    )
    assert batch_record is not None
    assert batch_record["file_count"] == 2
    assert batch_record["status"] == "PENDING"
    assert Path(batch_record["manifest_path"]).exists()

    second = service.create_batch()
    assert second.created is False

    db.close()


def test_batch_service_copy_mode_preserves_source(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    batch_dir = tmp_path / "batches"
    db = DatabaseManager(tmp_path / "db.sqlite")

    file_one = source_dir / "one.txt"
    file_two = source_dir / "two.txt"
    file_one.write_text("alpha", encoding="utf-8")
    file_two.write_text("beta", encoding="utf-8")

    _insert_file(db, file_one, file_one.stat().st_size, "sha-one")
    _insert_file(db, file_two, file_two.stat().st_size, "sha-two")

    service = BatchService(
        db,
        source_dir=source_dir,
        batch_dir=batch_dir,
        transfer_mode="copy",
    )

    result = service.create_batch()

    assert result.created is True
    assert file_one.exists()
    assert file_two.exists()

    assert result.batch_name is not None
    batch_path = batch_dir / result.batch_name
    assert batch_path.exists()
    assert (batch_path / "one.txt").exists()
    assert (batch_path / "two.txt").exists()

    rows = db.fetchall(
        "SELECT path, status, batch_id, target_path FROM files ORDER BY path"
    )
    archived = [row for row in rows if row["status"] == FILE_STATUS_ARCHIVED]
    batched = [row for row in rows if row["status"] == FILE_STATUS_BATCHED]

    assert len(archived) == 2
    for row in archived:
        assert row["batch_id"] is None
        assert row["target_path"] and Path(row["target_path"]).exists()

    assert len(batched) == 2
    for row in batched:
        assert row["batch_id"]
        assert Path(row["path"]).exists()

    db.close()


def test_batch_router_creates_batch_response(tmp_path: Path) -> None:
    asyncio.run(_run_router_scenario(tmp_path))


async def _run_router_scenario(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    batch_dir = tmp_path / "batch"
    db = DatabaseManager(tmp_path / "db.sqlite")

    file_path = source_dir / "solo.txt"
    file_path.write_text("payload", encoding="utf-8")
    size = file_path.stat().st_size

    _insert_file(db, file_path, size, "sha-solo")

    service = BatchService(
        db,
        source_dir=source_dir,
        batch_dir=batch_dir,
        max_size_gb=1,
    )

    response = await create_batch(service=service)
    assert response.created is True
    assert response.file_count == 1
    assert response.batch_name is not None
    assert response.manifest_path is not None

    follow_up = await create_batch(service=service)
    assert follow_up.created is False

    db.close()


def test_batch_service_respects_file_limit(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    batch_dir = tmp_path / "batches"
    db = DatabaseManager(tmp_path / "db.sqlite")

    for idx in range(3):
        file_path = source_dir / f"file-{idx}.txt"
        file_path.write_text(f"payload-{idx}", encoding="utf-8")
        size = file_path.stat().st_size
        _insert_file(db, file_path, size, f"sha-{idx}")

    service = BatchService(
        db,
        source_dir=source_dir,
        batch_dir=batch_dir,
        selection_mode="files",
        max_files=2,
    )

    result = service.create_batch()

    assert result.created is True
    assert result.file_count == 2
    assert result.reason is None

    remaining_unique = db.fetchall(
        "SELECT path FROM files WHERE status = ?", (FILE_STATUS_UNIQUE,)
    )
    # One file should remain unbatched because of the file-count limit.
    assert len(remaining_unique) == 1

    db.close()


def test_batch_service_blocks_until_previous_sorted(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    batch_dir = tmp_path / "batches"
    db = DatabaseManager(tmp_path / "db.sqlite")

    first_file = source_dir / "initial.txt"
    first_file.write_text("initial", encoding="utf-8")
    _insert_file(db, first_file, first_file.stat().st_size, "sha-initial")

    service = BatchService(db, source_dir=source_dir, batch_dir=batch_dir)

    first_batch = service.create_batch()
    assert first_batch.created is True
    assert first_batch.batch_name is not None

    later_file = source_dir / "later.txt"
    later_file.write_text("later", encoding="utf-8")
    _insert_file(db, later_file, later_file.stat().st_size, "sha-later")

    blocked = service.create_batch()
    assert blocked.created is False
    assert blocked.reason is not None
    assert blocked.blocking_batch == first_batch.batch_name
    assert blocked.blocking_batch_id == first_batch.batch_id
    assert blocked.blocking_status == BATCH_STATUS_PENDING

    db.execute(
        "UPDATE batches SET status = ?, sorted_at = datetime('now') WHERE id = ?",
        ("SORTED", first_batch.batch_id),
    ).close()

    second_batch = service.create_batch()
    assert second_batch.created is True
    assert second_batch.batch_name != first_batch.batch_name

    db.close()
