#!/usr/bin/env bash
# Build a macOS executable bundle.
#
# Usage:
#   build/build.sh                  # build for current arch (default)
#   TARGET_ARCH=arm64 build/build.sh    # native Apple Silicon (build on M1)
#   TARGET_ARCH=x86_64 build/build.sh  # native Intel        (build on Intel)
#   TARGET_ARCH=universal2 build/build.sh   # universal bundle (build on M1)
#
# Output: dist/keyboard-music/

set -euo pipefail

cd "$(dirname "$0")/.."

TARGET_ARCH="${TARGET_ARCH:-$(uname -m)}"
ARCH_LABEL="$TARGET_ARCH"
case "$TARGET_ARCH" in
    arm64|x86_64) ;;
    universal2) ARCH_LABEL="universal2 (x86_64 + arm64)" ;;
    *) echo "error: TARGET_ARCH must be x86_64, arm64, or universal2 (got '$TARGET_ARCH')" >&2; exit 2 ;;
esac

# Locate Homebrew prefix. Intel installs to /usr/local, M1 to /opt/homebrew.
BREW_PREFIX="$(brew --prefix 2>/dev/null || echo /usr/local)"
case "$TARGET_ARCH" in
    x86_64)   EXPECTED_PREFIX="/usr/local" ;;
    arm64)    EXPECTED_PREFIX="/opt/homebrew" ;;
    universal2) EXPECTED_PREFIX="/opt/homebrew" ;;  # universal2 only works on M1
esac
if [ "$BREW_PREFIX" != "$EXPECTED_PREFIX" ]; then
    cat >&2 <<EOF
warning: running on $BREW_PREFIX but TARGET_ARCH=$TARGET_ARCH expects $EXPECTED_PREFIX.
         The bundled libfluidsynth will be the wrong architecture.
         Recommended: build each architecture on its native Mac.
EOF
fi

# Step 1: collect + rewrite the Homebrew dylibs (re-runs every build).
bash scripts/collect_dylibs.sh

# Step 1b: optionally prepare the bundled SoundFont. Set BUNDLE_SOUNDFONT=1
# to ship a 1.2 GB SF2 inside the bundle (no first-run download needed).
if [ "${BUNDLE_SOUNDFONT:-0}" = "1" ]; then
    bash scripts/bundle_soundfont.sh
fi

# Step 2: PyInstaller.
.venv/bin/pyinstaller build/keyboard-music.spec --noconfirm --clean

# Step 3: re-sign the bundle so ad-hoc signatures on the embedded
# Python.framework and dylibs all share the same Team ID.
codesign --force --deep --sign - dist/keyboard-music

# Report.
echo
echo "Built dist/keyboard-music/ for $ARCH_LABEL:"
du -sh dist/keyboard-music
file dist/keyboard-music/keyboard-music