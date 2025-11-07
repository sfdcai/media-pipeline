"""Application entry point for the Media Pipeline API."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from api.batch_router import router as batch_router
from api.cleanup_router import router as cleanup_router
from api.config_router import router as config_router
from api.dashboard_router import router as dashboard_router
from api.dedup_router import router as dedup_router
from api.sort_router import router as sort_router
from api.sync_router import router as sync_router
from api.workflow_router import router as workflow_router
from middlewares import APIKeyMiddleware
from modules.workflow import WorkflowManager, WorkflowOrchestrator
from utils.config_loader import get_config_value, load_config, resolve_config_path
from utils.service_container import build_service_container

app = FastAPI(title="Media Pipeline", version="0.2.0")
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _initialize_services(application: FastAPI) -> None:
    config_override = os.getenv("MEDIA_PIPELINE_CONFIG")
    config_path = resolve_config_path(config_override)
    config_data = load_config(config_path)
    container = build_service_container(config_data, config_path=config_path)

    application.state.db = container.database
    application.state.dedup_service = container.dedup_service
    application.state.batch_service = container.batch_service
    application.state.sync_service = container.sync_service
    application.state.sort_service = container.sort_service
    application.state.cleanup_service = container.cleanup_service
    application.state.dashboard_service = container.dashboard_service
    application.state.syncthing_api = container.syncthing_api
    application.state.config = container.config
    application.state.config_path = str(config_path)
    os.environ.setdefault("MEDIA_PIPELINE_CONFIG", str(config_path))

    orchestrator = WorkflowOrchestrator(container)
    application.state.workflow_orchestrator = orchestrator
    application.state.workflow_manager = WorkflowManager(orchestrator)


_initialize_services(app)
app.include_router(dedup_router)
app.include_router(config_router)
app.include_router(batch_router)
app.include_router(sync_router)
app.include_router(sort_router)
app.include_router(cleanup_router)
app.include_router(dashboard_router)
app.include_router(workflow_router)


def _configure_auth(application: FastAPI) -> None:
    config = getattr(application.state, "config", None)
    if config is None:
        config = load_config()

    config_key = get_config_value("auth", "api_key", default="", config=config)
    header_name = get_config_value("auth", "header_name", default="x-api-key", config=config)
    env_key = os.getenv("MEDIA_PIPELINE_API_KEY")
    api_key = str(env_key or config_key or "").strip()

    exempt_paths = {
        "",
        "/",
        "/health",
        "/config",
        "/dashboard",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    if api_key:
        application.add_middleware(
            APIKeyMiddleware,
            api_key=api_key,
            header_name=str(header_name or "x-api-key"),
            exempt_paths=exempt_paths,
        )


_configure_auth(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/control", response_class=HTMLResponse)
def control_center(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("control.html", {"request": request})


@app.get("/config", response_class=JSONResponse)
async def configuration_snapshot(request: Request) -> JSONResponse:
    """Expose the effective configuration for convenience tooling."""

    config = getattr(request.app.state, "config", None)
    if not isinstance(config, dict):
        config = load_config()
    return JSONResponse(config)


__all__ = ["app"]
