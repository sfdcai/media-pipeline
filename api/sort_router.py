"""FastAPI router exposing sorting endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from modules.exif_sorter import SortService

router = APIRouter(prefix="/api/sort", tags=["sort"])


class SortStartResponse(BaseModel):
    batch: str
    sorted_files: int
    skipped_files: int
    started: bool


class SortStatusResponse(BaseModel):
    batch: str
    status: str
    total_files: int
    sorted_files: int


async def get_sort_service(request: Request) -> SortService:
    service = getattr(request.app.state, "sort_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Sort service not configured")
    return service


@router.post("/start/{batch_name}", response_model=SortStartResponse)
async def start_sort(
    batch_name: str,
    service: SortService = Depends(get_sort_service),
) -> SortStartResponse:
    try:
        result = service.start(batch_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SortStartResponse(**asdict(result))


@router.get("/status/{batch_name}", response_model=SortStatusResponse)
async def sort_status(
    batch_name: str,
    service: SortService = Depends(get_sort_service),
) -> SortStatusResponse:
    try:
        result = service.status(batch_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SortStatusResponse(**asdict(result))


__all__ = ["router", "start_sort", "sort_status"]
