"""Unit tests for soundfont.py — using mocked HTTP responses."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from errors import SoundFontError
from soundfont import (
    EXPECTED_SIZE_MAX,
    EXPECTED_SIZE_MIN,
    cache_dir,
    ensure_soundfont,
    sha256_file,
    soundfont_path,
)


# --- helpers ------------------------------------------------------------


class FakeResponse:
    """Stand-in for requests.Response that supports context-manager protocol."""

    def __init__(self, chunks, total_length):
        self._chunks = chunks
        self.headers = {"content-length": str(total_length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        for c in self._chunks:
            yield c


# --- pure helpers ------------------------------------------------------


class TestHelpers:
    def test_cache_dir(self):
        assert cache_dir() == Path.home() / ".keyboard-music"

    def test_soundfont_path(self):
        assert soundfont_path() == cache_dir() / "piano.sf2"

    def test_sha256_hello_world(self, tmp_path):
        f = tmp_path / "h.bin"
        f.write_bytes(b"hello world")
        # Known SHA-256 of "hello world".
        assert sha256_file(f) == (
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        )


# --- cache hit ---------------------------------------------------------


class TestCacheHit:
    _URL = "https://example.com/piano.sf2"

    def test_existing_valid_file_returned_without_download(self, tmp_path):
        target = tmp_path / "piano.sf2"
        # 100 MB: within [EXPECTED_SIZE_MIN, EXPECTED_SIZE_MAX].
        target.write_bytes(b"x" * (100 * 1024 * 1024))

        with patch("soundfont.requests.get") as mock_get:
            result = ensure_soundfont(url=self._URL, target=target, progress=False)
        assert result == target
        mock_get.assert_not_called()

    def test_existing_too_small_redownloads(self, tmp_path):
        target = tmp_path / "piano.sf2"
        target.write_bytes(b"tiny")  # below EXPECTED_SIZE_MIN

        bad_response = FakeResponse([], 0)
        with patch("soundfont.requests.get", return_value=bad_response):
            with pytest.raises(SoundFontError) as exc:
                ensure_soundfont(url=self._URL, target=target, progress=False)
            assert "implausibly sized" in str(exc.value).lower()


# --- download ----------------------------------------------------------


class TestDownload:
    _URL = "https://example.com/piano.sf2"

    def _make_fake_sf2(self):
        chunk_size = 64 * 1024
        n_chunks = 1600  # 1600 * 64 KB = ~100 MB
        chunks = [b"x" * chunk_size for _ in range(n_chunks)]
        return chunks, chunk_size * n_chunks

    def test_successful_download_writes_file(self, tmp_path):
        target = tmp_path / "piano.sf2"
        chunks, total = self._make_fake_sf2()
        response = FakeResponse(chunks, total)
        with patch("soundfont.requests.get", return_value=response):
            result = ensure_soundfont(
                url=self._URL, target=target, progress=False, force=True
            )
        assert result.exists()
        assert result.stat().st_size == total

    def test_partial_file_cleaned_on_http_error(self, tmp_path):
        target = tmp_path / "piano.sf2"

        def boom(*a, **kw):
            raise requests.HTTPError("simulated 404")

        with patch("soundfont.requests.get", side_effect=boom):
            with pytest.raises(SoundFontError):
                ensure_soundfont(
                    url=self._URL, target=target, progress=False, force=True
                )
        leftovers = list(target.parent.iterdir())
        assert all(not p.name.startswith("download-") for p in leftovers)

    def test_size_below_min_raises(self, tmp_path):
        target = tmp_path / "piano.sf2"
        response = FakeResponse([b"x" * 1024], 1024)  # 1 KB
        with patch("soundfont.requests.get", return_value=response):
            with pytest.raises(SoundFontError):
                ensure_soundfont(
                    url=self._URL, target=target, progress=False, force=True
                )
        assert not target.exists()

    def test_size_above_max_raises(self, tmp_path):
        target = tmp_path / "piano.sf2"
        chunk_size = 64 * 1024
        response = FakeResponse([b"x" * chunk_size], 3 * 1024 * 1024 * 1024)
        with patch("soundfont.requests.get", return_value=response):
            with pytest.raises(SoundFontError):
                ensure_soundfont(
                    url=self._URL, target=target, progress=False, force=True
                )

    def test_force_redownloads_even_when_cached(self, tmp_path):
        target = tmp_path / "piano.sf2"
        target.write_bytes(b"x" * (100 * 1024 * 1024))  # valid cache

        chunks, total = self._make_fake_sf2()
        response = FakeResponse(chunks, total)
        with patch("soundfont.requests.get", return_value=response):
            result = ensure_soundfont(
                url=self._URL, target=target, progress=False, force=True
            )
        assert result.stat().st_size == total


# --- expected sha256 ---------------------------------------------------


class TestExpectedSHA256:
    _URL = "https://example.com/piano.sf2"

    def test_hash_mismatch_rejects_file(self, tmp_path, monkeypatch):
        import hashlib
        payload = b"x" * (100 * 1024 * 1024)
        real_hash = hashlib.sha256(payload).hexdigest()

        target = tmp_path / "piano.sf2"
        response = FakeResponse([payload], len(payload))

        monkeypatch.setattr("soundfont.EXPECTED_SHA256", "0" * 64)

        with patch("soundfont.requests.get", return_value=response):
            with pytest.raises(SoundFontError) as exc:
                ensure_soundfont(
                    url=self._URL, target=target, progress=False, force=True
                )
            assert "hash mismatch" in str(exc.value).lower()
        assert not target.exists()