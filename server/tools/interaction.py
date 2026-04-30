"""Interaction tools: click, type, swipe, etc."""

from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from ..device import DeviceManager
from ..ime import (
    is_agent_keyboard_active,
    set_agent_keyboard as _set_agent_keyboard_impl,
)


def register(mcp: FastMCP, dm: DeviceManager) -> None:
    @mcp.tool()
    async def click(index: int) -> str:
        """Click/tap a UI element by its index from get_device_state output."""
        ui = await dm.current_ui()
        try:
            x, y = ui.get_element_coords(index)
        except ValueError as e:
            return f"Error: {e}"

        driver, _ = await dm.ensure_ready()
        await driver.tap(x, y)

        info = ui.get_element_info(index)
        detail = f"Text: '{info.get('text', 'N/A')}', Class: {info.get('className', 'N/A')}"
        return f"Clicked element {index} at ({x}, {y}). {detail}"

    @mcp.tool()
    async def click_at(x: int, y: int) -> str:
        """Click/tap at specific pixel coordinates on the screen.
        Use element bounds from get_device_state as reference for coordinates."""
        ui = await dm.current_ui()
        try:
            abs_x, abs_y = ui.convert_point(x, y)
        except Exception as e:
            return f"Error: {e}"

        driver, _ = await dm.ensure_ready()
        await driver.tap(abs_x, abs_y)
        return f"Tapped at ({abs_x}, {abs_y})"

    @mcp.tool()
    async def long_press(index: int) -> str:
        """Long-press a UI element by its index."""
        ui = await dm.current_ui()
        try:
            x, y = ui.get_element_coords(index)
        except ValueError as e:
            return f"Error: {e}"

        driver, _ = await dm.ensure_ready()
        await driver.swipe(x, y, x, y, duration_ms=1000)
        return f"Long-pressed element {index} at ({x}, {y})"

    @mcp.tool()
    async def long_press_at(x: int, y: int) -> str:
        """Long-press at specific pixel coordinates."""
        ui = await dm.current_ui()
        try:
            abs_x, abs_y = ui.convert_point(x, y)
        except Exception as e:
            return f"Error: {e}"

        driver, _ = await dm.ensure_ready()
        await driver.swipe(abs_x, abs_y, abs_x, abs_y, duration_ms=1000)
        return f"Long-pressed at ({abs_x}, {abs_y})"

    @mcp.tool()
    async def type_text(text: str, index: int, clear: bool = False) -> str:
        """Type text into a UI input field. Specify the element index to focus
        the field before typing. Set clear=true to clear existing text first
        (recommended for URL bars, search fields, or when replacing text).

        REQUIRES the agent keyboard to be active. Call
        `set_agent_keyboard(active=True)` at the start of your interaction
        session, and `set_agent_keyboard(active=False)` when done."""
        if not await is_agent_keyboard_active(dm):
            return (
                "Error: agent keyboard is not active. Call "
                "`set_agent_keyboard(active=True)` first, then retry. "
                "Without the agent keyboard active, typing fails and the "
                "on-screen keyboard blocks UI elements."
            )

        ui = await dm.current_ui()
        driver, _ = await dm.ensure_ready()

        if index != -1:
            try:
                x, y = ui.get_element_coords(index)
                await driver.tap(x, y)
            except ValueError as e:
                return f"Error focusing element: {e}"

        success = await driver.input_text(text, clear)
        if success:
            return f"Typed text into element {index} (clear={clear})"
        return "Failed to type text: input failed"

    @mcp.tool()
    async def set_agent_keyboard(active: bool) -> str:
        """Toggle the agent keyboard (an invisible IME used for programmatic
        text input).

        Turn it ON at the start of an interaction session. While active:
          - typing via `type_text` works
          - the on-screen keyboard does NOT pop up when input fields are
            focused, so it never blocks clicks on UI elements behind it

        Turn it OFF when:
          - you finish your interaction session
          - you need the human user to type (e.g. via ws-scrcpy) — they
            need the regular on-screen keyboard

        Idempotent: calling with the current state returns a clear message
        and makes no change."""
        result = await _set_agent_keyboard_impl(dm, active)
        return result.message

    @mcp.tool()
    async def swipe(
        start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 1.0
    ) -> str:
        """Swipe from one point to another. Useful for scrolling.
        To scroll down: swipe upward (e.g., start_y=1500, end_y=500).
        Duration is in seconds (default 1.0)."""
        ui = await dm.current_ui()
        driver, _ = await dm.ensure_ready()

        try:
            sx, sy = ui.convert_point(start_x, start_y)
            ex, ey = ui.convert_point(end_x, end_y)
        except Exception as e:
            return f"Error: {e}"

        duration_ms = int(duration * 1000)
        await driver.swipe(sx, sy, ex, ey, duration_ms=duration_ms)
        return f"Swiped from ({sx}, {sy}) to ({ex}, {ey})"

    @mcp.tool()
    async def system_button(button: str) -> str:
        """Press a system button. Available buttons: back, home, enter."""
        driver, _ = await dm.ensure_ready()
        try:
            await driver.press_button(button)
            return f"Pressed {button.upper()} button"
        except ValueError as e:
            return f"Error: {e}"

    @mcp.tool()
    async def open_app(package: str) -> str:
        """Open an app by its package name. Use list_apps to find package names.
        Example: open_app(package="com.android.settings")"""
        driver, _ = await dm.ensure_ready()
        result = await driver.start_app(package)
        await asyncio.sleep(1)
        return result

    @mcp.tool()
    async def list_apps() -> str:
        """List all installed apps with their package names.
        Use the package names with open_app to launch apps."""
        driver, _ = await dm.ensure_ready()
        apps = await driver.get_apps(include_system=True)
        if not apps:
            return "No apps found"
        lines = []
        for app_info in apps:
            name = app_info.get("name", "Unknown")
            pkg = app_info.get("package", "unknown")
            lines.append(f"  {name}: {pkg}")
        return f"Installed apps ({len(lines)}):\n" + "\n".join(sorted(lines))

    @mcp.tool()
    async def wait(seconds: float = 1.0) -> str:
        """Wait for a specified duration in seconds. Useful for waiting for
        animations, page loads, or other time-based operations."""
        await asyncio.sleep(seconds)
        return f"Waited {seconds} seconds"
