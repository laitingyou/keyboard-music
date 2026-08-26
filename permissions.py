"""macOS Accessibility permission detection and helpers.

pynput's macOS backend requires Accessibility permission to monitor keyboard
events globally. Without it, ``pynput.keyboard.Listener.run()`` silently
produces no callbacks. We detect this up front and either exit with clear
instructions or poll until the user grants the permission.
"""

from __future__ import annotations

import sys
import time
from typing import Callable


def is_macos() -> bool:
    return sys.platform == "darwin"


def check_accessibility() -> bool:
    """Whether the current process is trusted for Accessibility input monitoring.

    Returns True on Windows / Linux (no equivalent gate). On macOS, requires
    ``pyobjc-framework-CoreGraphics``, which pynput's macOS backend pulls in
    transitively. If pyobjc isn't installed we conservatively return True so
    pynput gets a chance to fail (with its own error) — better than false
    negatives.
    """
    if not is_macos():
        return True
    try:
        from Quartz.CoreGraphics import AXIsProcessTrusted
    except ImportError:
        return True
    try:
        return bool(AXIsProcessTrusted())
    except Exception:  # noqa: BLE001
        return False


def wait_for_accessibility(
    timeout: float = 60.0,
    poll: float = 0.5,
    on_tick: Callable[[float], None] | None = None,
) -> bool:
    """Block until Accessibility permission is granted or ``timeout`` elapses.

    ``on_tick(seconds_remaining)`` is called each poll for UI feedback.
    Returns True if permission was granted, False on timeout / interrupt.
    """
    if not is_macos():
        return True
    if check_accessibility():
        return True
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            if on_tick:
                on_tick(remaining)
            time.sleep(poll)
            if check_accessibility():
                return True
    except KeyboardInterrupt:
        return False
    return check_accessibility()


def permission_instructions() -> str:
    """Return platform-specific instructions for granting the required permission."""
    if is_macos():
        return (
            "macOS requires Accessibility permission to monitor keystrokes.\n"
            "\n"
            "  1. Open System Settings → Privacy & Security → Accessibility.\n"
            "  2. Click + and add this app (Terminal, iTerm, your IDE, etc.).\n"
            "  3. Toggle it on.\n"
            "  4. Re-run keyboard-music, or pass --wait-permission to wait\n"
            "     for the grant and auto-resume."
        )
    return "No special permission needed on this platform."