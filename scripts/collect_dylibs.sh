#!/usr/bin/env bash
# Collect libfluidsynth + transitive Homebrew deps into build/libs/, rewriting
# install names to @loader_path so the PyInstaller bundle is self-contained.
#
# Files are stored under their canonical (symlink) names - e.g.
# libfluidsynth.3.dylib, not the versioned libfluidsynth.3.6.0.dylib - because
# that's both what the loader asks for and what dependents reference.
set -euo pipefail

cd "$(dirname "$0")/.."

OUT="build/libs"
rm -rf "$OUT"
mkdir -p "$OUT"

ROOT="/usr/local/opt/fluid-synth/lib/libfluidsynth.dylib"
if [ ! -e "$ROOT" ]; then
    echo "error: $ROOT not found. brew install fluid-synth first." >&2
    exit 1
fi

# BFS using a sentinel file to track seen reals.
SEEN="$(mktemp)"
trap 'rm -f "$SEEN"' EXIT

TODO=("$ROOT")

while [ ${#TODO[@]} -gt 0 ]; do
    LIB="${TODO[0]}"
    TODO=("${TODO[@]:1}")
    REAL=$(realpath "$LIB")
    CANON=$(basename "$LIB")
    if grep -Fxq "$REAL" "$SEEN"; then continue; fi
    echo "$REAL" >> "$SEEN"

    cp "$REAL" "$OUT/$CANON"
    chmod u+w "$OUT/$CANON"

    while IFS= read -r dep; do
        case "$dep" in
            /System/*|/usr/lib/*) ;;
            *) TODO+=("$dep") ;;
        esac
    done < <(otool -L "$REAL" 2>/dev/null | tail -n +2 | awk '{print $1}')
done

for f in "$OUT"/*.dylib; do
    install_name_tool -id "@loader_path/$(basename "$f")" "$f"
    while IFS= read -r dep; do
        DEPNAME=$(basename "$dep")
        if [ -e "$OUT/$DEPNAME" ]; then
            install_name_tool -change "$dep" "@loader_path/$DEPNAME" "$f" 2>/dev/null || true
        fi
    done < <(otool -L "$f" | tail -n +2 | awk '{print $1}')
    codesign --force --sign - "$f" >/dev/null 2>&1 || true
done

echo "Bundled $(ls "$OUT" | wc -l | tr -d ' ') dylibs into $OUT:"
ls "$OUT"