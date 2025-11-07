"""FastAPI router for dashboard summary metrics."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from modules.dashboard import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class DashboardSummaryModel(BaseModel):
    generated_at: str
    files: dict[str, Any]
    batches: dict[str, Any]
    storage: dict[str, Any]
    recent_batches: list[dict[str, Any]]


async def get_dashboard_service(request: Request) -> DashboardService:
    service = getattr(request.app.state, "dashboard_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Dashboard service not configured")
    return service


@router.get("", response_model=DashboardSummaryModel)
async def get_dashboard_summary(
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummaryModel:
    summary = service.summary()
    return DashboardSummaryModel(**asdict(summary))


__all__ = ["router", "get_dashboard_summary"]
