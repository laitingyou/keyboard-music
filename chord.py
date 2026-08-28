"""Chord definitions for Caps-Lock chord mode.

When chord mode is toggled on (via Caps Lock), the bottom two keyboard
rows play triads instead of single notes; the top two rows keep playing
single notes - a piano-like "split keyboard" (chords for the left hand,
melody for the right).

Each chord key is bound to a root note (its mapped pitch); the chord
intervals are added to that root.

  Row 4 (ZXCV): diatonic triads of C major - the familiar song chords.
  Row 3 (ASDF): minor triads on black-key roots - lush chromatic colors
                (C#m, D#m, F#m, G#m, A#m) that blend gently under melodies.

Chords fire at ``CHORD_VELOCITY`` (lower than the single-note default)
so they sit underneath melodies rather than dominating them.
"""

from __future__ import annotations

from typing import Mapping, Tuple

# Semitone intervals from the root for each chord key. Keys on rows 3 and 4
# form the chord zone; rows 1-2 are unaffected (melody zone).
CHORD_INTERVALS: Mapping[str, Tuple[int, ...]] = {
    # Row 4 (ZXCV) - white-key roots in piano mode (C3..E4)
    "z": (0, 4, 7),   # C major (C-E-G)
    "x": (0, 3, 7),   # D minor (D-F-A)
    "c": (0, 3, 7),   # E minor (E-G-B)
    "v": (0, 4, 7),   # F major (F-A-C)
    "b": (0, 4, 7),   # G major (G-B-D)
    "n": (0, 3, 7),   # A minor (A-C-E)
    "m": (0, 3, 7),   # B minor (B-D-F#)
    ",": (0, 4, 7),   # C major (next octave)
    ".": (0, 3, 7),   # D minor
    "/": (0, 3, 7),   # E minor
    # Row 3 (ASDF) - black-key roots in piano mode (C#3..A#4)
    "a": (0, 3, 7),   # C# minor (C#-E-G#)
    "s": (0, 3, 7),   # D# minor (D#-F#-A#)
    "d": (0, 3, 7),   # F# minor (F#-A-C#)
    "f": (0, 3, 7),   # G# minor (G#-B-D#)
    "g": (0, 3, 7),   # A# minor (A#-C#-F)
    "h": (0, 3, 7),   # C# minor (octave up)
    "j": (0, 3, 7),   # D# minor
    "k": (0, 3, 7),   # F# minor
    "l": (0, 3, 7),   # G# minor
    ";": (0, 3, 7),   # A# minor
}

# Lower than the single-note default (100) so chords sit gently under
# the foreground. NOTE: Salamander's velocity layers are real recordings -
# values below ~60 map to near-inaudible pp playing. 72 is clearly audible
# while still sounding soft next to single notes at 100.
CHORD_VELOCITY: int = 72


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