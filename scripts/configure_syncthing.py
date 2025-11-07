#!/usr/bin/env python3
"""CLI helper to ensure the Syncthing GUI/listeners bind to 0.0.0.0."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.syncthing_configurator import ensure_accessible_syncthing


def guess_config_path() -> Path:
    env = os.getenv("SYNCTHING_CONFIG_DIR")
    if env:
        return Path(env).expanduser() / "config.xml"
    home = Path(os.getenv("HOME", "~")).expanduser()
    return home / ".config" / "syncthing" / "config.xml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=guess_config_path(),
        help="Path to Syncthing config.xml (default: %(default)s)",
    )
    parser.add_argument("--gui-host", default="0.0.0.0", help="Host for the web GUI")
    parser.add_argument("--gui-port", type=int, default=8384, help="Port for the web GUI")
    parser.add_argument(
        "--listen-host",
        default="0.0.0.0",
        help="Host address for sync listeners",
    )
    parser.add_argument(
        "--listen-port",
        action="append",
        type=int,
        default=[22000],
        help="Listener port (can repeat, default: 22000)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = ensure_accessible_syncthing(
            args.config,
            gui_host=args.gui_host,
            gui_port=args.gui_port,
            listen_host=args.listen_host,
            listen_ports=args.listen_port,
        )
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    print(f"Syncthing config: {args.config}")
    print(f"GUI address: {result.gui_address}")
    print("Listen addresses:")
    for addr in result.listen_addresses:
        print(f"  - {addr}")
    print("Changed:" if result.changed else "Already configured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
