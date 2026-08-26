"""Per-key sustain state machine.

The naive approach (a global ``sustain_active`` flag plus a set of sustained
notes) has subtle correctness bugs around ordering and stuck notes. This
module implements the cleanest fix — each key has its own state:

    IDLE      — never pressed, or released with sustain off
    ACTIVE    — physical key held; note is ringing
    SUSTAINED — physical key released but note still ringing under sustain

Transitions:
    on_key_down:  IDLE      -> ACTIVE   (note_on)
                  ACTIVE    -> ACTIVE   (ignore; this is OS auto-repeat)
                  SUSTAINED -> ACTIVE   (re-attack: note_on)
    on_key_up:    ACTIVE    -> SUSTAINED (if sustain_active)  keep ringing
                  ACTIVE    -> IDLE      (else)              note_off
                  SUSTAINED -> (no-op until sustain_off)
                  IDLE      -> (no-op)

    on_sustain_down:  sustain_active := True
    on_sustain_up:    sustain_active := False; for every SUSTAINED key, note_off
                      and drop. ACTIVE keys are still physically held so they
                      remain ACTIVE.

Velocity (realism): a real piano's loudness is decided by the attack — there
is no "hold longer = louder" (that's an organ). Two modes:

    velocity_dynamic=False (default): every note gets a small random ±velocity
        jitter. Real performers never hit a key twice at the same force, and
        this single change kills the "MIDI keyboard" sound.

    velocity_dynamic=True: the note is delayed by VELOCITY_DELAY seconds (an
        imperceptible 35 ms — real piano actions have comparable latency) so
        we can measure how long the key was held. Fast taps (held < ~50 ms)
        fire loud; keys held longer fire softer, like a gentle touch. The
        velocity also gets random jitter on top.
"""

from __future__ import annotations

import enum
import random
import threading
import time
from typing import Optional

from pynput.keyboard import Key


class KeyState(enum.Enum):
    IDLE = "idle"
    ACTIVE = "active"
    SUSTAINED = "sustained"


# How long on_key_down waits before firing the note in velocity-dynamic mode.
# 35 ms is imperceptible (real grand-piano actions have ~20-50 ms latency).
VELOCITY_DELAY = 0.035

# Base velocity and jitter for the default (non-dynamic) mode.
BASE_VELOCITY = 100
VELOCITY_JITTER = 14  # ±14 → notes vary from 86 to 114


# Sustain pedal key choices.
SUSTAIN_LEFT: frozenset = frozenset({Key.shift})
SUSTAIN_RIGHT: frozenset = frozenset({Key.shift_r})
SUSTAIN_EITHER: frozenset = frozenset({Key.shift, Key.shift_r})


def resolve_sustain_keys(choice: str) -> frozenset:
    """Map the ``--sustain-key`` CLI value to a pynput key set."""
    if choice == "left":
        return SUSTAIN_LEFT
    if choice == "right":
        return SUSTAIN_RIGHT
    if choice == "either":
        return SUSTAIN_EITHER
    raise ValueError(f"unknown sustain-key choice: {choice!r}")


def _velocity_for_held(held: float, rng: random.Random) -> int:
    """Velocity from key-hold duration: fast taps are loud, long holds gentle.

    Real piano dynamics come from attack speed, not duration; on a computer
    keyboard, hold duration is our only proxy for attack speed. The mapping
    is 127 (very fast) down to ~60 (held > 500 ms), plus small jitter.
    """
    # held goes 0 → 0.5 s; velocity goes 127 → 60.
    vel = 127 - 67 * min(1.0, held / 0.5)
    vel += rng.randint(-8, 8)
    return max(1, min(127, int(vel)))


class SustainController:
    """Translates key events into piano note events, with per-key state tracking.

    ``synth`` is any object exposing ``note_on(midi, velocity)``, ``note_off(midi)``,
    and ``panic()`` — typically a ``PianoSynth``.

    If ``sustain_on_start`` is True, the controller starts with the sustain
    pedal engaged: every released note keeps ringing until the user presses
    and releases Shift (which clears all sustained notes), or hits panic.
    Shift's behavior is otherwise unchanged.

    ``transpose_semitones`` lets the caller shift the keyboard's pitch range
    at runtime (used by the listener's arrow-key handler). New notes played
    after a transpose use the shifted MIDI; previously ringing notes are
    unaffected.

    ``velocity_dynamic`` enables the attack-based velocity mode described in
    the module docstring. ``rng`` is an injectable ``random.Random`` used for
    the velocity jitter (tests pass a seeded instance).
    """

    def __init__(
        self,
        synth,
        mapping: dict,
        sustain_keys: frozenset,
        sustain_on_start: bool = False,
        velocity_dynamic: bool = False,
        rng: Optional[random.Random] = None,
    ):
        self._synth = synth
        self._mapping = mapping
        self._sustain_keys = sustain_keys
        self._sustain_on_start: bool = sustain_on_start
        self.sustain_active: bool = sustain_on_start
        self.trans: int = 0  # semitones of shift applied to new notes
        self.velocity_dynamic = velocity_dynamic
        self._rng = rng if rng is not None else random.Random()
        # Guard for key-state bookkeeping (listener thread vs. timer thread).
        self._state_lock = threading.RLock()
        # pynkey -> (KeyState, midi_note_at_time_of_press)
        self._key_states: dict = {}
        # velocity-dynamic bookkeeping: pending timers + press timestamps.
        self._pending: dict = {}    # key -> threading.Timer (note not yet fired)
        self._press_times: dict = {}  # key -> time.monotonic() at press

    # --- properties exposed for the listener ------------------------------

    @property
    def mapping(self) -> dict:
        return self._mapping

    @property
    def sustain_keys(self) -> frozenset:
        return self._sustain_keys

    # --- runtime controls -------------------------------------------------

    def transpose(self, delta_semitones: int) -> int:
        """Shift the pitch of new note_on events by ``delta_semitones`` (clamped
        so resulting MIDI stays in [0, 127]). Returns the new shift."""
        new = self.trans + delta_semitones
        # Clamp so the lowest possible note (MIDI 0 in mapping) + shift
        # doesn't go negative. With 48 keys and base 0, the lowest MIDI is 0
        # anyway, so this is effectively a sanity check.
        self.trans = max(-127, min(127, new))
        return self.trans

    # --- callbacks --------------------------------------------------------

    def on_key_down(self, key, midi: int) -> None:
        # Apply live transposition to new notes.
        midi = max(0, min(127, midi + self.trans))
        with self._state_lock:
            prev = self._key_states.get(key)
            if prev is None:
                # IDLE -> ACTIVE
                self._start_note(key, midi)
            elif prev[0] == KeyState.SUSTAINED:
                # Re-attack: user re-pressed a key that was being sustained.
                self._start_note(key, midi)
            # else ACTIVE -> ACTIVE: OS auto-repeat, ignore.

    def on_key_up(self, key) -> None:
        with self._state_lock:
            # If a velocity-dynamic note is still pending (held < VELOCITY_DELAY),
            # fire it immediately as a loud staccato note — a fast tap.
            timer = self._pending.pop(key, None)
            if timer is not None:
                timer.cancel()
                entry = self._key_states.pop(key, None)
                if entry is not None:
                    _, midi = entry
                    vel = max(100, self._rng.randint(105, 127))
                    self._synth.note_on(midi, vel)
                    self._synth.note_off(midi)
                return

            entry = self._key_states.get(key)
            if entry is None or entry[0] != KeyState.ACTIVE:
                return
            _, midi = entry
            if self.sustain_active:
                self._key_states[key] = (KeyState.SUSTAINED, midi)
            else:
                self._synth.note_off(midi)
                del self._key_states[key]

    def _start_note(self, key, midi: int) -> None:
        """Begin a note: either immediately (default) or after the velocity
        probe delay (velocity_dynamic mode)."""
        if not self.velocity_dynamic:
            vel = BASE_VELOCITY + self._rng.randint(-VELOCITY_JITTER, VELOCITY_JITTER)
            vel = max(1, min(127, vel))
            self._synth.note_on(midi, vel)
            self._key_states[key] = (KeyState.ACTIVE, midi)
            return

        # Defer the note until we can measure how long the key was held.
        t0 = time.monotonic()
        self._press_times[key] = t0
        timer = threading.Timer(VELOCITY_DELAY, self._fire_dynamic, args=(key, midi, t0))
        timer.daemon = True
        timer.start()
        self._pending[key] = timer
        # Mark ACTIVE immediately so auto-repeat presses are filtered while
        # the timer is pending. on_key_up cancels the timer via _pending.
        self._key_states[key] = (KeyState.ACTIVE, midi)

    def _fire_dynamic(self, key, midi: int, t0: float) -> None:
        """Timer callback: fire the deferred note with attack-based velocity."""
        with self._state_lock:
            self._pending.pop(key, None)
            entry = self._key_states.get(key)
            if entry is None:
                return  # key was released-and-cleared before firing
            held = time.monotonic() - t0
            vel = _velocity_for_held(held, self._rng)
            self._synth.note_on(midi, vel)
            # State is already ACTIVE — nothing more to do here.

    def on_sustain_down(self) -> None:
        if self._sustain_on_start:
            # Pedal is permanently down in this mode; Shift is a no-op.
            return
        self.sustain_active = True

    def on_sustain_up(self) -> None:
        if self._sustain_on_start:
            # Pedal is permanently down; Shift release must NOT silence
            # notes the user explicitly chose to sustain.
            return
        self.sustain_active = False
        with self._state_lock:
            # Release every SUSTAINED note. ACTIVE notes are still physically
            # held and stay ACTIVE — when the user finally releases them, the
            # usual ACTIVE -> IDLE path will fire (sustain is now False).
            for key, (state, midi) in list(self._key_states.items()):
                if state == KeyState.SUSTAINED:
                    self._synth.note_off(midi)
                    del self._key_states[key]

    def panic(self) -> None:
        with self._state_lock:
            for timer in self._pending.values():
                timer.cancel()
            self._pending.clear()
            self._press_times.clear()
            self._synth.panic()
            self._key_states.clear()
            # Don't reset sustain_active - it reflects user intent (Shift
            # still held = pedal still down). Panic only silences what's
            # currently ringing.

    # --- introspection for tests -----------------------------------------

    def active_notes(self) -> list[int]:
        """Return MIDI notes currently ringing (ACTIVE + SUSTAINED)."""
        with self._state_lock:
            return [midi for _, midi in self._key_states.values()]

    def state_of(self, key) -> Optional[KeyState]:
        with self._state_lock:
            entry = self._key_states.get(key)
            return entry[0] if entry else None