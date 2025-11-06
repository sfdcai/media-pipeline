"""Utilities for computing file hashes."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MiB
HashAlgorithm = Literal["sha256", "md5", "sha1"]


def compute_file_hash(
    path: Path | str,
    algorithm: HashAlgorithm = "sha256",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> str:
    """Compute the hash for *path* using the requested *algorithm*.

    The file is streamed in ``chunk_size`` chunks to avoid loading large
    files into memory. ``algorithm`` defaults to ``sha256`` and currently
    supports a curated set of hashlib algorithms that meet the project's
    integrity requirements.
    """

    normalized_path = Path(path).expanduser().resolve()
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    try:
        hasher = hashlib.new(algorithm)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Unsupported hash algorithm: {algorithm}") from exc

    with normalized_path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(chunk_size), b""):
            hasher.update(chunk)

    return hasher.hexdigest()


__all__ = ["compute_file_hash", "HashAlgorithm", "DEFAULT_CHUNK_SIZE"]
