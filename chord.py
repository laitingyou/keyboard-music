"""Chord definitions for Caps-Lock chord mode.

When chord mode is active (held by default via Caps Lock), pressing a key
on the ZXCV row triggers a triad instead of a single note. Each chord key
is bound to a root note — the chord intervals are added to that root.

The 10 ZXCV keys cover the diatonic scale of the row's natural pitch
range. The mix of major and minor triads (and one B minor for a touch of
warmth at the top) gives a varied harmonic palette without sounding
startling, matching the user's request for "温柔".

Held with low velocity (``CHORD_VELOCITY``) so chords sit underneath
single-note melodies rather than dominating them.
"""

from __future__ import annotations

from typing import Mapping, Tuple

# Semitone intervals from the root for each chord key on the ZXCV row.
# Mix of major (0, 4, 7) and minor (0, 3, 7) triads.
CHORD_INTERVALS: Mapping[str, Tuple[int, ...]] = {
    # Lower octave (ZXCV in piano mode → C3..B3)
    "z": (0, 4, 7),   # C major (C–E–G)
    "x": (0, 3, 7),   # D minor (D–F–A)
    "c": (0, 3, 7),   # E minor (E–G–B)
    "v": (0, 4, 7),   # F major (F–A–C, C is one octave above)
    "b": (0, 4, 7),   # G major (G–B–D)
    "n": (0, 3, 7),   # A minor (A–C–E, C and E one octave above)
    "m": (0, 3, 7),   # B minor (B–D–F#, both D and F# one octave above)
    # Upper octave (", . / in piano mode → C4..E4)
    ",": (0, 4, 7),   # C major
    ".": (0, 3, 7),   # D minor
    "/": (0, 3, 7),   # E minor
}

# Lower than the single-note default (100) so chords sit gently under
# the foreground.
CHORD_VELOCITY: int = 50


def chord_notes_for(root_midi: int, char: str) -> list[int]:
    """Return the list of MIDI notes for a chord, or ``[]`` if ``char``
    isn't a chord key or ``root_midi`` is unknown.

    Out-of-range notes (root + interval > 127) are dropped.
    """
    intervals = CHORD_INTERVALS.get(char)
    if intervals is None or root_midi is None:
        return []
    return [
        n for n in (root_midi + offset for offset in intervals)
        if 0 <= n <= 127
    ]