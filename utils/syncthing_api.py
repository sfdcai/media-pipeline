"""Lightweight client for interacting with the Syncthing REST API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping
from urllib import error, parse, request


class SyncthingAPIError(RuntimeError):
    """Raised when the Syncthing API returns an error response."""


@dataclass(slots=True)
class SyncthingCompletion:
    """Represents folder completion progress reported by Syncthing."""

    folder: str
    completion: float


class SyncthingAPI:
    """Minimal REST client for the subset of Syncthing endpoints we require."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        if not base_url:
            raise ValueError("Syncthing base URL must be provided")
        self._base_url = base_url.rstrip("/")
        self._api_key = (api_key or "").strip()
        self._timeout = timeout

    # ------------------------------------------------------------------
    def _build_headers(self) -> Mapping[str, str]:
        headers: dict[str, str] = {"accept": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Mapping[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        if method.upper() == "GET" and data:
            query = parse.urlencode(data)
            url = f"{url}?{query}"
            payload = None
        else:
            payload = None if data is None else json.dumps(data).encode("utf-8")
        req = request.Request(url, method=method.upper(), data=payload)
        headers = self._build_headers()
        if payload is not None:
            headers["content-type"] = "application/json"
        for key, value in headers.items():
            req.add_header(key, value)
        try:
            with request.urlopen(req, timeout=self._timeout) as response:
                raw = response.read()
        except error.HTTPError as exc:  # pragma: no cover - network failure
            if exc.fp is not None:  # ensure underlying file handles are closed
                try:
                    body = exc.read()
                finally:
                    try:
                        exc.fp.close()
                    except Exception:  # pragma: no cover - best effort only
                        pass
            else:
                body = b""

            details: list[str] = []
            if exc.code in {401, 403}:
                details.append("unauthorized. Verify Syncthing API key and ACLs.")

            if body:
                try:
                    decoded = body.decode("utf-8", errors="replace").strip()
                except Exception:  # pragma: no cover - best effort only
                    decoded = ""
                if decoded:
                    details.append(decoded.splitlines()[0])

            detail_suffix = f" - {' '.join(details)}" if details else ""
            raise SyncthingAPIError(
                f"Syncthing request failed ({exc.code} {exc.reason}){detail_suffix}"
            ) from exc
        except error.URLError as exc:  # pragma: no cover - network failure
            raise SyncthingAPIError(f"Unable to reach Syncthing: {exc}") from exc

        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:  # pragma: no cover - unexpected payload
            return raw.decode("utf-8")

    # ------------------------------------------------------------------
    def trigger_rescan(
        self,
        path: str | None = None,
        *,
        folder: str | None = None,
        subdirs: list[str] | None = None,
    ) -> None:
        """Request that Syncthing rescans for changes.

        When ``folder`` is provided the call uses ``/db/scan`` which expects the
        Syncthing folder identifier and optional ``subdirs`` relative to that
        folder. Otherwise the method falls back to ``/system/scan`` using the
        absolute ``path`` for older setups.
        """

        if folder:
            payload: dict[str, Any] = {"folder": folder}
            if subdirs:
                payload["subdirs"] = subdirs
            self._request("POST", "/db/scan", data=payload)
            return

        if not path:
            raise ValueError("trigger_rescan requires either folder or path")

        self._request("POST", "/system/scan", data={"path": path})

    def folder_completion(
        self, folder: str, *, device: str | None = None
    ) -> SyncthingCompletion:
        """Return the completion percentage for a Syncthing folder.

        Syncthing returns slightly different payloads depending on whether a
        device identifier is supplied. This helper normalises the structure and
        falls back to the global completion percentage when available.
        """

        params: dict[str, Any] = {"folder": folder}
        if device:
            params["device"] = device
        payload = self._request("GET", "/db/completion", data=params)

        completion_value: float | None = None
        if isinstance(payload, Mapping):
            completion_field = payload.get("completion")
            if isinstance(completion_field, Mapping):
                completions: list[float] = []
                for value in completion_field.values():
                    if isinstance(value, Mapping) and "completion" in value:
                        try:
                            completions.append(float(value["completion"]))
                        except (TypeError, ValueError):
                            continue
                    else:
                        try:
                            completions.append(float(value))
                        except (TypeError, ValueError):
                            continue
                if completions:
                    completion_value = min(completions)
            elif completion_field is not None:
                try:
                    completion_value = float(completion_field)
                except (TypeError, ValueError):
                    completion_value = None

            if completion_value is None:
                for key in ("globalCompletion", "globalcompletion"):
                    if key in payload:
                        try:
                            completion_value = float(payload[key])
                        except (TypeError, ValueError):
                            completion_value = None
                        break

        if completion_value is None and not isinstance(payload, Mapping):
            try:
                completion_value = float(payload)
            except (TypeError, ValueError):
                completion_value = None

        percentage = completion_value if completion_value is not None else 0.0
        percentage = max(0.0, min(100.0, float(percentage)))
        return SyncthingCompletion(folder=folder, completion=percentage)

    def system_status(self) -> Mapping[str, Any]:
        """Fetch Syncthing's system status information."""

        payload = self._request("GET", "/system/status")
        if isinstance(payload, Mapping):
            return payload
        return {}

    def folder_status(self, folder: str) -> Mapping[str, Any]:
        """Return the current folder status payload for *folder*."""

        payload = self._request("GET", "/db/status", data={"folder": folder})
        if isinstance(payload, Mapping):
            return payload
        return {}


__all__ = ["SyncthingAPI", "SyncthingAPIError", "SyncthingCompletion"]
