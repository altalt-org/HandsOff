"""App store tools: download and install APKs via apkeep (APKPure, F-Droid)."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
import zipfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ..config import DEVICE_SERIAL
from ..device import DeviceManager

logger = logging.getLogger("handsoff")

APKEEP_BIN = "apkeep"
VALID_SOURCES = {"apkpure", "f-droid"}
# apkeep CLI uses different source names than our user-facing API
_APKEEP_SOURCE_MAP = {"apkpure": "apk-pure", "f-droid": "f-droid"}


def _download_apk(package: str, source: str, output_dir: Path) -> list[Path]:
    """Download APK(s) using apkeep. Returns list of downloaded APK files."""
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source '{source}', must be one of: {', '.join(VALID_SOURCES)}")

    apkeep_source = _APKEEP_SOURCE_MAP[source]
    cmd = [APKEEP_BIN, "-a", package, "-d", apkeep_source, str(output_dir)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"apkeep download failed: {result.stderr.strip() or result.stdout.strip()}"
        )

    # Find downloaded files
    apk_files = sorted(output_dir.glob("*.apk"))
    if apk_files:
        return apk_files

    # Check for XAPK (ZIP containing split APKs)
    xapk_files = sorted(output_dir.glob("*.xapk"))
    if xapk_files:
        return _extract_xapk(xapk_files[0], output_dir)

    raise RuntimeError(
        f"No APK files found after download. apkeep output: {result.stdout.strip()}"
    )


def _extract_xapk(xapk_path: Path, output_dir: Path) -> list[Path]:
    """Extract APK files from an XAPK (ZIP) bundle."""
    extract_dir = output_dir / "_xapk"
    extract_dir.mkdir()
    with zipfile.ZipFile(xapk_path, "r") as zf:
        zf.extractall(extract_dir)

    apk_files = sorted(extract_dir.glob("*.apk"))
    if not apk_files:
        raise RuntimeError("XAPK archive contained no APK files")

    logger.info(f"Extracted {len(apk_files)} APK(s) from XAPK bundle")
    return apk_files


def _install_apks(apk_files: list[Path], serial: str) -> str:
    """Install APK(s) via ADB. Uses install-multiple for split APKs."""
    cmd = ["adb", "-s", serial]
    if len(apk_files) == 1:
        cmd += ["install", "-r", str(apk_files[0])]
    else:
        cmd += ["install-multiple", "-r"] + [str(f) for f in apk_files]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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
            apkeep_source = _APKEEP_SOURCE_MAP[source]
            cmd = [APKEEP_BIN, "-l", "-a", package, "-d", apkeep_source]
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
        Handles both single APKs and XAPK (split APK) bundles automatically.
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

                total_mb = sum(f.stat().st_size for f in apk_files) / (1024 * 1024)
                logger.info(f"Installing {len(apk_files)} APK(s) ({total_mb:.1f} MB)...")

                await asyncio.to_thread(_install_apks, apk_files, DEVICE_SERIAL)

                parts = [f"Installed {package} from {source}"]
                for apk in apk_files:
                    size_mb = apk.stat().st_size / (1024 * 1024)
                    parts.append(f"  {apk.name} ({size_mb:.1f} MB)")
                parts.append("All temporary files cleaned up.")
                return "\n".join(parts)
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
