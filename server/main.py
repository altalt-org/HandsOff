#!/usr/bin/env python3
"""
HandsOff Server

Single server exposing:
  - MCP tools at /mcp (SSE transport) for AI agent device control
  - REST API at /api for health checks and future endpoints

Usage:
    python server/main.py
    DEVICE_SERIAL=localhost:5555 PORT=8000 python server/main.py
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import subprocess
import sys

# Ensure droidrun-pkg is importable when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "droidrun-pkg"))

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent

from droidrun.tools.driver.android import AndroidDriver
from droidrun.tools.ui.provider import AndroidStateProvider
from droidrun.tools.ui.state import UIState
from droidrun.tools.filters import ConciseFilter
from droidrun.tools.formatters import IndexedFormatter
from droidrun.portal import ensure_portal_ready
from async_adbutils import adb
from PIL import Image as PILImage
import docker

logger = logging.getLogger("handsoff")
logging.basicConfig(level=logging.INFO)

DEVICE_SERIAL = os.environ.get("DEVICE_SERIAL", "localhost:5555")
USE_TCP = os.environ.get("DROIDRUN_USE_TCP", "true").lower() in ("1", "true", "yes")
PORT = int(os.environ.get("PORT", "8000"))
REDROID_CONTAINER = os.environ.get("REDROID_CONTAINER", "redroid")

# ── Instructions ─────────────────────────────────────────────────────────

INSTRUCTIONS = """\
# DroidRun Device Control — Agent Instructions

You control an Android device through MCP tools. You are the decision-making
agent — observe the screen, reason about what to do, call a tool, then
observe the result and repeat.

## Workflow

1. Call `get_device_state` to see what's on screen
2. Analyze the UI elements and their indices
3. Call an action tool (click, type, swipe, etc.)
4. Call `get_device_state` again to see the result
5. Repeat until the task is complete

## Understanding the UI State

`get_device_state` returns a text description of all visible UI elements.
Each interactive element has a numeric **index** — use these indices with
tools like `click`, `type`, and `long_press`.

Example state output:
```
[0] TextView "Settings"
[1] Switch "Wi-Fi" (OFF)
[2] TextView "Bluetooth"
[3] Button "More"
```

To tap the Wi-Fi switch, call `click(index=1)`.

## Available Tools

### Observation
- `get_device_state` — Get the current screen's UI element tree with indices + phone state (current app/activity). **Call this after every action** to see what changed.
- `screenshot` — Get a visual screenshot of the current screen as an image. Use when you need to see visual details the accessibility tree doesn't capture (colors, images, layout).

### Interaction
- `click(index)` — Tap a UI element by its index from the state
- `click_at(x, y)` — Tap at specific pixel coordinates (use element bounds as reference)
- `long_press(index)` — Long-press a UI element
- `long_press_at(x, y)` — Long-press at pixel coordinates
- `type(text, index, clear?)` — Type text into an input field. Set `clear=true` to clear existing text first (recommended for URL bars, search fields)
- `swipe(start_x, start_y, end_x, end_y, duration?)` — Swipe gesture. Useful for scrolling (swipe up to scroll down). Duration in seconds (default 1.0)
- `system_button(button)` — Press a system button: "back", "home", or "enter"
- `open_app(package)` — Open an app by package name. Use `list_apps` to find packages.

### Utility
- `list_apps` — List installed apps and their package names
- `wait(duration?)` — Wait for animations/loading (duration in seconds, default 1.0)
- `device_health` — Check device connection health

### Power Control
- `restart_device` — Restart the device (like rebooting a phone, ~15-20s downtime)
- `power_off` — Shut down the device
- `power_on` — Turn on a powered-off device (~15-20s boot time)

### Low-level ADB
- `adb_shell(command)` — Run a raw ADB shell command
- `adb_install(apk_path)` — Install an APK from the server filesystem
- `adb_packages` — List all installed packages

## Tips

- **Always observe after acting.** Call `get_device_state` after each action to verify the result before deciding the next step.
- **Use indices from the latest state.** Indices can change after actions — always use indices from the most recent `get_device_state` call.
- **Scroll to find off-screen content.** If you don't see what you're looking for, swipe to scroll. To scroll down: `swipe(540, 1500, 540, 500)` (swipe up on screen).
- **Use `open_app` for navigation.** To open an app, use `open_app` with the package name rather than navigating through the launcher manually.
- **Use `system_button("back")` to go back.** This is more reliable than finding a back button in the UI.
- **Use `clear=true` when replacing text.** When typing into a field that already has text (like URL bars), set `clear=true` to replace rather than append.
- **Check preconditions.** Before executing a task, verify the required conditions are met (e.g., the right app is open, the right screen is showing).
"""

# ── Global state (initialized lazily on first tool call) ─────────────────
_driver: AndroidDriver | None = None
_state_provider: AndroidStateProvider | None = None
_device_obj = None  # raw async_adbutils device for ADB shell
_ui: UIState | None = None
_ready = False
_ready_lock = asyncio.Lock()


# ── MCP Server ───────────────────────────────────────────────────────────

mcp = FastMCP(
    "droidrun",
    instructions=INSTRUCTIONS,
)


# ── FastAPI App ──────────────────────────────────────────────────────────

app = FastAPI(title="HandsOff")
app.mount("/mcp", mcp.sse_app())


# ── REST API ─────────────────────────────────────────────────────────────

@app.get("/api/health")
async def api_health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "device": DEVICE_SERIAL,
        "connected": _ready,
    }


# ── Bootstrap ────────────────────────────────────────────────────────────

async def _ensure_ready() -> tuple[AndroidDriver, AndroidStateProvider]:
    """Connect to the device and create the state provider (once)."""
    global _driver, _state_provider, _device_obj, _ready

    async with _ready_lock:
        if _ready:
            return _driver, _state_provider

        serial = DEVICE_SERIAL
        logger.info(f"Connecting to device {serial}...")

        # ADB connect for TCP devices (e.g. redroid)
        if ":" in serial:
            subprocess.run(["adb", "connect", serial], capture_output=True)

        # Auto-setup Portal
        device_obj = await adb.device(serial=serial)
        await ensure_portal_ready(device_obj)

        driver = AndroidDriver(serial=serial, use_tcp=USE_TCP)
        await driver.connect()

        state_provider = AndroidStateProvider(
            driver,
            tree_filter=ConciseFilter(),
            tree_formatter=IndexedFormatter(),
        )

        _driver = driver
        _state_provider = state_provider
        _device_obj = device_obj
        _ready = True
        logger.info("Device connected and ready.")
        return driver, state_provider


async def _get_state() -> UIState:
    """Fetch fresh UI state from the device."""
    global _ui
    _, state_provider = await _ensure_ready()
    _ui = await state_provider.get_state()
    return _ui


async def _current_ui() -> UIState:
    """Return the most recent UI state, fetching if needed."""
    if _ui is None:
        return await _get_state()
    return _ui


# ── Instructions resource (for re-reading after context compaction) ──────

@mcp.resource("droidrun://instructions")
def get_instructions() -> str:
    """Agent instructions for using the DroidRun device control tools."""
    return INSTRUCTIONS


# ── Observation tools ────────────────────────────────────────────────────

@mcp.tool()
async def get_device_state() -> str:
    """Get the current device screen state: a text description of all visible
    UI elements with their indices, plus which app/activity is in the foreground.
    Call this after every action to see what changed."""
    ui = await _get_state()

    parts = []

    # Phone state
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
    driver, _ = await _ensure_ready()
    png_bytes = await driver.screenshot()

    # Resize and compress to JPEG to stay within Claude Code's MCP token limits.
    # Claude Code treats ImageContent base64 as text tokens, so large PNGs
    # easily exceed the default 25k token limit.
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


# ── Interaction tools ────────────────────────────────────────────────────

@mcp.tool()
async def click(index: int) -> str:
    """Click/tap a UI element by its index from get_device_state output."""
    ui = await _current_ui()
    try:
        x, y = ui.get_element_coords(index)
    except ValueError as e:
        return f"Error: {e}"

    driver, _ = await _ensure_ready()
    await driver.tap(x, y)

    info = ui.get_element_info(index)
    detail = f"Text: '{info.get('text', 'N/A')}', Class: {info.get('className', 'N/A')}"
    return f"Clicked element {index} at ({x}, {y}). {detail}"


@mcp.tool()
async def click_at(x: int, y: int) -> str:
    """Click/tap at specific pixel coordinates on the screen.
    Use element bounds from get_device_state as reference for coordinates."""
    ui = await _current_ui()
    try:
        abs_x, abs_y = ui.convert_point(x, y)
    except Exception as e:
        return f"Error: {e}"

    driver, _ = await _ensure_ready()
    await driver.tap(abs_x, abs_y)
    return f"Tapped at ({abs_x}, {abs_y})"


@mcp.tool()
async def long_press(index: int) -> str:
    """Long-press a UI element by its index."""
    ui = await _current_ui()
    try:
        x, y = ui.get_element_coords(index)
    except ValueError as e:
        return f"Error: {e}"

    driver, _ = await _ensure_ready()
    await driver.swipe(x, y, x, y, duration_ms=1000)
    return f"Long-pressed element {index} at ({x}, {y})"


@mcp.tool()
async def long_press_at(x: int, y: int) -> str:
    """Long-press at specific pixel coordinates."""
    ui = await _current_ui()
    try:
        abs_x, abs_y = ui.convert_point(x, y)
    except Exception as e:
        return f"Error: {e}"

    driver, _ = await _ensure_ready()
    await driver.swipe(abs_x, abs_y, abs_x, abs_y, duration_ms=1000)
    return f"Long-pressed at ({abs_x}, {abs_y})"


@mcp.tool()
async def type_text(text: str, index: int, clear: bool = False) -> str:
    """Type text into a UI input field. Specify the element index to focus
    the field before typing. Set clear=true to clear existing text first
    (recommended for URL bars, search fields, or when replacing text)."""
    ui = await _current_ui()
    driver, _ = await _ensure_ready()

    # Tap the element to focus it
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
async def swipe(
    start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 1.0
) -> str:
    """Swipe from one point to another. Useful for scrolling.
    To scroll down: swipe upward (e.g., start_y=1500, end_y=500).
    Duration is in seconds (default 1.0)."""
    ui = await _current_ui()
    driver, _ = await _ensure_ready()

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
    driver, _ = await _ensure_ready()
    try:
        await driver.press_button(button)
        return f"Pressed {button.upper()} button"
    except ValueError as e:
        return f"Error: {e}"


@mcp.tool()
async def open_app(package: str) -> str:
    """Open an app by its package name. Use list_apps to find package names.
    Example: open_app(package="com.android.settings")"""
    driver, _ = await _ensure_ready()
    result = await driver.start_app(package)
    await asyncio.sleep(1)  # Wait for app to launch
    return result


@mcp.tool()
async def list_apps() -> str:
    """List all installed apps with their package names.
    Use the package names with open_app to launch apps."""
    driver, _ = await _ensure_ready()
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
async def wait(duration: float = 1.0) -> str:
    """Wait for a specified duration in seconds. Useful for waiting for
    animations, page loads, or other time-based operations."""
    await asyncio.sleep(duration)
    return f"Waited {duration} seconds"


# ── ADB tools ────────────────────────────────────────────────────────────

@mcp.tool()
async def adb_shell(command: str) -> str:
    """Run a raw ADB shell command on the device. Returns the command output."""
    await _ensure_ready()
    try:
        output = await _device_obj.shell(command)
        return output if output else "(no output)"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def adb_install(apk_path: str) -> str:
    """Install an APK from a path on the server filesystem."""
    await _ensure_ready()
    try:
        await _device_obj.install(apk_path)
        return f"Successfully installed {apk_path}"
    except Exception as e:
        return f"Error installing APK: {e}"


@mcp.tool()
async def adb_packages() -> str:
    """List all installed packages on the device."""
    await _ensure_ready()
    try:
        output = await _device_obj.shell("pm list packages")
        return output if output else "No packages found"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def device_health() -> str:
    """Check device connection health and return device info."""
    if not _ready:
        return "Device not connected. Call any tool to trigger connection."
    try:
        output = await _device_obj.shell("getprop ro.build.display.id")
        return f"Connected: {DEVICE_SERIAL}\nBuild: {output.strip()}"
    except Exception as e:
        return f"Device error: {e}"


# ── Power control tools ──────────────────────────────────────────────────

def _reset_device_state():
    """Reset global device state so the next tool call re-initializes."""
    global _driver, _state_provider, _device_obj, _ui, _ready
    _driver = None
    _state_provider = None
    _device_obj = None
    _ui = None
    _ready = False


def _get_docker_client():
    """Get a Docker client connected to the host Docker socket."""
    return docker.DockerClient(base_url="unix:///var/run/docker.sock")


@mcp.tool()
async def restart_device() -> str:
    """Restart the Android device (equivalent to rebooting a phone).
    The device will be unavailable for ~15-20 seconds while it reboots."""
    try:
        client = _get_docker_client()
        container = client.containers.get(REDROID_CONTAINER)
        _reset_device_state()
        container.restart(timeout=10)
        await asyncio.sleep(15)  # Wait for Android to boot
        return "Device restarted successfully. Call get_device_state to verify."
    except docker.errors.NotFound:
        return f"Error: container '{REDROID_CONTAINER}' not found"
    except Exception as e:
        return f"Error restarting device: {e}"


@mcp.tool()
async def power_off() -> str:
    """Power off the Android device (equivalent to shutting down a phone).
    The device will be unavailable until power_on is called."""
    try:
        client = _get_docker_client()
        container = client.containers.get(REDROID_CONTAINER)
        _reset_device_state()
        container.stop(timeout=10)
        return "Device powered off."
    except docker.errors.NotFound:
        return f"Error: container '{REDROID_CONTAINER}' not found"
    except Exception as e:
        return f"Error powering off device: {e}"


@mcp.tool()
async def power_on() -> str:
    """Power on the Android device (equivalent to turning on a phone).
    The device will take ~15-20 seconds to boot."""
    try:
        client = _get_docker_client()
        container = client.containers.get(REDROID_CONTAINER)
        container.start()
        _reset_device_state()
        await asyncio.sleep(15)  # Wait for Android to boot
        return "Device powered on. Call get_device_state to verify."
    except docker.errors.NotFound:
        return f"Error: container '{REDROID_CONTAINER}' not found"
    except Exception as e:
        return f"Error powering on device: {e}"


# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
