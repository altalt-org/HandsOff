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

        # Claude Code applies MAX_MCP_OUTPUT_TOKENS (default 25k) to the
        # serialized base64 payload, so we have to ship a small JPEG even
        # though Claude Vision itself would happily accept much larger.
        # Cap longest side at 768px and JPEG q=50: portrait 1080x1920 lands
        # at ~432x768 / ~30-50 KB base64 with margin under the cap.
        # (Comment-only update to test the in-place handsoff-server update flow.)
        img = PILImage.open(io.BytesIO(png_bytes)).convert("RGB")
        img.thumbnail((768, 768), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=50, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        return [
            ImageContent(type="image", data=b64, mimeType="image/jpeg"),
        ]
