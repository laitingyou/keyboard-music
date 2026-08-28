"""FluidSynth wrapper: low-latency piano playback via SoundFont.

Uses ctypes to load the native ``libfluidsynth`` directly — there is no
maintained Python wrapper as of 2026 (the ``fluidsynth`` and ``pyfluidsynth``
PyPI packages have been Python 2-only for years).

Native library install instructions:
  - macOS:   ``brew install fluid-synth``
  - Windows: ``choco install fluidsynth`` (or download from
             https://github.com/FluidSynth/fluidsynth/releases and add bin/ to PATH)
  - Linux:   ``apt install fluidsynth`` (or distro equivalent)
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
import threading
from pathlib import Path
from typing import Optional

from errors import FluidSynthInitError


# --- libfluidsynth ctypes bindings --------------------------------------


_LIB = None  # loaded lazily on first PianoSynth() instantiation


def _bundled_lib_dir() -> Optional[str]:
    """Directory holding bundled native libs (PyInstaller builds), if any."""
    # PyInstaller onefile extracts to sys._MEIPASS; onedir uses exec dir.
    import glob

    for base in (
        getattr(sys, "_MEIPASS", None),
        os.path.dirname(os.path.abspath(sys.argv[0])),
        os.path.dirname(os.path.abspath(sys.executable)),
    ):
        if not base:
            continue
        lib_dir = os.path.join(base, "libs")
        if os.path.isdir(lib_dir) and glob.glob(os.path.join(lib_dir, "libfluidsynth*")):
            return lib_dir
    return None


def _load_library():
    """Locate and load libfluidsynth across platforms. Idempotent."""
    global _LIB
    if _LIB is not None:
        return _LIB
    candidates = []
    if sys.platform == "darwin":
        candidates = ["libfluidsynth.dylib", "libfluidsynth.3.dylib",
                      "libfluidsynth.2.dylib", "libfluidsynth.1.dylib"]
    elif sys.platform == "win32":
        candidates = ["libfluidsynth-3.dll", "libfluidsynth-2.dll",
                      "libfluidsynth-1.dll", "fluidsynth.dll", "libfluidsynth.dll"]
    else:
        candidates = ["libfluidsynth.so.3", "libfluidsynth.so.2",
                      "libfluidsynth.so.1", "libfluidsynth.so"]

    last_err: Optional[OSError] = None
    attempts = []

    # Bundled libs first (PyInstaller builds ship their own copies).
    bundled = _bundled_lib_dir()
    if bundled:
        for name in candidates:
            attempts.append(os.path.join(bundled, name))

    # Then system-wide lookup.
    for name in candidates:
        found = ctypes.util.find_library(
            name.replace(".so", "").replace(".dylib", "").replace(".dll", "")
        )
        if found:
            attempts.append(found)
        attempts.append(name)

    for path in attempts:
        try:
            _LIB = ctypes.CDLL(path)
            break
        except OSError as e:
            last_err = e
            continue

    if _LIB is None:
        raise FluidSynthInitError(
            "Could not locate libfluidsynth. Install it:\n"
            "  macOS:   brew install fluid-synth\n"
            "  Windows: choco install fluidsynth\n"
            "  Linux:   apt install fluidsynth  (or distro equivalent)"
            + (f"\n(last error: {last_err})" if last_err else "")
        )

    # settings.h
    _LIB.new_fluid_settings.argtypes = []
    _LIB.new_fluid_settings.restype = ctypes.c_void_p
    _LIB.delete_fluid_settings.argtypes = [ctypes.c_void_p]
    _LIB.delete_fluid_settings.restype = None
    _LIB.fluid_settings_setstr.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
    _LIB.fluid_settings_setstr.restype = ctypes.c_int
    _LIB.fluid_settings_setint.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    _LIB.fluid_settings_setint.restype = ctypes.c_int
    _LIB.fluid_settings_setnum.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_double]
    _LIB.fluid_settings_setnum.restype = ctypes.c_int

    # synth.h
    _LIB.new_fluid_synth.argtypes = [ctypes.c_void_p]
    _LIB.new_fluid_synth.restype = ctypes.c_void_p
    _LIB.delete_fluid_synth.argtypes = [ctypes.c_void_p]
    _LIB.delete_fluid_synth.restype = None
    _LIB.fluid_synth_sfload.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    _LIB.fluid_synth_sfload.restype = ctypes.c_int
    _LIB.fluid_synth_program_select.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
    ]
    _LIB.fluid_synth_program_select.restype = ctypes.c_int
    _LIB.fluid_synth_noteon.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _LIB.fluid_synth_noteon.restype = ctypes.c_int
    _LIB.fluid_synth_noteoff.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    _LIB.fluid_synth_noteoff.restype = ctypes.c_int
    _LIB.fluid_synth_cc.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _LIB.fluid_synth_cc.restype = ctypes.c_int

    # audio driver.h
    _LIB.new_fluid_audio_driver.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _LIB.new_fluid_audio_driver.restype = ctypes.c_void_p
    _LIB.delete_fluid_audio_driver.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _LIB.delete_fluid_audio_driver.restype = None

    return _LIB


def _cstr(value) -> bytes:
    """Encode a string to bytes (FluidSynth C API takes const char*)."""
    if isinstance(value, str):
        return value.encode("utf-8")
    return value


# --- per-platform audio driver selection --------------------------------

_DEFAULT_DRIVERS: dict[str, str] = {
    "darwin": "coreaudio",
    "win32": "wasapi",
    "linux": "alsa",
}


def _default_sample_rate() -> int:
    """Sample rate matching the system's default output device.

    The CoreAudio HAL goes silent when FluidSynth's rate disagrees with the
    device's current rate (e.g. device switched to 48 kHz by a video call or
    remote-desktop app). On macOS we ask CoreAudio for the device's actual
    rate via pure ctypes (no pyobjc dependency); elsewhere we fall back to
    44100, which WASAPI resamples fine.
    """
    if sys.platform != "darwin":
        return 44100
    try:
        ca = ctypes.CDLL(
            "/System/Library/Frameworks/CoreAudio.framework/CoreAudio"
        )

        class _Addr(ctypes.Structure):
            _fields_ = [
                ("mSelector", ctypes.c_uint32),
                ("mScope", ctypes.c_uint32),
                ("mElement", ctypes.c_uint32),
            ]

        ca.AudioObjectGetPropertyData.argtypes = [
            ctypes.c_uint32,                    # AudioObjectID
            ctypes.POINTER(_Addr),              # AudioObjectPropertyAddress
            ctypes.c_uint32,                    # qualifier size
            ctypes.c_void_p,                    # qualifier data
            ctypes.POINTER(ctypes.c_uint32),    # ioDataSize
            ctypes.c_void_p,                    # outData
        ]
        ca.AudioObjectGetPropertyData.restype = ctypes.c_int32

        # Four-char-code constants from CoreAudio headers.
        SYSTEM_OBJECT = 1
        SCOPE_GLOBAL = 0x676C6F62      # 'glob'
        ELEMENT_MAIN = 0
        DEFAULT_OUTPUT_DEVICE = 0x644F7574  # 'dOut'
        NOMINAL_SAMPLE_RATE = 0x6E737274    # 'nsrt'

        # Step 1: default output device ID.
        addr = _Addr(DEFAULT_OUTPUT_DEVICE, SCOPE_GLOBAL, ELEMENT_MAIN)
        dev = ctypes.c_uint32(0)
        size = ctypes.c_uint32(ctypes.sizeof(dev))
        st = ca.AudioObjectGetPropertyData(
            SYSTEM_OBJECT, ctypes.byref(addr), 0, None,
            ctypes.byref(size), ctypes.byref(dev),
        )
        if st != 0 or dev.value == 0:
            return 44100

        # Step 2: that device's nominal sample rate (scope is GLOBAL for
        # this property - the OUTPUT scope returns 'what', unknown property).
        addr2 = _Addr(NOMINAL_SAMPLE_RATE, SCOPE_GLOBAL, ELEMENT_MAIN)
        rate = ctypes.c_double(0.0)
        size2 = ctypes.c_uint32(ctypes.sizeof(rate))
        st = ca.AudioObjectGetPropertyData(
            dev.value, ctypes.byref(addr2), 0, None,
            ctypes.byref(size2), ctypes.byref(rate),
        )
        if st != 0 or rate.value <= 0:
            return 44100
        return int(rate.value)
    except Exception:  # noqa: BLE001 - any failure falls back to 44100
        return 44100

# Reverb preset tuned for a concert-hall feel: big room, low damp (bright
# highs that bloom), wide stereo image, generous wet mix. If you prefer a
# tight dry sound, run with --no-effects.
#
# The tail here is deliberately long: piano samples decay naturally in
# ~3-5s, and the room tail carries both single notes AND chords past their
# dry decay. Lower damp = longer, brighter tail; higher level = wetter mix.
# (Bluetooth speakers also clip quiet tails via their noise gate, so a
# louder wet mix keeps the sustain audible over BT.)
_DEFAULT_SETTINGS: list[tuple[str, str, object]] = [
    # (key, type, value) where type ∈ {"int", "num", "str"}
    # NOTE: synth.sample-rate is set separately from the probed device rate.
    ("synth.polyphony", "int", 256),
    ("synth.gain", "num", 0.9),
    ("synth.cpu-cores", "int", os.cpu_count() or 1),
    # 4th-order interpolation is the FluidSynth 2.6 default - no setting needed.
    ("synth.reverb.active", "int", 1),
    ("synth.reverb.damp", "num", 0.2),
    ("synth.reverb.room-size", "num", 1.0),
    ("synth.reverb.width", "num", 1.0),
    ("synth.reverb.level", "num", 0.72),
    ("synth.chorus.active", "int", 1),
    ("synth.chorus.depth", "num", 1.5),
    ("synth.chorus.speed", "num", 0.25),
    ("synth.chorus.nr", "int", 3),
    ("synth.chorus.level", "num", 0.25),
]


def _audio_driver() -> Optional[str]:
    return _DEFAULT_DRIVERS.get(sys.platform)


# --- high-level wrapper -------------------------------------------------


class PianoSynth:
    """Thread-safe libfluidsynth wrapper configured for low-latency piano playback."""

    def __init__(
        self,
        soundfont_path: Path,
        driver: Optional[str] = None,
        gain: float = 0.9,
        polyphony: int = 256,
        sample_rate: Optional[int] = None,
        no_effects: bool = False,
    ):
        self._lock = threading.Lock()
        self._settings: Optional[ctypes.c_void_p] = None
        self._synth: Optional[ctypes.c_void_p] = None
        self._audio: Optional[ctypes.c_void_p] = None
        self._sfid: Optional[int] = None
        self.sample_rate: int = sample_rate if sample_rate else _default_sample_rate()

        # Lazy-load libfluidsynth; raises FluidSynthInitError if not installed.
        _load_library()

        try:
            self._settings = _LIB.new_fluid_settings()
            if not self._settings:
                raise FluidSynthInitError("new_fluid_settings() returned NULL")
        except FluidSynthInitError:
            raise
        except Exception as e:
            raise FluidSynthInitError(f"Failed to create FluidSettings: {e}") from e

        # Apply settings. NOTE: audio.period-size / audio.periods are
        # deliberately NOT forced - tiny buffers (64x2) silently kill CoreAudio
        # output at 48 kHz. FluidSynth's own defaults are safe everywhere.
        for key, kind, value in _DEFAULT_SETTINGS:
            # Skip effects settings if no_effects was requested.
            if no_effects and ("reverb" in key or "chorus" in key):
                continue
            self._set(key, kind, value)
        self._set("synth.gain", "num", gain)
        self._set("synth.polyphony", "int", polyphony)
        self._set("synth.sample-rate", "num", float(self.sample_rate))

        # Audio driver selection (must happen before new_fluid_synth? Actually
        # the synth reads the audio driver at new_fluid_audio_driver time).
        chosen_driver = driver or _audio_driver()
        if chosen_driver:
            self._set("audio.driver", "str", chosen_driver)

        try:
            self._synth = _LIB.new_fluid_synth(self._settings)
            if not self._synth:
                raise FluidSynthInitError("new_fluid_synth() returned NULL")
        except FluidSynthInitError:
            self._cleanup_settings()
            raise
        except Exception as e:
            self._cleanup_settings()
            raise FluidSynthInitError(f"Failed to create FluidSynth: {e}") from e

        try:
            sfid = _LIB.fluid_synth_sfload(self._synth, _cstr(str(soundfont_path)), 1)
            if sfid < 0:
                raise FluidSynthInitError(f"sfload returned {sfid}")
            self._sfid = sfid
        except FluidSynthInitError:
            self._cleanup_pre_audio()
            raise
        except Exception as e:
            self._cleanup_pre_audio()
            raise FluidSynthInitError(
                f"Failed to load SoundFont at {soundfont_path}: {e}"
            ) from e

        # Select grand piano preset (channel 0, bank 0, program 0).
        _LIB.fluid_synth_program_select(self._synth, 0, self._sfid, 0, 0)

        # Start audio driver (must be last).
        try:
            self._audio = _LIB.new_fluid_audio_driver(self._settings, self._synth)
            if not self._audio:
                raise FluidSynthInitError(
                    f"new_fluid_audio_driver returned NULL (driver={chosen_driver!r}). "
                    f"Is libfluidsynth installed?"
                )
        except FluidSynthInitError:
            self._cleanup_pre_audio()
            raise
        except Exception as e:
            self._cleanup_pre_audio()
            raise FluidSynthInitError(
                f"Failed to start FluidSynth audio driver {chosen_driver!r}: {e}"
            ) from e

    # --- ctypes helpers --------------------------------------------------

    def _set(self, key: str, kind: str, value: object) -> None:
        if kind == "int":
            fn = _LIB.fluid_settings_setint
        elif kind == "num":
            fn = _LIB.fluid_settings_setnum
        else:
            fn = _LIB.fluid_settings_setstr
            value = _cstr(value)
        try:
            if kind == "str":
                fn(self._settings, _cstr(key), value)
            elif kind == "int":
                fn(self._settings, _cstr(key), int(value))
            else:
                fn(self._settings, _cstr(key), float(value))
        except Exception as e:  # noqa: BLE001
            print(
                f"warning: failed to apply FluidSynth setting {key}={value}: {e}",
                file=sys.stderr,
            )

    def _cleanup_pre_audio(self) -> None:
        if self._synth:
            _LIB.delete_fluid_synth(self._synth)
            self._synth = None
        self._cleanup_settings()

    def _cleanup_settings(self) -> None:
        if self._settings:
            _LIB.delete_fluid_settings(self._settings)
            self._settings = None

    # --- public API ------------------------------------------------------

    def note_on(self, midi: int, velocity: int = 100) -> None:
        if not 0 <= midi <= 127 or not self._synth:
            return
        with self._lock:
            _LIB.fluid_synth_noteon(self._synth, 0, midi, velocity)

    def note_off(self, midi: int) -> None:
        if not 0 <= midi <= 127 or not self._synth:
            return
        with self._lock:
            _LIB.fluid_synth_noteoff(self._synth, 0, midi)

    def panic(self) -> None:
        if not self._synth:
            return
        with self._lock:
            for ch in range(16):
                _LIB.fluid_synth_cc(self._synth, ch, 123, 0)
                for note in range(128):
                    _LIB.fluid_synth_noteoff(self._synth, ch, note)

    def close(self) -> None:
        with self._lock:
            # Order matters: audio driver → synth → settings.
            if self._audio and self._settings:
                _LIB.delete_fluid_audio_driver(self._audio, self._settings)
            self._audio = None
            if self._synth:
                _LIB.delete_fluid_synth(self._synth)
            self._synth = None
            self._cleanup_settings()