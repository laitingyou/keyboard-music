"""Unit tests for visualizer geometry helpers (no window needed)."""

from __future__ import annotations

from visualizer import (
    LINE_GAP,
    STAFF_UNIT,
    TOP_LINE_Y,
    ledger_lines,
    midi_to_y,
)


class TestMidiToY:
    def test_top_line_is_F5(self):
        assert midi_to_y(77) == TOP_LINE_Y

    def test_bottom_line_is_E4(self):
        assert midi_to_y(64) == TOP_LINE_Y + 4 * LINE_GAP

    def test_c4_on_first_ledger_line(self):
        # C4 sits one line-gap below the bottom line.
        assert midi_to_y(60) == TOP_LINE_Y + 5 * LINE_GAP

    def test_f4_in_bottom_space(self):
        # F4 is a half-step above E4 → half a line-gap up.
        assert midi_to_y(65) == TOP_LINE_Y + 4 * LINE_GAP - STAFF_UNIT

    def test_adjacent_white_keys_half_gap(self):
        # Adjacent staff positions (line↔space) are adjacent white keys:
        # E-F (half step) and F-G (whole step) both span one unit = half a
        # line gap. That's how staff geometry works.
        assert midi_to_y(64) - midi_to_y(65) == STAFF_UNIT
        assert midi_to_y(65) - midi_to_y(67) == STAFF_UNIT

    def test_c5_in_middle_space(self):
        # C5 (72) = third space: between B4 (line 2) and D5 (line 1).
        assert midi_to_y(72) == TOP_LINE_Y + 1.5 * LINE_GAP

    def test_octave_step_is_seven_units(self):
        # C4 -> C5 = 7 white-key steps = 3.5 line gaps.
        assert midi_to_y(60) - midi_to_y(72) == 3.5 * LINE_GAP

    def test_high_note_above_staff(self):
        assert midi_to_y(88) < TOP_LINE_Y


class TestLedgerLines:
    def test_in_staff_no_ledgers(self):
        for midi in (64, 70, 77):
            assert ledger_lines(midi) == []

    def test_c4_single_ledger(self):
        # C4 (60): one ledger line below the staff.
        lines = ledger_lines(60)
        assert len(lines) == 1
        assert lines[0] == TOP_LINE_Y + 5 * LINE_GAP

    def test_a3_two_ledgers(self):
        # A3 (57): ledger lines at C4 and A3 positions.
        lines = ledger_lines(57)
        assert len(lines) == 2
        assert lines == [TOP_LINE_Y + 5 * LINE_GAP, TOP_LINE_Y + 6 * LINE_GAP]

    def test_b3_single_ledger(self):
        # B3 (59): in the space between C4's and A3's lines — one ledger
        # line (the nearest one below).
        lines = ledger_lines(59)
        assert len(lines) == 1
        assert lines[0] == TOP_LINE_Y + 6 * LINE_GAP

    def test_high_note_ledgers(self):
        # C6 (84): two ledger lines above the staff.
        lines = ledger_lines(84)
        assert len(lines) == 2
        assert all(y < TOP_LINE_Y for y in lines)
        # First ledger line just above the top staff line (A5).
        assert lines[0] == TOP_LINE_Y - LINE_GAP

    def test_a5_single_high_ledger(self):
        lines = ledger_lines(81)  # A5 — on the first ledger line above.
        assert len(lines) == 1
        assert lines[0] == TOP_LINE_Y - LINE_GAP

    def test_g5_needs_a5_line(self):
        # G5 (79) is in the space above F5 — needs A5's ledger line.
        lines = ledger_lines(79)
        assert len(lines) == 1
        assert lines[0] == TOP_LINE_Y - LINE_GAP