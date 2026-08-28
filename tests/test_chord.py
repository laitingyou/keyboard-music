"""Unit tests for chord.py."""

from __future__ import annotations

import pytest

from chord import CHORD_INTERVALS, CHORD_VELOCITY, chord_notes_for


# Keys on rows 3 and 4 (ASDF + ZXCV) map to exactly one triad each.
EXPECTED_KEYS = list("asdfghjkl;zxcvbnm,./")


class TestChordData:
    def test_chord_keys_complete(self):
        # The 20 keys of rows 3+4 (ASDF + ZXCV) all have chord definitions;
        # nothing else does.
        assert set(CHORD_INTERVALS) == set(EXPECTED_KEYS)

    def test_intervals_are_in_octave(self):
        # All chord intervals must be < 12 semitones (no wrapping inside a
        # chord). That keeps each chord to one octave of range.
        for key, ivs in CHORD_INTERVALS.items():
            for iv in ivs:
                assert 0 <= iv < 12, f"{key!r}: interval {iv} out of [0, 12)"

    def test_each_chord_is_a_triad(self):
        # All our chords are 3-note triads.
        for ivs in CHORD_INTERVALS.values():
            assert len(ivs) == 3

    def test_velocity_is_low_for_gentle_chords(self):
        # The user requested 温柔 (gentle) — velocity slightly under the
        # default single-note velocity of 100, but clearly audible.
        assert 70 <= CHORD_VELOCITY <= 100

    def test_chord_quality_mix_has_both_major_and_minor(self):
        # Major: intervals = (0, 4, 7). Minor: (0, 3, 7). Both should be
        # present for harmonic variety.
        qualities = set(CHORD_INTERVALS.values())
        assert (0, 4, 7) in qualities  # major triad
        assert (0, 3, 7) in qualities  # minor triad


class TestChordNotesFor:
    # In piano mode (the default), ZXCV maps to: z=C3, x=D3, c=E3, v=F3,
    # b=G3, n=A3, m=B3, ,=C4, .=D4, /=E4. Add 3rd + 5th to make triads.
    def test_z_plays_C_major(self):
        notes = chord_notes_for(48, "z")  # C3 = 48
        assert notes == [48, 52, 55]  # C3, E3, G3

    def test_x_plays_D_minor(self):
        notes = chord_notes_for(50, "x")  # D3 = 50
        assert notes == [50, 53, 57]  # D3, F3, A3

    def test_b_plays_G_major(self):
        notes = chord_notes_for(55, "b")  # G3 = 55
        assert notes == [55, 59, 62]  # G3, B3, D4

    def test_upper_octave_comma_plays_C_major(self):
        notes = chord_notes_for(60, ",")  # C4 = 60
        assert notes == [60, 64, 67]  # C4, E4, G4

    def test_a_plays_C_sharp_minor(self):
        # Piano mode: a = C#3 (49). Minor triad: C#3-E3-G#3.
        notes = chord_notes_for(49, "a")
        assert notes == [49, 52, 56]

    def test_g_plays_A_sharp_minor(self):
        # Piano mode: g = A#3 (58). A# minor: A#3-C#4-F4.
        notes = chord_notes_for(58, "g")
        assert notes == [58, 61, 65]

    def test_asdf_row_all_minor(self):
        # Row 3 (ASDF) is uniformly minor for a gentle, lush palette.
        for ch in "asdfghjkl;":
            assert CHORD_INTERVALS[ch] == (0, 3, 7), f"{ch!r} not minor"

    def test_unknown_char_returns_empty(self):
        assert chord_notes_for(60, "q") == []

    def test_none_root_returns_empty(self):
        assert chord_notes_for(None, "z") == []

    def test_notes_above_127_are_dropped(self):
        # Synth sample rate 48000Hz case: a high root could push the fifth
        # past 127. Just verify clipping works.
        notes = chord_notes_for(127, "z")
        # 127+4 = 131 (E8) is dropped; 127+7 = 134 (G8) dropped; only 127
        # (C8) remains.
        assert all(0 <= n <= 127 for n in notes)

    def test_velocity_clamped_in_safe_range(self):
        # (Piano velocity model: 0 = silent, 127 = loudest.)
        assert 0 < CHORD_VELOCITY <= 127