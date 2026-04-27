"""Transactional IME swap for agent text injection.

The image ships with a multilingual default IME (e.g. HeliBoard) so humans
typing through ws-scrcpy get full Korean / multilingual support. But the
DroidrunKeyboardIME's `inputText` only works when it's the *active* IME —
that's how `currentInputConnection.commitText` finds a connection.

So agent `input_text` flow:

    1. read current default IME
    2. set DroidrunKeyboardIME as default
    3. await for the IME to bind to the focused field
    4. run the inputText call
    5. restore previous IME (always — finally clause)

A single asyncio.Lock serializes concurrent agent typing so we never strand
the device on Droidrun.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from .device import DeviceManager

logger = logging.getLogger("handsoff")

DROIDRUN_IME = "com.droidrun.portal/.input.DroidrunKeyboardIME"

# Time for the IME framework to bind the new IME to the focused field.
# 100ms is reliably enough on emulator/redroid; 200ms gives slack for slow boots.
IME_BIND_DELAY_S = 0.2

_swap_lock = asyncio.Lock()


async def _current_default_ime(dm: DeviceManager) -> str | None:
    out = await dm.device_obj.shell(
        "settings get secure default_input_method"
    )
    out = (out or "").strip()
    if not out or out == "null":
        return None
    return out


async def _set_default_ime(dm: DeviceManager, ime_id: str) -> None:
    await dm.device_obj.shell(f"ime set {ime_id}")


@asynccontextmanager
async def droidrun_ime_active(dm: DeviceManager):
    """Activate DroidrunKeyboardIME for the duration of the block, then
    restore whatever IME was previously default. Serialized via _swap_lock
    so concurrent agent calls don't fight over the active IME.
    """
    await dm.ensure_ready()
    async with _swap_lock:
        previous = await _current_default_ime(dm)
        already_droidrun = previous == DROIDRUN_IME

        if not already_droidrun:
            logger.debug(
                f"IME swap: {previous} -> {DROIDRUN_IME}"
            )
            await _set_default_ime(dm, DROIDRUN_IME)
            await asyncio.sleep(IME_BIND_DELAY_S)

        try:
            yield
        finally:
            if not already_droidrun and previous:
                try:
                    await _set_default_ime(dm, previous)
                    logger.debug(f"IME restored: {previous}")
                except Exception as e:
                    logger.error(f"Failed to restore IME to {previous}: {e}")
