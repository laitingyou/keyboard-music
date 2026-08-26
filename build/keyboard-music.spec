# PyInstaller spec for keyboard-music (macOS).
# Run:  build/build.sh              # builds for current arch
#       TARGET_ARCH=arm64 build/build.sh    # cross-arch (needs arm64 dylibs)
#       TARGET_ARCH=universal2 build/build.sh   # universal bundle (needs arm64 dylibs)

import os
import platform
import sys
from PyInstaller.utils.hooks import collect_submodules

# Architecture override via env var. Default: detect from current Python.
# Values: 'x86_64', 'arm64', 'universal2'.
TARGET_ARCH = os.environ.get("TARGET_ARCH") or platform.machine()

# Hidden imports for pynput's darwin backend + pyobjc frameworks it pulls.
# PyInstaller's static scanner misses these because pynput imports them
# dynamically based on sys.platform.
hiddenimports = []
hiddenimports += collect_submodules('pynput')
hiddenimports += [
    'pynput._util.darwin',
    'pynput._util.xorg',
    'pynput._util.win32',
    'Quartz',
    'Quartz.CoreAudio',
    'AppKit',
    'ApplicationServices',
    'CoreData',
    'Foundation',
    'CoreText',
    'objc',
    'appdirs',
]

# Resolve paths relative to the spec file. PyInstaller injects SPECPATH
# (the directory containing the spec).
SPEC_DIR = SPECPATH
print(f"[spec] TARGET_ARCH={TARGET_ARCH} SPEC_DIR={SPEC_DIR}", file=sys.stderr)

# Bundle the Homebrew dylibs we collected (libfluidsynth + its deps). The
# synth._load_library() loader checks for a libs/ folder next to the
# executable (PyInstaller onedir) or in sys._MEIPASS (onefile).
datas = [
    (os.path.join(SPEC_DIR, 'libs'), 'libs'),
    # SoundFont: only included if build/soundfonts/piano.sf2 exists
    # (created by scripts/bundle_soundfont.sh). PyInstaller skips missing
    # sources gracefully.
    (os.path.join(SPEC_DIR, 'soundfonts'), 'soundfonts'),
]

a = Analysis(
    ['../main.py'],
    pathex=['..'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy.tests', 'pytest', 'IPython', 'jupyter',
        'pandas', 'scipy', 'PIL',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='keyboard-music',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,         # CLI tool - keep terminal attached so logs/flags work
    disable_windowed_traceback=False,
    target_arch=TARGET_ARCH,
    codesign_identity='-',  # ad-hoc sign (Gatekeeper-friendly on local runs)
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='keyboard-music',
    target_arch=TARGET_ARCH,
)