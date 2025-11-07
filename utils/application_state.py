"""Helpers for wiring the service container into a FastAPI application."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from modules.workflow import WorkflowManager, WorkflowOrchestrator
from utils.service_container import ServiceContainer


def _close_database(candidate: Any) -> None:
    close = getattr(candidate, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # pragma: no cover - defensive cleanup
            pass


def install_container(app: FastAPI, container: ServiceContainer) -> None:
    """Attach *container* services to *app* and refresh global state."""

    state = app.state

    existing_db = getattr(state, "db", None)
    if existing_db is not container.database and existing_db is not None:
        _close_database(existing_db)

    state.db = container.database
    state.dedup_service = container.dedup_service
    state.batch_service = container.batch_service
    state.sync_service = container.sync_service
    state.sort_service = container.sort_service
    state.cleanup_service = container.cleanup_service
    state.dashboard_service = container.dashboard_service
    state.syncthing_api = container.syncthing_api
    state.config = container.config
    state.config_path = str(container.config_path)
    state.workflow_settings = container.workflow_settings
    state.container = container

    orchestrator = WorkflowOrchestrator(container)
    state.workflow_orchestrator = orchestrator
    state.workflow_manager = WorkflowManager(orchestrator)

    os.environ["MEDIA_PIPELINE_CONFIG"] = str(container.config_path)


__all__ = ["install_container"]
