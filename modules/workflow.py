"""Workflow orchestration helpers for the media pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from modules.batch import BATCH_STATUS_SORTED, BATCH_STATUS_SYNCED
from modules.cleanup import CleanupReport
from modules.sync_monitor import SyncStatus
from utils.config_loader import get_config_value
from utils.db_manager import DatabaseManager
from utils.service_container import ServiceContainer
from utils.syncthing_api import SyncthingAPIError


@dataclass(slots=True)
class PipelineStepResult:
    """Outcome for an individual step in the workflow."""

    name: str
    status: str
    message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineRunResult:
    """Aggregate summary for a full workflow execution."""

    started_at: str
    finished_at: str
    steps: list[PipelineStepResult]
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "steps": [
                {
                    "name": step.name,
                    "status": step.status,
                    "message": step.message,
                    "data": step.data,
                }
                for step in self.steps
            ],
            "errors": list(self.errors),
        }


class WorkflowOrchestrator:
    """Coordinate services to execute workflow steps."""

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container

    # ------------------------------------------------------------------
    async def run_dedup(self) -> PipelineStepResult:
        dedup = self._container.dedup_service
        started = await dedup.start()
        if started:
            await dedup.wait_for_completion()
        status = dedup.status()
        message = "Deduplication already running" if not started else None
        if status.get("error"):
            message = status["error"]
        return PipelineStepResult(
            name="dedup",
            status="completed" if not status.get("error") else "error",
            message=message,
            data=status,
        )

    def run_batch(self) -> PipelineStepResult:
        batch_service = self._container.batch_service
        try:
            result = batch_service.create_batch()
        except Exception as exc:  # pragma: no cover - defensive guard
            return PipelineStepResult(
                name="batch",
                status="error",
                message=str(exc),
            )

        data = result.to_dict()
        status = "completed" if result.created else "skipped"
        message = None if result.created else "No eligible files for batching"
        return PipelineStepResult(name="batch", status=status, message=message, data=data)

    async def run_sync(self, batch_id: int) -> PipelineStepResult:
        sync_service = self._container.sync_service
        batch_record = self._get_batch(batch_id)
        if batch_record is None:
            return PipelineStepResult(
                name="sync",
                status="error",
                message=f"Unknown batch id {batch_id}",
            )
        batch_name = batch_record["name"]
        try:
            start_result = sync_service.start(batch_name)
        except (ValueError, FileNotFoundError) as exc:
            return PipelineStepResult(
                name="sync",
                status="error",
                message=str(exc),
            )
        except SyncthingAPIError as exc:
            return PipelineStepResult(
                name="sync",
                status="error",
                message=str(exc),
                data={"batch": batch_name},
            )

        data = {
            "batch_id": batch_id,
            "batch": start_result.batch,
            "status": start_result.status,
            "started": start_result.started,
        }
        status = "completed" if start_result.started else "skipped"
        if start_result.status == BATCH_STATUS_SYNCED:
            status = "completed"
        elif start_result.status != BATCH_STATUS_SYNCED and not start_result.started:
            data["reason"] = "Batch already syncing"

        if start_result.started:
            sync_status = await self._await_sync_completion(batch_name)
            data["progress"] = sync_status.progress
            data["status"] = sync_status.status
            data["synced_at"] = sync_status.synced_at
            if sync_status.detail:
                data["detail"] = sync_status.detail
            if sync_status.status != BATCH_STATUS_SYNCED:
                status = "warning"
                data["reason"] = "Sync did not reach completion"

        return PipelineStepResult(name="sync", status=status, data=data)

    async def _await_sync_completion(
        self, batch_name: str, *, attempts: int = 10, interval: float = 3.0
    ) -> SyncStatus:
        sync_service = self._container.sync_service
        status = sync_service.status(batch_name)
        remaining = attempts
        while status.status != BATCH_STATUS_SYNCED and remaining > 0:
            remaining -= 1
            await asyncio.sleep(interval)
            status = sync_service.status(batch_name)
        return status

    def run_sort(self, batch_id: int) -> PipelineStepResult:
        sort_service = self._container.sort_service
        batch_record = self._get_batch(batch_id)
        if batch_record is None:
            return PipelineStepResult(
                name="sort",
                status="error",
                message=f"Unknown batch id {batch_id}",
            )
        batch_name = batch_record["name"]
        try:
            result = sort_service.start(batch_name)
        except ValueError as exc:
            return PipelineStepResult(
                name="sort",
                status="error",
                message=str(exc),
            )

        status = "completed" if result.started else "skipped"
        data = {
            "batch_id": batch_id,
            "batch": result.batch,
            "sorted_files": result.sorted_files,
            "skipped_files": result.skipped_files,
        }
        if not result.started:
            data["reason"] = "Batch already sorted"
        return PipelineStepResult(name="sort", status=status, data=data)

    def run_cleanup(self) -> PipelineStepResult:
        cleanup = self._container.cleanup_service
        report = cleanup.run()
        if isinstance(report, CleanupReport):
            data = {
                "removed_batch_dirs": report.removed_batch_dirs,
                "deleted_temp_files": report.deleted_temp_files,
                "rotated_logs": report.rotated_logs,
            }
        else:  # pragma: no cover - defensive
            data = {
                "removed_batch_dirs": getattr(report, "removed_batch_dirs", []),
                "deleted_temp_files": getattr(report, "deleted_temp_files", []),
                "rotated_logs": getattr(report, "rotated_logs", []),
            }
        return PipelineStepResult(name="cleanup", status="completed", data=data)

    async def run_pipeline(self) -> PipelineRunResult:
        started_at = datetime.now(timezone.utc).isoformat()
        steps: list[PipelineStepResult] = []
        errors: list[str] = []

        dedup_result = await self.run_dedup()
        steps.append(dedup_result)
        if dedup_result.status == "error" and dedup_result.message:
            errors.append(f"dedup: {dedup_result.message}")

        batch_result = self.run_batch()
        batch_steps: list[PipelineStepResult] = [batch_result]

        blocking_data = batch_result.data if batch_result.data else {}
        blocking_status = blocking_data.get("blocking_status") if isinstance(blocking_data, dict) else None
        blocking_batch_id = (
            blocking_data.get("blocking_batch_id") if isinstance(blocking_data, dict) else None
        )
        if (
            batch_result.status == "skipped"
            and blocking_status == BATCH_STATUS_SYNCED
            and blocking_batch_id is not None
        ):
            try:
                target_batch_id = int(blocking_batch_id)
            except (TypeError, ValueError):
                target_batch_id = None
            if target_batch_id is not None:
                sort_existing = self.run_sort(target_batch_id)
                batch_steps.append(sort_existing)
                if sort_existing.status == "error" and sort_existing.message:
                    errors.append(f"sort: {sort_existing.message}")
                if sort_existing.status in {"completed", "skipped"}:
                    retry_result = self.run_batch()
                    batch_steps.append(retry_result)
                    batch_result = retry_result

        steps.extend(batch_steps)
        batch_id = batch_result.data.get("batch_id") if batch_result.data else None
        if batch_result.status == "error" and batch_result.message:
            errors.append(f"batch: {batch_result.message}")

        if batch_result.status == "completed" and batch_id:
            sync_result = await self.run_sync(int(batch_id))
            steps.append(sync_result)
            if sync_result.status in {"error", "warning"} and sync_result.message:
                errors.append(f"sync: {sync_result.message}")

            if sync_result.status == "completed":
                sort_result = self.run_sort(int(batch_id))
                steps.append(sort_result)
                if sort_result.status == "error" and sort_result.message:
                    errors.append(f"sort: {sort_result.message}")
            else:
                steps.append(
                    PipelineStepResult(
                        name="sort",
                        status="skipped",
                        message="Sorting deferred until sync completes",
                    )
                )
        else:
            steps.append(
                PipelineStepResult(
                    name="sync",
                    status="skipped",
                    message="No batch created",
                )
            )
            steps.append(
                PipelineStepResult(
                    name="sort",
                    status="skipped",
                    message="No batch created",
                )
            )

        cleanup_result = self.run_cleanup()
        steps.append(cleanup_result)

        finished_at = datetime.now(timezone.utc).isoformat()
        return PipelineRunResult(
            started_at=started_at,
            finished_at=finished_at,
            steps=steps,
            errors=errors,
        )

    # ------------------------------------------------------------------
    def refresh_syncing_batches(self) -> list[dict[str, Any]]:
        """Poll Syncthing for batches marked as syncing and update progress."""

        return self._container.sync_service.refresh_syncing_batches()

    # ------------------------------------------------------------------
    def build_overview(
        self, *, last_run: PipelineRunResult | None, running: bool
    ) -> dict[str, Any]:
        dedup_status = self._container.dedup_service.status()
        syncing_batches = self.refresh_syncing_batches()
        batch_snapshot = self._latest_batches(limit=5)
        counts = self._file_status_counts()

        overview: dict[str, Any] = {
            "running": running,
            "dedup": dedup_status,
            "recent_batches": batch_snapshot,
            "file_counts": counts,
            "syncing_batches": syncing_batches,
        }
        overview["config"] = {
            "path": str(self._container.config_path),
            "log_dir": str(
                get_config_value(
                    "system", "log_dir", default="", config=self._container.config
                )
            ),
            "syncthing": {
                "api_url": get_config_value(
                    "syncthing",
                    "api_url",
                    default="",
                    config=self._container.config,
                ),
                "folder_id": self._container.sync_service.folder_id,
                "device_id": self._container.sync_service.device_id,
                "last_error": self._container.sync_service.last_error,
            },
        }
        if last_run is not None:
            overview["last_run"] = last_run.to_dict()
        return overview

    def _latest_batches(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self._container.database.fetchall(
            """
            SELECT id, name, status, created_at, synced_at, sorted_at, manifest_path
            FROM batches
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (limit,),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append({
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "created_at": row["created_at"],
                "synced_at": row["synced_at"],
                "sorted_at": row["sorted_at"],
                "manifest_path": row["manifest_path"],
            })
        return result

    def _get_batch(self, batch_id: int) -> dict[str, Any] | None:
        row = self._container.database.fetchone(
            "SELECT id, name, status FROM batches WHERE id = ?",
            (int(batch_id),),
        )
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "name": row["name"],
            "status": row["status"],
        }

    def _file_status_counts(self) -> dict[str, int]:
        db: DatabaseManager = self._container.database
        rows = db.fetchall(
            "SELECT status, COUNT(*) AS count FROM files GROUP BY status ORDER BY status"
        )
        return {row["status"]: int(row["count"]) for row in rows}


class WorkflowManager:
    """Coordinate asynchronous workflow runs for shared state consumers."""

    def __init__(self, orchestrator: WorkflowOrchestrator) -> None:
        self._orchestrator = orchestrator
        self._lock = asyncio.Lock()
        self._current_task: asyncio.Task[PipelineRunResult] | None = None
        self._last_result: PipelineRunResult | None = None
        self._last_error: str | None = None

    @property
    def orchestrator(self) -> WorkflowOrchestrator:
        return self._orchestrator

    async def trigger(self) -> bool:
        async with self._lock:
            if self._current_task and not self._current_task.done():
                return False
            loop = asyncio.get_running_loop()
            self._current_task = loop.create_task(self._run())
            return True

    async def _run(self) -> PipelineRunResult:
        try:
            result = await self._orchestrator.run_pipeline()
            self._last_result = result
            self._last_error = None
            return result
        except Exception as exc:  # pragma: no cover - defensive
            self._last_result = None
            self._last_error = str(exc)
            raise
        finally:
            async with self._lock:
                self._current_task = None

    def status(self) -> dict[str, Any]:
        running = bool(self._current_task and not self._current_task.done())
        return {
            "running": running,
            "last_result": self._last_result.to_dict() if self._last_result else None,
            "error": self._last_error,
        }

    def overview(self) -> dict[str, Any]:
        running = bool(self._current_task and not self._current_task.done())
        return self._orchestrator.build_overview(
            last_run=self._last_result, running=running
        )


__all__ = [
    "PipelineRunResult",
    "PipelineStepResult",
    "WorkflowManager",
    "WorkflowOrchestrator",
]
