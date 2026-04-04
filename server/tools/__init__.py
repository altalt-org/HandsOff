"""MCP tool registration."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..device import DeviceManager
from ..power import PowerBackend
from . import adb, interaction, observation, power


def register_all(
    mcp: FastMCP,
    device_manager: DeviceManager,
    power_backend: PowerBackend,
) -> None:
    """Register all MCP tools on the server."""
    observation.register(mcp, device_manager)
    interaction.register(mcp, device_manager)
    adb.register(mcp, device_manager)
    power.register(mcp, device_manager, power_backend)
