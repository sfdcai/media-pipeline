"""Maintenance utilities for pruning temporary artefacts."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CleanupReport:
    """Summary of performed clean-up actions."""

    removed_batch_dirs: list[str]
    deleted_temp_files: list[str]
    rotated_logs: list[str]


class CleanupService:
    """Remove stale files and rotate logs based on configuration."""

    def __init__(
        self,
        *,
        batch_dir: Path,
        temp_dir: Path,
        log_dir: Path,
        temp_retention_days: int = 7,
        log_max_bytes: int = 5 * 1024 * 1024,
        batch_pattern: str | None = None,
    ) -> None:
        self._batch_dir = Path(batch_dir).expanduser().resolve()
        self._temp_dir = Path(temp_dir).expanduser().resolve()
        self._log_dir = Path(log_dir).expanduser().resolve()
        self._retention = timedelta(days=temp_retention_days)
        self._log_max_bytes = log_max_bytes
        self._batch_regex = self._compile_batch_pattern(batch_pattern)

    # ------------------------------------------------------------------
    def run(self) -> CleanupReport:
        removed_batches = self._purge_empty_batches()
        deleted_temp = self._prune_temp_files()
        rotated = self._rotate_logs()

        return CleanupReport(
            removed_batch_dirs=removed_batches,
            deleted_temp_files=deleted_temp,
            rotated_logs=rotated,
        )

    # ------------------------------------------------------------------
    def _purge_empty_batches(self) -> list[str]:
        removed: list[str] = []
        if not self._batch_dir.exists():
            return removed
        for candidate in sorted(self._batch_dir.iterdir()):
            if not candidate.is_dir():
                continue
            if not self._is_purge_candidate(candidate.name):
                continue
            try:
                next(candidate.iterdir())
            except StopIteration:
                shutil.rmtree(candidate, ignore_errors=True)
                removed.append(str(candidate))
                LOGGER.info("Removed empty batch directory", extra={"path": str(candidate)})
            except OSError:
                LOGGER.debug("Unable to inspect batch directory", extra={"path": str(candidate)})
        return removed

    def _prune_temp_files(self) -> list[str]:
        deleted: list[str] = []
        if not self._temp_dir.exists():
            return deleted
        threshold = datetime.now(timezone.utc) - self._retention
        for candidate in self._temp_dir.rglob("*"):
            if not candidate.is_file():
                continue
            try:
                stat = candidate.stat()
            except FileNotFoundError:
                continue
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if modified > threshold:
                continue
            try:
                candidate.unlink()
                deleted.append(str(candidate))
                LOGGER.info("Removed stale temp file", extra={"path": str(candidate)})
            except FileNotFoundError:
                continue
        return deleted

    def _rotate_logs(self) -> list[str]:
        rotated: list[str] = []
        if not self._log_dir.exists():
            return rotated
        for logfile in sorted(self._log_dir.glob("*.log")):
            try:
                size = logfile.stat().st_size
            except FileNotFoundError:
                continue
            if size < self._log_max_bytes:
                continue
            rotated_path = logfile.with_name(f"{logfile.name}.1")
            try:
                if rotated_path.exists():
                    rotated_path.unlink()
                logfile.rename(rotated_path)
                logfile.touch()
                rotated.append(str(rotated_path))
                LOGGER.info(
                    "Rotated log file due to size threshold",
                    extra={"path": str(logfile), "rotated": str(rotated_path)},
                )
            except OSError:
                LOGGER.exception("Failed to rotate log file", extra={"path": str(logfile)})
        return rotated

    def _compile_batch_pattern(self, pattern: str | None) -> re.Pattern[str] | None:
        if not pattern:
            return None
        escaped = re.escape(pattern)
        regex_source = re.sub(r"\\\{index[^}]*\\\}", r"(?P<index>\\d+)", escaped)
        if "(?P<index>" not in regex_source:
            return None
        return re.compile(f"^{regex_source}$")

    def _is_purge_candidate(self, name: str) -> bool:
        if name.startswith('.'):
            return False
        if name in {".stfolder", ".stignore"}:
            return False
        if self._batch_regex is None:
            return True
        return bool(self._batch_regex.match(name))


__all__ = ["CleanupService", "CleanupReport"]
