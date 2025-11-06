"""API key enforcement middleware."""

from __future__ import annotations

from typing import Iterable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Simple header-based API key authentication."""

    def __init__(
        self,
        app,
        *,
        api_key: str,
        header_name: str = "x-api-key",
        exempt_paths: Iterable[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._api_key = api_key
        self._header_name = header_name.lower()
        self._exempt_paths = {path.rstrip("/") for path in (exempt_paths or set())}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ):  # type: ignore[override]
        if not self._api_key:
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        if path in self._exempt_paths:
            return await call_next(request)
        if any(path.startswith(prefix + "/") for prefix in self._exempt_paths if prefix):
            return await call_next(request)

        provided = request.headers.get(self._header_name)
        if provided is None:
            provided = request.headers.get(self._header_name.title())
        if provided is None:
            provided = request.query_params.get("api_key")

        if provided != self._api_key:
            return JSONResponse(
                status_code=401,
                content={"status": "error", "message": "Unauthorized"},
                headers={"WWW-Authenticate": "API-Key"},
            )

        return await call_next(request)


__all__ = ["APIKeyMiddleware"]
