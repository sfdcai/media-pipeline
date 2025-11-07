"""Helpers for making Syncthing listen on externally accessible addresses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

GUI_PORT_DEFAULT = 8384
LISTEN_PORT_DEFAULT = 22000


@dataclass(slots=True)
class SyncthingConfigResult:
    """Outcome of applying accessibility tweaks to a Syncthing config."""

    changed: bool
    gui_address: str | None
    listen_addresses: list[str]


def ensure_accessible_syncthing(
    config_path: Path,
    *,
    gui_host: str = "0.0.0.0",
    gui_port: int = GUI_PORT_DEFAULT,
    listen_host: str = "0.0.0.0",
    listen_ports: Iterable[int] | None = None,
) -> SyncthingConfigResult:
    """Patch *config_path* so the GUI and listeners bind to public interfaces."""

    if listen_ports is None:
        listen_ports = [LISTEN_PORT_DEFAULT]

    path = Path(config_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Syncthing config not found: {path}")

    tree = ET.parse(path)
    root = tree.getroot()

    changed = False

    # GUI address block ---------------------------------------------------
    gui_node = root.find("gui")
    desired_gui = f"{gui_host}:{gui_port}"
    gui_address_value: str | None = None
    if gui_node is not None:
        address = gui_node.find("address")
        if address is None:
            address = ET.SubElement(gui_node, "address")
        current = (address.text or "").strip()
        if current != desired_gui:
            address.text = desired_gui
            changed = True
        gui_address_value = address.text
    else:
        gui_node = ET.SubElement(root, "gui")
        address = ET.SubElement(gui_node, "address")
        address.text = desired_gui
        gui_address_value = desired_gui
        changed = True

    # Listen addresses ----------------------------------------------------
    options = root.find("options")
    if options is None:
        options = ET.SubElement(root, "options")
        changed = True

    existing = {
        (node.text or "").strip()
        for node in options.findall("listenAddress")
        if (node.text or "").strip()
    }

    desired_listen = set()
    for port in listen_ports:
        desired_listen.add(f"tcp://{listen_host}:{port}")
        desired_listen.add(f"quic://{listen_host}:{port}")

    # Remove the default-only address if custom ones will be injected
    if "default" in existing and desired_listen:
        for node in list(options.findall("listenAddress")):
            if (node.text or "").strip() == "default":
                options.remove(node)
                changed = True
        existing.discard("default")

    for value in sorted(desired_listen):
        if value not in existing:
            ET.SubElement(options, "listenAddress").text = value
            changed = True
            existing.add(value)

    listen_addresses = sorted(existing)

    if changed:
        tree.write(path, encoding="utf-8", xml_declaration=True)

    return SyncthingConfigResult(changed=changed, gui_address=gui_address_value, listen_addresses=listen_addresses)


__all__ = ["ensure_accessible_syncthing", "SyncthingConfigResult"]
