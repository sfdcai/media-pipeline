"""Factory helpers for constructing application services consistently."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.batch import BatchService
from modules.cleanup import CleanupService
from modules.dashboard import DashboardService
from modules.dedup import DedupService
from modules.exif_sorter import SortService
from modules.sync_monitor import SyncService
from utils.config_loader import get_config_value, load_config, resolve_config_path
from utils.db_manager import DatabaseManager
from utils.syncthing_api import SyncthingAPI


@dataclass(slots=True)
class ServiceContainer:
    """Bundle of core services used across the application."""

    config: dict[str, Any]
    config_path: Path
    database: DatabaseManager
    dedup_service: DedupService
    batch_service: BatchService
    sync_service: SyncService
    sort_service: SortService
    cleanup_service: CleanupService
    dashboard_service: DashboardService
    syncthing_api: SyncthingAPI


def build_service_container(
    config: dict[str, Any] | None = None,
    *,
    config_path: Path | str | None = None,
) -> ServiceContainer:
    """Construct application services from configuration.

    The logic mirrors the initialization performed for the FastAPI application
    while allowing other entry points (CLI, background workers) to share the
    same wiring without re-implementing the setup steps.
    """

    if config_path is not None:
        resolved_path = Path(config_path)
    else:
        resolved_path = Path(resolve_config_path())

    config_data = config or load_config(resolved_path)

    db_path = Path(get_config_value("system", "db_path", config=config_data))
    source_dir = Path(get_config_value("paths", "source_dir", config=config_data))
    duplicates_dir = Path(
        get_config_value("paths", "duplicates_dir", config=config_data)
    )
    batch_dir = Path(get_config_value("paths", "batch_dir", config=config_data))
    sorted_dir = Path(get_config_value("paths", "sorted_dir", config=config_data))
    temp_dir = Path(get_config_value("paths", "temp_dir", config=config_data))

    hash_algorithm = get_config_value(
        "dedup", "hash_algorithm", default="sha256", config=config_data
    )
    batch_max_size = get_config_value(
        "batch", "max_size_gb", default=15, config=config_data
    )
    batch_selection_mode = get_config_value(
        "batch", "selection_mode", default="size", config=config_data
    )
    batch_max_files = get_config_value(
        "batch", "max_files", default=0, config=config_data
    )
    batch_allow_parallel_value = get_config_value(
        "batch", "allow_parallel", default=False, config=config_data
    )
    if isinstance(batch_allow_parallel_value, str):
        batch_allow_parallel = batch_allow_parallel_value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    else:
        batch_allow_parallel = bool(batch_allow_parallel_value)
    batch_pattern = get_config_value(
        "batch", "naming_pattern", default="batch_{index:03d}", config=config_data
    )
    folder_pattern = get_config_value(
        "sorter", "folder_pattern", default="{year}/{month:02d}/{day:02d}", config=config_data
    )
    exif_fallback = bool(
        get_config_value("sorter", "exif_fallback", default=True, config=config_data)
    )

    syncthing_url = str(
        get_config_value(
            "syncthing",
            "api_url",
            default="http://127.0.0.1:8384/rest",
            config=config_data,
        )
    )
    syncthing_key = get_config_value("syncthing", "api_key", default="", config=config_data)
    syncthing_folder = get_config_value(
        "syncthing", "folder_id", default="", config=config_data
    )
    syncthing_device = get_config_value(
        "syncthing", "device_id", default="", config=config_data
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
        naming_pattern=str(batch_pattern)
        if batch_pattern is not None
        else "batch_{index:03d}",
        selection_mode=str(batch_selection_mode or "size"),
        max_files=batch_max_files,
        allow_parallel=batch_allow_parallel,
    )
    sync_service = SyncService(
        database,
        batch_dir=batch_dir,
        syncthing_api=syncthing_api,
        folder_id=str(syncthing_folder or "").strip() or None,
        device_id=str(syncthing_device or "").strip() or None,
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
        log_dir=Path(get_config_value("system", "log_dir", config=config_data)),
        batch_pattern=str(batch_pattern) if batch_pattern is not None else None,
    )
    dashboard_service = DashboardService(
        database,
        batch_dir=batch_dir,
        sorted_dir=sorted_dir,
    )

    return ServiceContainer(
        config=config_data,
        config_path=resolved_path,
        database=database,
        dedup_service=dedup_service,
        batch_service=batch_service,
        sync_service=sync_service,
        sort_service=sort_service,
        cleanup_service=cleanup_service,
        dashboard_service=dashboard_service,
        syncthing_api=syncthing_api,
    )


__all__ = ["ServiceContainer", "build_service_container"]
