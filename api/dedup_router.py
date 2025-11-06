"""FastAPI router for deduplication operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from modules.dedup import DedupService

router = APIRouter(prefix="/api/dedup", tags=["dedup"])


class DedupStartResponse(BaseModel):
    started: bool


class DedupStatusResponse(BaseModel):
    running: bool
    total_files: int
    processed_files: int
    duplicate_files: int
    error: str | None = None
    last_processed: str | None = None


async def get_dedup_service(request: Request) -> DedupService:
    service = getattr(request.app.state, "dedup_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Dedup service not configured")
    return service


@router.post("/start", response_model=DedupStartResponse)
async def start_dedup(
    service: DedupService = Depends(get_dedup_service),
) -> DedupStartResponse:
    started = await service.start()
    return DedupStartResponse(started=started)


@router.get("/status", response_model=DedupStatusResponse)
async def dedup_status(
    service: DedupService = Depends(get_dedup_service),
) -> DedupStatusResponse:
    state = service.status()
    return DedupStatusResponse(**state)


__all__ = ["router", "start_dedup", "dedup_status"]
