"""SoundFont download, verification, and caching.

The default SoundFont is Salamander Grand Piano V3 by Alexander Holm
(CC-BY-3.0, ~5 MB). On first run we download it to
``~/.keyboard-music/piano.sf2``. Subsequent runs reuse the cached file.

If you'd like to use a different SoundFont, pass ``--soundfont PATH`` and
we'll skip the download entirely.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path
from typing import Optional

import requests

from errors import SoundFontError


# Salamander Grand Piano V3 (48kHz/24bit) by Alexander Holm, CC-BY-3.0.
# Hosted on freepats.zenvoid.org as a .tar.xz archive. The extracted SF2
# file is ~1.3 GB. If this is too large, pass --soundfont PATH to use any
# other SF2 (a 5–30 MB piano SF2 from musical-artifacts.com works fine).
DEFAULT_URL = (
    "https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/"
    "SalamanderGrandPiano-SF2-V3+20200602.tar.xz"
)
# Filename of the SF2 inside the .tar.xz archive (only used if the URL ends
# in .tar.xz; the extracted SF2 is renamed to ``piano.sf2`` on disk).
ARCHIVE_SF2_NAME = "SalamanderGrandPiano-V3+20200602.sf2"

# If set, the downloaded file must match this SHA-256. None disables the
# check. Compute it once with: `shasum -a 256 piano.sf2`.
EXPECTED_SHA256: Optional[str] = None

# Sanity bounds for what a piano SF2 looks like in bytes.
# The default Salamander V3 archive is ~310 MB compressed and expands to a
# ~1.3 GB single SF2 file.
EXPECTED_SIZE_MIN = 50 * 1024 * 1024
EXPECTED_SIZE_MAX = 2 * 1024 * 1024 * 1024

CHUNK_SIZE = 64 * 1024
TIMEOUT_SECONDS = 30


def cache_dir() -> Path:
    return Path.home() / ".keyboard-music"


def soundfont_path() -> Path:
    return cache_dir() / "piano.sf2"


def bundled_soundfont_path() -> Optional[Path]:
    """If a SoundFont is shipped inside the PyInstaller bundle, return its
    path. Returns None if no bundled SF2 (e.g. a dev build without it).
    Lookup order: sys._MEIPASS first (PyInstaller onefile), then the
    directory next to sys.executable (onedir).
    """
    import sys as _sys

    bases = []
    meipass = getattr(_sys, "_MEIPASS", None)
    if meipass:
        bases.append(Path(meipass))
    bases.append(Path(_sys.executable).resolve().parent)
    bases.append(Path(__file__).resolve().parent)

    for base in bases:
        candidate = base / "soundfonts" / "piano.sf2"
        if candidate.exists():
            return candidate
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def _looks_valid(path: Path) -> bool:
    if not path.exists():
        return False
    size = path.stat().st_size
    return EXPECTED_SIZE_MIN <= size <= EXPECTED_SIZE_MAX


def ensure_soundfont(
    url: str = DEFAULT_URL,
    target: Optional[Path] = None,
    force: bool = False,
    progress: bool = True,
) -> Path:
    """Return the path to a cached SoundFont, downloading if necessary.

    Handles plain .sf2 downloads as well as .tar.xz archives that contain an
    .sf2 file (the canonical Salamander Grand Piano distribution is shipped
    as a .tar.xz).

    Args:
        url: Source URL if a download is required. The default downloads
            ~310 MB compressed / 1.3 GB extracted Salamander Grand Piano V3.
            For a smaller alternative, pass ``--soundfont PATH`` to point at
            any .sf2 you already have.
        target: Destination path. Defaults to ``~/.keyboard-music/piano.sf2``.
        force: Re-download even if a cached file already exists.
        progress: Print progress messages to stderr.
    """
    target = target or soundfont_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    if not force and target.exists() and _looks_valid(target):
        return target

    if progress:
        if url.endswith((".tar.xz", ".tar.bz2", ".tar.gz")):
            print(
                f"Downloading + extracting SoundFont from {url}",
                file=sys.stderr,
            )
            print(
                "  (this is ~310 MB compressed; first-run takes a minute)",
                file=sys.stderr,
            )
        else:
            print(f"Downloading SoundFont from {url}", file=sys.stderr)
        print(f"  → {target}", file=sys.stderr)

    # Use a unique partial path based on the URL so different URLs don't
    # collide in the cache directory.
    partial_name = "download-" + hashlib.sha256(url.encode()).hexdigest()[:12] + ".bin"
    partial = target.parent / partial_name
    try:
        downloaded = _download(url, partial, progress=progress)
    except requests.RequestException as e:
        partial.unlink(missing_ok=True)
        raise SoundFontError(f"Failed to download SoundFont: {e}") from e

    # If the downloaded file is an archive, extract the SF2.
    if downloaded.suffix == ".xz" or url.endswith(".tar.xz"):
        extracted = target.parent / (partial.stem + ".sf2")
        try:
            _extract_sf2_from_tarxz(downloaded, extracted, url, progress=progress)
        except Exception as e:
            downloaded.unlink(missing_ok=True)
            extracted.unlink(missing_ok=True)
            raise SoundFontError(f"Failed to extract archive: {e}") from e
        downloaded.unlink(missing_ok=True)
        downloaded = extracted
    elif downloaded.suffix == ".bz2" or url.endswith(".tar.bz2"):
        extracted = target.parent / (partial.stem + ".sf2")
        try:
            _extract_sf2_from_tarbz2(downloaded, extracted, url, progress=progress)
        except Exception as e:
            downloaded.unlink(missing_ok=True)
            extracted.unlink(missing_ok=True)
            raise SoundFontError(f"Failed to extract archive: {e}") from e
        downloaded.unlink(missing_ok=True)
        downloaded = extracted

    if not _looks_valid(downloaded):
        size = downloaded.stat().st_size if downloaded.exists() else 0
        downloaded.unlink(missing_ok=True)
        raise SoundFontError(
            f"Downloaded file is implausibly sized ({size} bytes). Aborted. "
            f"Expected between {EXPECTED_SIZE_MIN // 1024 // 1024} MB and "
            f"{EXPECTED_SIZE_MAX // 1024 // 1024} MB. Try a smaller SF2 via "
            f"--soundfont PATH."
        )

    if EXPECTED_SHA256:
        actual = sha256_file(downloaded)
        if actual.lower() != EXPECTED_SHA256.lower():
            downloaded.unlink(missing_ok=True)
            raise SoundFontError(
                f"SoundFont hash mismatch.\n"
                f"  expected: {EXPECTED_SHA256}\n"
                f"  actual:   {actual}\n"
                f"Refusing to use the file. Re-run after updating "
                f"EXPECTED_SHA256 in soundfont.py."
            )

    shutil.move(str(downloaded), str(target))
    if progress:
        size_mb = target.stat().st_size / 1024 / 1024
        print(f"  Done. {size_mb:.0f} MB cached at {target}", file=sys.stderr)
    return target


def _extract_sf2_from_tarxz(
    archive: Path, dest: Path, url: str, progress: bool
) -> None:
    """Find the .sf2 inside a .tar.xz archive and write it to ``dest``.

    Streams the archive to avoid loading everything into memory.
    """
    if progress:
        print("  Extracting...", file=sys.stderr)
    # lzma handles .xz on its own; tarfile reads the inner tar stream.
    import lzma
    import tarfile

    expected_name = ARCHIVE_SF2_NAME if "SalamanderGrandPiano" in url else None
    with lzma.open(archive, "rb") as xz:
        with tarfile.open(fileobj=xz, mode="r|") as tar:
            for member in tar:
                if member.isfile() and member.name.endswith(".sf2"):
                    if expected_name is None or member.name.endswith(expected_name):
                        with tar.extractfile(member) as src, dest.open("wb") as out:
                            shutil.copyfileobj(src, out)
                        return
    raise SoundFontError(f"No .sf2 file found inside {archive.name}")


def _extract_sf2_from_tarbz2(
    archive: Path, dest: Path, url: str, progress: bool
) -> None:
    if progress:
        print("  Extracting...", file=sys.stderr)
    import bz2
    import tarfile

    expected_name = ARCHIVE_SF2_NAME if "SalamanderGrandPiano" in url else None
    with bz2.open(archive, "rb") as bz:
        with tarfile.open(fileobj=bz, mode="r|") as tar:
            for member in tar:
                if member.isfile() and member.name.endswith(".sf2"):
                    if expected_name is None or member.name.endswith(expected_name):
                        with tar.extractfile(member) as src, dest.open("wb") as out:
                            shutil.copyfileobj(src, out)
                        return
    raise SoundFontError(f"No .sf2 file found inside {archive.name}")


def _download(url: str, dest: Path, progress: bool) -> Path:
    with requests.get(url, stream=True, timeout=TIMEOUT_SECONDS) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        written = 0
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                f.write(chunk)
                written += len(chunk)
                if progress and total:
                    pct = written * 100 / total
                    sys.stderr.write(
                        f"\r  {pct:5.1f}%  "
                        f"({written / 1024 / 1024:.1f} / "
                        f"{total / 1024 / 1024:.1f} MB)"
                    )
                    sys.stderr.flush()
        if progress:
            sys.stderr.write("\n")
    return dest