---
name: keyboard-music-packaging
description: Help with installing dependencies, building, and packaging the keyboard-music Python tool (a keyboard-to-piano background process using FluidSynth + SoundFont). Use when the user asks to "package", "build", "bundle", "install", or "distribute" keyboard-music, or needs help with the standalone macOS executable, library dependencies, or SoundFont download. Also use when the user asks about cross-architecture (Intel / Apple Silicon / universal2) builds of keyboard-music.
---

# keyboard-music packaging helper

You are a packaging assistant for the [keyboard-music](https://github.com/laitingyou/keyboard-music) project — a cross-platform Python tool that listens to keyboard input and plays piano notes through FluidSynth + a SoundFont.

The user's project directory can be identified by the presence of `pyproject.toml`, `scripts/install_*.sh/.ps1`, and `build/build.sh`. All commands below assume the user's CWD is that root unless noted.

## Install dependencies

### macOS

```bash
bash scripts/install_macos.sh
```

Homebrew installs `fluid-synth`; pip installs the Python package in editable mode. Requires Homebrew (https://brew.sh) and Python 3.10+.

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
```

Tries Chocolatey first; falls back to manual install instructions.

### Linux

```bash
sudo apt install fluidsynth
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Run from source

```bash
python main.py
```

On first run, downloads ~310 MB SoundFont and extracts it to `~/.keyboard-music/piano.sf2`. The tool prefers a bundled SoundFont if present (see `BUNDLE_SOUNDFONT=1` below).

Common flags:
- `--list-keys` — print the key→MIDI mapping table and exit
- `--self-test` — play one test note at each startup stage
- `--wait-permission` — macOS: poll for Accessibility grant
- `--verbose` / `-v` — debug logging

## Build a standalone executable (macOS)

```bash
bash build/build.sh                    # default arch, ~41 MB
TARGET_ARCH=arm64 build/build.sh      # native M1/M2/M3 (must build on M1)
TARGET_ARCH=universal2 build/build.sh # universal bundle (must build on M1)
BUNDLE_SOUNDFONT=1 build/build.sh    # also bundle the 1.2 GB SF2 → ~1.24 GB
```

The script performs three steps:

1. **`scripts/collect_dylibs.sh`** — BFS over Homebrew's libfluidsynth transitive deps; rewrites each dylib's install names to `@loader_path/<name>` so they all resolve from one shared directory.
2. **PyInstaller** (`build/keyboard-music.spec`) — bundles Python runtime, your modules, and the rewritten `libs/` into `dist/keyboard-music/`.
3. **`codesign --deep --sign -`** — fixes Team-ID mismatches between the bootloader and the embedded `Python.framework`.

### Architecture matrix

| Target Mac | Build it on | Command |
|---|---|---|
| Intel (x86_64) | Intel Mac | `build/build.sh` |
| Apple Silicon (M1/M2/M3) | M1 Mac | `build/build.sh` |
| Universal (one bundle, both) | M1 Mac | `TARGET_ARCH=universal2 build/build.sh` |

Cross-arch builds from Intel → M1 won't work because libfluidsynth dylibs come from `/usr/local/opt` (Intel Homebrew), not `/opt/homebrew` (M1 Homebrew). The build script warns if it detects this mismatch.

### Bundle size

- Without `BUNDLE_SOUNDFONT=1`: ~41 MB. SF2 downloads on first run.
- With `BUNDLE_SFONDFONT=1`: ~1.24 GB. SF2 ships inside, zero first-run latency.

## Verify the build

```bash
ls dist/keyboard-music/                    # should have keyboard-music + _internal/
file dist/keyboard-music/keyboard-music    # Mach-O 64-bit executable
./dist/keyboard-music/keyboard-music --list-keys     # CLI smoke test
./dist/keyboard-music/keyboard-music --self-test     # audio smoke test (3 notes)
```

`--self-test` plays one note at each stage (synth init → window open → listener started). If a stage fails, you know exactly where audio died.

## Running tests

```bash
pytest tests/                # all 79 should pass
pytest tests/test_sustain.py  # individual module
```

## Troubleshooting

### No sound

1. **macOS**: Did you grant Accessibility permission? Try `python main.py --wait-permission`.
2. **System audio**: `afplay /tmp/some.wav` works on its own? If not, fix system audio first.
3. **libfluidsynth missing**: `brew install fluid-synth` / `choco install fluidsynth` / `apt install fluidsynth`.
4. **Run `--self-test`** to localize which stage fails (synth / window / listener).

### Stuck notes

Press `Ctrl + Alt + P` to panic-silence everything. If that doesn't work, kill the process.

### macOS Accessibility keeps breaking

```bash
tccutil reset Input Monitoring
tccutil reset Accessibility
```

Then re-grant in System Settings → Privacy & Security → Accessibility. Required because pynput's CGEventTap needs both Input Monitoring AND Accessibility (since macOS Catalina).

### SoundFont download fails (404 / network)

Default URL: `https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/SalamanderGrandPiano-SF2-V3+20200602.tar.xz`

Workarounds:
- Use a smaller SF2: pass `--soundfont PATH` with any piano SF2 you have
- Manually pre-place the file at `~/.keyboard-music/piano.sf2` to skip the download

### Gatekeeper (macOS first-run on a new machine)

```bash
xattr -dr com.apple.quarantine dist/keyboard-music
```

Or right-click → Open to bypass once.

### Build fails: "different Team IDs"

`codesign --force --deep --sign - dist/keyboard-music` — already in build.sh, but if you skipped it manually, run it.

## Key CLI flags

| Flag | Default | Effect |
|---|---|---|
| `--mapping {pentatonic,pentatonic_minor,chromatic}` | chromatic | Scale type |
| `--soundfont PATH` | auto-download | Use a specific SF2 |
| `--base-midi INT` | 60 (C4) | Lowest MIDI note |
| `--no-sustain-on-start` | off | Start with sustain pedal up (Shift = momentary pedal) |
| `--no-sustain` | off | Disable sustain entirely |
| `--no-effects` | off | Dry sound (no reverb/chorus) |
| `--no-visualizer` | off | Headless (no staff window) |
| `--velocity-dynamic` | off | Attack-based velocity (35 ms delay) |
| `--list-keys` | — | Print key→MIDI table and exit |
| `--self-test` | — | Play test notes at each stage |
| `--wait-permission` | — | macOS: poll for Accessibility grant |
| `--verbose` / `-v` | off | Debug logging |

## Important file paths

- `pyproject.toml` — Python package metadata, deps
- `scripts/install_macos.sh` / `install_windows.ps1` — per-platform installers
- `scripts/collect_dylibs.sh` — bundles Homebrew deps for the executable
- `scripts/bundle_soundfont.sh` — copies SF2 into `build/soundfonts/` (BUNDLE_SOUNDFONT=1)
- `build/build.sh` — main build entry point
- `build/keyboard-music.spec` — PyInstaller spec
- `build/README.md` — full build documentation
- `tests/` — 79 unit tests
- `LICENSE` — MIT
- `README.md` — user-facing docs

## What NOT to commit

`.gitignore` already excludes:
- `dist/` (build output, 41 MB or 1.24 GB)
- `build/libs/`, `build/soundfonts/` (collected dylibs + SF2)
- `build/keyboard-music/` (PyInstaller intermediate)
- `.venv/`, `__pycache__/`, `.pytest_cache/`

Also do NOT commit:
- Your local `~/.keyboard-music/piano.sf2` (1.2 GB cache) — it's a runtime artifact, not source

## When the user wants to release

1. Update version in `pyproject.toml`
2. Run `BUNDLE_SOUNDFONT=1 build/build.sh`
3. Zip `dist/keyboard-music/` → `dist/keyboard-music.zip`
4. Create a GitHub Release with the zip attached as `keyboard-music-v0.X.Y.zip`
5. Reference the release in README

## When the user wants to add a new feature

1. Run tests first: `pytest tests/` should be green
2. Add new tests under `tests/`
3. Keep public API stable unless the change requires it
4. See `CONTRIBUTING.md` for PR workflow

## When the user wants to debug a hard issue

Check these first:
- Is the user on the latest commit? (`git pull`)
- Does the failure repro on a clean venv? (`python3 -m venv /tmp/clean && source /tmp/clean/bin/activate && pip install -e .`)
- Does `--self-test` show which stage fails?
- Does the bundled executable reproduce (vs source)?