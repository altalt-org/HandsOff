#!/usr/bin/env python3
"""
HandsOff API Server

Connects to a redroid container and exposes DroidRun agent control
plus raw ADB commands over a REST API.
"""

import asyncio
import base64
import os
from contextlib import asynccontextmanager

from adbutils import adb
from async_adbutils import AdbClient
from droidrun import (
    AndroidDriver,
    DeviceConfig,
    DroidAgent,
    DroidConfig,
)
from droidrun.portal import setup_portal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DEVICE_SERIAL = os.environ.get("DEVICE_SERIAL", "localhost:5555")


class RunGoalRequest(BaseModel):
    goal: str
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
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
    """Connect to the device and set up DroidRun Portal on startup."""
    # Connect ADB to the redroid container
    sync_device = adb.device(DEVICE_SERIAL)
    print(f"Connected to ADB device: {sync_device.serial}")

    # Set up DroidRun Portal (install APK, enable accessibility service)
    async_client = AdbClient()
    async_devices = await async_client.list()
    async_device = None
    for d in async_devices:
        if d.serial == DEVICE_SERIAL:
            async_device = d
            break

    if async_device:
        print("Setting up DroidRun Portal...")
        await setup_portal(async_device)
        print("DroidRun Portal ready")
    else:
        print(f"Warning: could not find async device {DEVICE_SERIAL}")

    # Create a shared AndroidDriver
    driver = AndroidDriver(DeviceConfig(serial=DEVICE_SERIAL, use_tcp=True))
    await driver.connect()
    app.state.driver = driver
    app.state.sync_device = sync_device

    yield

    print("Shutting down...")


app = FastAPI(title="HandsOff API", lifespan=lifespan)


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "device": DEVICE_SERIAL}


# ──────────────────────────────────────────────
# DroidRun Agent (AI goal execution)
# ──────────────────────────────────────────────

@app.post("/agent/run")
async def agent_run(req: RunGoalRequest):
    """Execute an AI agent goal on the device."""
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
# Direct device actions
# ──────────────────────────────────────────────

@app.get("/device/screenshot")
async def screenshot():
    """Take a screenshot, returned as base64 PNG."""
    driver: AndroidDriver = app.state.driver
    img_bytes = await driver.screenshot()
    return {"image": base64.b64encode(img_bytes).decode()}


@app.get("/device/ui-tree")
async def ui_tree():
    """Get the current UI accessibility tree."""
    driver: AndroidDriver = app.state.driver
    tree = await driver.get_ui_tree()
    return {"tree": tree}


@app.post("/device/tap")
async def tap(req: TapRequest):
    driver: AndroidDriver = app.state.driver
    await driver.tap(req.x, req.y)
    return {"status": "ok"}


@app.post("/device/swipe")
async def swipe(req: SwipeRequest):
    driver: AndroidDriver = app.state.driver
    await driver.swipe(req.start_x, req.start_y, req.end_x, req.end_y, req.duration)
    return {"status": "ok"}


@app.post("/device/input-text")
async def input_text(req: InputTextRequest):
    driver: AndroidDriver = app.state.driver
    await driver.input_text(req.text)
    return {"status": "ok"}


@app.post("/device/press-button")
async def press_button(button: str):
    """Press a button: home, back, enter, recent, volume_up, volume_down, power."""
    driver: AndroidDriver = app.state.driver
    await driver.press_button(button)
    return {"status": "ok"}


@app.post("/device/start-app")
async def start_app(req: StartAppRequest):
    driver: AndroidDriver = app.state.driver
    await driver.start_app(req.package)
    return {"status": "ok"}


@app.get("/device/apps")
async def list_apps():
    driver: AndroidDriver = app.state.driver
    apps = await driver.get_apps()
    return {"apps": apps}


# ──────────────────────────────────────────────
# Raw ADB shell
# ──────────────────────────────────────────────

@app.post("/adb/shell")
async def adb_shell(req: ShellRequest):
    """Run a raw ADB shell command."""
    device = app.state.sync_device
    try:
        output = device.shell(req.command)
        return {"output": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/adb/install")
async def adb_install(req: InstallAppRequest):
    """Install an APK from a path on the server."""
    device = app.state.sync_device
    try:
        device.install(req.apk_path)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/adb/packages")
async def adb_packages():
    """List installed packages."""
    device = app.state.sync_device
    packages = device.list_packages()
    return {"packages": packages}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
