"""Unit tests for the SustainController state machine."""

from __future__ import annotations

import random

import pytest

from sustain import (
    BASE_VELOCITY,
    VELOCITY_JITTER,
    KeyState,
    SUSTAIN_EITHER,
    SUSTAIN_LEFT,
    SUSTAIN_RIGHT,
    SustainController,
    _velocity_for_held,
    resolve_sustain_keys,
)


class MockSynth:
    """Records every call for assertion."""

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


def make_controller(sustain_keys=frozenset({"shift"}), **kwargs):
    synth = MockSynth()
    mapping = {c: 60 + i for i, c in enumerate("abcdef")}
    # Seeded rng so velocity jitter is deterministic in tests.
    kwargs.setdefault("rng", random.Random(42))
    return SustainController(synth, mapping, sustain_keys, **kwargs), synth


def notes_on(synth):
    """Return the list of MIDI notes played, dropping velocity details."""
    return [midi for midi, _ in synth.notes_on]


# --- basic lifecycle ----------------------------------------------------


class TestBasicLifecycle:
    def test_idle_to_active_to_idle(self):
        ctrl, synth = make_controller()
        ctrl.on_key_down("a", 60)
        assert notes_on(synth) == [60]
        assert ctrl.state_of("a") == KeyState.ACTIVE

        ctrl.on_key_up("a")
        assert synth.notes_off == [60]
        assert ctrl.state_of("a") is None

    def test_two_keys_independent(self):
        ctrl, synth = make_controller()
        ctrl.on_key_down("a", 60)
        ctrl.on_key_down("b", 61)
        assert notes_on(synth) == [60, 61]

        ctrl.on_key_up("a")
        assert synth.notes_off == [60]
        # 'b' stays active.
        assert ctrl.state_of("b") == KeyState.ACTIVE
        assert synth.notes_off == [60]  # 'b' still ringing

    def test_release_unknown_key_no_op(self):
        ctrl, synth = make_controller()
        ctrl.on_key_up("z")  # never pressed
        assert synth.notes_off == []


# --- auto-repeat filtering ---------------------------------------------


class TestAutoRepeat:
    def test_double_press_is_ignored(self):
        ctrl, synth = make_controller()
        ctrl.on_key_down("a", 60)
        ctrl.on_key_down("a", 60)  # OS auto-repeat
        ctrl.on_key_down("a", 60)
        assert notes_on(synth) == [60]


# --- sustain behavior --------------------------------------------------


class TestSustain:
    def test_release_under_sustain_keeps_ringing(self):
        ctrl, synth = make_controller()
        ctrl.on_sustain_down()
        ctrl.on_key_down("a", 60)
        ctrl.on_key_up("a")
        assert synth.notes_off == []
        assert ctrl.state_of("a") == KeyState.SUSTAINED
        assert ctrl.active_notes() == [60]

    def test_shift_release_stops_all_sustained(self):
        ctrl, synth = make_controller()
        ctrl.on_sustain_down()
        ctrl.on_key_down("a", 60)
        ctrl.on_key_down("b", 61)
        ctrl.on_key_up("a")
        ctrl.on_key_up("b")
        assert synth.notes_off == []

        ctrl.on_sustain_up()
        assert synth.notes_off == [60, 61]
        assert ctrl.active_notes() == []

    def test_active_preserved_when_shift_releases(self):
        """Key physically down (ACTIVE) must not be silenced when Shift releases.
        Only SUSTAINED keys should stop."""
        ctrl, synth = make_controller()
        ctrl.on_key_down("a", 60)
        ctrl.on_sustain_down()
        # 'a' is still ACTIVE — Shift going down doesn't change it.
        ctrl.on_sustain_up()
        assert ctrl.state_of("a") == KeyState.ACTIVE
        assert synth.notes_off == []  # nothing silenced

        # Now user releases 'a' — sustain is off, so normal note_off.
        ctrl.on_key_up("a")
        assert synth.notes_off == [60]

    def test_re_attack_after_sustained(self):
        ctrl, synth = make_controller()
        ctrl.on_sustain_down()
        ctrl.on_key_down("a", 60)
        ctrl.on_key_up("a")
        assert ctrl.state_of("a") == KeyState.SUSTAINED

        # User re-presses 'a' without releasing Shift — should re-trigger.
        ctrl.on_key_down("a", 60)
        assert notes_on(synth) == [60, 60]
        assert ctrl.state_of("a") == KeyState.ACTIVE

        # Cleanly release under sustain, then drop Shift.
        ctrl.on_key_up("a")
        ctrl.on_sustain_up()
        assert synth.notes_off == [60]

    def test_only_sustained_cleared_on_shift_release(self):
        """Mixed ACTIVE + SUSTAINED: only SUSTAINED keys stop."""
        ctrl, synth = make_controller()
        ctrl.on_sustain_down()
        ctrl.on_key_down("a", 60)
        ctrl.on_key_up("a")           # SUSTAINED
        ctrl.on_key_down("b", 61)      # ACTIVE (sustain still on but b just pressed)
        # Now release shift: only 'a' should note_off; 'b' stays ACTIVE.
        ctrl.on_sustain_up()
        assert synth.notes_off == [60]
        assert ctrl.state_of("b") == KeyState.ACTIVE


# --- panic --------------------------------------------------------------


class TestPanic:
    def test_panic_silences_everything(self):
        ctrl, synth = make_controller()
        ctrl.on_key_down("a", 60)
        ctrl.on_key_down("b", 61)
        ctrl.on_key_down("c", 62)
        ctrl.panic()

        assert synth.panics == 1
        assert ctrl.active_notes() == []
        for k in ("a", "b", "c"):
            assert ctrl.state_of(k) is None
        assert not ctrl.sustain_active

    def test_panic_then_release_no_extra_noteoff(self):
        ctrl, synth = make_controller()
        ctrl.on_key_down("a", 60)
        ctrl.panic()
        # Releasing the key after panic must NOT call note_off again — the
        # key state was cleared.
        ctrl.on_key_up("a")
        assert synth.notes_off == []


# --- sustain-on-start mode --------------------------------------------


class TestSustainOnStart:
    def test_default_is_off(self):
        ctrl, _ = make_controller()
        assert ctrl.sustain_active is False

    def test_sustain_on_start_initializes_active(self):
        synth = MockSynth()
        mapping = {c: 60 + i for i, c in enumerate("abc")}
        ctrl = SustainController(synth, mapping, frozenset(), sustain_on_start=True)
        assert ctrl.sustain_active is True

    def test_sustain_on_start_releases_on_key_up(self):
        synth = MockSynth()
        mapping = {c: 60 + i for i, c in enumerate("abc")}
        ctrl = SustainController(synth, mapping, frozenset(), sustain_on_start=True)
        # Press and release with sustain-on-start: note keeps ringing.
        ctrl.on_key_down("a", 60)
        ctrl.on_key_up("a")
        assert synth.notes_off == []
        assert ctrl.state_of("a") == KeyState.SUSTAINED

    def test_sustain_on_start_ignores_shift(self):
        synth = MockSynth()
        mapping = {c: 60 + i for i, c in enumerate("abc")}
        ctrl = SustainController(synth, mapping, frozenset(), sustain_on_start=True)
        ctrl.on_key_down("a", 60)
        ctrl.on_key_down("b", 61)
        ctrl.on_key_up("a")
        ctrl.on_key_up("b")
        assert synth.notes_off == []

        # Shift press/release must be a complete no-op in sustain-on-start mode.
        ctrl.on_sustain_down()
        ctrl.on_sustain_up()
        assert synth.notes_off == []
        assert ctrl.sustain_active is True
        assert ctrl.active_notes() == [60, 61]

    def test_panic_does_not_disengage_pedal_in_sustain_on_start(self):
        synth = MockSynth()
        mapping = {c: 60 + i for i, c in enumerate("abc")}
        ctrl = SustainController(synth, mapping, frozenset(), sustain_on_start=True)
        ctrl.on_key_down("a", 60)
        ctrl.panic()
        # Panic silences everything but leaves the pedal intent intact.
        assert ctrl.sustain_active is True
        assert ctrl.active_notes() == []
        # Next key still sustains (pedal still down).
        ctrl.on_key_down("b", 61)
        ctrl.on_key_up("b")
        assert synth.notes_off == []


# --- transpose ---------------------------------------------------------


class TestTranspose:
    def test_default_zero(self):
        ctrl, _ = make_controller()
        assert ctrl.trans == 0

    def test_transpose_up_shifts_new_notes(self):
        ctrl, synth = make_controller()
        ctrl.transpose(+12)  # up one octave
        ctrl.on_key_down("a", 60)
        # The note_on should be at 72, not 60.
        assert notes_on(synth) == [72]

    def test_transpose_down_shifts_new_notes(self):
        ctrl, synth = make_controller()
        ctrl.transpose(-12)  # down one octave
        ctrl.on_key_down("a", 60)
        assert notes_on(synth) == [48]

    def test_transpose_does_not_affect_already_ringing_notes(self):
        """Notes that started before a transpose should release at their
        original MIDI, not the post-transpose one (otherwise the user would
        end up with a stuck note when they transpose while playing)."""
        ctrl, synth = make_controller()
        ctrl.on_key_down("a", 60)
        # User transposes up while 'a' is held.
        ctrl.transpose(+12)
        ctrl.on_key_up("a")
        # Release should use the original MIDI (60), not 72.
        assert synth.notes_off == [60]
        assert 72 not in synth.notes_off

    def test_transpose_clamped_to_safe_range(self):
        ctrl, _ = make_controller()
        # Pushing past extremes clamps but does not raise.
        assert ctrl.transpose(+500) <= 127
        assert ctrl.transpose(-500) >= -127

    def test_transpose_multiple_steps(self):
        ctrl, synth = make_controller()
        ctrl.transpose(+12)
        ctrl.transpose(+12)  # now +24
        ctrl.on_key_down("a", 60)
        assert notes_on(synth) == [84]

    def test_transpose_affects_chord_roots(self):
        # Chord roots follow the live transpose (like single notes).
        ctrl, synth = make_controller()
        ctrl.transpose(+12)
        ctrl.on_chord_down("z", [60, 64, 67], 72)  # caller already transposed
        assert synth.notes_on == [(60, 72), (64, 72), (67, 72)]


# --- velocity realism --------------------------------------------------


class TestVelocity:
    def test_default_velocity_within_jitter_range(self):
        ctrl, synth = make_controller(rng=random.Random(1))
        for _ in range(30):
            ctrl.on_key_down("a", 60)
            ctrl.on_key_up("a")
        for midi, vel in synth.notes_on:
            assert midi == 60
            lo = BASE_VELOCITY - VELOCITY_JITTER
            hi = BASE_VELOCITY + VELOCITY_JITTER
            assert lo <= vel <= hi, f"velocity {vel} out of [{lo}, {hi}]"

    def test_velocity_varies_across_presses(self):
        ctrl, synth = make_controller(rng=random.Random(7))
        for _ in range(40):
            ctrl.on_key_down("a", 60)
            ctrl.on_key_up("a")
        velocities = {v for _, v in synth.notes_on}
        # With 40 presses and ±14 jitter, we should see more than one value.
        assert len(velocities) > 1

    def test_velocity_for_held_mapping(self):
        rng = random.Random(0)
        # Fast tap (near-zero hold) → loud.
        fast = _velocity_for_held(0.001, rng)
        assert fast >= 110
        # Long hold → gentler.
        long = _velocity_for_held(0.6, rng)
        assert long <= 70
        assert fast > long


class TestVelocityDynamic:
    def test_held_key_fires_after_delay(self):
        ctrl, synth = make_controller(velocity_dynamic=True)
        ctrl.on_key_down("a", 60)
        assert synth.notes_on == []  # nothing yet — probe delay
        import time as _time
        _time.sleep(0.1)  # > VELOCITY_DELAY (35 ms)
        assert notes_on(synth) == [60]
        ctrl.on_key_up("a")
        assert synth.notes_off == [60]

    def test_fast_tap_fires_loud_immediately(self):
        ctrl, synth = make_controller(velocity_dynamic=True)
        ctrl.on_key_down("a", 60)
        ctrl.on_key_up("a")  # released before the 35 ms probe
        # Short tap → immediate loud staccato note.
        assert notes_on(synth) == [60]
        assert synth.notes_off == [60]
        assert synth.notes_on[0][1] >= 100

    def test_panic_cancels_pending_timers(self):
        ctrl, synth = make_controller(velocity_dynamic=True)
        ctrl.on_key_down("a", 60)
        ctrl.panic()
        import time as _time
        _time.sleep(0.1)  # wait past the probe delay
        assert synth.notes_on == []  # timer was cancelled
        assert ctrl.active_notes() == []

    def test_auto_repeat_filtered_during_probe(self):
        ctrl, synth = make_controller(velocity_dynamic=True)
        ctrl.on_key_down("a", 60)
        ctrl.on_key_down("a", 60)  # auto-repeat while pending
        import time as _time
        _time.sleep(0.1)
        assert notes_on(synth) == [60]  # only one note



# --- chord sustain (mirrors single-note pedal logic) --------------------


class TestChordSustain:
    def make_ctrl(self, sustain_on_start=False):
        synth = MockSynth()
        mapping = {"z": 48, "x": 50, "a": 49}
        ctrl = SustainController(synth, mapping, frozenset(),
                                 sustain_on_start=sustain_on_start)
        return ctrl, synth

    def test_chord_release_without_sustain_stops_immediately(self):
        ctrl, synth = self.make_ctrl()
        ctrl.on_chord_down("z", [48, 52, 55], 72)
        assert synth.notes_on == [(48, 72), (52, 72), (55, 72)]
        ctrl.on_chord_up("z")
        assert synth.notes_off == [48, 52, 55]

    def test_chord_release_under_sustain_keeps_ringing(self):
        ctrl, synth = self.make_ctrl()
        ctrl.sustain_active = True
        ctrl.on_chord_down("z", [48, 52, 55], 72)
        ctrl.on_chord_up("z")
        # Notes keep ringing; nothing released yet.
        assert synth.notes_off == []
        assert len(ctrl._sustained_chords) == 1

    def test_sustain_up_releases_sustained_chords(self):
        ctrl, synth = self.make_ctrl()
        ctrl.sustain_active = True
        ctrl.on_chord_down("z", [48, 52, 55], 72)
        ctrl.on_chord_up("z")
        ctrl.on_chord_down("x", [50, 53, 57], 72)
        ctrl.on_chord_up("x")
        ctrl.sustain_active = False
        ctrl.on_sustain_up()
        assert set(synth.notes_off) == {48, 52, 55, 50, 53, 57}
        assert ctrl._sustained_chords == []

    def test_sustain_on_start_chords_ring_until_panic(self):
        # Default config: pedal always down. Chord released under the pedal
        # keeps ringing; on_sustain_up is a no-op; panic clears it.
        ctrl, synth = self.make_ctrl(sustain_on_start=True)
        ctrl.on_chord_down("z", [48, 52, 55], 72)
        ctrl.on_chord_up("z")
        assert synth.notes_off == []
        ctrl.on_sustain_up()  # no-op in this mode
        assert synth.notes_off == []
        ctrl.panic()
        assert synth.panics == 1
        assert ctrl._sustained_chords == []
        assert ctrl._chord_states == {}

    def test_panic_clears_held_chords_too(self):
        ctrl, synth = self.make_ctrl()
        ctrl.on_chord_down("z", [48, 52, 55], 72)
        ctrl.panic()
        assert ctrl._chord_states == {}
        assert ctrl.held_chord_notes("z") is None

    def test_held_chord_notes_introspection(self):
        ctrl, _ = self.make_ctrl()
        ctrl.on_chord_down("z", [48, 52, 55], 72)
        assert ctrl.held_chord_notes("z") == [48, 52, 55]
        ctrl.on_chord_up("z")
        assert ctrl.held_chord_notes("z") is None

    def test_out_of_range_notes_dropped(self):
        ctrl, synth = self.make_ctrl()
        ctrl.on_chord_down("z", [48, 52, 200], 72)
        assert synth.notes_on == [(48, 72), (52, 72)]

# --- resolve_sustain_keys ----------------------------------------------


class TestResolveSustainKeys:
    def test_left(self):
        assert resolve_sustain_keys("left") == SUSTAIN_LEFT

    def test_right(self):
        assert resolve_sustain_keys("right") == SUSTAIN_RIGHT

    def test_either(self):
        assert resolve_sustain_keys("either") == SUSTAIN_EITHER

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            resolve_sustain_keys("both")