"""Custom exception hierarchy for keyboard-music."""

from __future__ import annotations


class KeyboardMusicError(Exception):
    """Base exception. All keyboard-music errors inherit from this."""


class SoundFontError(KeyboardMusicError):
    """Raised when the SoundFont cannot be downloaded, cached, or loaded."""


class FluidSynthInitError(KeyboardMusicError):
    """Raised when the FluidSynth audio engine cannot be initialized."""


class MappingError(KeyboardMusicError):
    """Raised for invalid mapping mode arguments."""


class AccessibilityPermissionError(KeyboardMusicError):
    """Raised on macOS when Accessibility permission has not been granted."""