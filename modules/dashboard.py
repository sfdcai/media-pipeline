"""Data aggregation helpers for dashboard views."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from utils.db_manager import DatabaseManager


@dataclass(slots=True)
class DashboardSummary:
    """Aggregate metrics displayed on the dashboard."""

    generated_at: str
    files: dict[str, Any]
    batches: dict[str, Any]
    storage: dict[str, Any]
    recent_batches: list[dict[str, Any]]


class DashboardService:
    """Collects totals and derived metrics for the dashboard."""

    def __init__(
        self,
        db: DatabaseManager,
        *,
        batch_dir: Path,
        sorted_dir: Path,
    ) -> None:
        self._db = db
        self._batch_dir = Path(batch_dir).expanduser().resolve()
        self._sorted_dir = Path(sorted_dir).expanduser().resolve()

    # ------------------------------------------------------------------
    def summary(self) -> DashboardSummary:
        files = self._file_metrics()
        batches = self._batch_metrics()
        storage = self._storage_metrics()
        recent_batches = self._recent_batches()

        return DashboardSummary(
            generated_at=datetime.now(timezone.utc).isoformat(),
            files=files,
            batches=batches,
            storage=storage,
            recent_batches=recent_batches,
        )

    # ------------------------------------------------------------------
    def _file_metrics(self) -> dict[str, object]:
        total_row = self._db.fetchone("SELECT COUNT(*) AS total FROM files")
        total = int(total_row["total"]) if total_row else 0

        status_rows = self._db.fetchall(
            "SELECT status, COUNT(*) AS count FROM files GROUP BY status"
        )
        by_status: Dict[str, int] = {row["status"]: int(row["count"]) for row in status_rows}

        size_row = self._db.fetchone("SELECT SUM(size) AS size_sum FROM files")
        total_size = int(size_row["size_sum"]) if size_row and size_row["size_sum"] else 0

        return {
            "total": total,
            "by_status": by_status,
            "total_size_bytes": total_size,
            "completion_percent": self._completion_percentage(
                by_status.get("SORTED", 0), total
            ),
        }

    def _batch_metrics(self) -> dict[str, object]:
        total_row = self._db.fetchone("SELECT COUNT(*) AS total FROM batches")
        total = int(total_row["total"]) if total_row else 0

        status_rows = self._db.fetchall(
            "SELECT status, COUNT(*) AS count FROM batches GROUP BY status"
        )
        by_status: Dict[str, int] = {row["status"]: int(row["count"]) for row in status_rows}

        synced_row = self._db.fetchone(
            "SELECT COUNT(*) AS synced FROM batches WHERE status = 'SYNCED'"
        )
        sorted_row = self._db.fetchone(
            "SELECT COUNT(*) AS sorted FROM batches WHERE status = 'SORTED'"
        )

        return {
            "total": total,
            "by_status": by_status,
            "synced": int(synced_row["synced"]) if synced_row else 0,
            "sorted": int(sorted_row["sorted"]) if sorted_row else 0,
            "completion_percent": self._completion_percentage(
                by_status.get("SORTED", 0), total
            ),
        }

    def _storage_metrics(self) -> dict[str, object]:
        return {
            "batch_dir_bytes": self._directory_size(self._batch_dir),
            "sorted_dir_bytes": self._directory_size(self._sorted_dir),
        }

    def _recent_batches(self, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._db.fetchall(
            """
            SELECT id, name, status, file_count, size_bytes, created_at, synced_at, sorted_at
            FROM batches
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        recent: list[dict[str, Any]] = []
        for row in rows:
            recent.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "status": row["status"],
                    "file_count": int(row["file_count"] or 0),
                    "size_bytes": int(row["size_bytes"] or 0),
                    "created_at": row["created_at"],
                    "synced_at": row["synced_at"],
                    "sorted_at": row["sorted_at"],
                }
            )
        return recent

    def _completion_percentage(self, completed: int, total: int) -> float:
        if total <= 0:
            return 0.0
        try:
            return round((completed / total) * 100, 1)
        except ZeroDivisionError:
            return 0.0

    def _directory_size(self, path: Path) -> int:
        if not path.exists():
            return 0
        total = 0
        for candidate in path.rglob("*"):
            if candidate.is_file():
                try:
                    total += candidate.stat().st_size
                except FileNotFoundError:  # pragma: no cover - race
                    continue
        return total


__all__ = ["DashboardService", "DashboardSummary"]
