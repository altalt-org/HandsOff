#!/usr/bin/env python3
"""
HandsOff API Server

Connects to a redroid container and exposes device control
plus raw ADB commands over a REST API.
"""

import asyncio
import base64
import os
import subprocess
from contextlib import asynccontextmanager

from adbutils import adb
from droidrun import DroidAgent, DroidConfig, DeviceConfig
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DEVICE_SERIAL = os.environ.get("DEVICE_SERIAL", "localhost:5555")

# Key codes for common buttons
KEYCODES = {
    "home": 3, "back": 4, "enter": 66, "recent": 187,
    "volume_up": 24, "volume_down": 25, "power": 26,
    "tab": 61, "delete": 67, "menu": 82,
}


class RunGoalRequest(BaseModel):
    goal: str
    timeout: int = 300


class TapRequest(BaseModel):
    x: int
    y: int


class SwipeRequest(BaseModel):
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    duration: int = 300


class InputTextRequest(BaseModel):
    text: str


class ShellRequest(BaseModel):
    command: str


class InstallAppRequest(BaseModel):
    apk_path: str


class StartAppRequest(BaseModel):
    package: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.device = None
    result = subprocess.run(["adb", "connect", DEVICE_SERIAL], capture_output=True, text=True)
    if "connected" in result.stdout:
        app.state.device = adb.device(DEVICE_SERIAL)
        print(f"Connected to ADB device: {DEVICE_SERIAL}")
    else:
        print(f"ADB connect failed at startup (redroid may still be booting): {result.stdout.strip()}")
    yield
    print("Shutting down...")


app = FastAPI(title="HandsOff API", lifespan=lifespan)


def get_device():
    """Return a live ADB device, reconnecting if necessary."""
    device = get_device()
    if device is not None:
        try:
            device.shell("echo ok")
            return device
        except Exception:
            app.state.device = None

    result = subprocess.run(["adb", "connect", DEVICE_SERIAL], capture_output=True, text=True)
    if "connected" not in result.stdout and "already connected" not in result.stdout:
        raise HTTPException(status_code=503, detail="Android device not ready, try again shortly")

    app.state.device = adb.device(DEVICE_SERIAL)
    return app.state.device


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    connected = app.state.device is not None
    return {"status": "ok", "device": DEVICE_SERIAL, "connected": connected}


# ──────────────────────────────────────────────
# DroidRun Agent (AI goal execution)
# ──────────────────────────────────────────────

@app.post("/agent/run")
async def agent_run(req: RunGoalRequest):
    """Execute a natural language goal on the device using DroidRun AI agent."""
    config = DroidConfig(
        device=DeviceConfig(serial=DEVICE_SERIAL, use_tcp=True),
    )
    agent = DroidAgent(
        goal=req.goal,
        config=config,
    )
    try:
        result = await asyncio.wait_for(agent.run(), timeout=req.timeout)
        return {
            "success": result.success,
            "reason": result.reason,
            "steps": result.steps,
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Agent timed out")


# ──────────────────────────────────────────────
# Device actions (via adb shell commands)
# ──────────────────────────────────────────────

@app.get("/device/screenshot")
async def screenshot():
    """Take a screenshot, returned as base64 PNG."""
    device = get_device()
    png = device.shell("screencap -p", encoding=None)
    return {"image": base64.b64encode(png).decode()}


@app.get("/device/ui-tree")
async def ui_tree():
    """Get the UI accessibility tree via DroidRun Portal content provider."""
    device = get_device()
    result = device.shell(
        'content query --uri content://com.droidrun.portal/state'
    )
    return {"tree": result}


@app.post("/device/tap")
async def tap(req: TapRequest):
    device = get_device()
    device.shell(f"input tap {req.x} {req.y}")
    return {"status": "ok"}


@app.post("/device/swipe")
async def swipe(req: SwipeRequest):
    device = get_device()
    device.shell(
        f"input swipe {req.start_x} {req.start_y} {req.end_x} {req.end_y} {req.duration}"
    )
    return {"status": "ok"}


@app.post("/device/input-text")
async def input_text(req: InputTextRequest):
    device = get_device()
    # Escape special characters for adb shell input
    escaped = req.text.replace("\\", "\\\\").replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
    device.shell(f"input text '{escaped}'")
    return {"status": "ok"}


@app.post("/device/press-button")
async def press_button(button: str):
    """Press a button: home, back, enter, recent, volume_up, volume_down, power."""
    device = get_device()
    keycode = KEYCODES.get(button)
    if keycode is None:
        raise HTTPException(status_code=400, detail=f"Unknown button: {button}. Available: {list(KEYCODES.keys())}")
    device.shell(f"input keyevent {keycode}")
    return {"status": "ok"}


@app.post("/device/start-app")
async def start_app(req: StartAppRequest):
    device = get_device()
    device.shell(f"monkey -p {req.package} -c android.intent.category.LAUNCHER 1")
    return {"status": "ok"}


@app.get("/device/apps")
async def list_apps():
    device = get_device()
    packages = device.list_packages()
    return {"apps": packages}


# ──────────────────────────────────────────────
# Raw ADB shell
# ──────────────────────────────────────────────

@app.post("/adb/shell")
async def adb_shell(req: ShellRequest):
    """Run a raw ADB shell command."""
    device = get_device()
    try:
        output = device.shell(req.command)
        return {"output": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/adb/install")
async def adb_install(req: InstallAppRequest):
    """Install an APK from a path on the server."""
    device = get_device()
    try:
        device.install(req.apk_path)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/adb/packages")
async def adb_packages():
    """List installed packages."""
    device = get_device()
    packages = device.list_packages()
    return {"packages": packages}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
