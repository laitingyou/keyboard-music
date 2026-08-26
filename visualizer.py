"""Live grand-staff visualizer: a small window that draws each note on a
treble staff as you type.

Runs on the Tk main thread. pynput's listener thread delivers note events via
a thread-safe queue; the Tk main loop polls the queue with ``after()``.

Pure geometry helpers (``midi_to_y``, ``ledger_lines``) are module-level so
they can be unit-tested without opening a window.
"""

from __future__ import annotations

import queue
import threading
from typing import Optional

# Geometry of the staff.
TOP_LINE_Y = 30.0      # top staff line (F5) y in pixels
LINE_GAP = 12.0        # distance between adjacent staff lines
STAFF_UNIT = LINE_GAP / 2  # one unit = half a line gap (one white-key step)

# Treble staff reference: F5 (77) is the top line, E4 (64) the bottom line,
# C4 (60) sits on the first ledger line below the staff. Staff geometry is
# not linear in semitones: adjacent line/space pairs are 1 or 2 semitones
# (E-F and B-C are half steps). So positions are measured in "white-key
# steps": each white key moves one unit (half a line gap); black keys sit
# half a unit in between.
#
# Units are counted downward from F5 (top line = 0 units, E4 = 8 units).
SEMI_UNIT = {
    0: 0.0, 1: 0.5, 2: 1.0, 3: 1.5, 4: 2.0,   # C  C# D  D# E
    5: 3.0, 6: 3.5, 7: 4.0, 8: 4.5, 9: 5.0,   # F  F# G  G# A
    10: 5.5, 11: 6.0,                          # A# B
}
# C4 = 10 units (bottom line 8 + 1 line gap); each octave = 7 units.
_C4_UNITS = 10

NOTE_SPACING = 36      # horizontal advance per note
NOTE_RADIUS = 6        # note-head half-size
STAFF_LEFT = 50        # left margin (clef area)
STAFF_RIGHT_MARGIN = 60
CLEF = "\U0001d11e"    # 𝄞 U+1D11E MUSICAL SYMBOL G CLEF


def _staff_units(midi: int) -> float:
    octave, semi = divmod(midi, 12)
    return _C4_UNITS - (octave - 5) * 7 - SEMI_UNIT[semi]


def midi_to_y(midi: int) -> float:
    """Y position of a note head for the given MIDI pitch.

    F5 (77) is the top line, E4 (64) the bottom line; C4 (60) sits on the
    first ledger line below. Every white key = one unit (half a line gap);
    black keys are halfway between.
    """
    return TOP_LINE_Y + _staff_units(midi) * STAFF_UNIT


def ledger_lines(midi: int) -> list[float]:
    """Ledger line Y positions needed for a note outside the staff.

    Staff geometry counts white-key steps: adjacent staff positions (line↔
    space) are adjacent white keys — whether the interval is a whole step
    (C-D) or a half step (E-F). Below E4 (units > 8) ledger lines run at
    every 2 units starting at 10 (C4's line); above F5 (units < 0) they run
    at every 2 units starting at -2 (A5's line). A note head sitting on a
    ledger line keeps every line up to it; a note in a space keeps the
    nearest line(s) below it (the far upper line is dropped).
    """
    units = _staff_units(midi)
    lines: list[float] = []
    if units > 8:
        last = int(units) if int(units) % 2 == 0 else int(units) + 1
        cands = list(range(10, last + 1, 2))
        if units % 2 != 0 and len(cands) > 1:
            cands = cands[1:]  # space note: drop the farthest upper line
        for u in cands:
            lines.append(TOP_LINE_Y + u * STAFF_UNIT)
    elif units < 0:
        first = int(units) if int(units) % 2 == 0 else int(units) - 1
        cands = list(range(-2, first - 1, -2))
        if units % 2 != 0 and len(cands) > 1:
            cands = cands[1:]
        for u in cands:
            lines.append(TOP_LINE_Y + u * STAFF_UNIT)
    return lines


class Visualizer:
    """Tk window showing a treble staff with live notes."""

    def __init__(self, title: str = "keyboard-music — 五线谱", width: int = 940, height: int = 220):
        import tkinter as tk

        self._queue: "queue.Queue[tuple[str, int]]" = queue.Queue()  # ('on'|'off', midi)
        self._x = STAFF_LEFT  # next note's x position
        self._notes: dict = {}  # midi -> canvas item ids (for sustain tails)
        self._closed = False

        self.root = tk.Tk()
        self.root.title(title)
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(self.root, width=width, height=height, bg="white")
        self.canvas.pack(fill="both", expand=True)
        self._width = width

        self._draw_staff()
        self.root.after(20, self._poll)

    # --- drawing setup ----------------------------------------------------

    def _draw_staff(self) -> None:
        c = self.canvas
        bottom = TOP_LINE_Y + 4 * LINE_GAP
        for i in range(5):
            y = TOP_LINE_Y + i * LINE_GAP
            c.create_line(STAFF_LEFT - 10, y, self._width - STAFF_RIGHT_MARGIN + 10, y,
                          fill="black", width=1.5)
        # Clef (treble).
        c.create_text(STAFF_LEFT - 24, TOP_LINE_Y + 2 * LINE_GAP, text=CLEF,
                      font=("Helvetica", 40), fill="black")
        # Left barline.
        c.create_line(STAFF_LEFT - 10, TOP_LINE_Y, STAFF_LEFT - 10, bottom, width=2)

    def _draw_ledger(self, midi: int) -> None:
        for y in ledger_lines(midi):
            self.canvas.create_line(
                self._x - NOTE_RADIUS * 2, y, self._x + NOTE_RADIUS * 2, y,
                fill="black", width=1.2,
            )

    # --- event delivery (callable from any thread) ------------------------

    def enqueue_note(self, midi: int, note_on: bool) -> None:
        """Thread-safe: called from the pynput listener thread."""
        self._queue.put(("on" if note_on else "off", midi))

    def enqueue_panic(self) -> None:
        """Thread-safe: clear the staff (used by the panic hotkey)."""
        self._queue.put(("panic", 0))

    # --- Tk main-loop side --------------------------------------------------

    def _poll(self) -> None:
        if self._closed:
            return
        try:
            while True:
                kind, midi = self._queue.get_nowait()
                if kind == "on":
                    self._note_on(midi)
                elif kind == "off":
                    self._note_off(midi)
                elif kind == "panic":
                    self._new_page()
        except queue.Empty:
            pass
        self.root.after(20, self._poll)

    def _note_on(self, midi: int) -> None:
        y = midi_to_y(midi)
        self._draw_ledger(midi)

        head = self.canvas.create_oval(
            self._x - NOTE_RADIUS, y - NOTE_RADIUS,
            self._x + NOTE_RADIUS, y + NOTE_RADIUS,
            fill="black", outline="black",
        )
        # Stem: up if note is below middle line (B4 = 71), down otherwise.
        if y > TOP_LINE_Y + 2 * LINE_GAP:
            stem = self.canvas.create_line(
                self._x + NOTE_RADIUS, y - NOTE_RADIUS,
                self._x + NOTE_RADIUS, y - NOTE_RADIUS - 4 * LINE_GAP,
                width=1.5,
            )
        else:
            stem = self.canvas.create_line(
                self._x - NOTE_RADIUS, y + NOTE_RADIUS,
                self._x - NOTE_RADIUS, y + NOTE_RADIUS + 4 * LINE_GAP,
                width=1.5,
            )

        self._notes[midi] = (head, stem)
        self._x += NOTE_SPACING
        if self._x > self._width - STAFF_RIGHT_MARGIN:
            self._new_page()

    def _note_off(self, midi: int) -> None:
        """Draw a sustain tail (small horizontal line) at the release point."""
        entry = self._notes.get(midi)
        if entry is None:
            return
        head, stem = entry
        # Draw the tail just past the note head.
        self.canvas.create_line(
            self._x, midi_to_y(midi), self._x + 8, midi_to_y(midi),
            fill="black", width=1.5,
        )

    def _new_page(self) -> None:
        self.canvas.delete("all")
        self._x = STAFF_LEFT
        self._notes.clear()
        self._draw_staff()

    # --- lifecycle --------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        self._closed = True
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass


class VisualSynthProxy:
    """Wraps a synth so every note event also lands on the Visualizer.

    The SustainController calls ``note_on``/``note_off``/``panic`` on its
    synth — passing this proxy keeps the controller logic untouched while the
    visualizer stays in sync. All methods are safe to call from any thread.
    """

    def __init__(self, synth, visualizer: Optional[Visualizer]):
        self._synth = synth
        self._visualizer = visualizer

    def note_on(self, midi: int, velocity: int = 100) -> None:
        self._synth.note_on(midi, velocity)
        if self._visualizer is not None:
            self._visualizer.enqueue_note(midi, True)

    def note_off(self, midi: int) -> None:
        self._synth.note_off(midi)
        if self._visualizer is not None:
            self._visualizer.enqueue_note(midi, False)

    def panic(self) -> None:
        self._synth.panic()
        if self._visualizer is not None:
            self._visualizer.enqueue_panic()

    def close(self) -> None:
        self._synth.close()

    @property
    def synth(self):
        return self._synth