"""Unit tests for the listener's chord-mode logic.

Uses a mock synth (no real audio) and bypasses pynpup entirely — we drive
    ``listener._on_press`` and ```` with synthetic keys.
"""

from __future__ import annotations

import pytest

from listener import KeyboardListener
from pynput.keyboard import Key, KeyCode
from sustain import SustainController


class MockSynth:
    def __init__(self):
        self.notes_on: list[tuple[int, int]] = []
        self.notes_off: list[int] = []
        self.panics = 0

    def note_on(self, midi: int, velocity: int = 100) -> None:
        self.notes_on.append((midi, velocity))

    def note_off(self, midi: int) -> None:
        self.notes_off.append(midi)

    def panic(self) -> None:
        self.panics += 1


def make_listener(mapping=None):
    synth = MockSynth()
    if mapping is None:
        # Match piano mode for the ZXCV row keys (default mapping).
        mapping = {
            "z": 48, "x": 50, "c": 52, "v": 53, "b": 55,
            "n": 57, "m": 59, ",": 60, ".": 62, "/": 64,
            "q": 60,  # non-chord char (white-key above 1)
            "1": 61,  # digit (black)
        }
    # Seeded RNG so velocity jitter is deterministic in tests.
    controller = SustainController(synth, mapping, frozenset(), rng=__import__("random").Random(42))
    return KeyboardListener(controller), synth


class TestChordMode:
    def test_chord_mode_off_by_default(self):
        listener, _ = make_listener()
        assert listener._chord_mode is False

    def test_pressing_caps_lock_toggles_mode_on(self):
        listener, _ = make_listener()
        listener._on_press(Key.caps_lock)
        assert listener._chord_mode is True

    def test_releasing_caps_lock_keeps_mode_on(self):
        # Toggle semantics: the mode persists after the key is released -
        # only a second press turns it off. No holding required.
        listener, _ = make_listener()
        listener._on_press(Key.caps_lock)
        listener._on_release(Key.caps_lock)
        assert listener._chord_mode is True

    def test_second_press_toggles_mode_off(self):
        listener, _ = make_listener()
        listener._on_press(Key.caps_lock)
        listener._on_press(Key.caps_lock)
        assert listener._chord_mode is False

    def test_mode_persists_across_other_keys(self):
        listener, _ = make_listener()
        listener._on_press(Key.caps_lock)
        listener._on_press(KeyCode.from_char("q"))
        listener._on_release(KeyCode.from_char("q"))
        listener._on_release(Key.caps_lock)
        assert listener._chord_mode is True

    def test_chord_key_with_mode_off_plays_single_note(self):
        # Without Caps Lock, pressing Z plays just the single mapped note
        # at the standard single-note velocity (jittered ±14 around 100).
        listener, synth = make_listener()
        listener._on_press(KeyCode.from_char("z"))
        assert len(synth.notes_on) == 1
        midi, vel = synth.notes_on[0]
        assert midi == 48
        assert 86 <= vel <= 114

    def test_chord_key_with_mode_on_plays_full_triad(self):
        listener, synth = make_listener()
        listener._on_press(Key.caps_lock)
        listener._on_press(KeyCode.from_char("z"))
        # z -> C major triad (C-E-G) at the gentle chord velocity.
        assert synth.notes_on == [(48, 50), (52, 50), (55, 50)]

    def test_chord_key_release_stops_only_its_chord(self):
        listener, synth = make_listener()
        listener._on_press(Key.caps_lock)
        listener._on_press(KeyCode.from_char("z"))
        listener._on_press(KeyCode.from_char("x"))
        assert synth.notes_on == [
            (48, 50), (52, 50), (55, 50),  # z chord
            (50, 50), (53, 50), (57, 50),  # x chord
        ]
        synth.notes_off.clear()
        listener._on_release(KeyCode.from_char("z"))
        # Only z's notes should be released; x keeps ringing.
        assert set(synth.notes_off) == {48, 52, 55}

    def test_re_pressing_same_chord_does_not_retrigger(self):
        # Pressing Z twice in a row (without releasing) should not stack
        # duplicate notes — the held_chords dict already has the entry.
        listener, synth = make_listener()
        listener._on_press(Key.caps_lock)
        listener._on_press(KeyCode.from_char("z"))
        listener._on_press(KeyCode.from_char("z"))  # re-press
        assert synth.notes_on == [(48, 50), (52, 50), (55, 50)]

    def test_non_chord_key_with_mode_on_plays_single_note(self):
        # Caps Lock held but pressing a non-chord key (q, 1) plays single
        # note normally — chord mode only affects the ZXCV row.
        listener, synth = make_listener()
        listener._on_press(Key.caps_lock)
        listener._on_press(KeyCode.from_char("q"))
        assert len(synth.notes_on) == 1
        midi, vel = synth.notes_on[0]
        assert midi == 60
        listener._on_press(KeyCode.from_char("1"))
        assert len(synth.notes_on) == 2
        assert synth.notes_on[1][0] == 61

    def test_releasing_caps_lock_does_not_stop_chords(self):
        # The user's chord is held by the chord KEY (Z), not the toggle key.
        # Releasing Caps Lock leaves the chord still active in _held_chords.
        listener, synth = make_listener()
        listener._on_press(Key.caps_lock)
        listener._on_press(KeyCode.from_char("z"))
        assert "z" in listener._held_chords
        listener._on_release(Key.caps_lock)
        # Toggle semantics: release is a no-op - mode stays ON.
        assert listener._chord_mode is True
        assert "z" in listener._held_chords
        # Toggling OFF mid-chord leaves held chords ringing.
        listener._on_press(Key.caps_lock)
        assert listener._chord_mode is False
        # Releasing z finally stops it.
        listener._on_release(KeyCode.from_char("z"))
        assert "z" not in listener._held_chords

    def test_out_of_range_chord_notes_are_dropped(self):
        # If the chord root is so high that some intervals exceed 127,
        # those notes are dropped silently. We can't easily test this
        # without a high-mapping override — covered in test_chord.py.
        pass


class TestCustomChordToggleKey:
    def test_custom_toggle(self):
        # Use Tab as the chord toggle instead of Caps Lock.
        synth = MockSynth()
        mapping = {"z": 48, "x": 50}
        controller = SustainController(synth, mapping, frozenset())
        listener = KeyboardListener(controller, chord_toggle_key=Key.tab)

        listener._on_press(Key.tab)
        assert listener._chord_mode is True
        listener._on_press(KeyCode.from_char("z"))
        assert synth.notes_on == [(48, 50), (52, 50), (55, 50)]