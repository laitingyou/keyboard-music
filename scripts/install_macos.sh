#!/usr/bin/env bash
# Install keyboard-music on macOS.
# Requires: Homebrew (https://brew.sh), Python 3.10+.

set -euo pipefail

if ! command -v brew >/dev/null 2>&1; then
    echo "error: Homebrew is required. Install from https://brew.sh" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 not found. Install via 'brew install python' or python.org." >&2
    exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="$(echo "$PY_VERSION" | cut -d. -f1)"
PY_MINOR="$(echo "$PY_VERSION" | cut -d. -f2)"
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "error: Python 3.10+ required (found $PY_VERSION)." >&2
    exit 1
fi

echo "==> Installing fluid-synth via Homebrew..."
brew install fluid-synth

echo "==> Installing keyboard-music (editable)..."
python3 -m pip install --user -e .

echo
echo "Done. To run:"
    echo "    keyboard-music"
echo
echo "On first launch macOS will prompt you to grant Accessibility"
echo "permission to your terminal. After granting, the tool will work."
echo "If the prompt doesn't appear, use:"
echo "    keyboard-music --wait-permission"