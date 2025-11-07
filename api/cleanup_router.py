"""FastAPI router for maintenance tasks."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from modules.cleanup import CleanupService

router = APIRouter(prefix="/api/cleanup", tags=["cleanup"])


class CleanupResponse(BaseModel):
    removed_batch_dirs: list[str]
    deleted_temp_files: list[str]
    rotated_logs: list[str]


async def get_cleanup_service(request: Request) -> CleanupService:
    service = getattr(request.app.state, "cleanup_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Cleanup service not configured")
    return service


@router.post("/run", response_model=CleanupResponse)
async def run_cleanup(
    service: CleanupService = Depends(get_cleanup_service),
) -> CleanupResponse:
    result = service.run()
    return CleanupResponse(**asdict(result))


__all__ = ["router", "run_cleanup"]
