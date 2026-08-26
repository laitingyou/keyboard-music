"""Unit tests for mapping.py."""

from __future__ import annotations

import pytest
from pynput.keyboard import Key

from errors import MappingError
from mapping import (
    CHROMATIC,
    KEY_ORDER,
    PENTATONIC_MAJOR,
    PENTATONIC_MINOR,
    SPECIAL_KEYS,
    build_mapping,
    list_keys,
    quantize_to_scale,
)


# --- quantize_to_scale --------------------------------------------------


class TestQuantizeToScale:
    def test_already_in_scale(self):
        # All five pentatonic notes pass through unchanged.
        for note in (48, 50, 52, 55, 57):
            assert quantize_to_scale(note, PENTATONIC_MAJOR) == note

    def test_in_between_picks_nearest(self):
        # C# (49): nearest C (48) or D (50), distance 1 each. min() picks first.
        assert quantize_to_scale(49, PENTATONIC_MAJOR) == 48
        # D# (51): nearest D (50) or E (52), distance 1 each.
        assert quantize_to_scale(51, PENTATONIC_MAJOR) == 50

    def test_wraparound_to_next_octave(self):
        # B (71): nearest is C of next octave (72, distance 1) vs A (69, distance 2).
        assert quantize_to_scale(71, PENTATONIC_MAJOR) == 72

    def test_pentatonic_minor_picks_correct(self):
        # A minor pentatonic: C(0) Eb(3) F(5) G(7) Bb(10)
        assert quantize_to_scale(48, PENTATONIC_MINOR) == 48   # C
        assert quantize_to_scale(51, PENTATONIC_MINOR) == 51   # Eb
        assert quantize_to_scale(53, PENTATONIC_MINOR) == 53   # F
        assert quantize_to_scale(58, PENTATONIC_MINOR) == 58   # Bb (10)
        # F# (54) is between F (53) and G (55): pick F (distance 1) vs G (distance 1).
        assert quantize_to_scale(54, PENTATONIC_MINOR) == 53

    def test_chromatic_is_passthrough(self):
        for midi in range(0, 128):
            assert quantize_to_scale(midi, CHROMATIC) == midi

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            quantize_to_scale(-1, PENTATONIC_MAJOR)
        with pytest.raises(ValueError):
            quantize_to_scale(128, PENTATONIC_MAJOR)


# --- build_mapping ------------------------------------------------------


class TestBuildMapping:
    def test_chromatic_first_key(self):
        m = build_mapping("chromatic", 48)
        assert m["`"] == 48  # C3

    def test_chromatic_last_key(self):
        m = build_mapping("chromatic", 48)
        assert m["/"] == 48 + len(KEY_ORDER) - 1  # B6 = 95

    def test_chromatic_strictly_monotonic(self):
        m = build_mapping("chromatic", 48)
        prev = -1
        for c in KEY_ORDER:
            assert m[c] > prev
            prev = m[c]

    def test_chromatic_count_matches_key_order(self):
        m = build_mapping("chromatic", 48)
        printable = [k for k in m if isinstance(k, str)]
        assert len(printable) == len(KEY_ORDER)
        for c in KEY_ORDER:
            assert c in m

    def test_pentatonic_all_notes_in_scale(self):
        m = build_mapping("pentatonic", 48)
        for k, v in m.items():
            assert v % 12 in PENTATONIC_MAJOR, (
                f"key {k!r} maps to non-pentatonic MIDI {v} (semitone {v % 12})"
            )

    def test_pentatonic_first_key_unchanged(self):
        # Backtick maps to C (semitone 0), which is in the pentatonic scale.
        assert build_mapping("pentatonic", 48)["`"] == 48

    def test_pentatonic_minor_in_scale(self):
        m = build_mapping("pentatonic_minor", 48)
        for k, v in m.items():
            assert v % 12 in PENTATONIC_MINOR

    def test_special_keys_in_scale_for_pentatonic(self):
        # In pentatonic modes, special keys snap to the nearest scale note,
        # so every output is in PENTATONIC_MAJOR (semantically: "all notes
        # produced by the tool are pentatonic").
        m = build_mapping("pentatonic", 48)
        for k, v in m.items():
            assert v % 12 in PENTATONIC_MAJOR, (
                f"key {k!r} maps to non-pentatonic MIDI {v} (semitone {v % 12})"
            )

    def test_special_keys_absolute_in_chromatic(self):
        # In chromatic mode, special keys preserve their original MIDI values.
        m = build_mapping("chromatic", 48)
        for key, expected in SPECIAL_KEYS.items():
            assert m[key] == expected

    def test_base_midi_validation(self):
        with pytest.raises(MappingError):
            build_mapping("chromatic", -1)
        with pytest.raises(MappingError):
            build_mapping("chromatic", 128)
        with pytest.raises(MappingError):
            build_mapping("chromatic", 100)  # 100 + 47 = 147 > 127

    def test_unknown_mode_raises(self):
        with pytest.raises(MappingError):
            build_mapping("diatonic", 48)

    def test_pentatonic_alias(self):
        m_major = build_mapping("pentatonic", 48)
        m_long = build_mapping("pentatonic_major", 48)
        assert m_major == m_long


# --- list_keys ----------------------------------------------------------


class TestListKeys:
    def test_sorted_by_midi(self):
        m = build_mapping("chromatic", 48)
        rows = list_keys(m)
        midis = [r[1] for r in rows]
        assert midis == sorted(midis)

    def test_includes_printable_and_special(self):
        m = build_mapping("chromatic", 48)
        rows = list_keys(m)
        names = {r[2] for r in rows}
        # Spot-check both kinds.
        assert "'`'" in names
        assert any(n.startswith("Key.") for n in names)