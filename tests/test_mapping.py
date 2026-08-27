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
    build_piano_mapping,
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


# --- piano mapping ---------------------------------------------------------


# Reference semitone offsets within an octave.
BLACK = [1, 3, 6, 8, 10]
WHITE = [0, 2, 4, 5, 7, 9, 11]

# Per-row contents in physical left-to-right order, with the row's octave
# offset relative to base_midi (set in test cases below).
NUM_ROW = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
QW_ROW  = ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"]
AS_ROW  = ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";"]
ZX_ROW  = ["z", "x", "c", "v", "b", "n", "m", ",", ".", "/"]


class TestPianoMapping:
    BASE = 60  # C4

    def test_number_row_only_black_keys(self):
        m = build_piano_mapping(self.BASE)
        for ch in NUM_ROW:
            assert (m[ch] - self.BASE) % 12 in BLACK, (
                f"{ch!r} → MIDI {m[ch]} (semitone "
                f"{(m[ch] - self.BASE) % 12}) is not a black-key offset"
            )

    def test_qwerty_row_only_white_keys(self):
        m = build_piano_mapping(self.BASE)
        for ch in QW_ROW:
            assert (m[ch] - self.BASE) % 12 in WHITE, (
                f"{ch!r} → MIDI {m[ch]} (semitone "
                f"{(m[ch] - self.BASE) % 12}) is not a white-key offset"
            )

    def test_asdf_row_only_black_keys(self):
        m = build_piano_mapping(self.BASE)
        for ch in AS_ROW:
            assert (m[ch] - self.BASE) % 12 in BLACK

    def test_zxcv_row_only_white_keys(self):
        m = build_piano_mapping(self.BASE)
        for ch in ZX_ROW:
            assert (m[ch] - self.BASE) % 12 in WHITE

    def test_left_to_right_ascending_within_each_row(self):
        m = build_piano_mapping(self.BASE)
        for row in (NUM_ROW, QW_ROW, AS_ROW, ZX_ROW):
            pitches = [m[ch] for ch in row]
            assert pitches == sorted(pitches), (
                f"row {row[0]}..{row[-1]} not ascending: {pitches}"
            )

    def test_zero_is_highest_in_number_row(self):
        # The user's hard requirement: 0 is at the far right, and in this row
        # the rightmost key produces the highest pitch.
        m = build_piano_mapping(self.BASE)
        assert m["0"] > m["1"]
        assert m["0"] == max(m[ch] for ch in NUM_ROW)

    def test_zero_is_higher_than_nine(self):
        m = build_piano_mapping(self.BASE)
        assert m["0"] > m["9"]
    def test_top_two_rows_higher_than_bottom_two(self):
        # With default base_midi, the upper octave pair (rows 1+2) should
        # produce pitches >= the lower octave pair (rows 3+4).
        m = build_piano_mapping(self.BASE)
        upper = max(max(m[ch] for ch in NUM_ROW), max(m[ch] for ch in QW_ROW))
        lower = min(min(m[ch] for ch in AS_ROW), min(m[ch] for ch in ZX_ROW))
        assert upper > lower

    def test_q_and_1_are_adjacent_semitones(self):
        # White C and black C# in the same upper-octave pair should differ by
        # exactly 1 semitone — i.e. pressing 'q' then '1' is a half-step.
        m = build_piano_mapping(self.BASE)
        assert m["1"] - m["q"] == 1

    def test_first_key_of_each_row_known_pitches(self):
        # Concrete expectations make refactoring safer.
        m = build_piano_mapping(self.BASE)
        # '1' is the FIRST (leftmost) key in the number row; maps to C# in base octave
        assert m["1"] == self.BASE + BLACK[0]         # 61 = C#4
        # 'q' is leftmost in QWERTY row; C in base octave
        assert m["q"] == self.BASE + WHITE[0]         # 60 = C4
        # 'a' is leftmost in ASDF row; C# in octave below base
        assert m["a"] == self.BASE - 12 + BLACK[0]    # 49 = C#3
        # 'z' is leftmost in ZXCV row; C in octave below base
        assert m["z"] == self.BASE - 12 + WHITE[0]    # 48 = C3

    def test_rows_wrap_into_next_octave(self):
        # Each row has 10 keys. Black rows (5 keys/octave × 2 octaves = 10 keys)
        # span 21 semitones (9 + 12). White rows (10 keys, 7/octave) span 16
        # semitones (one full octave of 12 + 4 partial).
        m = build_piano_mapping(self.BASE)
        assert m["0"] - m["1"] == 21   # digits (black): C#4 to A#5
        assert m[";"] - m["a"] == 21   # asdf (black): C#3 to A#4
        # QWERTY: C4 (q) to E5 (p) — one octave + 3 semitones
        assert m["p"] - m["q"] == 16
        # ZXCV: C3 (z) to E4 (/) — same span
        assert m["/"] - m["z"] == 16

    def test_special_keys_kept_at_absolute_midi(self):
        # Space, Enter, etc. should play at their canonical anchors.
        from mapping import SPECIAL_KEYS
        m = build_piano_mapping(self.BASE)
        for k, v in SPECIAL_KEYS.items():
            assert m[k] == v

    def test_invalid_base_midi_raises(self):
        from errors import MappingError
        with pytest.raises(MappingError):
            build_piano_mapping(-1)
        with pytest.raises(MappingError):
            build_piano_mapping(128)

    def test_base_too_high_overflow_raises(self):
        # With base_midi=120, the number row's last key would exceed MIDI 127.
        from errors import MappingError
        with pytest.raises(MappingError):
            build_piano_mapping(120)

    def test_piano_mode_selectable_via_build_mapping(self):
        m = build_mapping("piano", self.BASE)
        # Spot-check a known mapping (the same as direct build_piano_mapping).
        assert m["q"] == self.BASE + WHITE[0]    # 60 = C4
        assert m["0"] > m["1"]


# --- piano mapping end -----------------------------------------------------