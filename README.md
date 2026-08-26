# keyboard-music

Play piano notes while you type. Cross-platform (macOS + Windows), Python background process that hooks the keyboard, maps each key to a piano note, and plays it through a realistic piano SoundFont.

## Features

- **All keys map to notes** — every printable key, plus Space, Enter, Backspace, Tab, Esc, F1–F12.
- **Position-based mapping** — lower-left keys are lower-pitched, upper-right keys are higher-pitched.
- **Two musical modes**: `pentatonic` (default — any random typing sounds consonant) and `chromatic` (every key has a unique pitch for full piano feel).
- **Shift = sustain pedal** — hold Shift while playing, and released notes keep ringing until you release Shift.
- **Live staff-notation window** — a small window shows each note on a treble staff as you play (with ledger lines for notes outside the staff; auto-pages after ~24 notes). Tk-based, no extra dependencies. Disable with `--no-visualizer`.
- **Realistic piano sound** via the [Salamander Grand Piano V3](https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/) SoundFont (CC-BY-3.0, auto-downloaded as a .tar.xz archive on first run).
- **Panic hotkey** (`Ctrl + Alt + P`) for instant silence if anything gets weird.

> **Note on the bundled SoundFont**: the canonical Salamander Grand Piano V3 SF2 is ~1.3 GB extracted. The first run downloads and extracts the ~310 MB compressed archive — takes a minute or so. If that's too big, pass `--soundfont PATH` to point at any other SF2 you have (5–30 MB free piano soundfonts are widely available).

## Installation

### macOS

```bash
bash scripts/install_macos.sh
```

Requires [Homebrew](https://brew.sh) and Python 3.10+. The script:

1. Installs `fluid-synth` via Homebrew.
2. Installs the Python package in editable mode.

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
```

Requires Python 3.10+. The script will use Chocolatey if available, otherwise guide you through a manual install of FluidSynth from the [releases page](https://github.com/FluidSynth/fluidsynth/releases/latest).

### Linux

```bash
sudo apt install fluidsynth
pip install -e .
```

## Running

```bash
keyboard-music
```

On first launch the tool downloads the SoundFont (~5 MB) to `~/.keyboard-music/piano.sf2`.

### macOS Accessibility permission

macOS requires you to grant Accessibility permission for the keyboard hook to work. The tool will print instructions on the first run. Easiest workflow:

```bash
keyboard-music --wait-permission
```

This polls for the grant and auto-resumes once you toggle Accessibility on in **System Settings → Privacy & Security → Accessibility**.

### CLI flags

```
--mapping {pentatonic,pentatonic_minor,chromatic}   default: pentatonic
--soundfont PATH                                    skip auto-download; use this SF2
--sustain-key {left,right,either}                   default: either
--base-midi INT                                     default: 48 (C3). Range [0, 80]
--redownload                                        re-download the SoundFont
--no-sustain                                        disable Shift-as-sustain
--sustain-on-start                                  start with sustain pedal engaged (Shift becomes a no-op; use Ctrl+Alt+P panic to silence)
--no-effects                                        disable built-in reverb + chorus (dry sound)
--velocity-dynamic                                  attack-based velocity (fast taps loud, long holds gentle)
--no-visualizer                                     no staff-notation window (headless)
--wait-permission                                   macOS: poll for Accessibility grant
--verbose, -v                                       debug logging
--list-keys                                         print the key→MIDI table and exit
```

### Examples

```bash
# Default — pentatonic, both Shifts are sustain
keyboard-music

# Real piano feel — every key has a unique pitch
keyboard-music --mapping chromatic

# Right Shift is sustain, left Shift is for typing capitals
keyboard-music --sustain-key right

# Higher overall pitch
keyboard-music --base-midi 60
```

## How keys map to notes

The default mapping walks the keyboard left-to-right top-to-bottom. Each character key produces a note from the C major pentatonic scale (C, D, E, G, A) so any random typing sounds consonant. Special keys (Space, Enter, etc.) hit fixed anchor pitches.

```
Row:  ` 1 2 3 4 5 6 7 8 9 0 - =
Scale: C C D E E G G A A C D D   (pentatonic, base = C3)

Row:   q w e r t y u i o p [ ] \
Scale: D D E G G A A C D D E G

Row:   a s d f g h j k l ; '
Scale: A A C D D E G G A C D

Row:   z x c v b n m , . /
Scale: E G A C D E G A C D
```

Use `keyboard-music --list-keys` to see the exact MIDI table for your `--mapping` and `--base-midi`.

## Sustain behavior

The Shift key acts like a real piano's sustain pedal:

- **Press a key** → note starts ringing.
- **Press Shift, then release the key** → the note keeps ringing (state goes to `SUSTAINED`).
- **Release Shift** → all sustained notes stop. Keys you are still physically holding continue to ring until you release them.

`--sustain-on-start` flips the default: every released note keeps ringing. In this mode Shift is intentionally a no-op (the pedal stays down forever). To silence what's accumulated, hit the panic hotkey `Ctrl + Alt + P`.

`Ctrl + Alt + P` triggers a **panic** — every note is silenced immediately. Use this if you suspect a stuck note.

## Transpose (octave-shift)

The keyboard covers 4 octaves by default. To reach lower or higher registers:

- **↑ (Up arrow)** — shift the keyboard up one octave.
- **↓ (Down arrow)** — shift the keyboard down one octave.

The current shift is logged on stderr (`transpose: +12 semitones`). Press the arrows repeatedly to stack shifts; combine with `--base-midi` to set the starting register. Notes that are already ringing when you transpose are released at their original MIDI, so no stuck notes.

## Sound realism

The default config is tuned for realism on top of the Salamander Grand Piano V3 samples (88 keys × 16 velocity layers, 48 kHz / 24-bit — the best free piano SF2):

- **Velocity dynamics**: every note gets a ±14 velocity jitter by default, mimicking how a real player never hits a key twice with the same force. For attack-based dynamics (fast taps loud, long holds gentle), add `--velocity-dynamic` (costs a 35 ms probe delay — imperceptible, real piano actions are similar).
- **Reverb**: a concert-hall preset (room-size 0.85, damp 0.3, level 0.5) — big, bright, wide. `--no-effects` disables reverb/chorus entirely for a dry studio sound.
- **Chorus**: 3 voices, depth 1.5, level 0.25 — subtle stereo widening.

Tweak further by editing `_DEFAULT_SETTINGS` in `synth.py`:

| Setting | Default | Effect |
|---|---|---|
| `synth.reverb.room-size` | 0.85 | bigger = longer hall |
| `synth.reverb.damp` | 0.3 | lower = brighter highs |
| `synth.reverb.level` | 0.5 | wet/dry mix |
| `synth.chorus.nr` | 3 | voice count (more = thicker) |
| `synth.chorus.depth` | 1.5 | modulation depth |

To go beyond the free ceiling (Salamander is it), run the `--midi-out` mode against a pro host — see below.

## MIDI-out mode (pro-grade piano)

If you have Logic, GarageBand, MainStage, Pianoteq, or Kontakt, the tool can forward keystrokes as real MIDI instead of using FluidSynth:

```
(TODO — not yet implemented)
```

## Building a standalone executable (macOS)

See [`build/README.md`](build/README.md). The result is a `dist/keyboard-music/` directory you can copy anywhere and run without installing Python or Homebrew.

## Troubleshooting

### No sound

1. **macOS**: Did you grant Accessibility permission? Try `keyboard-music --wait-permission` to see clearer error output.
2. **System audio**: Is your output device working? FluidSynth routes through the default OS audio driver.
3. **libfluidsynth missing**: install it via your package manager (Homebrew, Chocolatey, apt).

### Stuck notes

1. Press `Ctrl + Alt + P` to panic-silence everything.
2. If that doesn't work, kill the process: `pkill -f keyboard-music` (macOS/Linux) or close the PowerShell window (Windows).
3. Report a bug with the steps to reproduce.

### Latency / crackling

Default settings aim for ~1.5 ms latency (period-size 64). If you hear crackling on a slow machine, edit `synth.py` and bump `period-size` to 128 or 256. Reinstalling is unnecessary — `pip install -e .` picks up changes immediately.

### Wrong SoundFont

```bash
keyboard-music --soundfont /path/to/your.sf2
```

### Re-download SoundFont

```bash
keyboard-music --redownload
```

Or delete `~/.keyboard-music/piano.sf2` and the next launch will fetch a fresh copy.

## Architecture

| File | Role |
|---|---|
| `main.py` | CLI entry, signal handling, lifecycle |
| `synth.py` | FluidSynth wrapper, low-latency settings, thread-safe note API |
| `mapping.py` | QWERTY → MIDI table (chromatic + pentatonic modes) |
| `sustain.py` | Per-key state machine (IDLE / ACTIVE / SUSTAINED) |
| `listener.py` | pynput adapter, panic hotkey tracking |
| `soundfont.py` | Auto-download Salamander SF2, SHA-256 check, atomic cache |
| `permissions.py` | macOS Accessibility detection + wait-for-grant helper |
| `errors.py` | Exception hierarchy |

## License

MIT.

The bundled SoundFont (Salamander Grand Piano V3) is CC-BY-3.0 by Alexander Holm.