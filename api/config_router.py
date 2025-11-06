"""FastAPI router for managing application configuration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, MutableMapping, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from utils.config_loader import (
    load_config,
    load_raw_config,
    merge_configs,
    resolve_config_path,
    save_config,
)
from utils.db_manager import DatabaseManager

router = APIRouter(prefix="/api/config", tags=["config"])


def _flatten_changes(
    previous: Any, current: Any, prefix: Tuple[str, ...] = ()
) -> Iterable[Tuple[str, Any, Any]]:
    if isinstance(previous, MutableMapping) or isinstance(current, MutableMapping):
        prev_map: MutableMapping[str, Any]
        curr_map: MutableMapping[str, Any]
        prev_map = previous if isinstance(previous, MutableMapping) else {}
        curr_map = current if isinstance(current, MutableMapping) else {}
        keys = set(prev_map) | set(curr_map)
        for key in sorted(keys):
            yield from _flatten_changes(
                prev_map.get(key),
                curr_map.get(key),
                prefix + (str(key),),
            )
        return

    if previous != current:
        dotted = ".".join(prefix) if prefix else ""
        yield (dotted, previous, current)


def get_database(request: Request) -> DatabaseManager:
    database = getattr(request.app.state, "db", None)
    if database is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not configured",
        )
    return database


def get_actor(request: Request) -> str:
    return request.headers.get("X-Actor", "api")


def get_config_path() -> Path:
    return resolve_config_path()


@router.get("", response_model=Dict[str, Any])
async def read_config(config_path: Path = Depends(get_config_path)) -> Dict[str, Any]:
    try:
        return load_config(config_path)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.put("", response_model=Dict[str, Any])
async def update_config(
    updates: Dict[str, Any] = Body(..., embed=False),
    db: DatabaseManager = Depends(get_database),
    config_path: Path = Depends(get_config_path),
    actor: str = Depends(get_actor),
) -> Dict[str, Any]:
    try:
        existing_raw = load_raw_config(config_path)
        existing_effective = load_config(config_path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if not updates:
        return existing_effective

    if not isinstance(updates, MutableMapping):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload"
        )

    merged_raw = merge_configs(existing_raw, updates)
    save_config(merged_raw, config_path)
    updated_effective = load_config(config_path)

    changes = list(_flatten_changes(existing_effective, updated_effective))
    if changes:
        timestamp = datetime.now(timezone.utc).isoformat()
        rows = []
        for key, old_value, new_value in changes:
            rows.append(
                (
                    timestamp,
                    key,
                    json.dumps(old_value, sort_keys=True, ensure_ascii=False),
                    json.dumps(new_value, sort_keys=True, ensure_ascii=False),
                    actor,
                )
            )
        db.executemany(
            "INSERT INTO config_changes (ts, key, old_value, new_value, actor) VALUES (?, ?, ?, ?, ?)",
            rows,
        )

    return updated_effective


__all__ = ["router", "read_config", "update_config", "get_database", "get_actor"]
