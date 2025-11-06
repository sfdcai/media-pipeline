"""Helpers for extracting EXIF metadata from media files."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import piexif

EXIF_DATE_FIELDS: tuple[tuple[str, int], ...] = (
    ("Exif", piexif.ExifIFD.DateTimeOriginal),
    ("Exif", piexif.ExifIFD.DateTimeDigitized),
    ("0th", piexif.ImageIFD.DateTime),
)


def extract_capture_datetime(path: Path | str) -> Optional[datetime]:
    """Return the best-effort capture datetime for *path*.

    The function inspects EXIF tags commonly used by cameras. When the EXIF
    metadata is not available or invalid, ``None`` is returned.
    """

    candidate = Path(path)
    if not candidate.exists():
        return None

    try:
        metadata = piexif.load(str(candidate))
    except (piexif.InvalidImageDataError, ValueError):
        return None

    for container, field in EXIF_DATE_FIELDS:
        bucket = metadata.get(container)
        if not bucket:
            continue
        raw_value = bucket.get(field)
        if not raw_value:
            continue
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8", errors="ignore")
        if isinstance(raw_value, str):
            parsed = _parse_exif_datetime(raw_value)
            if parsed:
                return parsed
    return None


def _parse_exif_datetime(value: str) -> Optional[datetime]:
    try:
        dt = datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc)


__all__ = ["extract_capture_datetime"]
