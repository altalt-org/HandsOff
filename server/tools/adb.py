"""Low-level ADB tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..config import DEVICE_SERIAL
from ..device import DeviceManager


def register(mcp: FastMCP, dm: DeviceManager) -> None:
    @mcp.tool()
    async def adb_shell(command: str) -> str:
        """Run a raw ADB shell command on the device. Returns the command output."""
        await dm.ensure_ready()
        try:
            output = await dm.device_obj.shell(command)
            return output if output else "(no output)"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    async def adb_install(apk_path: str) -> str:
        """Install an APK from a path on the server filesystem."""
        await dm.ensure_ready()
        try:
            await dm.device_obj.install(apk_path)
            return f"Successfully installed {apk_path}"
        except Exception as e:
            return f"Error installing APK: {e}"

    @mcp.tool()
    async def adb_packages() -> str:
        """List all installed packages on the device."""
        await dm.ensure_ready()
        try:
            output = await dm.device_obj.shell("pm list packages")
            return output if output else "No packages found"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    async def device_health() -> str:
        """Check device connection health and return device info."""
        if not dm.is_ready:
            return "Device not connected. Call any tool to trigger connection."
        try:
            output = await dm.device_obj.shell("getprop ro.build.display.id")
            return f"Connected: {DEVICE_SERIAL}\nBuild: {output.strip()}"
        except Exception as e:
            return f"Device error: {e}"
