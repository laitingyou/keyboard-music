"""pynput keyboard listener → controller event dispatch.

Responsibilities:
    - Translate pynput key events into one of: 'sustain', 'note', 'ignore'.
    - Track Ctrl + Alt held simultaneously so the 'p' key triggers a panic.
    - Map Up/Down arrow keys to runtime octave-shift on the controller.
    - Forward 'note' events to SustainController, which owns all state.
"""

from __future__ import annotations

import sys
from typing import Optional

from pynput.keyboard import Key, Listener

from mapping import IGNORED_KEYS
from sustain import SustainController


class KeyboardListener:
    """Wraps pynput's keyboard Listener for the controller.

    The listener thread runs callbacks concurrently with the main thread.
    All state mutation happens in the SustainController, which is designed
    to be called from any thread (synth calls are protected by a lock).
    """

    # Modifiers required for the panic hotkey (Ctrl + Alt + P).
    PANIC_MOD_KEYS = frozenset({Key.ctrl, Key.ctrl_r, Key.alt, Key.alt_r})
    PANIC_TRIGGER = "p"

    def __init__(
        self,
        controller: SustainController,
        transpose_step: int = 12,
    ):
        self.controller = controller
        self.transpose_step = transpose_step
        self._listener = Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        # Modifiers currently held (used for panic hotkey detection).
        self._panic_mods: set = set()

    # --- public API -------------------------------------------------------

    def run(self) -> None:
        """Block until ``stop()`` is called."""
        self._listener.run()

    def start(self) -> None:
        """Start listening on a background thread (returns immediately).

        Used when another thread (e.g. Tk mainloop) owns the main thread.
        """
        self._listener.start()

    def stop(self) -> None:
        self._listener.stop()

    def join(self, timeout: Optional[float] = None) -> None:
        self._listener.join(timeout)

    # --- pynput callbacks -------------------------------------------------

    def _resolve(self, key) -> tuple[str, Optional[int]]:
        """Classify a pynput key as 'sustain' / 'note' / 'ignore'."""
        if isinstance(key, Key):
            if key in self.controller.sustain_keys:
                return ("sustain", None)
            if key in IGNORED_KEYS:
                return ("ignore", None)
            midi = self.controller.mapping.get(key)
            return ("note", midi) if midi is not None else ("ignore", None)
        # KeyCode (character key, possibly with media-key VKs).
        char = getattr(key, "char", None)
        if not char:
            return ("ignore", None)
        midi = self.controller.mapping.get(char)
        return ("note", midi) if midi is not None else ("ignore", None)

    def _is_panic_ready(self) -> bool:
        # Any-side Ctrl AND any-side Alt both held.
        has_ctrl = bool(self._panic_mods & {Key.ctrl, Key.ctrl_r})
        has_alt = bool(self._panic_mods & {Key.alt, Key.alt_r})
        return has_ctrl and has_alt

    def _on_press(self, key) -> None:
        # Transpose: arrow keys shift the keyboard's pitch range at runtime.
        if key == Key.up:
            new_shift = self.controller.transpose(+self.transpose_step)
            print(f"transpose: {new_shift:+d} semitones", file=sys.stderr)
            return
        if key == Key.down:
            new_shift = self.controller.transpose(-self.transpose_step)
            print(f"transpose: {new_shift:+d} semitones", file=sys.stderr)
            return

        # Panic hotkey: track modifiers, fire on 'p' trigger.
        if key in self.PANIC_MOD_KEYS:
            self._panic_mods.add(key)
            return
        char = getattr(key, "char", None)
        if char == self.PANIC_TRIGGER and self._is_panic_ready():
            self.controller.panic()
            return
        kind, midi = self._resolve(key)
        if kind == "sustain":
            self.controller.on_sustain_down()
        elif kind == "note" and midi is not None:
            self.controller.on_key_down(key, midi)
        # 'ignore' keys fall through silently.

    def _on_release(self, key) -> None:
        if key in self.PANIC_MOD_KEYS:
            self._panic_mods.discard(key)
            return
        kind, _ = self._resolve(key)
        if kind == "sustain":
            self.controller.on_sustain_up()
        elif kind == "note":
            self.controller.on_key_up(key)