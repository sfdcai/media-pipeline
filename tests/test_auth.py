import asyncio
from pathlib import Path
import sys

from fastapi import Request
from fastapi.responses import JSONResponse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from middlewares import APIKeyMiddleware


async def _run_middleware(headers: list[tuple[bytes, bytes]] | None = None) -> int:
    async def call_next(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/protected",
        "headers": headers or [],
        "query_string": b"",
    }

    middleware = APIKeyMiddleware(lambda scope, receive, send: None, api_key="secret", exempt_paths={"/health"})

    async def empty_receive() -> dict[str, bytes]:
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(scope, receive=empty_receive)
    response = await middleware.dispatch(request, call_next)
    return response.status_code


def test_api_key_middleware_blocks_requests() -> None:
    status = asyncio.run(_run_middleware())
    assert status == 401

    allowed = asyncio.run(
        _run_middleware(headers=[(b"x-api-key", b"secret")])
    )
    assert allowed == 200
