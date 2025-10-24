# AGENTS.md — Agent & Contributor Guide

This document helps contributors and automated coding agents work effectively in this repository (MusRen). It describes the code structure, development workflow, and conventions to keep edits safe, reviewable, and testable.

## Project overview

- Stack: Python 3.8+ (CLI utility and small library).
- Purpose: organize, tag and optionally embed metadata/artwork/lyrics into audio files.
- Entrypoints:
  - `app.py` — public `main()` entry used by the CLI.
  - `core/` — modules for audio processing: `artwork.py`, `audio_processor.py`, `install_covers.py`, `cli.py`.
  - `utils/` — helper utilities (`dependencies.py`, `tools.py`).
- Optional binaries: `fpcalc` (Chromaprint) may be required for fingerprinting-based recognition.

## Run commands (Windows example)

- Create venv: `py -3 -m venv .venv`
- Activate (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

- Install deps:

```powershell
py -3 -m pip install -r requirements.txt
# For optional features (recognition, lyrics, musicbrainz):
py -3 -m pip install .[recognition,lyrics,musicbrainz]
```

- Run tests:

```powershell
py -3 -m pytest -q
```

- Run CLI (example):

```powershell
py -3 app.py --help
# or, if installed as a package:
py -3 -m musren
```

## Development environment recommendations

- Python: 3.8+ (the repo was developed with modern Python; prefer 3.10+ where available).
- Use an isolated virtual environment per project (venv, venvwrapper, or pyenv/virtualenv).
- Editor: VSCode with Python extension. Recommended VSCode extensions are provided in `.vscode/extensions.json` when present.
- Do not rely on module-level network I/O, subprocess calls, or file-system mutations — the project uses lazy imports and guards for optional features.

## Codebase map

- `app.py` — public entry point, exposes `main()`.
- `core/` — core processing logic:
  - `artwork.py` — fetching and embedding album art (lazy imports for `mutagen`, `requests`).
  - `audio_processor.py` — metadata edits, recognition (optional `acoustid`), lyrics embedding.
  - `install_covers.py` — batch cover installer CLI.
  - `cli.py` — command parsing and orchestration.
- `utils/` — small utilities and dependency checks (`dependencies.py`, `tools.py`).
- `constants/` — small project constants and settings.
- `tests/` — non-invasive tests (import checks and lightweight validators).

## Conventions and rules (important for agents)

- Language: English for all generated messages, docs, and commit messages.
- Docstrings & typing: keep docstrings short (1–3 lines) and prefer explicit type annotations for new functions.
- Lazy imports: do not import optional third-party libraries at module import time. Use local imports inside functions that need them.
- No side-effects on import: avoid network, filesystem writes, or subprocess calls at import time.
- Error handling: prefer explicit `except Exception:` with logged or returned messages; avoid silent `except:` swallowing.
- Extras: optional features are exposed via `extras_require` in `setup.py` (see groups: `recognition`, `lyrics`, `musicbrainz`).

## Agent workflow (how to make safe changes)

Agents (human or automated) should follow a short, repeatable workflow for non-trivial edits.

1. Plan: outline 2–6 concrete steps (search, edit, validate) and list files to change.
2. Search: use `rg`/`ripgrep` or VSCode workspace search to find symbols/files; open files in small chunks to limit scope.
3. Edit: prefer small, focused patches — one file per patch where practical.
   - Use the repository's patch format when possible.
4. Validate locally:
   - Run import checks first (e.g., `py -3 -c "import importlib; importlib.import_module('app')"`).
   - Run tests: `py -3 -m pytest -q`.
5. Document and PR: include a short description, related tests, and verification steps in the PR body.

## Common low-risk tasks (how-to)

- Make an optional dependency lazy:
  - Move `import mutagen` inside the function that needs it.
  - Add a guard message when the module is missing (do not crash at import time).
  - Add a tiny test asserting the module still imports when the optional dependency is not installed.

- Add `fpcalc` check for Chromaprint:
  - Use `shutil.which('fpcalc')` and SEARCH paths (project root and `utils/`) before failing.
  - Document binary install steps in `README.md`.

- Add tests:
  - Prefer non-invasive tests that assert importability and small functional behaviors.
  - If a feature requires optional deps, either mark the test to skip when deps missing or add those extras in CI.

## Minimal prompt template for agents

When asking an LLM to make code changes in this repo, use a concise template:

```
Repository path: <absolute path>
Goal: <one-sentence goal>
Constraints:
- English only
- Short docstrings, explicit types for new code
- No import-time side-effects
- Keep patches small (1 file per patch when possible)
Files to inspect: <list>

Produce:
1) A short plan (2–6 steps)
2) Patches per file (diff format)
3) Tests to add/update
4) A brief validation summary and commands
```

## Agent checklist (quick)

- [ ] Did I plan 2–6 steps? 
- [ ] Did I avoid module-level side effects? 
- [ ] Did I run import checks and tests? 
- [ ] Did I produce a small, reversible patch? 
```text
- [ ] Did I plan 2–6 steps?
- [ ] Did I avoid module-level side effects?
- [ ] Did I run import checks and tests?
- [ ] Did I produce a small, reversible patch?
```

## File naming and placement

- Use `AGENTS.md` (plural) in the repository root for agent guidance; it is visible and friendly for contributors.
- Keep hidden files (starting with `.`) for machine metadata only. We recommend `AGENTS.md` over a dot-file to increase discoverability.

## VSCode & CI integration (optional enhancements)

- Recommend these VSCode extensions to contributors: `ms-python.python`, `yzhang.markdown-all-in-one`, `gruntfuggly.todo-tree`, `eamodio.gitlens`.
- Consider adding `.vscode/extensions.json` and `.vscode/settings.json` to recommend and configure these (I can add them).
- Add a helper script `tools/sync_agent_todo.py` to export checklist items to `.agent_todos.json` for tooling and UI integration.
- Consider adding a GitHub Actions workflow to ensure `AGENTS.md` exists and basic checks pass on push/PR.

---
Last updated: 2025-10-24
