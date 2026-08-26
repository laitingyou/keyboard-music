"""CLI entry point: keyboard-music."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from errors import KeyboardMusicError
from listener import KeyboardListener
from mapping import build_mapping, list_keys
from permissions import (
    check_accessibility,
    is_macos,
    permission_instructions,
    wait_for_accessibility,
)
from soundfont import DEFAULT_URL, bundled_soundfont_path, ensure_soundfont
from sustain import SustainController, resolve_sustain_keys
from synth import PianoSynth


# --- CLI ----------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="keyboard-music",
        description="Play piano notes while you type.",
    )
    p.add_argument(
        "--mapping",
        choices=["pentatonic", "pentatonic_minor", "chromatic"],
        default="chromatic",
        help="Scale to map keys to. Default: chromatic (every key = a unique pitch).",
    )
    p.add_argument(
        "--soundfont",
        type=Path,
        help="Path to a SoundFont .sf2 file. Skips auto-download.",
    )
    p.add_argument(
        "--sustain-key",
        choices=["left", "right", "either"],
        default="either",
        help="Which Shift key acts as the sustain pedal. Default: either.",
    )
    p.add_argument(
        "--base-midi",
        type=int,
        default=60,
        help="MIDI note for the lowest key (the backtick). Default 60 (middle C). Range [0, 80].",
    )
    p.add_argument(
        "--soundfont-url",
        default=DEFAULT_URL,
        help="URL to download the SoundFont from.",
    )
    p.add_argument(
        "--redownload",
        action="store_true",
        help="Force re-download of the SoundFont even if cached.",
    )
    p.add_argument(
        "--no-sustain",
        action="store_true",
        help="Disable sustain entirely (Shift becomes a normal modifier, "
             "released notes stop immediately). Overrides everything else.",
    )
    p.add_argument(
        "--no-sustain-on-start",
        action="store_true",
        help="Disable the default-on-at-startup sustain pedal. Use this if you "
             "want Shift to act as a normal momentary pedal instead.",
    )
    p.add_argument(
        "--sustain-on-start",
        action="store_true",
        help="(Legacy flag; sustain is on by default now.) Kept for backward compatibility.",
    )
    p.add_argument(
        "--no-effects",
        action="store_true",
        help="Disable FluidSynth's built-in reverb and chorus (drier sound).",
    )
    p.add_argument(
        "--velocity-dynamic",
        action="store_true",
        help="Attack-based velocity: fast taps play loud, long holds play "
             "gentle (35 ms probe delay). Without this, every note uses a "
             "fixed velocity with ±14 jitter.",
    )
    p.add_argument(
        "--no-visualizer",
        action="store_true",
        help="Do not open the staff-notation window (headless mode).",
    )
    p.add_argument(
        "--self-test",
        action="store_true",
        help="Play a test note at each startup stage (synth init / window open / "
             "listener start) to pinpoint where audio dies.",
    )
    p.add_argument(
        "--wait-permission",
        action="store_true",
        help="On macOS, wait for Accessibility permission instead of exiting.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging.",
    )
    p.add_argument(
        "--list-keys",
        action="store_true",
        help="Print the key-to-MIDI mapping and exit.",
    )
    return p.parse_args(argv)


def setup_logging(verbose: bool) -> logging.Logger:
    log = logging.getLogger("keyboard_music")
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    return log


# --- helpers ------------------------------------------------------------


_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_name(midi: int) -> str:
    """Human-readable pitch name like 'C4', 'F#5'."""
    if not 0 <= midi <= 127:
        return f"midi={midi}"
    octave = midi // 12 - 1
    return f"{_NOTE_NAMES[midi % 12]}{octave}"


# --- main ---------------------------------------------------------------


def main(argv=None) -> int:
    args = parse_args(argv)
    log = setup_logging(args.verbose)

    if args.list_keys:
        try:
            mapping = build_mapping(args.mapping, args.base_midi)
        except KeyboardMusicError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(
            f"Mapping: {args.mapping}    base MIDI: {args.base_midi} "
            f"({midi_name(args.base_midi)})"
        )
        print()
        print(f"  {'MIDI':>4}  {'NOTE':<5}  KEY")
        print(f"  {'-'*4}  {'-'*5}  {'-'*30}")
        for _key, midi, name in list_keys(mapping):
            print(f"  {midi:>4}  {midi_name(midi):<5} {name}")
        return 0

    # macOS Accessibility gate.
    if is_macos() and not check_accessibility():
        if args.wait_permission:
            print(permission_instructions(), file=sys.stderr)
            print(file=sys.stderr)

            def _tick(remaining: float) -> None:
                print(
                    f"\r  waiting for Accessibility permission "
                    f"({int(remaining):>3}s remaining) ",
                    end="",
                    file=sys.stderr,
                )

            granted = wait_for_accessibility(timeout=120.0, on_tick=_tick)
            print(file=sys.stderr)
            if not granted:
                print("error: timed out waiting for Accessibility permission.", file=sys.stderr)
                return 2
            print("Accessibility permission granted. Continuing.", file=sys.stderr)
        else:
            print(permission_instructions(), file=sys.stderr)
            print(
                "\nRe-run with --wait-permission to wait for the grant.",
                file=sys.stderr,
            )
            return 2

    # SoundFont. Priority: --soundfont override → bundled (PyInstaller build
    # that ships the SF2) → user cache → auto-download on first run.
    sf2: Optional[Path] = None
    source = ""
    if args.soundfont:
        sf2 = args.soundfont
        if not sf2.exists():
            print(f"error: --soundfont path does not exist: {sf2}", file=sys.stderr)
            return 1
        source = "user override"
    else:
        bundled = bundled_soundfont_path()
        if bundled is not None and not args.redownload:
            sf2 = bundled
            source = f"bundled ({bundled.stat().st_size / 1024 / 1024 / 1024:.1f} GB)"
        else:
            sf2 = ensure_soundfont(url=args.soundfont_url, force=args.redownload)
            source = "user cache (downloaded on first run)"
    log.info("SoundFont: %s", source)

    # Build runtime.
    try:
        mapping = build_mapping(args.mapping, args.base_midi)
    except KeyboardMusicError as e:
        log.error("Mapping error: %s", e)
        return 2

    sustain_keys = frozenset() if args.no_sustain else resolve_sustain_keys(args.sustain_key)
    # Default is sustain-on-start. Turn it off if --no-sustain-on-start was
    # given, or if --no-sustain was given (which disables sustain entirely).
    sustain_on_start = not (args.no_sustain_on_start or args.no_sustain)

    # Audio engine first: initializing Tk (NSApplication) before CoreAudio
    # has been observed to break FluidSynth's CoreAudio output on macOS.
    try:
        synth = PianoSynth(sf2, no_effects=args.no_effects)
    except KeyboardMusicError as e:
        log.error("Synth init failed: %s", e)
        return 1

    def _stage_note(name: str, midi: int = 72) -> None:
        """Self-test: play one note and log the stage."""
        import time as _t

        log.info("self-test [%s]: playing MIDI %d - listening?", name, midi)
        synth.note_on(midi, 110)
        _t.sleep(0.4)
        synth.note_off(midi)
        _t.sleep(0.2)

    if args.self_test:
        log.info("self-test: synth sample rate = %d Hz", synth.sample_rate)
        _stage_note("1-synth-init", 72)

    # Visualizer window (Tk). Degrades gracefully to headless when Tk is
    # unavailable (e.g. minimal Python installs, headless servers).
    visualizer = None
    if not args.no_visualizer:
        try:
            from visualizer import VisualSynthProxy, Visualizer

            visualizer = Visualizer()
        except Exception as e:  # noqa: BLE001
            log.warning("visualizer unavailable (%s); running headless", e)
            visualizer = None

    if visualizer is not None:
        synth = VisualSynthProxy(synth, visualizer)

    if args.self_test:
        # Drain any queued visualizer events so the window is fresh.
        _stage_note("2-window-open", 67)

    controller = SustainController(
        synth, mapping, sustain_keys,
        sustain_on_start=sustain_on_start,
        velocity_dynamic=args.velocity_dynamic,
    )
    listener = KeyboardListener(controller)

    # Signal handlers guarantee the synth is closed even on Ctrl+C.
    # Use os._exit() — sys.exit() raises SystemExit which pynput's listener
    # thread can intercept and block on macOS, leaving the process hanging.
    _shutdown_done = False

    def _shutdown(signum, frame):  # noqa: ARG001
        nonlocal _shutdown_done
        if _shutdown_done:
            return
        _shutdown_done = True
        log.info("shutting down (signal %s)...", signum)
        try:
            controller.panic()
        except Exception:  # noqa: BLE001
            pass
        try:
            listener.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            if visualizer is not None:
                visualizer.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            synth.close()
        except Exception:  # noqa: BLE001
            pass
        os._exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    try:
        signal.signal(signal.SIGTERM, _shutdown)
    except (AttributeError, ValueError):
        # SIGTERM doesn't exist on Windows; SIGINT is enough there.
        pass

    log.info(
        "keyboard-music running. mapping=%s, base_midi=%s, sustain_key=%s%s%s%s%s. "
        "Ctrl+Alt+P to panic. Ctrl+C to quit.",
        args.mapping,
        args.base_midi,
        args.sustain_key if not args.no_sustain else "disabled",
        f" soundfont={sf2.name}",
        " (sustain on by default)" if sustain_on_start else "",
        " (velocity-dynamic)" if args.velocity_dynamic else "",
        " (visualizer)" if visualizer is not None else " (headless)",
    )
    if visualizer is not None:
        # Tk must own the main thread; pynput runs on its own thread.
        listener.start()
        if args.self_test:
            _stage_note("3-listener-started", 60)
        visualizer.run()
    else:
        listener.start()
        if args.self_test:
            _stage_note("3-listener-started", 60)
        listener.join()

    # run() returns when stop() is called from another thread.
    controller.panic()
    synth.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())