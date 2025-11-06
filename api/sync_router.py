"""FastAPI router exposing synchronization endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from modules.sync_monitor import SyncService

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


async def get_sync_service(request: Request) -> SyncService:
    service = getattr(request.app.state, "sync_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Sync service not configured")
    return service


@router.post("/start/{batch_name}", response_model=SyncStartResponse)
async def start_sync(
    batch_name: str,
    service: SyncService = Depends(get_sync_service),
) -> SyncStartResponse:
    try:
        result = service.start(batch_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SyncStartResponse(**result.__dict__)


@router.get("/status/{batch_name}", response_model=SyncStatusResponse)
async def sync_status(
    batch_name: str,
    service: SyncService = Depends(get_sync_service),
) -> SyncStatusResponse:
    try:
        result = service.status(batch_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SyncStatusResponse(**result.__dict__)


__all__ = ["router", "start_sync", "sync_status"]
