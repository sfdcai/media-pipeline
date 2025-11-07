from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from api.workflow_router import (
    run_workflow,
    workflow_overview,
    workflow_sort,
    workflow_status,
    workflow_sync,
)
from modules.batch import BatchCreationResult
from modules.cleanup import CleanupReport
from modules.exif_sorter import SortResult
from modules.sync_monitor import SyncStartResult, SyncStatus
from modules.workflow import WorkflowManager, WorkflowOrchestrator


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class StubDedupService:
    def __init__(self) -> None:
        self.started = False

    async def start(self) -> bool:
        self.started = not self.started
        return self.started

    async def wait_for_completion(self) -> None:  # pragma: no cover - simple stub
        return None

    def status(self) -> dict[str, object]:
        return {
            "running": False,
            "total_files": 10,
            "processed_files": 10,
            "duplicate_files": 1,
            "error": None,
            "last_processed": "example.jpg",
        }


class StubBatchService:
    def create_batch(self) -> BatchCreationResult:
        return BatchCreationResult(
            created=True,
            batch_id=1,
            batch_name="batch_001",
            file_count=3,
            size_bytes=123,
            manifest_path="/tmp/manifest.json",
        )


class StubSyncService:
    def __init__(self) -> None:
        self._status_calls = 0

    def start(self, batch_name: str) -> SyncStartResult:
        return SyncStartResult(batch=batch_name, started=True, status="SYNCING")

    def status(self, batch_name: str) -> SyncStatus:
        self._status_calls += 1
        if self._status_calls >= 2:
            return SyncStatus(batch=batch_name, status="SYNCED", progress=100.0, synced_at="now")
        return SyncStatus(batch=batch_name, status="SYNCING", progress=50.0, synced_at=None)


class StubSortService:
    def start(self, batch_name: str) -> SortResult:
        return SortResult(batch=batch_name, sorted_files=3, skipped_files=0, started=True)


class StubCleanupService:
    def run(self) -> CleanupReport:
        return CleanupReport(
            removed_batch_dirs=["/tmp/batch_001"],
            deleted_temp_files=[],
            rotated_logs=[],
        )


class StubDatabase:
    def fetchall(self, query: str, params: tuple[object, ...] | None = None):
        if "FROM batches" in query:
            return [
                {
                    "id": 1,
                    "name": "batch_001",
                    "status": "SYNCED",
                    "created_at": "2024-01-01T00:00:00Z",
                    "synced_at": "2024-01-01T00:10:00Z",
                    "sorted_at": "2024-01-01T00:20:00Z",
                    "manifest_path": "/tmp/manifest.json",
                }
            ]
        return [{"status": "UNIQUE", "count": 3}, {"status": "SORTED", "count": 5}]

    def fetchone(self, query: str, params: tuple[object, ...] | None = None):
        if "WHERE id = ?" in query:
            return {"id": 1, "name": "batch_001", "status": "SYNCED"}
        return None


def build_stub_orchestrator() -> WorkflowOrchestrator:
    container = SimpleNamespace(
        config={"system": {}},
        database=StubDatabase(),
        dedup_service=StubDedupService(),
        batch_service=StubBatchService(),
        sync_service=StubSyncService(),
        sort_service=StubSortService(),
        cleanup_service=StubCleanupService(),
    )
    return WorkflowOrchestrator(container)  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_workflow_orchestrator_pipeline_happy_path():
    orchestrator = build_stub_orchestrator()
    result = await orchestrator.run_pipeline()

    assert not result.errors
    assert any(step.name == "dedup" for step in result.steps)
    assert any(step.name == "batch" and step.status == "completed" for step in result.steps)
    assert any(step.name == "sync" and step.data.get("status") == "SYNCED" for step in result.steps)
    assert any(step.name == "sort" and step.status == "completed" for step in result.steps)
    assert any(step.name == "cleanup" for step in result.steps)


@pytest.mark.anyio
async def test_workflow_orchestrator_overview_includes_last_run():
    orchestrator = build_stub_orchestrator()
    last_run = await orchestrator.run_pipeline()
    overview = orchestrator.build_overview(last_run=last_run, running=False)

    assert overview["dedup"]["processed_files"] == 10
    assert overview["recent_batches"][0]["name"] == "batch_001"
    assert overview["file_counts"]["SORTED"] == 5
    assert overview["last_run"]["steps"]


class FakeManager:
    def __init__(self) -> None:
        orchestrator = build_stub_orchestrator()
        self._manager = WorkflowManager(orchestrator)

    async def trigger(self) -> bool:
        return True

    def status(self) -> dict[str, object]:
        return {"running": False, "last_result": None, "error": None}

    def overview(self) -> dict[str, object]:
        return {
            "running": False,
            "dedup": {"running": False},
            "recent_batches": [],
            "file_counts": {},
        }

    @property
    def orchestrator(self) -> WorkflowOrchestrator:
        return self._manager.orchestrator


@pytest.mark.anyio
async def test_workflow_router_endpoints():
    fake_manager = FakeManager()

    assert await run_workflow(fake_manager) == {"started": True}

    status_payload = await workflow_status(fake_manager)
    assert status_payload["running"] is False

    overview_payload = await workflow_overview(fake_manager)
    assert "dedup" in overview_payload

    sync_payload = await workflow_sync(1, fake_manager)
    assert sync_payload["status"] in {"completed", "warning", "error"}

    sort_payload = await workflow_sort(1, fake_manager)
    assert sort_payload["status"] == "completed"

