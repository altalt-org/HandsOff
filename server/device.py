"""Device connection and UI state management."""

from __future__ import annotations

import asyncio
import logging
import subprocess

from async_adbutils import adb
from droidrun.tools.driver.android import AndroidDriver
from droidrun.tools.ui.provider import AndroidStateProvider
from droidrun.tools.ui.state import UIState
from droidrun.tools.filters import ConciseFilter
from droidrun.tools.formatters import IndexedFormatter
from droidrun.portal import ensure_portal_ready

from .config import DEVICE_SERIAL, USE_TCP

logger = logging.getLogger("handsoff")


class DeviceManager:
    """Manages the Android device connection and UI state."""

    def __init__(self) -> None:
        self.driver: AndroidDriver | None = None
        self.state_provider: AndroidStateProvider | None = None
        self.device_obj = None  # raw async_adbutils device for ADB shell
        self.ui: UIState | None = None
        self._ready = False
        self._ready_lock = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        return self._ready

    async def ensure_ready(self) -> tuple[AndroidDriver, AndroidStateProvider]:
        """Connect to the device and create the state provider (once)."""
        async with self._ready_lock:
            if self._ready:
                return self.driver, self.state_provider

            serial = DEVICE_SERIAL
            logger.info(f"Connecting to device {serial}...")

            # ADB connect for TCP devices (e.g. redroid)
            if ":" in serial:
                subprocess.run(["adb", "connect", serial], capture_output=True)

            # Auto-setup Portal
            device_obj = await adb.device(serial=serial)
            await ensure_portal_ready(device_obj)

            driver = AndroidDriver(serial=serial, use_tcp=USE_TCP)
            await driver.connect()

            state_provider = AndroidStateProvider(
                driver,
                tree_filter=ConciseFilter(),
                tree_formatter=IndexedFormatter(),
            )

            self.driver = driver
            self.state_provider = state_provider
            self.device_obj = device_obj
            self._ready = True
            logger.info("Device connected and ready.")
            return driver, state_provider

    async def get_state(self) -> UIState:
        """Fetch fresh UI state from the device."""
        _, state_provider = await self.ensure_ready()
        self.ui = await state_provider.get_state()
        return self.ui

    async def current_ui(self) -> UIState:
        """Return the most recent UI state, fetching if needed."""
        if self.ui is None:
            return await self.get_state()
        return self.ui

    def reset(self) -> None:
        """Reset device state so the next call re-initializes."""
        self.driver = None
        self.state_provider = None
        self.device_obj = None
        self.ui = None
        self._ready = False
