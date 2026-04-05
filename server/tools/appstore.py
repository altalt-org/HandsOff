"""App store tools: download and install APKs via apkeep (APKPure, F-Droid)."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ..config import DEVICE_SERIAL
from ..device import DeviceManager

logger = logging.getLogger("handsoff")

APKEEP_BIN = "apkeep"
VALID_SOURCES = {"apkpure", "f-droid"}


def _download_apk(package: str, source: str, output_dir: Path) -> list[Path]:
    """Download APK(s) using apkeep. Returns list of downloaded APK files."""
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source '{source}', must be one of: {', '.join(VALID_SOURCES)}")

    cmd = [APKEEP_BIN, "-a", package, "-d", source, str(output_dir)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"apkeep download failed: {result.stderr.strip() or result.stdout.strip()}"
        )

    # Find downloaded APK files
    apk_files = sorted(output_dir.glob("*.apk"))
    if not apk_files:
        # apkeep may also download .xapk files
        xapk_files = sorted(output_dir.glob("*.xapk"))
        if xapk_files:
            raise RuntimeError(
                f"Downloaded XAPK format (not a standard APK). "
                f"This app may not be available as a single APK from {source}."
            )
        raise RuntimeError(
            f"No APK files found after download. apkeep output: {result.stdout.strip()}"
        )

    return apk_files


def _install_apk(apk_path: Path, serial: str) -> str:
    """Install a single APK via ADB."""
    result = subprocess.run(
        ["adb", "-s", serial, "install", "-r", str(apk_path)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ADB install failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def register(mcp: FastMCP, dm: DeviceManager) -> None:
    @mcp.tool()
    async def app_versions(package: str, source: str = "apkpure") -> str:
        """List available versions of an app from APKPure or F-Droid.
        Example: app_versions(package="org.mozilla.firefox", source="apkpure")
        Example: app_versions(package="org.mozilla.fennec_fdroid", source="f-droid")"""
        if source not in VALID_SOURCES:
            return f"Error: source must be one of: {', '.join(VALID_SOURCES)}"

        try:
            cmd = [APKEEP_BIN, "-l", "-a", package, "-d", source]
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                return f"Error: {result.stderr.strip() or result.stdout.strip()}"
            output = result.stdout.strip()
            if not output:
                return f"No versions found for '{package}' on {source}"
            return f"Available versions for {package} on {source}:\n{output}"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    async def app_install(package: str, source: str = "apkpure") -> str:
        """Download an app from APKPure or F-Droid and install it on the device.
        Downloads a single monolithic APK — no split APK merging needed.
        Sources: "apkpure" (default), "f-droid"
        Example: app_install(package="org.mozilla.firefox", source="apkpure")"""
        await dm.ensure_ready()

        if source not in VALID_SOURCES:
            return f"Error: source must be one of: {', '.join(VALID_SOURCES)}"

        try:
            with tempfile.TemporaryDirectory(prefix="handsoff-apk-") as tmpdir:
                tmp = Path(tmpdir)

                logger.info(f"Downloading {package} from {source}...")
                apk_files = await asyncio.to_thread(_download_apk, package, source, tmp)

                apk = apk_files[0]
                size_mb = apk.stat().st_size / (1024 * 1024)
                logger.info(f"Installing {apk.name} ({size_mb:.1f} MB)...")

                await asyncio.to_thread(_install_apk, apk, DEVICE_SERIAL)

                return (
                    f"Installed {package} from {source}\n"
                    f"APK: {apk.name} ({size_mb:.1f} MB)\n"
                    f"All temporary files cleaned up."
                )
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    async def app_download(package: str, source: str = "apkpure") -> str:
        """Download an app from APKPure or F-Droid WITHOUT installing it.
        Pushes the APK to the Android device's storage via ADB.
        Returns the file path on the device.
        Sources: "apkpure" (default), "f-droid"
        Example: app_download(package="org.mozilla.firefox", source="apkpure")"""
        await dm.ensure_ready()

        if source not in VALID_SOURCES:
            return f"Error: source must be one of: {', '.join(VALID_SOURCES)}"

        try:
            with tempfile.TemporaryDirectory(prefix="handsoff-apk-") as tmpdir:
                tmp = Path(tmpdir)
                apk_files = await asyncio.to_thread(_download_apk, package, source, tmp)

                lines = [f"Downloaded {package} from {source}", ""]
                device_paths = []
                for apk in apk_files:
                    size_mb = apk.stat().st_size / (1024 * 1024)
                    device_dest = f"/sdcard/Download/{apk.name}"
                    result = await asyncio.to_thread(
                        subprocess.run,
                        ["adb", "-s", DEVICE_SERIAL, "push", str(apk), device_dest],
                        capture_output=True, text=True, timeout=300,
                    )
                    if result.returncode != 0:
                        raise RuntimeError(f"adb push failed: {result.stderr.strip()}")
                    device_paths.append(device_dest)
                    lines.append(f"  {device_dest} ({size_mb:.1f} MB)")

                lines.append(f"\nTo install: use adb_shell with 'pm install -r {device_paths[0]}'")
                return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"
