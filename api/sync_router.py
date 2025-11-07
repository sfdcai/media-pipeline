"""FastAPI router exposing synchronization endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from modules.sync_monitor import SyncDiagnostics, SyncService

router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncStartResponse(BaseModel):
    batch: str
    started: bool
    status: str


class SyncStatusResponse(BaseModel):
    batch: str
    status: str
    progress: float
    synced_at: str | None = None
    detail: str | None = None


class SyncDiagnosticsResponse(BaseModel):
    batch_dir: str
    folder_id: str | None = None
    device_id: str | None = None
    last_error: str | None = None
    syncthing_status: dict[str, Any]


def _resolve_batch_name(batch_id: int, request: Request) -> str:
    database = getattr(request.app.state, "db", None)
    if database is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    row = database.fetchone("SELECT name FROM batches WHERE id = ?", (batch_id,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown batch id {batch_id}")
    return row["name"]


def _resolve_batch_name(batch_id: int, request: Request) -> str:
    database = getattr(request.app.state, "db", None)
    if database is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    row = database.fetchone("SELECT name FROM batches WHERE id = ?", (batch_id,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown batch id {batch_id}")
    return row["name"]


async def get_sync_service(request: Request) -> SyncService:
    service = getattr(request.app.state, "sync_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Sync service not configured")
    return service


SyncServiceDep = Annotated[SyncService, Depends(get_sync_service)]


@router.post("/start/{batch_id}", response_model=SyncStartResponse)
async def start_sync(
    batch_id: int,
    request: Request,
    service: SyncServiceDep,
) -> SyncStartResponse:
    try:
        batch_name = _resolve_batch_name(batch_id, request)
        result = service.start(batch_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SyncStartResponse(**result.__dict__)


@router.get("/status/{batch_id}", response_model=SyncStatusResponse)
async def sync_status(
    batch_id: int,
    request: Request,
    service: SyncServiceDep,
) -> SyncStatusResponse:
    try:
        batch_name = _resolve_batch_name(batch_id, request)
        result = service.status(batch_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SyncStatusResponse(**result.__dict__)


@router.get("/diagnostics", response_model=SyncDiagnosticsResponse)
async def sync_diagnostics(service: SyncServiceDep) -> SyncDiagnosticsResponse:
    diagnostics: SyncDiagnostics = service.diagnostics()
    return SyncDiagnosticsResponse(**diagnostics.__dict__)


__all__ = ["router", "start_sync", "sync_status", "sync_diagnostics"]
