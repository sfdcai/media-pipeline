"""YAML configuration loader for the media pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, MutableMapping

import yaml

DEFAULT_CONFIG_PATH = Path("/etc/media-pipeline/config.yaml")
DEFAULT_CONFIG: Dict[str, Any] = {
    "paths": {
        "source_dir": str(Path("/var/lib/media-pipeline/source")),
        "duplicates_dir": str(Path("/var/lib/media-pipeline/duplicates")),
        "batch_dir": str(Path("/var/lib/media-pipeline/batches")),
        "sorted_dir": str(Path("/var/lib/media-pipeline/sorted")),
        "temp_dir": str(Path("/var/lib/media-pipeline/temp")),
    },
    "dedup": {
        "hash_algorithm": "sha256",
        "threads": 2,
        "move_duplicates": False,
    },
    "system": {
        "db_path": str(Path("/var/lib/media-pipeline/db.sqlite")),
        "log_dir": str(Path("/var/log/media-pipeline")),
        "port_api": 8080,
        "port_dbui": 8081,
        "max_parallel_fs_ops": 4,
        "cleanup_empty_batches": True,
    },
}


def _deep_merge(
    base: MutableMapping[str, Any], override: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key, value in override.items():
        if (
            key in base
            and isinstance(base[key], MutableMapping)
            and isinstance(value, MutableMapping)
        ):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path: Path | str | None = None) -> Dict[str, Any]:
    """Load configuration from YAML, falling back to defaults when absent."""

    candidate = Path(path) if path else None
    if candidate is None:
        env_override = os.getenv("MEDIA_PIPELINE_CONFIG")
        candidate = Path(env_override) if env_override else DEFAULT_CONFIG_PATH

    if candidate.exists():
        with candidate.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    else:
        data = {}

    merged = yaml.safe_load(yaml.dump(DEFAULT_CONFIG))
    if isinstance(data, dict):
        _deep_merge(merged, data)
    return merged


def get_config_value(
    *keys: str, default: Any | None = None, config: Dict[str, Any] | None = None
) -> Any:
    """Retrieve a nested configuration value by walking *keys*."""

    current: Any = config or load_config()
    for key in keys:
        if not isinstance(current, MutableMapping) or key not in current:
            return default
        current = current[key]
    return current


__all__ = ["load_config", "get_config_value", "DEFAULT_CONFIG_PATH", "DEFAULT_CONFIG"]
