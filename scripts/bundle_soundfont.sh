#!/usr/bin/env bash
# Download the Salamander Grand Piano V3 SoundFont into build/soundfonts/ so
# the next PyInstaller build ships it inside the bundle. Re-uses the
# cached file under ~/.keyboard-music/piano.sf2 if present.
#
# Run once before build:
#   bash scripts/bundle_soundfont.sh
#
# Or set BUNDLE_SOUNDFONT=1 in build.sh and it'll run automatically.

set -euo pipefail

cd "$(dirname "$0")/.."

OUT_DIR="build/soundfonts"
OUT="$OUT_DIR/piano.sf2"
mkdir -p "$OUT_DIR"

if [ -e "$OUT" ]; then
    echo "Already present: $OUT ($(du -h "$OUT" | cut -f1))"
    exit 0
fi

CACHE="$HOME/.keyboard-music/piano.sf2"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

if [ -e "$CACHE" ]; then
    echo "Copying cached SoundFont from $CACHE"
    cp "$CACHE" "$OUT"
else
    URL="https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/SalamanderGrandPiano-SF2-V3+20200602.tar.xz"
    ARCHIVE="$TMPDIR/sal.tar.xz"
    EXTRACTED="$TMPDIR/SalamanderGrandPiano-SF2-V3+20200602"
    echo "Downloading SoundFont (310 MB, ~1 min)..."
    curl -fsSL -o "$ARCHIVE" "$URL"
    echo "Extracting..."
    tar -xJf "$ARCHIVE" -C "$TMPDIR"
    SF2="$EXTRACTED/SalamanderGrandPiano-V3+20200602.sf2"
    if [ ! -e "$SF2" ]; then
        echo "error: extracted archive does not contain expected SF2 file" >&2
        exit 1
    fi
    cp "$SF2" "$OUT"
fi

echo "Bundled: $OUT ($(du -h "$OUT" | cut -f1))"