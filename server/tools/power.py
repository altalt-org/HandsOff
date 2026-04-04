"""Power control tools: restart, power off, power on."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..device import DeviceManager
from ..power import PowerBackend


def register(mcp: FastMCP, dm: DeviceManager, backend: PowerBackend) -> None:
    @mcp.tool()
    async def restart_device() -> str:
        """Restart the Android device (equivalent to rebooting a phone).
        The device will be unavailable for ~15-20 seconds while it reboots."""
        dm.reset()
        try:
            return await backend.restart()
        except Exception as e:
            return f"Error restarting device: {e}"

    @mcp.tool()
    async def power_off() -> str:
        """Power off the Android device (equivalent to shutting down a phone).
        The device will be unavailable until power_on is called."""
        dm.reset()
        try:
            return await backend.power_off()
        except Exception as e:
            return f"Error powering off device: {e}"

    @mcp.tool()
    async def power_on() -> str:
        """Power on the Android device (equivalent to turning on a phone).
        The device will take ~15-20 seconds to boot."""
        try:
            result = await backend.power_on()
            dm.reset()
            return result
        except Exception as e:
            return f"Error powering on device: {e}"
