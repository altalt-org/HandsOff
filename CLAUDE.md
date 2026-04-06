# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HandsOff is an MCP server that lets AI agents control Android devices (ReDroid containers) over ADB. It exposes device interaction tools (tap, swipe, type, screenshot, app install, power control) via FastMCP over SSE transport, mounted on a FastAPI app.

## Architecture

**Two packages, one server:**

- `server/` — FastAPI + FastMCP application. Entry point is `server/app.py` which creates the FastAPI app, mounts MCP at `/mcp`, and registers tools. Run with `uvicorn server.app:app`.
- `droidrun-pkg/` — Vendored fork of the DroidRun framework. Only the lightweight core is used: `tools/driver/` (AndroidDriver, ADB), `tools/ui/` (UIState, accessibility tree parsing), `tools/android/` (Portal client), and `portal.py` (Portal APK auto-install). Heavy agent/LLM deps are commented out in its pyproject.toml.

**MCP tool modules** (`server/tools/`):
- `observation.py` — `get_device_state`, `screenshot`
- `interaction.py` — `click`, `click_at`, `type_text`, `swipe`, `long_press`, `long_press_at`, `system_button`, `open_app`, `list_apps`, `wait`
- `appstore.py` — `app_install`, `app_download`, `app_versions` (uses `apkeep` CLI)
- `adb.py` — `adb_shell`, `adb_install`, `adb_packages`, `device_health`
- `power.py` — `restart_device`, `power_off`, `power_on`

**Key abstractions:**
- `DeviceManager` (`server/device.py`) — lazy-init async ADB connection + Portal setup, thread-safe via `asyncio.Lock`. All tools receive this shared instance.
- `PowerBackend` (`server/power.py`) — ABC with `DockerBackend` (controls containers via docker.sock) and `KubernetesBackend` (deletes pods / scales StatefulSets). Selected by `POWER_BACKEND` env var.
- Portal APK — accessibility service auto-installed on the device at first connection. Provides the UI element tree that `get_device_state` reads.

**ReDroid image builder** (`redroid-script/`) — Python CLI that generates a Dockerfile for custom Android images with GApps, Magisk, Portal, locale config, etc.

## Running Locally

```bash
# Full stack via Docker Compose (redroid + server + scrcpy-web)
docker compose up -d

# Server standalone (requires ADB-reachable device)
cd server
pip install -e ../droidrun-pkg
pip install -r requirements.txt  # or: uv pip install -r pyproject.toml
DEVICE_SERIAL=localhost:5555 python -m server.main
```

Ports: 8000 (MCP + API), 8080 (scrcpy-web screen mirror), 5555 (ADB).

## Environment Variables

Configured in `server/config.py`:
- `DEVICE_SERIAL` (default `localhost:5555`) — ADB device address
- `DROIDRUN_USE_TCP` (default `true`) — use TCP ADB connection
- `PORT` (default `8000`) — server listen port
- `REDROID_CONTAINER` (default `redroid`) — Docker container name for power control
- `POWER_BACKEND` (`docker` | `kubernetes`) — power control backend
- `K8S_NAMESPACE`, `K8S_POD_NAME`, `K8S_STATEFULSET` — Kubernetes power control config

## CI/CD

- **Server image** (`.github/workflows/build-server.yml`): builds on push to `main` when `server/**` or `droidrun-pkg/**` change. Pushes to `ghcr.io/altalt-org/handsoff-server`. ARM64 only (Blacksmith runners).
- **ReDroid image** (`.github/workflows/build-redroid.yml`): builds on version tags (`v*.*.*`). Pushes to `ghcr.io/altalt-org/redroid-custom`.

## Build Notes

- Python 3.11-3.13 supported, 3.12 used in production Docker image.
- Docker build uses `uv` for dependency installation with cache mounts.
- `apkeep` binary is installed in the Docker image for APK downloads from APKPure/F-Droid.
- No test suite exists. Testing is manual against a running device.

## Linting

droidrun-pkg has ruff configured (`line-length = 100`, rules: E, W, F, I, B, ignores E501):

```bash
cd droidrun-pkg
ruff check .
ruff format .
```

## Code Conventions

- All device I/O is async (`async_adbutils`, `httpx`).
- MCP tools follow a functional registration pattern: each module exports a `register(mcp, device_manager, ...)` function that defines tools via `@mcp.tool()`.
- `device_manager.ensure_ready()` must be called at the start of every tool to lazily initialize the ADB connection.
