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


@dataclass(slots=True)
class WorkflowDebugSettings:
    """Runtime controls for interactive workflow execution."""

    enabled: bool = False
    auto_advance: bool = False
    step_timeout_sec: float = 0.0


@dataclass(slots=True)
class WorkflowDebugState:
    """Track debug progress for external observers."""

    enabled: bool = False
    waiting: bool = False
    current_step: str | None = None
    last_step: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    note: str | None = None

    def to_dict(self, *, settings: WorkflowDebugSettings) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "waiting": self.waiting,
            "current_step": self.current_step,
            "last_step": self.last_step,
            "history": list(self.history),
            "note": self.note,
            "settings": {
                "auto_advance": settings.auto_advance,
                "step_timeout_sec": settings.step_timeout_sec,
            },
        }


class WorkflowOrchestrator:
    """Coordinate services to execute workflow steps."""

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container
        self._workflow_settings = container.workflow_settings
        delays = self._workflow_settings.get("delays", {})
        trace_settings = self._workflow_settings.get("trace", {})
        try:
            settle_value = float(delays.get("syncthing_settle_sec", 0) or 0)
        except (TypeError, ValueError):
            settle_value = 0.0
        try:
            post_sync_value = float(delays.get("post_sync_sec", 0) or 0)
        except (TypeError, ValueError):
            post_sync_value = 0.0
        try:
            sample_value = int(trace_settings.get("syncthing_samples", 25) or 25)
        except (TypeError, ValueError):
            sample_value = 25
        poll_config = get_config_value(
            "syncthing", "poll_interval_sec", default=10, config=container.config
        )
        try:
            poll_value = float(poll_config or 10)
        except (TypeError, ValueError):
            poll_value = 10.0
        self._syncthing_settle_sec = max(0.0, settle_value)
        self._post_sync_delay_sec = max(0.0, post_sync_value)
        self._syncthing_samples = max(1, sample_value)
        self._syncthing_poll_interval = max(1.0, poll_value / 5.0)

    @property
    def container(self) -> ServiceContainer:
        return self._container

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

        trace: list[dict[str, Any]] = []
        trace.append(sync_service.syncthing_snapshot(phase="pre-start"))

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
            "syncthing_settle_sec": self._syncthing_settle_sec,
            "post_sync_delay_sec": self._post_sync_delay_sec,
        }
        step_status = "completed" if start_result.started else "skipped"
        if start_result.status == BATCH_STATUS_SYNCED:
            step_status = "completed"
        elif start_result.status != BATCH_STATUS_SYNCED and not start_result.started:
            data["reason"] = "Batch already syncing"

        if start_result.started:
            sync_status, progress_trace = await self._monitor_sync_progress(batch_name)
            trace.extend(progress_trace)
            data["progress"] = sync_status.progress
            data["status"] = sync_status.status
            data["synced_at"] = sync_status.synced_at
            if sync_status.detail:
                data["detail"] = sync_status.detail
            if sync_status.syncthing:
                data["syncthing"] = sync_status.syncthing
            if sync_status.status != BATCH_STATUS_SYNCED:
                step_status = "warning"
                data["reason"] = "Sync did not reach completion"

        data["syncthing_trace"] = trace[-self._syncthing_samples :]
        return PipelineStepResult(name="sync", status=step_status, data=data)

    async def _monitor_sync_progress(self, batch_name: str) -> tuple[SyncStatus, list[dict[str, Any]]]:
        """Watch Syncthing progress until the batch settles."""

        sync_service = self._container.sync_service
        trace: list[dict[str, Any]] = []

        settle_remaining = self._syncthing_settle_sec
        while settle_remaining > 0 and len(trace) < self._syncthing_samples:
            trace.append(sync_service.syncthing_snapshot(phase="settle"))
            wait_time = min(self._syncthing_poll_interval, settle_remaining)
            await asyncio.sleep(wait_time)
            settle_remaining -= wait_time

        attempts = max(self._syncthing_samples - len(trace), 1)
        status = sync_service.status(batch_name)

        while attempts > 0:
            snapshot = dict(status.syncthing or {})
            snapshot.setdefault("status", status.status)
            snapshot.setdefault("progress", status.progress)
            snapshot.setdefault("synced_at", status.synced_at)
            snapshot["timestamp"] = datetime.now(timezone.utc).isoformat()
            trace.append(snapshot)

            if status.status == BATCH_STATUS_SYNCED:
                state_value = str(snapshot.get("state") or "").lower()
                if not state_value or ("scan" not in state_value and state_value != "syncing"):
                    break

            attempts -= 1
            if attempts <= 0:
                break
            await asyncio.sleep(self._syncthing_poll_interval)
            status = sync_service.status(batch_name)

        return status, trace[-self._syncthing_samples :]

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

    async def run_pipeline(
        self, *, debug: "WorkflowDebugController | None" = None
    ) -> PipelineRunResult:
        started_at = datetime.now(timezone.utc).isoformat()
        steps: list[PipelineStepResult] = []
        errors: list[str] = []

        dedup_result = await self.run_dedup()
        await self._append_step(steps, dedup_result, debug)
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

        for entry in batch_steps:
            await self._append_step(steps, entry, debug)
        batch_id = batch_result.data.get("batch_id") if batch_result.data else None
        if batch_result.status == "error" and batch_result.message:
            errors.append(f"batch: {batch_result.message}")

        if batch_result.status == "completed" and batch_id:
            sync_result = await self.run_sync(int(batch_id))
            await self._append_step(steps, sync_result, debug)
            if sync_result.status in {"error", "warning"} and sync_result.message:
                errors.append(f"sync: {sync_result.message}")

            if sync_result.status == "completed":
                await self._post_sync_delay()
                sort_result = self.run_sort(int(batch_id))
                await self._append_step(steps, sort_result, debug)
                if sort_result.status == "error" and sort_result.message:
                    errors.append(f"sort: {sort_result.message}")
            else:
                await self._append_step(
                    steps,
                    PipelineStepResult(
                        name="sort",
                        status="skipped",
                        message="Sorting deferred until sync completes",
                    ),
                    debug,
                )
        else:
            await self._append_step(
                steps,
                PipelineStepResult(
                    name="sync",
                    status="skipped",
                    message="No batch created",
                ),
                debug,
            )
            await self._append_step(
                steps,
                PipelineStepResult(
                    name="sort",
                    status="skipped",
                    message="No batch created",
                ),
                debug,
            )

        cleanup_result = self.run_cleanup()
        await self._append_step(steps, cleanup_result, debug)

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

    async def _append_step(
        self,
        accumulator: list[PipelineStepResult],
        result: PipelineStepResult,
        debug: "WorkflowDebugController | None",
    ) -> None:
        accumulator.append(result)
        if debug is not None:
            await debug.after_step(result)

    async def _post_sync_delay(self) -> None:
        delay = self._post_sync_delay_sec
        if delay > 0:
            await asyncio.sleep(delay)

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
        self._debug_state = WorkflowDebugState()
        self._debug_settings = WorkflowDebugSettings()
        self._debug_event = asyncio.Event()
        self._debug_event.set()

    @property
    def orchestrator(self) -> WorkflowOrchestrator:
        return self._orchestrator

    async def trigger(self) -> bool:
        async with self._lock:
            if self._current_task and not self._current_task.done():
                return False
            settings = self._derive_debug_settings()
            self._prepare_debug(settings)
            loop = asyncio.get_running_loop()
            self._current_task = loop.create_task(self._run(settings))
            return True

    async def _run(self, settings: WorkflowDebugSettings) -> PipelineRunResult:
        controller = WorkflowDebugController(self, settings)
        try:
            result = await self._orchestrator.run_pipeline(debug=controller)
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
                self._debug_state.waiting = False
                self._debug_state.current_step = None
                self._debug_event.set()

    def status(self) -> dict[str, Any]:
        running = bool(self._current_task and not self._current_task.done())
        return {
            "running": running,
            "last_result": self._last_result.to_dict() if self._last_result else None,
            "error": self._last_error,
            "debug": self.debug_state(),
        }

    def overview(self) -> dict[str, Any]:
        running = bool(self._current_task and not self._current_task.done())
        return self._orchestrator.build_overview(
            last_run=self._last_result, running=running
        )

    def debug_state(self) -> dict[str, Any]:
        return self._debug_state.to_dict(settings=self._debug_settings)

    def advance_debug(self) -> dict[str, Any]:
        self._debug_state.note = "Manual continue requested"
        self._debug_event.set()
        return self.debug_state()

    def _prepare_debug(self, settings: WorkflowDebugSettings) -> None:
        self._debug_settings = settings
        state = self._debug_state
        state.enabled = settings.enabled
        state.waiting = False
        state.current_step = None
        state.last_step = None
        state.note = None
        state.history.clear()
        self._debug_event.set()

    def _derive_debug_settings(self) -> WorkflowDebugSettings:
        mapping = getattr(self._orchestrator.container, "workflow_settings", {})
        debug_map = mapping.get("debug", {}) if isinstance(mapping, dict) else {}
        enabled = bool(debug_map.get("enabled"))
        auto = bool(debug_map.get("auto_advance"))
        try:
            timeout = float(debug_map.get("step_timeout_sec", 0) or 0)
        except (TypeError, ValueError):
            timeout = 0.0
        return WorkflowDebugSettings(
            enabled=enabled,
            auto_advance=auto,
            step_timeout_sec=max(0.0, timeout),
        )

    def _register_step_result(self, result: PipelineStepResult) -> None:
        entry = {
            "name": result.name,
            "status": result.status,
            "message": result.message,
            "data": result.data,
        }
        self._debug_state.last_step = entry
        history = self._debug_state.history
        history.append(entry)
        max_items = 25
        if len(history) > max_items:
            del history[:-max_items]

    async def _await_debug_confirmation(self, step_name: str, timeout: float | None) -> None:
        if not self._debug_settings.enabled or self._debug_settings.auto_advance:
            return
        self._debug_state.waiting = True
        self._debug_state.current_step = step_name
        self._debug_event.clear()
        try:
            if timeout and timeout > 0:
                await asyncio.wait_for(self._debug_event.wait(), timeout)
                self._debug_state.note = None
            else:
                await self._debug_event.wait()
                self._debug_state.note = None
        except asyncio.TimeoutError:
            self._debug_state.note = f"Step '{step_name}' auto-continued after timeout"
        finally:
            self._debug_state.waiting = False
            self._debug_state.current_step = None
            self._debug_event.set()


class WorkflowDebugController:
    """Bridge orchestrator step callbacks with debug state management."""

    def __init__(self, manager: WorkflowManager, settings: WorkflowDebugSettings) -> None:
        self._manager = manager
        self._settings = settings

    async def after_step(self, result: PipelineStepResult) -> None:
        self._manager._register_step_result(result)
        if not self._settings.enabled:
            return
        if self._settings.auto_advance:
            return
        timeout = self._settings.step_timeout_sec
        await self._manager._await_debug_confirmation(
            result.name,
            timeout if timeout and timeout > 0 else None,
        )


__all__ = [
    "PipelineRunResult",
    "PipelineStepResult",
    "WorkflowManager",
    "WorkflowOrchestrator",
]
