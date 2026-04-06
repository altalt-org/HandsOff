"""Service exposure manager: ADB port forwarding + dynamic reverse proxy."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
import httpx

from .config import DEVICE_SERIAL

logger = logging.getLogger("handsoff")


@dataclass
class ExposedService:
    """Tracks one exposed Android-VM service."""

    name: str
    android_port: int
    server_port: int  # ADB-forwarded port on the HandsOff server
    path_prefix: str  # e.g. "iris" → routes under /services/iris/


@dataclass
class ServiceManager:
    """Manages ADB port forwards and dynamic FastAPI proxy routes."""

    app: FastAPI
    _services: dict[str, ExposedService] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # ── Public API ──────────────────────────────────────────────────────

    async def expose(
        self, android_port: int, path_prefix: str, name: str | None = None,
    ) -> ExposedService:
        async with self._lock:
            name = name or path_prefix
            if name in self._services:
                raise ValueError(f"Service '{name}' is already exposed")

            # Normalise prefix — strip leading/trailing slashes
            path_prefix = path_prefix.strip("/")
            # Check prefix collision
            for svc in self._services.values():
                if svc.path_prefix == path_prefix:
                    raise ValueError(
                        f"Path prefix '{path_prefix}' already in use by service '{svc.name}'"
                    )

            # ADB forward
            server_port = await asyncio.to_thread(
                _adb_forward, android_port, DEVICE_SERIAL,
            )
            logger.info(
                f"ADB forward: HandsOff server :{server_port} → Android VM :{android_port}"
            )

            svc = ExposedService(
                name=name,
                android_port=android_port,
                server_port=server_port,
                path_prefix=path_prefix,
            )
            self._services[name] = svc

            # Register proxy routes
            self._add_proxy_routes(svc)

            logger.info(f"Service '{name}' exposed at /services/{path_prefix}/")
            return svc

    async def unexpose(self, name: str) -> None:
        async with self._lock:
            svc = self._services.pop(name, None)
            if svc is None:
                raise ValueError(f"No service named '{name}'")

            # Remove ADB forward
            await asyncio.to_thread(
                _adb_remove_forward, svc.server_port, DEVICE_SERIAL,
            )

            # Remove dynamic routes
            self._remove_proxy_routes(svc)

            logger.info(f"Service '{svc.name}' unexposed")

    def list(self) -> list[ExposedService]:
        return list(self._services.values())

    # ── Route management ────────────────────────────────────────────────

    def _route_name(self, svc: ExposedService, suffix: str) -> str:
        return f"_svc_{svc.name}_{suffix}"

    def _add_proxy_routes(self, svc: ExposedService) -> None:
        prefix = f"/services/{svc.path_prefix}"
        upstream = f"http://127.0.0.1:{svc.server_port}"

        async def _do_proxy(request: Request, upstream_url: str) -> StreamingResponse:
            """Stream the upstream response back to the client.

            Uses httpx streaming so that long-lived responses (SSE, chunked
            transfer, large downloads) are forwarded incrementally instead of
            buffered in memory.
            """
            body = await request.body()
            headers = dict(request.headers)
            headers.pop("host", None)

            client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=None, write=10, pool=10))
            req = client.build_request(
                method=request.method,
                url=upstream_url,
                headers=headers,
                content=body,
            )
            resp = await client.send(req, stream=True)

            async def _stream():
                try:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
                finally:
                    await resp.aclose()
                    await client.aclose()

            # Filter hop-by-hop headers from upstream
            fwd_headers = {
                k: v for k, v in resp.headers.multi_items()
                if k.lower() not in ("transfer-encoding", "connection")
            }

            return StreamingResponse(
                content=_stream(),
                status_code=resp.status_code,
                headers=fwd_headers,
            )

        # WebSocket: /services/<prefix>/{path} — registered BEFORE HTTP
        # catch-all so Starlette's router sees it first for upgrade requests.
        @self.app.websocket_route(
            prefix + "/{path:path}",
            name=self._route_name(svc, "ws"),
        )
        async def _proxy_ws(ws: WebSocket, path: str, _up: str = upstream) -> None:
            await ws.accept()
            ws_url = f"ws://127.0.0.1:{svc.server_port}/{path}"

            import websockets

            try:
                async with websockets.connect(ws_url) as upstream_ws:
                    async def _client_to_upstream():
                        try:
                            while True:
                                data = await ws.receive_text()
                                await upstream_ws.send(data)
                        except WebSocketDisconnect:
                            await upstream_ws.close()

                    async def _upstream_to_client():
                        try:
                            async for msg in upstream_ws:
                                if isinstance(msg, str):
                                    await ws.send_text(msg)
                                else:
                                    await ws.send_bytes(msg)
                        except Exception:
                            await ws.close()

                    await asyncio.gather(_client_to_upstream(), _upstream_to_client())
            except Exception as e:
                logger.warning(f"WebSocket proxy error for {svc.name}: {e}")
                await ws.close(code=1011, reason=str(e))

        # HTTP catch-all: /services/<prefix>/{path}
        @self.app.api_route(
            prefix + "/{path:path}",
            methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
            name=self._route_name(svc, "http"),
            include_in_schema=False,
        )
        async def _proxy_http(request: Request, path: str, _up: str = upstream) -> StreamingResponse:
            url = f"{_up}/{path}"
            if request.url.query:
                url = f"{url}?{request.url.query}"
            return await _do_proxy(request, url)

        # Also handle bare prefix (no trailing path)
        @self.app.api_route(
            prefix,
            methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
            name=self._route_name(svc, "http_root"),
            include_in_schema=False,
        )
        async def _proxy_http_root(request: Request, _up: str = upstream) -> StreamingResponse:
            url = _up
            if request.url.query:
                url = f"{url}?{request.url.query}"
            return await _do_proxy(request, url)

    def _remove_proxy_routes(self, svc: ExposedService) -> None:
        """Remove dynamically added routes from the FastAPI app."""
        names_to_remove = {
            self._route_name(svc, "http"),
            self._route_name(svc, "http_root"),
            self._route_name(svc, "ws"),
        }
        self.app.routes[:] = [
            r for r in self.app.routes
            if getattr(r, "name", None) not in names_to_remove
        ]


# ── ADB helpers ─────────────────────────────────────────────────────────


def _adb_forward(android_port: int, serial: str) -> int:
    """Create an ADB forward. Returns the assigned server-side port."""
    result = subprocess.run(
        ["adb", "-s", serial, "forward", "tcp:0", f"tcp:{android_port}"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"adb forward failed: {result.stderr.strip()}")
    # adb forward tcp:0 prints the assigned port
    return int(result.stdout.strip())


def _adb_remove_forward(server_port: int, serial: str) -> None:
    subprocess.run(
        ["adb", "-s", serial, "forward", "--remove", f"tcp:{server_port}"],
        capture_output=True, text=True, timeout=10,
    )
