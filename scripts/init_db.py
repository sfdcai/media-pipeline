#!/usr/bin/env python3
"""CLI helper to create or upgrade the SQLite schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from utils import config_loader
from utils.db_manager import DatabaseManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "Optional configuration file path. Defaults to MEDIA_PIPELINE_CONFIG "
            "or /etc/media-pipeline/config.yaml."
        ),
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Override the database path. Defaults to the value from the configuration file.",
    )
    return parser.parse_args()


def ensure_config(path: Path | None) -> Path:
    """Guarantee a configuration file exists on disk."""

    resolved = config_loader.resolve_config_path(path)
    if not resolved.exists():
        default_cfg = config_loader.merge_configs(config_loader.DEFAULT_CONFIG, {})
        config_loader.save_config(default_cfg, resolved)
    return resolved


def main() -> int:
    args = parse_args()
    config_path = ensure_config(args.config)
    config = config_loader.load_config(config_path)

    db_path_value = args.db or config_loader.get_config_value(
        "system", "db_path", config=config
    )
    if not db_path_value:
        print("Database path could not be determined from configuration.", file=sys.stderr)
        return 1

    db_path = Path(db_path_value)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    log_dir_value = config_loader.get_config_value(
        "system", "log_dir", config=config
    )
    if log_dir_value:
        Path(log_dir_value).mkdir(parents=True, exist_ok=True)

    manager = DatabaseManager(db_path)
    manager.close()

    print(f"Database initialized at {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
