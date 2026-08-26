# Building the standalone executable

`build/build.sh` produces `dist/keyboard-music/`, a self-contained macOS bundle — no Homebrew, no Python install needed on the target machine.

## Architectures

| Target machine | Build it with | Notes |
|---|---|---|
| Intel Mac (x86_64) | `build/build.sh` (default on Intel) | Native, no Rosetta. |
| Apple Silicon (M1/M2/M3) | Run on M1: `build/build.sh` | Native arm64. |
| Either (universal bundle) | Run on M1: `TARGET_ARCH=universal2 build/build.sh` | One bundle for both; needs /opt/homebrew present. |

The Python interpreter in this repo's `.venv` is already a `universal2` Mach-O
binary, so the same venv builds for either architecture — only the bundled
native libraries change.

## How it was built

```bash
# On the Mac that matches TARGET_ARCH:
brew install fluid-synth            # once per machine
build/build.sh                       # default arch
# or:
TARGET_ARCH=arm64 build/build.sh
TARGET_ARCH=universal2 build/build.sh
```

Internally the script runs three steps:

1. **`scripts/collect_dylibs.sh`** — BFS over Homebrew's libfluidsynth transitive deps; rewrite each dylib's install names to `@loader_path/<name>` so they all resolve from one shared directory.
2. **PyInstaller** (`build/keyboard-music.spec`) — bundles the Python runtime, your modules, and the rewritten `libs/` into `dist/keyboard-music/`. Hidden imports cover `pynput`'s dynamic darwin backend and the Quartz/AppKit wrappers it uses.
3. **`codesign --deep --sign -`** — fixes Team-ID mismatches between the bootloader and the nested `Python.framework`.

## What's inside `dist/keyboard-music/`

- `keyboard-music` — launcher binary (4.7 MB)
- `_internal/` — Python runtime + bundled deps (~36 MB)
  - `libs/` — 11 dylibs, all `@loader_path`-resolved
  - `Python.framework/`, bytecode, Tk data, etc.
  - `soundfonts/piano.sf2` — **optional**: the 1.2 GB Salamander Grand Piano V3 SF2,
    present only if you built with `BUNDLE_SOUNDFONT=1`. When present, the
    tool uses it directly with no first-run download needed.

Total: ~41 MB without SF2, ~1.24 GB with `BUNDLE_SOUNDFONT=1`.

## Bundling the SoundFont

By default the executable does NOT include the SoundFont — on first run
it downloads ~310 MB and extracts to `~/.keyboard-music/piano.sf2`. To ship
the SF2 inside the bundle (no download on first run):

```bash
BUNDLE_SOUNDFONT=1 build/build.sh
```

This copies the file from `~/.keyboard-music/piano.sf2` (or downloads it
if absent) into `build/soundfonts/piano.sf2` before PyInstaller bundles it.
The runtime prefers the bundled copy, falls back to the user cache, and
only downloads if neither is present.

## Running

```bash
cd dist/keyboard-music
./keyboard-music --list-keys        # CLI flags work
./keyboard-music                     # interactive
./keyboard-music --no-visualizer     # headless
```

## Distributing

Zip the `dist/keyboard-music/` directory and share. Recipients don't need
to install anything. They still need to grant Accessibility permission to
their terminal app (System Settings → Privacy & Security → Accessibility)
the first time they run it.

## Cross-arch notes

- **M1 users**: just `build/build.sh` on your M1. You'll get a native arm64 bundle.
- **Intel users**: same command gives you x86_64. To ship to M1 users too, build a **second** bundle on the M1 and ship both (or use `TARGET_ARCH=universal2` on M1).
- **Can't cross-build** from Intel → M1 because libfluidsynth's dylibs come from `/usr/local/opt` (Intel Homebrew); the arm64 versions live at `/opt/homebrew` on M1. The script warns if it detects this mismatch.

## Limitations

- **macOS only** for now. Windows/Linux would need their own
  `collect_dylibs.sh` equivalents and a different executable layout.
- **Ad-hoc signed**, not notarized. macOS may show a Gatekeeper warning
  on first run (right-click → Open, or `xattr -dr com.apple.quarantine`).
  For public distribution, sign with a real Developer ID and notarize.