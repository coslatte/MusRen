from pathlib import Path

import core.cli_typer as cli_typer


class _NullStatus:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_resolve_directory_prompts_for_another_folder(monkeypatch, tmp_path):
    initial_directory = tmp_path / "empty"
    alternate_directory = tmp_path / "music"
    initial_directory.mkdir()
    alternate_directory.mkdir()

    seen_directories = []

    def fake_get_audio_files(directory, recursive=False):
        current_directory = Path(directory)
        seen_directories.append(current_directory)
        if current_directory == alternate_directory:
            return [str(alternate_directory / "track.mp3")]
        return []

    prompts = iter([str(alternate_directory)])

    monkeypatch.setattr(cli_typer, "get_audio_files", fake_get_audio_files)
    monkeypatch.setattr(
        cli_typer.console, "status", lambda *args, **kwargs: _NullStatus()
    )
    monkeypatch.setattr(cli_typer.console, "print", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_typer.typer, "confirm", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        cli_typer.typer, "prompt", lambda *args, **kwargs: next(prompts)
    )

    resolved_directory, files = cli_typer.resolve_directory_with_audio_files(
        initial_directory,
        recursive=False,
    )

    assert resolved_directory == alternate_directory
    assert files == [str(alternate_directory / "track.mp3")]
    assert seen_directories == [initial_directory, alternate_directory]
