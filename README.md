# Music Renamer

Music Renamer its a tool that helps you rename music files based on metadata and optionally embed synchronized lyrics and album art.

## Features

- Rename files using existing metadata (artist, title)
- Optional audio fingerprint recognition using Chromaprint / AcoustID
- Fill missing metadata for recognized tracks (date, genre, track number, etc.)
- Download and embed album artwork
- Fetch and embed synchronized lyrics (LRC)
- Supports MP3, FLAC and M4A files

## Installation

### Requirements

- Python 3.6 or newer

Core Python packages used by the project are listed in `requirements.txt`. Optional features require extra packages (see below).

Install core dependencies (recommended for full functionality):

```powershell
py -3 -m pip install -r requirements.txt
```

Install in editable mode:

```powershell
py -3 -m pip install -e .
```

Optional features can be installed using pip extras:

```powershell
# Recognition (pyacoustid)
py -3 -m pip install -e .[recognition]

# Synchronized lyrics
py -3 -m pip install -e .[lyrics]

# MusicBrainz support for improved album lookup
py -3 -m pip install -e .[musicbrainz]
```

### Virtual Environment for Development (CLI)

For developing or running the CLI, we recommend using a local virtual environment to isolate dependencies. A common name is `.venv`.

In Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -r requirements.txt
```

Once activated, run `py -3 app.py` or install in editable mode with `py -3 -m pip install -e .`.

### Chromaprint (fpcalc)

To use audio fingerprint recognition you need the `fpcalc` binary (Chromaprint). Install or place `fpcalc` as follows:

- Windows: download `fpcalc.exe` from the Chromaprint releases and either put it in your PATH (recommended) or place it in the project root or the `utils/` directory.
- macOS: `brew install chromaprint`
- Linux: `apt-get install libchromaprint-tools` (or use your distro package manager)

## Project Layout

```text
core/                   # core functionality
├── __init__.py
├── audio_processor.py  # main audio processing
└── artwork.py          # album art handling
utils/                  # helper utilities
├── __init__.py
└── dependencies.py     # dependency helpers and checks

cli.py                  # CLI interface
app.py                  # entrypoint
install_covers.py       # script to add album covers
setup.py                # packaging
```

## Usage

Basic run (interactive CLI):

```powershell
py -3 app.py
```

Fetch and embed synchronized lyrics:

```powershell
py -3 app.py -l
```

Use recognition (requires pyacoustid and fpcalc):

```powershell
py -3 app.py -l --recognition
```

Add covers only:

```powershell
py -3 install_covers.py
```

You can also run `py -3 app.py --help` for the full list of CLI options.

## Troubleshooting

If you see errors indicating `fpcalc` is missing, follow the Chromaprint instructions above and ensure `fpcalc` is available in PATH or placed in the project root or `utils/` directory. For Python packages, use the pip extras shown earlier to install optional features.

## Tests

Run unit tests with pytest (install pytest first):

```powershell
py -3 -m pip install pytest
py -3 -m pytest -q
```
