"""Application entry point for the Media Pipeline API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from api.config_router import router as config_router
from api.dedup_router import router as dedup_router
from modules.dedup import DedupService
from utils.config_loader import get_config_value, load_config
from utils.db_manager import DatabaseManager

app = FastAPI(title="Media Pipeline", version="0.2.0")


def _initialize_services(application: FastAPI) -> None:
    config = load_config()

    db_path = Path(get_config_value("system", "db_path", config=config))
    source_dir = Path(get_config_value("paths", "source_dir", config=config))
    duplicates_dir = Path(get_config_value("paths", "duplicates_dir", config=config))
    hash_algorithm = get_config_value(
        "dedup", "hash_algorithm", default="sha256", config=config
    )

    database = DatabaseManager(db_path)
    dedup_service = DedupService(
        database,
        source_dir=source_dir,
        duplicates_dir=duplicates_dir,
        hash_algorithm=hash_algorithm,
    )

    application.state.db = database
    application.state.dedup_service = dedup_service


_initialize_services(app)
app.include_router(dedup_router)
app.include_router(config_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


__all__ = ["app"]
