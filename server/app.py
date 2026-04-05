"""FastAPI + MCP server creation and wiring."""

from __future__ import annotations

import logging
import os
import sys

# Ensure droidrun-pkg is importable when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "droidrun-pkg"))

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from .config import DEVICE_SERIAL
from .device import DeviceManager
from .instructions import INSTRUCTIONS
from .power import create_power_backend
from .tools import register_all

logging.basicConfig(level=logging.INFO)

# ── Core objects ────────────────────────────────────────────────────────

device_manager = DeviceManager()

mcp = FastMCP("droidrun", instructions=INSTRUCTIONS, host="0.0.0.0")

app = FastAPI(title="HandsOff")
app.mount("/mcp", mcp.sse_app())

# ── Register all MCP tools ─────────────────────────────────────────────

register_all(mcp, device_manager, create_power_backend())

# ── MCP resource ───────────────────────────────────────────────────────

@mcp.resource("droidrun://instructions")
def get_instructions() -> str:
    """Agent instructions for using the DroidRun device control tools."""
    return INSTRUCTIONS

# ── REST API ───────────────────────────────────────────────────────────

@app.get("/api/health")
async def api_health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "device": DEVICE_SERIAL,
        "connected": device_manager.is_ready,
    }
