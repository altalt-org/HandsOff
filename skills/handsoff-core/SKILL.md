---
name: handsoff-core
description: Core knowledge for working with HandsOff — an AI-powered Android device control platform using ReDroid containers, ADB, and MCP.
---

# HandsOff Core

HandsOff is a platform that lets LLM agents control Android devices via natural language. It runs a containerized Android OS (ReDroid) alongside a FastAPI/MCP server that exposes device control tools.

## Architecture

- **redroid** — Docker container running Android OS (`ghcr.io/altalt-org/redroid-custom`)
- **server** — FastAPI + MCP bridge that communicates with the device via ADB
- **droidrun-pkg** — Python framework for LLM-based device control

## Building the Android Image

The image is built with `redroid-script/redroid.py`. Modules are composable:

```bash
python3 redroid.py -a 12.0.0 -mtg -m -l -dp -ss -loc en-US,ko-KR \
  -p ro.product.model=SM-T970 \
  -p ro.product.brand=Samsung
```

| Flag | Module |
|------|--------|
| `-mtg` | MindTheGapps (Google apps + Gboard) |
| `-m` | Magisk (bootless root) |
| `-l` | Lawnchair launcher |
| `-dp` | DroidRun Portal (accessibility service for agent control) |
| `-ss` | Skip setup wizard |
| `-loc` | System locales (comma-separated, e.g. `en-US,ko-KR`) |
| `-p` | System property override |

Each module lives in `redroid-script/stuff/` and generates an init.rc script copied into the image.

## Locale Configuration

The `-loc` flag bakes locales into the image at build time. The first locale is the primary language. Any standard BCP 47 locale can be used — add as many as needed, comma-separated.

```bash
# English primary, Korean available
-loc en-US,ko-KR

# Korean primary, English available
-loc ko-KR,en-US

# Multiple languages
-loc en-US,ko-KR,ja-JP,zh-CN,es-ES
```

To change locales at runtime without rebuilding:

```bash
adb shell settings put system system_locales en-US,ko-KR,ja-JP
```

The change takes effect immediately. Gboard (included via MindTheGapps) supports input for many languages out of the box.

## Docker Compose

The standard deployment runs two services:

- `redroid` on port 5555 (ADB)
- `server` on port 8000 (MCP/API)

Configure via environment variables: `DEVICE_SERIAL`, `REDROID_CONTAINER`.

## MCP Tools

The server exposes tools via MCP for LLM agents: `adb_shell`, UI observation, tap/swipe/type interaction, Play Store download/install, and power management.
