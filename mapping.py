"""Keyboard → MIDI note mapping.

Each printable key on the QWERTY (US) layout maps to a MIDI note. The mapping
walks the keyboard left-to-right top-to-bottom so that lower-left keys are
lower-pitched and upper-right keys are higher-pitched.

Two modes:
    - 'chromatic'        — strict 1:1 mapping. Every key has a unique pitch.
    - 'pentatonic'       — every key snaps to the nearest note in the C major
                            pentatonic scale (C D E G A). Random typing sounds
                            consonant because the scale contains no half-steps.
    - 'pentatonic_minor' — same idea, A minor pentatonic (A C D E G).

Special keys (Space, Enter, function keys, etc.) are mapped to fixed absolute
MIDI notes, so they remain useful as anchor pitches regardless of mode.
"""

from __future__ import annotations

from pynput.keyboard import Key

from errors import MappingError


# QWERTY (US) key positions, read left-to-right top-to-bottom.
# 48 keys: 13 (number row) + 13 (top row) + 12 (home row) + 10 (bottom row).
KEY_ORDER: str = "`1234567890-=" + "qwertyuiop[]\\" + "asdfghjkl;'" + "zxcvbnm,./"

# Scale definitions: semitone offsets from C in any octave.
PENTATONIC_MAJOR: tuple[int, ...] = (0, 2, 4, 7, 9)    # C D E G A
PENTATONIC_MINOR: tuple[int, ...] = (0, 3, 5, 7, 10)   # C Eb F G Bb (= A minor)
CHROMATIC: tuple[int, ...] = tuple(range(12))

# Special key MIDI notes (absolute; independent of base_midi).
SPECIAL_KEYS: dict = {
    Key.space: 36,        # C2 — low rumble for the spacebar
    Key.enter: 60,        # C4 — middle C
    Key.backspace: 48,    # C3
    Key.tab: 36,          # C2
    Key.esc: 24,          # C1
    Key.f1: 84, Key.f2: 86, Key.f3: 88, Key.f4: 90,
    Key.f5: 92, Key.f6: 94, Key.f7: 96, Key.f8: 98,
    Key.f9: 100, Key.f10: 102, Key.f11: 104, Key.f12: 106,
}

# Modifier keys that never produce notes (Shift is the sustain pedal and is
# handled separately in the controller).
IGNORED_KEYS: frozenset = frozenset({
    Key.ctrl, Key.ctrl_r,
    Key.alt, Key.alt_r,
    Key.cmd, Key.cmd_r,
    Key.caps_lock,
    Key.media_play_pause, Key.media_next, Key.media_previous,
    Key.media_volume_up, Key.media_volume_down, Key.media_volume_mute,
    Key.media_eject,
})


def _scale_distance(a: int, b: int) -> int:
    """Distance in semitones between two pitch classes (max 6, with wrap)."""
    d = abs(a - b)
    return min(d, 12 - d)


def _scale_distance(a: int, b: int) -> int:
    """Distance in semitones between two pitch classes (max 6, with wrap)."""
    d = abs(a - b)
    return min(d, 12 - d)


def quantize_to_scale(midi: int, scale: tuple[int, ...]) -> int:
    """Snap a MIDI note to the nearest pitch class in ``scale``.

    The scale repeats every octave, so we compare against both ``scale`` (same
    octave) and ``scale + 12`` (next octave). This lets a B (semitone 11) wrap
    up to the C of the next octave rather than snapping down to a C that is
    actually 11 semitones lower.
    """
    if not 0 <= midi <= 127:
        raise ValueError(f"MIDI note out of range: {midi}")
    octave, semitone = divmod(midi, 12)
    candidates = list(scale) + [s + 12 for s in scale]
    nearest = min(candidates, key=lambda s: abs(s - semitone))
    return octave * 12 + nearest


def build_mapping(mode: str, base_midi: int = 48) -> dict:
    """Build a ``{key → midi_note}`` lookup.

    Args:
        mode: ``'pentatonic'`` (default major), ``'pentatonic_minor'``,
            or ``'chromatic'``.
        base_midi: MIDI note for the lowest key (`` ` ``). Default 48 (C3).
            Must leave room for all 48 keys: ``base_midi + 47 <= 127``.

    Returns:
        Dict where keys are pynput ``Key`` enum values for special keys, or
        single-character strings for printable keys. Values are MIDI note numbers.
    """
    if mode in ("pentatonic", "pentatonic_major"):
        scale = PENTATONIC_MAJOR
    elif mode == "pentatonic_minor":
        scale = PENTATONIC_MINOR
    elif mode == "chromatic":
        scale = CHROMATIC
    else:
        raise MappingError(
            f"Unknown mapping mode: {mode!r} "
            "(expected 'pentatonic', 'pentatonic_minor', or 'chromatic')"
        )

    if not 0 <= base_midi <= 127:
        raise MappingError(f"base_midi must be in [0, 127], got {base_midi}")
    if base_midi + len(KEY_ORDER) - 1 > 127:
        raise MappingError(
            f"base_midi + {len(KEY_ORDER) - 1} exceeds MIDI range; "
            f"use base_midi <= {127 - len(KEY_ORDER) + 1}"
        )

    mapping: dict = {}
    for k, v in SPECIAL_KEYS.items():
        if scale is CHROMATIC:
            mapping[k] = v
        else:
            mapping[k] = quantize_to_scale(v, scale)

    for i, char in enumerate(KEY_ORDER):
        midi = base_midi + i
        if scale is not CHROMATIC:
            midi = quantize_to_scale(midi, scale)
        mapping[char] = midi

    return mapping


def list_keys(mapping: dict) -> list[tuple]:
    """Return the mapping as an ordered list of ``(key, midi, name)`` tuples,
    useful for `--list-keys` output and tests."""
    out = []
    for k, midi in mapping.items():
        if isinstance(k, Key):
            name = f"Key.{k.name}"
        else:
            name = repr(k)
        out.append((k, midi, name))
    out.sort(key=lambda row: row[1])
    return out