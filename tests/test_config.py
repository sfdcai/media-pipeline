from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.config_router import read_config, update_config
from utils.config_loader import DEFAULT_CONFIG
from utils.db_manager import DatabaseManager


def test_read_config_returns_defaults_and_overrides(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("dedup:\n  threads: 8\n", encoding="utf-8")
    monkeypatch.setenv("MEDIA_PIPELINE_CONFIG", str(config_path))

    result = asyncio.run(read_config(config_path=config_path))

    assert result["dedup"]["threads"] == 8
    assert "paths" in result
    assert result["paths"]["source_dir"]


def test_update_config_merges_and_logs(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("dedup:\n  threads: 3\n", encoding="utf-8")
    monkeypatch.setenv("MEDIA_PIPELINE_CONFIG", str(config_path))

    db_path = tmp_path / "db.sqlite"
    database = DatabaseManager(db_path)

    updates = {
        "dedup": {"threads": 6},
        "paths": {"source_dir": "/data/source"},
    }

    result = asyncio.run(
        update_config(updates, db=database, config_path=config_path, actor="tester")
    )

    assert result["dedup"]["threads"] == 6
    assert result["paths"]["source_dir"] == "/data/source"

    stored = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert stored["dedup"]["threads"] == 6
    assert stored["paths"]["source_dir"] == "/data/source"

    rows = database.fetchall(
        "SELECT key, old_value, new_value, actor FROM config_changes"
    )
    assert len(rows) == 2
    parsed = {
        (
            row["key"],
            json.loads(row["old_value"]),
            json.loads(row["new_value"]),
            row["actor"],
        )
        for row in rows
    }
    assert (
        "dedup.threads",
        3,
        6,
        "tester",
    ) in parsed
    default_source = DEFAULT_CONFIG["paths"]["source_dir"]
    assert (
        "paths.source_dir",
        default_source,
        "/data/source",
        "tester",
    ) in parsed

    second = asyncio.run(
        update_config(updates, db=database, config_path=config_path, actor="tester")
    )
    assert second == result
    rows_after = database.fetchall(
        "SELECT key, old_value, new_value, actor FROM config_changes"
    )
    assert len(rows_after) == 2

    database.close()
