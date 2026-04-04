#!/usr/bin/env python3
"""
HandsOff Server

Single server exposing:
  - MCP tools at /mcp (SSE transport) for AI agent device control
  - REST API at /api for health checks and future endpoints

Usage:
    python -m server.main
    DEVICE_SERIAL=localhost:5555 PORT=8000 python -m server.main
"""

from __future__ import annotations

from .app import app  # noqa: F401 — uvicorn references this
from .config import PORT

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
