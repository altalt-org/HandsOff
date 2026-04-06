"""Service exposure tools: proxy Android-VM services through the HandsOff server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..config import PORT
from ..services import ServiceManager


def register(mcp: FastMCP, svc_mgr: ServiceManager) -> None:
    @mcp.tool()
    async def expose_service(
        android_port: int,
        path_prefix: str,
        name: str | None = None,
    ) -> str:
        """Expose a service running on the Android device through the HandsOff server.

        Creates an ADB port forward from the HandsOff server to the Android
        device, then registers a reverse-proxy route on the HandsOff server so
        the service is reachable at:

            http://<handsoff-server>:<port>/services/<path_prefix>/

        Both HTTP and WebSocket traffic are proxied.

        Args:
            android_port: The port the service is listening on inside the Android device.
            path_prefix: URL path segment (e.g. "iris" → /services/iris/).
            name: Optional human-readable name. Defaults to path_prefix.

        Example: expose_service(android_port=3000, path_prefix="iris")
                 → http://handsoff:8000/services/iris/
        """
        try:
            svc = await svc_mgr.expose(android_port, path_prefix, name)
            return (
                f"Service '{svc.name}' exposed.\n"
                f"  Android device port: {svc.android_port}\n"
                f"  HandsOff proxy URL:  http://0.0.0.0:{PORT}/services/{svc.path_prefix}/\n"
                f"  WebSocket:           ws://0.0.0.0:{PORT}/services/{svc.path_prefix}/ws\n"
                f"\nAll HTTP/WS requests to the proxy URL are forwarded to the Android device."
            )
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    async def unexpose_service(name: str) -> str:
        """Stop exposing a service. Removes the proxy route and ADB port forward.

        Args:
            name: The service name (as returned by expose_service or list_services).

        Example: unexpose_service(name="iris")
        """
        try:
            await svc_mgr.unexpose(name)
            return f"Service '{name}' unexposed. Proxy route and port forward removed."
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    async def list_services() -> str:
        """List all currently exposed services and their proxy URLs."""
        services = svc_mgr.list()
        if not services:
            return "No services currently exposed."

        lines = ["Exposed services:", ""]
        for svc in services:
            lines.append(
                f"  {svc.name}:\n"
                f"    Android device port: {svc.android_port}\n"
                f"    HandsOff proxy URL:  http://0.0.0.0:{PORT}/services/{svc.path_prefix}/\n"
                f"    ADB forward port:    {svc.server_port}"
            )
        return "\n".join(lines)
