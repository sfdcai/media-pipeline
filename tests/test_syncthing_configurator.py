from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.syncthing_configurator import ensure_accessible_syncthing


def _write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_configurator_adds_listeners(tmp_path: Path) -> None:
    config_path = tmp_path / "config.xml"
    _write_config(
        config_path,
        """
        <configuration>
          <gui>
            <enabled>true</enabled>
            <address>127.0.0.1:8384</address>
          </gui>
          <options>
            <listenAddress>default</listenAddress>
          </options>
        </configuration>
        """,
    )

    result = ensure_accessible_syncthing(config_path)
    assert result.changed is True
    assert result.gui_address == "0.0.0.0:8384"
    assert "tcp://0.0.0.0:22000" in result.listen_addresses
    assert "quic://0.0.0.0:22000" in result.listen_addresses

    # Second invocation should be idempotent
    second = ensure_accessible_syncthing(config_path)
    assert second.changed is False
    assert second.listen_addresses == result.listen_addresses
