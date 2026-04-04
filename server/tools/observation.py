"""Observation tools: get_device_state, screenshot."""

from __future__ import annotations

import base64
import io

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent
from PIL import Image as PILImage

from ..device import DeviceManager


def register(mcp: FastMCP, dm: DeviceManager) -> None:
    @mcp.tool()
    async def get_device_state() -> str:
        """Get the current device screen state: a text description of all visible
        UI elements with their indices, plus which app/activity is in the foreground.
        Call this after every action to see what changed."""
        ui = await dm.get_state()

        parts = []

        pkg = ui.phone_state.get("package_name", "unknown")
        activity = ui.phone_state.get("activity_name", "unknown")
        parts.append(f"App: {pkg}")
        parts.append(f"Activity: {activity}")
        parts.append(f"Screen: {ui.screen_width}x{ui.screen_height}")

        if ui.focused_text:
            parts.append(f"Focused input text: {ui.focused_text}")

        parts.append("")
        parts.append("UI Elements:")
        parts.append(ui.formatted_text)

        return "\n".join(parts)

    @mcp.tool()
    async def screenshot() -> list[TextContent | ImageContent]:
        """Take a screenshot of the current device screen. Returns the image
        so you can see visual details the accessibility tree doesn't capture."""
        driver, _ = await dm.ensure_ready()
        png_bytes = await driver.screenshot()

        # Resize and compress to JPEG to stay within Claude Code's MCP token limits.
        img = PILImage.open(io.BytesIO(png_bytes))
        max_height = 800
        if img.height > max_height:
            ratio = max_height / img.height
            img = img.resize((int(img.width * ratio), max_height), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=60)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        return [
            ImageContent(type="image", data=b64, mimeType="image/jpeg"),
        ]
