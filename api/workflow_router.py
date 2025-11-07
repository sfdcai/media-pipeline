"""Endpoints that expose high-level workflow orchestration helpers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from modules.workflow import WorkflowManager

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


def get_manager(request: Request) -> WorkflowManager:
    manager = getattr(request.app.state, "workflow_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Workflow manager not configured",
        )
    return manager


@router.post("/run", response_model=dict)
async def run_workflow(manager: WorkflowManager = Depends(get_manager)) -> dict:
    started = await manager.trigger()
    return {"started": started}


@router.get("/status", response_model=dict)
async def workflow_status(manager: WorkflowManager = Depends(get_manager)) -> dict:
    return manager.status()


@router.get("/overview", response_model=dict)
async def workflow_overview(manager: WorkflowManager = Depends(get_manager)) -> dict:
    return manager.overview()


@router.post("/sync/{batch_name}", response_model=dict)
async def workflow_sync(
    batch_name: str, manager: WorkflowManager = Depends(get_manager)
) -> dict:
    result = await manager.orchestrator.run_sync(batch_name)
    return {
        "status": result.status,
        "message": result.message,
        "data": result.data,
    }


@router.post("/sort/{batch_name}", response_model=dict)
async def workflow_sort(
    batch_name: str, manager: WorkflowManager = Depends(get_manager)
) -> dict:
    result = manager.orchestrator.run_sort(batch_name)
    return {
        "status": result.status,
        "message": result.message,
        "data": result.data,
    }


__all__ = [
    "router",
    "run_workflow",
    "workflow_status",
    "workflow_overview",
    "workflow_sync",
    "workflow_sort",
]
