from datetime import datetime, timezone
from pathlib import Path
import os
import sys

import piexif
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.batch import (
    BATCH_STATUS_SORTED,
    BATCH_STATUS_SYNCED,
    FILE_STATUS_ARCHIVED,
    FILE_STATUS_SORTED,
    FILE_STATUS_SYNCED,
)
from modules.exif_sorter import SortService
from utils.db_manager import DatabaseManager


def _insert_batch(db: DatabaseManager, name: str, status: str) -> int:
    cursor = db.execute(
        """
        INSERT INTO batches(name, size_bytes, file_count, status, created_at, synced_at, manifest_path)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            0,
            2,
            status,
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            f"/tmp/{name}/manifest.json",
        ),
    )
    try:
        batch_id = cursor.lastrowid
    finally:
        cursor.close()
    return int(batch_id)


def _insert_file(
    db: DatabaseManager,
    *,
    path: Path,
    batch_id: int,
    status: str = FILE_STATUS_SYNCED,
    exif_datetime: str | None = None,
) -> None:
    db.execute(
        """
        INSERT INTO files(path, size, status, batch_id, exif_datetime)
        VALUES(?, ?, ?, ?, ?)
        """,
        (str(path), path.stat().st_size, status, batch_id, exif_datetime),
    ).close()


def _write_exif_image(path: Path, captured: datetime) -> None:
    image = Image.new("RGB", (1, 1), color=(255, 0, 0))
    image.save(path, format="JPEG")
    zeroth_ifd = {piexif.ImageIFD.Make: b"Test"}
    exif_ifd = {piexif.ExifIFD.DateTimeOriginal: captured.strftime("%Y:%m:%d %H:%M:%S").encode("utf-8")}
    exif_dict = {"0th": zeroth_ifd, "Exif": exif_ifd, "1st": {}, "thumbnail": None}
    piexif.insert(piexif.dump(exif_dict), str(path))


def test_sort_service_moves_files(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "db.sqlite")
    batch_dir = tmp_path / "batches"
    sorted_dir = tmp_path / "sorted"
    batch_path = batch_dir / "batch_001"
    batch_path.mkdir(parents=True, exist_ok=True)

    image_with_exif = batch_path / "photo.jpg"
    capture_time = datetime(2021, 5, 4, 12, 30, tzinfo=timezone.utc)
    _write_exif_image(image_with_exif, capture_time)

    text_file = batch_path / "notes.txt"
    text_file.write_text("hello", encoding="utf-8")
    fallback_time = datetime(2020, 1, 2, 3, 4, tzinfo=timezone.utc)
    os.utime(text_file, (fallback_time.timestamp(), fallback_time.timestamp()))

    batch_id = _insert_batch(db, "batch_001", BATCH_STATUS_SYNCED)
    _insert_file(db, path=image_with_exif, batch_id=batch_id)
    _insert_file(db, path=text_file, batch_id=batch_id)

    service = SortService(
        db,
        batch_dir=batch_dir,
        sorted_dir=sorted_dir,
        folder_pattern="{year}/{month:02d}/{day:02d}",
        exif_fallback=True,
    )

    result = service.start("batch_001")
    assert result.started is True
    assert result.sorted_files == 2

    expected_dir = sorted_dir / "2021/05/04"
    fallback_dir = sorted_dir / "2020/01/02"
    assert (expected_dir / "photo.jpg").exists()
    assert (fallback_dir / "notes.txt").exists()

    batch_record = db.fetchone("SELECT status FROM batches WHERE name = ?", ("batch_001",))
    assert batch_record["status"] == BATCH_STATUS_SORTED

    file_rows = db.fetchall(
        "SELECT status, target_path, exif_datetime FROM files WHERE batch_id = ?",
        (batch_id,),
    )
    assert all(row["status"] == FILE_STATUS_SORTED for row in file_rows)
    assert all(Path(row["target_path"]).exists() for row in file_rows)
    assert any("2021-05-04" in (row["exif_datetime"] or "") for row in file_rows)

    status = service.status("batch_001")
    assert status.total_files == 2
    assert status.sorted_files == 2
    assert status.status == BATCH_STATUS_SORTED

    second = service.start("batch_001")
    assert second.started is False

    db.close()


def test_sort_service_copy_mode_retains_batch(tmp_path: Path) -> None:
    db = DatabaseManager(tmp_path / "db.sqlite")
    batch_dir = tmp_path / "batches"
    sorted_dir = tmp_path / "sorted"
    batch_path = batch_dir / "batch_002"
    batch_path.mkdir(parents=True, exist_ok=True)

    image_path = batch_path / "photo.jpg"
    capture_time = datetime(2022, 6, 1, 9, 0, tzinfo=timezone.utc)
    _write_exif_image(image_path, capture_time)

    batch_id = _insert_batch(db, "batch_002", BATCH_STATUS_SYNCED)
    _insert_file(db, path=image_path, batch_id=batch_id)

    service = SortService(
        db,
        batch_dir=batch_dir,
        sorted_dir=sorted_dir,
        transfer_mode="copy",
    )

    result = service.start("batch_002")
    assert result.started is True
    assert result.sorted_files == 1

    destination = sorted_dir / "2022/06/01/photo.jpg"
    assert destination.exists()
    # Original file in the batch directory should remain because of copy mode.
    assert image_path.exists()

    rows = db.fetchall(
        "SELECT path, status, batch_id, target_path FROM files WHERE batch_id = ? OR status = ?",
        (batch_id, FILE_STATUS_ARCHIVED),
    )

    archived = [row for row in rows if row["status"] == FILE_STATUS_ARCHIVED]
    assert archived
    for row in archived:
        assert row["batch_id"] is None
        assert row["path"] == str(image_path)
        assert row["target_path"] == str(destination)

    sorted_rows = [row for row in rows if row["status"] == FILE_STATUS_SORTED]
    assert sorted_rows and sorted_rows[0]["path"] == str(destination)

    db.close()
