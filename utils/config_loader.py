"""YAML configuration loader for the media pipeline."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, MutableMapping, cast

import yaml

DEFAULT_CONFIG_PATH = Path("/etc/media-pipeline/config.yaml")
DEFAULT_CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "default_config.yaml"


def _load_default_config() -> Dict[str, Any]:
    """Read the repository default configuration YAML."""

    if DEFAULT_CONFIG_FILE.exists():
        with DEFAULT_CONFIG_FILE.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if isinstance(data, dict):
            return cast(Dict[str, Any], data)
        raise ValueError("Default configuration file must contain a mapping at the top level")

    # Fallback values mirror the documented defaults.
    return {
        "paths": {
            "source_dir": str(Path("/mnt/nas/photos_raw")),
            "duplicates_dir": str(Path("/mnt/nas/duplicates")),
            "batch_dir": str(Path("/mnt/nas/syncthing/upload")),
            "sorted_dir": str(Path("/mnt/nas/photos_sorted")),
            "temp_dir": str(Path("/opt/media-pipeline/data/temp")),
        },
        "batch": {
            "max_size_gb": 15,
            "naming_pattern": "batch_{index:03d}",
            "selection_mode": "size",
            "max_files": 0,
            "allow_parallel": False,
            "transfer_mode": "move",
        },
        "dedup": {
            "hash_algorithm": "sha256",
            "threads": 4,
            "move_duplicates": True,
        },
        "syncthing": {
            "api_url": "http://127.0.0.1:8384/rest",
            "api_key": "",
            "folder_id": "",
            "device_id": "",
            "poll_interval_sec": 60,
            "auto_sort_after_sync": True,
            "rescan_delay_sec": 3,
        },
        "sorter": {
            "folder_pattern": "{year}/{month:02d}/{day:02d}",
            "exif_fallback": True,
            "transfer_mode": "move",
        },
        "auth": {
            "api_key": "",
            "header_name": "x-api-key",
        },
        "system": {
            "db_path": str(Path("/var/lib/media-pipeline/db.sqlite")),
            "log_dir": str(Path("/var/log/media-pipeline")),
            "port_api": 8080,
            "port_dbui": 8081,
            "max_parallel_fs_ops": 4,
            "cleanup_empty_batches": True,
        },
        "workflow": {
            "debug": {
                "enabled": False,
                "auto_advance": False,
                "step_timeout_sec": 0,
            },
            "delays": {
                "syncthing_settle_sec": 5,
                "post_sync_sec": 10,
            },
            "trace": {
                "syncthing_samples": 25,
            },
        },
    }


DEFAULT_CONFIG: Dict[str, Any] = _load_default_config()


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


def resolve_config_path(path: Path | str | None = None) -> Path:
    """Resolve the configuration file path using overrides or defaults."""

    if path is not None:
        if isinstance(path, Path):
            text = str(path).strip()
            if text:
                return Path(text).expanduser()
        else:
            text = str(path).strip()
            if text:
                return Path(text).expanduser()

    env_override = os.getenv("MEDIA_PIPELINE_CONFIG", "").strip()
    if env_override:
        return Path(env_override).expanduser()
    return DEFAULT_CONFIG_PATH


def load_raw_config(path: Path | str | None = None) -> Dict[str, Any]:
    """Load configuration data from YAML without applying defaults."""

    candidate = resolve_config_path(path)
    if candidate.exists():
        with candidate.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    else:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Configuration file must contain a mapping at the top level")
    return data


def merge_configs(
    base: MutableMapping[str, Any], override: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Return a deep-merged copy of *base* updated with *override*."""

    merged = deepcopy(base)
    _deep_merge(merged, override)
    return merged


def save_config(data: MutableMapping[str, Any], path: Path | str | None = None) -> Path:
    """Persist configuration data to YAML on disk."""

    candidate = resolve_config_path(path)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    with candidate.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=True, allow_unicode=True)
    return candidate


def load_config(path: Path | str | None = None) -> Dict[str, Any]:
    """Load configuration from YAML, falling back to defaults when absent."""

    data = load_raw_config(path)

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


__all__ = [
    "load_config",
    "load_raw_config",
    "save_config",
    "merge_configs",
    "resolve_config_path",
    "get_config_value",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_CONFIG",
]
