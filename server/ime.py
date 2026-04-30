"""Agent-controlled IME swap.

The image ships with a multilingual default IME (Gboard) so humans typing
through ws-scrcpy get full Korean / multilingual support and an on-screen
keyboard. But that on-screen keyboard pops up whenever any input field is
focused — including when the agent taps an input — and covers UI elements
the agent then tries to interact with.

DroidrunKeyboardIME is invisible (no on-screen surface) and exposes a
`commitText` path used by the agent's `type_text` tool. When it is the
default IME, no on-screen keyboard renders on focus.

The agent toggles between these via `set_agent_keyboard(active)`:

    active=True  → swap default to DroidrunKeyboardIME, remember previous
    active=False → restore the previously remembered IME (or fall back
                   to Gboard if none was captured)

A single asyncio.Lock serializes concurrent toggle calls.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .device import DeviceManager

logger = logging.getLogger("handsoff")

DROIDRUN_IME = "com.droidrun.portal/.input.DroidrunKeyboardIME"

# Fallback restore target if we have no recorded previous IME (e.g. server
# restarted while the agent keyboard was already active). Matches gboard.py.
DEFAULT_USER_IME = (
    "com.google.android.inputmethod.latin/"
    "com.android.inputmethod.latin.LatinIME"
)

# Time for the IME framework to bind the new IME to the focused field.
IME_BIND_DELAY_S = 0.2

_swap_lock = asyncio.Lock()
_saved_ime: str | None = None


@dataclass
class IMEResult:
    ok: bool
    changed: bool
    current: str
    message: str


async def _current_default_ime(dm: DeviceManager) -> str | None:
    out = await dm.device_obj.shell("settings get secure default_input_method")
    out = (out or "").strip()
    if not out or out == "null":
        return None
    return out


async def _set_default_ime(dm: DeviceManager, ime_id: str) -> str:
    """Run `ime set` and return its stdout/stderr for diagnostics."""
    return (await dm.device_obj.shell(f"ime set {ime_id}")) or ""


async def is_agent_keyboard_active(dm: DeviceManager) -> bool:
    await dm.ensure_ready()
    return (await _current_default_ime(dm)) == DROIDRUN_IME


async def set_agent_keyboard(dm: DeviceManager, active: bool) -> IMEResult:
    """Toggle the agent keyboard (DroidrunKeyboardIME) on/off.

    Idempotent. Returns an IMEResult with ok/changed flags and a
    human-readable message suitable for an MCP tool response.
    """
    global _saved_ime

    await dm.ensure_ready()
    async with _swap_lock:
        try:
            current = await _current_default_ime(dm)
        except Exception as e:
            return IMEResult(
                ok=False, changed=False, current="",
                message=f"Failed to read current IME: {e}",
            )

        if current is None:
            return IMEResult(
                ok=False, changed=False, current="",
                message="No default IME is set on the device.",
            )

        if active:
            if current == DROIDRUN_IME:
                return IMEResult(
                    ok=True, changed=False, current=current,
                    message="Agent keyboard already active.",
                )
            previous = current
            try:
                await _set_default_ime(dm, DROIDRUN_IME)
                await asyncio.sleep(IME_BIND_DELAY_S)
                new_current = await _current_default_ime(dm)
            except Exception as e:
                return IMEResult(
                    ok=False, changed=False, current=current,
                    message=f"Failed to activate agent keyboard: {e}",
                )
            if new_current != DROIDRUN_IME:
                return IMEResult(
                    ok=False, changed=False, current=new_current or "",
                    message=(
                        f"IME swap rejected by IMMS: still {new_current}. "
                        f"Make sure {DROIDRUN_IME} is enabled."
                    ),
                )
            _saved_ime = previous
            logger.info(f"Agent keyboard ON (was {previous})")
            return IMEResult(
                ok=True, changed=True, current=DROIDRUN_IME,
                message=f"Agent keyboard activated (previous IME: {previous}).",
            )

        # active=False
        if current != DROIDRUN_IME:
            return IMEResult(
                ok=True, changed=False, current=current,
                message=f"Agent keyboard already inactive (current IME: {current}).",
            )
        target = _saved_ime or DEFAULT_USER_IME
        try:
            await _set_default_ime(dm, target)
            await asyncio.sleep(IME_BIND_DELAY_S)
            new_current = await _current_default_ime(dm)
        except Exception as e:
            return IMEResult(
                ok=False, changed=False, current=current,
                message=f"Failed to restore IME to {target}: {e}",
            )
        if new_current != target:
            return IMEResult(
                ok=False, changed=False, current=new_current or "",
                message=(
                    f"IME restore rejected by IMMS: still {new_current}, "
                    f"expected {target}. The target IME may not be installed."
                ),
            )
        _saved_ime = None
        logger.info(f"Agent keyboard OFF (restored to {target})")
        return IMEResult(
            ok=True, changed=True, current=target,
            message=f"Agent keyboard deactivated (restored to {target}).",
        )
