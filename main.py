"""Application entry point for the Media Pipeline API."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api.batch_router import router as batch_router
from api.cleanup_router import router as cleanup_router
from api.config_router import router as config_router
from api.dashboard_router import router as dashboard_router
from api.dedup_router import router as dedup_router
from api.sort_router import router as sort_router
from api.sync_router import router as sync_router
from middlewares import APIKeyMiddleware
from modules.batch import BatchService
from modules.cleanup import CleanupService
from modules.dashboard import DashboardService
from modules.dedup import DedupService
from modules.exif_sorter import SortService
from modules.sync_monitor import SyncService
from utils.config_loader import get_config_value, load_config
from utils.db_manager import DatabaseManager
from utils.syncthing_api import SyncthingAPI

app = FastAPI(title="Media Pipeline", version="0.2.0")
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _initialize_services(application: FastAPI) -> None:
    config = load_config()

    db_path = Path(get_config_value("system", "db_path", config=config))
    source_dir = Path(get_config_value("paths", "source_dir", config=config))
    duplicates_dir = Path(get_config_value("paths", "duplicates_dir", config=config))
    hash_algorithm = get_config_value(
        "dedup", "hash_algorithm", default="sha256", config=config
    )
    batch_dir = Path(get_config_value("paths", "batch_dir", config=config))
    sorted_dir = Path(get_config_value("paths", "sorted_dir", config=config))
    temp_dir = Path(get_config_value("paths", "temp_dir", config=config))
    batch_max_size = get_config_value("batch", "max_size_gb", default=15, config=config)
    batch_pattern = get_config_value(
        "batch", "naming_pattern", default="batch_{index:03d}", config=config
    )
    syncthing_url = str(
        get_config_value("syncthing", "api_url", default="http://127.0.0.1:8384/rest", config=config)
    )
    syncthing_key = get_config_value("syncthing", "api_key", default="", config=config)
    syncthing_folder = get_config_value("syncthing", "folder_id", default="", config=config)
    folder_pattern = get_config_value(
        "sorter", "folder_pattern", default="{year}/{month:02d}/{day:02d}", config=config
    )
    exif_fallback = bool(
        get_config_value("sorter", "exif_fallback", default=True, config=config)
    )

    database = DatabaseManager(db_path)
    dedup_service = DedupService(
        database,
        source_dir=source_dir,
        duplicates_dir=duplicates_dir,
        hash_algorithm=hash_algorithm,
    )
    syncthing_api = SyncthingAPI(syncthing_url, api_key=str(syncthing_key or ""))
    batch_service = BatchService(
        database,
        source_dir=source_dir,
        batch_dir=batch_dir,
        max_size_gb=float(batch_max_size) if batch_max_size is not None else 0,
        naming_pattern=str(batch_pattern) if batch_pattern is not None else "batch_{index:03d}",
    )
    sync_service = SyncService(
        database,
        batch_dir=batch_dir,
        syncthing_api=syncthing_api,
        folder_id=str(syncthing_folder or "").strip() or None,
    )
    sort_service = SortService(
        database,
        batch_dir=batch_dir,
        sorted_dir=sorted_dir,
        folder_pattern=str(folder_pattern),
        exif_fallback=exif_fallback,
    )
    cleanup_service = CleanupService(
        batch_dir=batch_dir,
        temp_dir=temp_dir,
        log_dir=Path(get_config_value("system", "log_dir", config=config)),
    )
    dashboard_service = DashboardService(
        database, batch_dir=batch_dir, sorted_dir=sorted_dir
    )

    application.state.db = database
    application.state.dedup_service = dedup_service
    application.state.batch_service = batch_service
    application.state.sync_service = sync_service
    application.state.sort_service = sort_service
    application.state.cleanup_service = cleanup_service
    application.state.dashboard_service = dashboard_service
    application.state.syncthing_api = syncthing_api
    application.state.config = config


_initialize_services(app)
app.include_router(dedup_router)
app.include_router(config_router)
app.include_router(batch_router)
app.include_router(sync_router)
app.include_router(sort_router)
app.include_router(cleanup_router)
app.include_router(dashboard_router)


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


__all__ = ["app"]
