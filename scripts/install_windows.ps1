# Install keyboard-music on Windows.
# Requires: PowerShell 5+, Python 3.10+.
# Tries Chocolatey first; falls back to manual install instructions.

$ErrorActionPreference = "Stop"

function Test-Python {
    try {
        $py = (Get-Command python -ErrorAction Stop).Source
    } catch {
        Write-Error "python not found on PATH. Install Python 3.10+ from https://python.org."
        exit 1
    }
    $version = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
    $parts = $version.Split('.')
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) {
        Write-Error "Python 3.10+ required (found $version)."
        exit 1
    }
}

Write-Host "==> Checking for fluid-synth..."
$fs = Get-Command fluidsynth -ErrorAction SilentlyContinue
if (-not $fs) {
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Host "==> Installing fluid-synth via Chocolatey..."
        choco install fluidsynth -y
    } else {
        Write-Host "fluid-synth not found and Chocolatey is not installed."
        Write-Host "Please install fluid-synth manually:"
        Write-Host "  1. Download from https://github.com/FluidSynth/fluidsynth/releases/latest"
        Write-Host "  2. Extract the .zip"
        Write-Host "  3. Add the bin\ folder to your PATH"
        $choice = Read-Host "Press Enter after installing manually, or 'q' to quit"
        if ($choice -eq 'q') { exit 1 }
    }
}

Test-Python

Write-Host "==> Installing keyboard-music (editable)..."
python -m pip install -e .

# Install the Claude Code skill. The destination is the same on Windows;
# PowerShell expands $HOME to the user's profile directory.
$skillDir = Join-Path $HOME ".claude\skills\keyboard-music-packaging"
New-Item -ItemType Directory -Force -Path $skillDir | Out-Null
Copy-Item -Force "skill\SKILL.md" -Destination (Join-Path $skillDir "SKILL.md")
if (Test-Path (Join-Path $HOME ".claude")) {
    Write-Host "==> Installed Claude Code skill at $skillDir"
    Write-Host "    Restart any active Claude Code session to load the skill."
} else {
    Write-Host "==> Copied Claude Code skill to $skillDir (will activate when Claude Code is installed)."
}

Write-Host ""
Write-Host "Done. To run:"
Write-Host "    keyboard-music"
Write-Host ""
Write-Host "No special permission needed on Windows."