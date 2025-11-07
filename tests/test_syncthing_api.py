from __future__ import annotations

import json
import json
from typing import Any
from urllib import error

import pytest

from utils.syncthing_api import SyncthingAPI, SyncthingAPIError


class DummyResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "DummyResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - no cleanup required
        return None

    def close(self) -> None:  # pragma: no cover - compatibility with urllib
        return None


def _capture_request(monkeypatch, payload: bytes = b"{}") -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout: float = 0.0):  # type: ignore[override]
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        captured["data"] = req.data
        return DummyResponse(payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return captured


def test_trigger_rescan_uses_db_scan_when_folder(monkeypatch) -> None:
    captured = _capture_request(monkeypatch)

    api = SyncthingAPI("http://localhost:8384/rest", api_key=" secret ")
    api.trigger_rescan(folder="media", subdirs=["batch_001"])

    assert captured["url"].endswith("/db/scan")
    assert captured["method"] == "POST"
    body = json.loads(captured["data"].decode("utf-8"))
    assert body == {"folder": "media", "subdirs": ["batch_001"]}
    headers = {key.lower(): value for key, value in captured["headers"].items()}
    assert headers["x-api-key"] == "secret"


def test_trigger_rescan_requires_path_when_no_folder(monkeypatch) -> None:
    captured = _capture_request(monkeypatch)

    api = SyncthingAPI("http://localhost:8384/rest")
    api.trigger_rescan(path="/tmp/batch")

    assert captured["url"].endswith("/system/scan")
    assert json.loads(captured["data"].decode("utf-8")) == {"path": "/tmp/batch"}


def test_trigger_rescan_without_context_raises(monkeypatch) -> None:
    api = SyncthingAPI("http://localhost:8384/rest")
    with pytest.raises(ValueError):
        api.trigger_rescan()


def test_http_error_surfaces_auth_hint(monkeypatch) -> None:
    def fake_urlopen(req, timeout: float = 0.0):  # type: ignore[override]
        fp = DummyResponse(b"Forbidden")
        raise error.HTTPError(req.full_url, 403, "Forbidden", {}, fp)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    api = SyncthingAPI("http://localhost:8384/rest")

    with pytest.raises(SyncthingAPIError) as excinfo:
        api.folder_completion("media")

    assert "403" in str(excinfo.value)
    assert "unauthorized" in str(excinfo.value)


def test_folder_completion_parses_nested_completion(monkeypatch) -> None:
    payload = json.dumps({"completion": {"DEVICE": {"completion": 87.5}}}).encode("utf-8")
    captured = _capture_request(monkeypatch, payload=payload)

    api = SyncthingAPI("http://localhost:8384/rest")
    result = api.folder_completion("folder-a", device="DEVICE")

    assert "/db/completion" in captured["url"]
    assert captured["method"] == "GET"
    assert result.completion == pytest.approx(87.5)


def test_folder_completion_falls_back_to_global_completion(monkeypatch) -> None:
    payload = json.dumps({"globalCompletion": 99.9}).encode("utf-8")
    _capture_request(monkeypatch, payload=payload)

    api = SyncthingAPI("http://localhost:8384/rest")
    result = api.folder_completion("folder-b")

    assert result.completion == pytest.approx(99.9)


def test_system_status_returns_mapping(monkeypatch) -> None:
    payload = json.dumps({"myID": "ABC", "state": "idle"}).encode("utf-8")
    captured = _capture_request(monkeypatch, payload=payload)

    api = SyncthingAPI("http://localhost:8384/rest")
    status = api.system_status()

    assert captured["url"].endswith("/system/status")
    assert status == {"myID": "ABC", "state": "idle"}
