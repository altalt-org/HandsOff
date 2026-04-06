"""File transfer tools: push files to and pull files from the Android device."""

from __future__ import annotations

import asyncio
import base64
import logging
import subprocess
import tempfile
from pathlib import Path

import httpx

from mcp.server.fastmcp import FastMCP

from ..config import DEVICE_SERIAL
from ..device import DeviceManager

logger = logging.getLogger("handsoff")

# Max file size we'll return inline (10 MB). Larger pulls return a summary.
_MAX_INLINE_BYTES = 10 * 1024 * 1024


def _adb_push(local_path: str, device_path: str, serial: str) -> str:
    result = subprocess.run(
        ["adb", "-s", serial, "push", local_path, device_path],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"adb push failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def _adb_pull(device_path: str, local_path: str, serial: str) -> str:
    result = subprocess.run(
        ["adb", "-s", serial, "pull", device_path, local_path],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"adb pull failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def register(mcp: FastMCP, dm: DeviceManager) -> None:
    @mcp.tool()
    async def push_file(
        source_url: str,
        device_path: str,
        executable: bool = False,
    ) -> str:
        """Download a file from a URL and push it to the Android device.

        The file is downloaded to the HandsOff server first, then transferred
        to the Android device via ADB push.

        Args:
            source_url: HTTP(S) URL to download from (e.g. a GitHub release asset).
            device_path: Absolute path on the Android device (e.g. /data/local/tmp/app.apk).
            executable: If true, chmod +x the file on the device after pushing.

        Example: push_file(source_url="https://github.com/.../Iris.apk",
                           device_path="/data/local/tmp/Iris.apk",
                           executable=false)
        """
        await dm.ensure_ready()

        try:
            with tempfile.TemporaryDirectory(prefix="handsoff-push-") as tmpdir:
                # Derive a filename from the URL or device_path
                filename = Path(device_path).name or "download"
                local_file = Path(tmpdir) / filename

                # Download
                logger.info(f"Downloading {source_url} ...")
                async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
                    resp = await client.get(source_url)
                    resp.raise_for_status()
                    local_file.write_bytes(resp.content)

                size_mb = local_file.stat().st_size / (1024 * 1024)
                logger.info(f"Downloaded {size_mb:.1f} MB -> pushing to {device_path}")

                # Push to device
                await asyncio.to_thread(
                    _adb_push, str(local_file), device_path, DEVICE_SERIAL,
                )

                # Optionally make executable
                if executable:
                    await dm.device_obj.shell(f"chmod +x {device_path}")

                return (
                    f"Pushed {filename} ({size_mb:.1f} MB) to {device_path}"
                    + (" [executable]" if executable else "")
                )
        except httpx.HTTPStatusError as e:
            return f"Download failed: HTTP {e.response.status_code} for {source_url}"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    async def pull_file(device_path: str) -> str:
        """Pull a file from the Android device and return its contents.

        For text files the raw content is returned. For binary files the
        content is base64-encoded. Files larger than 10 MB return only
        metadata (size, first bytes) — use adb_shell to inspect them
        on-device instead.

        Args:
            device_path: Absolute path on the Android device.

        Example: pull_file(device_path="/data/local/tmp/config.json")
        """
        await dm.ensure_ready()

        try:
            with tempfile.TemporaryDirectory(prefix="handsoff-pull-") as tmpdir:
                filename = Path(device_path).name or "file"
                local_file = Path(tmpdir) / filename

                await asyncio.to_thread(
                    _adb_pull, device_path, str(local_file), DEVICE_SERIAL,
                )

                size = local_file.stat().st_size
                if size > _MAX_INLINE_BYTES:
                    return (
                        f"File too large to return inline ({size / (1024*1024):.1f} MB). "
                        f"Use adb_shell to inspect it on-device."
                    )

                raw = local_file.read_bytes()

                # Try decoding as text
                try:
                    text = raw.decode("utf-8")
                    return f"=== {device_path} ({size} bytes) ===\n{text}"
                except UnicodeDecodeError:
                    encoded = base64.b64encode(raw).decode("ascii")
                    return (
                        f"=== {device_path} ({size} bytes, binary, base64-encoded) ===\n"
                        f"{encoded}"
                    )
        except Exception as e:
            return f"Error: {e}"
