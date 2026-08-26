# Contributing to keyboard-music

Thanks for taking an interest! Bug reports, feature ideas, and pull requests
are all welcome.

## Reporting bugs

Open a GitHub issue. Include:

- macOS version (`sw_vers`) and architecture (`uname -m`)
- Python version (`python3 --version`)
- How you ran it (`bash scripts/install_macos.sh && ./dist/.../keyboard-music`)
- The full command line and any relevant `--verbose` log output
- For audio issues, confirm `afplay ~/.keyboard-music/piano.sf2` produces
  sound — that tells us whether the bug is in the SF2 or in our code

## Pull requests

1. Fork and create a feature branch (`git checkout -b fix/sustain-pedal`).
2. Make your change. Keep the public API stable unless the change requires it.
3. Add or update tests under `tests/`. We have 79; `pytest tests/` should
   stay green and ideally grow.
4. Run `pytest tests/` locally before pushing. New code without tests
   is a tough sell.
5. Don't add new runtime dependencies without prior discussion — every
   pip dep is one more thing the bundled executable has to carry.
6. Commit with a focused message (`git commit -m "sustain: don't clear
   notes when sustain_on_start"`).
7. Open a PR against `main`.

## Adding new key mappings

`mapping.py` is a single function. Add a test alongside your change:

```python
def test_my_new_mapping(self):
    m = build_mapping("my-mode", 60)
    assert m["a"] == 60
```

## Packaging changes

If you touch `build/keyboard-music.spec`, `scripts/collect_dylibs.sh`, or
`scripts/bundle_soundfont.sh`, run a clean local build to verify:

```bash
rm -rf dist build/libs build/soundfonts
BUNDLE_SOUNDFONT=1 bash build/build.sh
```

## Code style

- Standard Python; PEP 8 for layout
- Type hints on public functions
- Comments only where the *why* isn't obvious from the code
- Default to the simplest correct thing

## Release process

There isn't a formal release process yet. New commits land on `main`; if
the bundled executable should be rebuilt, the maintainer runs
`BUNDLE_SOUNDFONT=1 build/build.sh` and uploads `dist/keyboard-music/` to
the GitHub release page.

## Questions?

Open an issue or email laitingyou@outlook.com.