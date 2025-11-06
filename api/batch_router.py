"""FastAPI router for batch creation operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from modules.batch import BatchCreationResult, BatchService

router = APIRouter(prefix="/api/batch", tags=["batch"])


class BatchFileModel(BaseModel):
    source_path: str
    batch_path: str
    relative_path: str
    size: int
    sha256: str | None = None


class BatchCreateResponse(BaseModel):
    created: bool
    batch_name: str | None = None
    file_count: int = 0
    size_bytes: int = 0
    manifest_path: str | None = None
    created_at: str | None = None
    files: list[BatchFileModel] = Field(default_factory=list)


async def get_batch_service(request: Request) -> BatchService:
    service = getattr(request.app.state, "batch_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch service not configured",
        )
    return service


@router.post("/create", response_model=BatchCreateResponse)
async def create_batch(service: BatchService = Depends(get_batch_service)) -> BatchCreateResponse:
    try:
        result: BatchCreationResult = await run_in_threadpool(service.create_batch)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    data = result.to_dict()
    return BatchCreateResponse(**data)


__all__ = ["router", "create_batch", "get_batch_service"]
