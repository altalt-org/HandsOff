"""Google Play Store tools: download and install APKs from Play Store."""

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

# Architecture for APK downloads — arm64 matches redroid on ARM hosts
APK_ARCH = "arm64"


def _download_apk(package: str, output_dir: Path) -> dict:
    """Download APK(s) from Play Store to output_dir. Runs synchronously.

    Returns dict with keys: title, version, apk_files, obb_files.
    """
    from gplaydl.api import get_delivery, get_details, purchase
    from gplaydl.download import DownloadSpec, download_batch

    auth = _ensure_auth()

    details = get_details(package, auth)
    vc = details.version_code

    purchase(package, vc, auth)
    delivery = get_delivery(package, vc, auth)

    specs: list[DownloadSpec] = []
    apk_files: list[Path] = []          # base + config splits (install together)
    asset_packs: list[Path] = []        # asset pack APKs (install separately)
    obb_files: list[tuple[Path, str]] = []  # (local_path, device_dest)

    # Base APK
    base_path = output_dir / f"{package}-{vc}.apk"
    specs.append(DownloadSpec(
        url=delivery.download_url,
        dest=base_path,
        cookies=delivery.cookies,
        label="base APK",
    ))
    apk_files.append(base_path)

    # Split APKs
    for split in delivery.splits:
        split_path = output_dir / f"{package}-{vc}-{split.name}.apk"
        specs.append(DownloadSpec(
            url=split.url,
            dest=split_path,
            label=f"split: {split.name}",
        ))
        apk_files.append(split_path)

    # OBB and asset pack files
    for af in delivery.additional_files:
        if af.is_asset_pack:
            fname = f"{package}-{vc}-asset.apk"
            asset_path = output_dir / fname
            specs.append(DownloadSpec(
                url=af.url,
                dest=asset_path,
                cookies=af.cookies,
                gzipped=af.gzipped,
                label=fname,
            ))
            asset_packs.append(asset_path)
        else:
            fname = f"{af.type_label}.{af.version_code}.{package}.obb"
            obb_path = output_dir / fname
            device_dest = f"/sdcard/Android/obb/{package}/{fname}"
            specs.append(DownloadSpec(
                url=af.url,
                dest=obb_path,
                cookies=af.cookies,
                label=fname,
            ))
            obb_files.append((obb_path, device_dest))

    download_batch(specs)

    return {
        "title": details.title,
        "version": details.version_string,
        "apk_files": apk_files,
        "asset_packs": asset_packs,
        "obb_files": obb_files,
    }


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


def _push_obb_files(obb_files: list[tuple[Path, str]], serial: str) -> None:
    """Push OBB files to the device."""
    for local_path, device_dest in obb_files:
        # Ensure directory exists on device
        device_dir = str(Path(device_dest).parent)
        subprocess.run(
            ["adb", "-s", serial, "shell", "mkdir", "-p", device_dir],
            capture_output=True, timeout=10,
        )
        result = subprocess.run(
            ["adb", "-s", serial, "push", str(local_path), device_dest],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to push OBB: {result.stderr.strip()}")


def _ensure_auth():
    """Get Play Store auth token (sync helper)."""
    from gplaydl.auth import ensure_auth
    auth = ensure_auth(arch=APK_ARCH)
    if not auth:
        raise RuntimeError("Failed to authenticate with Google Play (token dispenser unreachable)")
    return auth


def register(mcp: FastMCP, dm: DeviceManager) -> None:
    @mcp.tool()
    async def play_search(query: str, limit: int = 5) -> str:
        """Search for apps on the Google Play Store.
        Returns app names, package names, and developers.
        Example: play_search(query="file manager", limit=5)"""
        from gplaydl.api import search_apps

        try:
            auth = await asyncio.to_thread(_ensure_auth)
            results = await asyncio.to_thread(search_apps, query, auth, limit)
            if not results:
                return f"No results found for '{query}'"
            lines = [f"Search results for '{query}' ({len(results)}):"]
            for app in results:
                lines.append(f"  {app.get('title', '?')} — {app.get('package', '?')} (by {app.get('creator', '?')})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    async def play_info(package: str) -> str:
        """Get detailed info about an app on the Google Play Store.
        Shows name, version, developer, rating, download count, and Play Store URL.
        Example: play_info(package="com.whatsapp")"""
        from gplaydl.api import get_details

        try:
            auth = await asyncio.to_thread(_ensure_auth)
            details = await asyncio.to_thread(get_details, package, auth)
            try:
                rating = f"{float(details.rating):.1f}/5"
            except (ValueError, TypeError):
                rating = str(details.rating)
            lines = [
                f"Name: {details.title}",
                f"Package: {details.package}",
                f"Version: {details.version_string} (code: {details.version_code})",
                f"Developer: {details.developer}",
                f"Rating: {rating}",
                f"Downloads: {details.downloads}",
                f"Play Store: {details.play_url}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    async def install_from_play(package: str) -> str:
        """Download an app from Google Play Store and install it on the device.
        Downloads the APK (including split APKs), installs via ADB, then cleans
        up all downloaded files. Only works with free apps.
        Example: install_from_play(package="com.android.chrome")"""
        await dm.ensure_ready()

        try:
            with tempfile.TemporaryDirectory(prefix="handsoff-apk-") as tmpdir:
                tmp = Path(tmpdir)

                # Download (sync — run in thread to avoid blocking event loop)
                result = await asyncio.to_thread(_download_apk, package, tmp)
                title = result["title"]
                version = result["version"]
                apk_files = result["apk_files"]
                asset_packs = result["asset_packs"]
                obb_files = result["obb_files"]

                total = len(apk_files) + len(asset_packs)
                logger.info(f"Downloaded {title} v{version} ({total} APK(s))")

                # Install base + config split APKs together
                await asyncio.to_thread(_install_apks, apk_files, DEVICE_SERIAL)

                # Asset packs are best-effort — they're normally delivered at
                # runtime by the Play Store and many apps work without them.
                asset_results = []
                for asset in asset_packs:
                    try:
                        await asyncio.to_thread(
                            _install_apks, [asset], DEVICE_SERIAL
                        )
                        asset_results.append((asset.name, True, None))
                    except RuntimeError as e:
                        asset_results.append((asset.name, False, str(e)))
                        logger.warning(f"Asset pack install failed (non-fatal): {e}")

                # Push OBB files if any
                if obb_files:
                    await asyncio.to_thread(_push_obb_files, obb_files, DEVICE_SERIAL)

                parts = [f"Installed {title} v{version} ({len(apk_files)} APK(s))"]
                for name, ok, err in asset_results:
                    if ok:
                        parts.append(f"Asset pack {name}: installed")
                    else:
                        parts.append(f"Asset pack {name}: skipped (app will download at runtime)")
                if obb_files:
                    parts.append(f"Pushed {len(obb_files)} OBB file(s) to device")
                parts.append("All temporary files cleaned up.")
                return "\n".join(parts)

        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    async def download_from_play(package: str) -> str:
        """Download an app from Google Play Store WITHOUT installing it.
        Files are saved to a temporary directory inside the container.
        Returns the file paths so you can install later with adb_install.
        Only works with free apps.
        Example: download_from_play(package="com.android.chrome")"""
        # Use a persistent temp dir (not auto-cleaned) so files survive for later install
        tmpdir = tempfile.mkdtemp(prefix="handsoff-apk-")
        tmp = Path(tmpdir)

        try:
            result = await asyncio.to_thread(_download_apk, package, tmp)
            title = result["title"]
            version = result["version"]
            apk_files = result["apk_files"]
            asset_packs = result["asset_packs"]
            obb_files = result["obb_files"]

            parts = [f"Downloaded {title} v{version}"]
            parts.append(f"Directory: {tmpdir}")
            parts.append("")
            parts.append("APK files:")
            for f in apk_files:
                size_mb = f.stat().st_size / (1024 * 1024)
                parts.append(f"  {f.name} ({size_mb:.1f} MB)")
            if asset_packs:
                parts.append("Asset packs:")
                for f in asset_packs:
                    size_mb = f.stat().st_size / (1024 * 1024)
                    parts.append(f"  {f.name} ({size_mb:.1f} MB)")
            if obb_files:
                parts.append("OBB files:")
                for f, dest in obb_files:
                    size_mb = f.stat().st_size / (1024 * 1024)
                    parts.append(f"  {f.name} ({size_mb:.1f} MB) → {dest}")

            all_apks = len(apk_files) + len(asset_packs)
            if all_apks == 1:
                parts.append(f"\nTo install: use adb_install with path {apk_files[0]}")
            else:
                parts.append(f"\nNote: This app has {all_apks} APK(s).")
                parts.append("Use install_from_play instead for automatic split APK installation.")

            return "\n".join(parts)

        except Exception as e:
            # Clean up on failure
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
            return f"Error: {e}"
