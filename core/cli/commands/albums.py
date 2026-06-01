import os
import shutil
from collections import defaultdict
from pathlib import Path

import typer
from rich.box import SIMPLE, SIMPLE_HEAVY
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from constants.settings import AUDIO_EXTENSIONS
from utils.tools import (
    format_progress_desc,
    get_audio_files,
    get_pause_manager,
    suppress_noisy_loggers,
)

console = Console()
albums_app = typer.Typer(help="Organize audio files into album folders")


def _is_single_album(album_name: str) -> bool:
    return (
        album_name.lower().strip() in ("single", "singles", "unknown album")
        or len(album_name.strip()) == 0
    )


@albums_app.command("run")
def albums_run(
    directory: Path = typer.Option(
        Path.cwd(),
        "--directory",
        "-d",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Directory containing audio files",
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive",
        "-R",
        help="Search files in subdirectories",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Execute without confirmations",
    ),
) -> None:
    """Organize audio files into album folders."""
    audio_dir = str(directory)
    files = get_audio_files(audio_dir, recursive=recursive)

    if not files:
        console.print(
            Panel(
                f"No audio files found in '{directory}'",
                border_style="yellow",
                title="Warning",
            )
        )
        return

    table = Table(title="Configuration", box=SIMPLE_HEAVY)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value", style="white")
    table.add_row("Directory", str(directory))
    table.add_row("Recursive", "Yes" if recursive else "No")
    table.add_row("Files found", str(len(files)))
    console.print(table)

    album_groups: dict[str, list[Path]] = defaultdict(list)

    suppress_noisy_loggers()
    pause = get_pause_manager()
    pause.start()

    with Progress(
        TextColumn("  [bold cyan]{task.description}"),
        BarColumn(bar_width=30, complete_style="cyan", finished_style="green"),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    ) as progress:
        task_id = progress.add_task("Analyzing albums...", total=len(files))

        for file_path in files:
            pause.wait_if_paused(console)
            file_path = Path(file_path)
            try:
                from mutagen._file import File as MutagenFile

                audio = MutagenFile(file_path, easy=True)
                album = "Unknown Album"

                if audio:
                    album_tags = audio.get("album", [])
                    if album_tags:
                        album = album_tags[0] if album_tags[0] else "Unknown Album"
            except Exception:
                album = "Unknown Album"

            album_groups[album].append(file_path)

            desc = format_progress_desc(f"Analyzing: {file_path.name}")
            progress.update(
                task_id,
                advance=1,
                description=f"[bold white]{desc}[/bold white]",
            )

    singles_dir = directory / "Singles"
    singles_dir.mkdir(exist_ok=True)

    albums_moved = 0
    singles_count = 0
    errors = []

    with Progress(
        TextColumn("  [bold cyan]{task.description}"),
        BarColumn(bar_width=30, complete_style="cyan", finished_style="green"),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    ) as progress:
        total_moves = sum(len(tracks) for tracks in album_groups.values())
        task_id = progress.add_task("Organizing...", total=total_moves)

        for album, tracks in album_groups.items():
            pause.wait_if_paused(console)
            is_single = _is_single_album(album)
            is_orphan = not is_single and len(tracks) == 1

            if is_single or is_orphan:
                dest_dir = singles_dir
                for track in tracks:
                    pause.wait_if_paused(console)
                    try:
                        dest_path = dest_dir / track.name
                        shutil.move(str(track), str(dest_path))
                        singles_count += 1
                    except Exception as e:
                        errors.append(f"{track.name}: {e}")
                    desc = format_progress_desc(f"Moving: {track.name}")
                    progress.update(
                        task_id,
                        advance=1,
                        description=f"[bold white]{desc}[/bold white]",
                    )
            else:
                safe_album = "".join(
                    c for c in album if c.isalnum() or c in (" ", "-", "_")
                ).rstrip()
                if not safe_album:
                    safe_album = "Unknown Album"
                album_dir = directory / safe_album
                album_dir.mkdir(exist_ok=True)

                for track in tracks:
                    pause.wait_if_paused(console)
                    try:
                        dest_path = album_dir / track.name
                        shutil.move(str(track), str(dest_path))
                        albums_moved += 1
                    except Exception as e:
                        errors.append(f"{track.name}: {e}")
                    desc = format_progress_desc(f"Moving: {track.name}")
                    progress.update(
                        task_id,
                        advance=1,
                        description=f"[bold white]{desc}[/bold white]",
                    )

    pause.stop()

    stats_table = Table(title="Organization Summary", box=SIMPLE)
    stats_table.add_column("Metric", style="bold cyan")
    stats_table.add_column("Value", style="white")
    stats_table.add_row(
        "Albums created",
        str(
            len(
                [
                    a
                    for a in album_groups.keys()
                    if not _is_single_album(a) and len(album_groups[a]) > 1
                ]
            )
        ),
    )
    stats_table.add_row("Tracks in albums", str(albums_moved))
    stats_table.add_row("Tracks in Singles", str(singles_count))
    stats_table.add_row("Errors", str(len(errors)))
    console.print(stats_table)

    if errors:
        error_table = Table(title="Errors", box=SIMPLE)
        error_table.add_column("File", style="bold red")
        error_table.add_column("Error", style="red")
        for error in errors:
            parts = error.split(": ", 1)
            error_table.add_row(parts[0], parts[1] if len(parts) > 1 else "Unknown")
        console.print(error_table)

    console.print(
        Panel(
            "Files organized successfully.",
            border_style="green",
            title="Completed",
        )
    )


@albums_app.command("revert")
def albums_revert(
    directory: Path = typer.Option(
        Path.cwd(),
        "--directory",
        "-d",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Directory that was previously organized",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Execute without confirmations",
    ),
) -> None:
    """Revert album organization: move all files back to the root directory."""
    audio_dir = Path(directory)
    files_in_subdirs = []
    for root, _, filenames in os.walk(audio_dir):
        root_path = Path(root)
        if root_path == audio_dir:
            continue
        for f in filenames:
            if f.lower().endswith(AUDIO_EXTENSIONS):
                files_in_subdirs.append(root_path / f)

    if not files_in_subdirs:
        console.print(
            Panel(
                "No audio files found in subdirectories. Nothing to revert.",
                border_style="yellow",
                title="Warning",
            )
        )
        return

    console.print(
        Panel(
            f"Found [bold]{len(files_in_subdirs)}[/bold] files in subdirectories that will be moved back to [bold]{audio_dir}[/bold].",
            border_style="cyan",
            title="Revert",
        )
    )

    if not yes:
        keep = typer.confirm("Do you want to revert the organization?")
        if not keep:
            console.print("[yellow]Cancelled.[/yellow]")
            return

    moved = 0
    errors = []

    pause = get_pause_manager()
    pause.start()

    with Progress(
        TextColumn("  [bold yellow]{task.description}"),
        BarColumn(bar_width=30, complete_style="yellow", finished_style="green"),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    ) as progress:
        task_id = progress.add_task("Reverting...", total=len(files_in_subdirs))

        for file_path in files_in_subdirs:
            pause.wait_if_paused(console)
            dest = audio_dir / file_path.name
            try:
                if dest.exists():
                    base = dest.stem
                    ext = dest.suffix
                    counter = 1
                    while dest.exists():
                        dest = audio_dir / f"{base} ({counter}){ext}"
                        counter += 1
                shutil.move(str(file_path), str(dest))
                moved += 1
            except Exception as e:
                errors.append(f"{file_path.name}: {e}")

            desc = format_progress_desc(f"Moving: {file_path.name}")
            progress.update(
                task_id,
                advance=1,
                description=f"[bold white]{desc}[/bold white]",
            )

    pause.stop()

    # Remove empty subdirectories
    try:
        for root, dirs, _ in os.walk(audio_dir, topdown=False):
            for d in dirs:
                dir_path = Path(root) / d
                try:
                    if dir_path != audio_dir and not any(dir_path.iterdir()):
                        dir_path.rmdir()
                except Exception:
                    pass
    except Exception:
        pass

    result = Table(title="Revert Summary", box=SIMPLE)
    result.add_column("Metric", style="bold cyan")
    result.add_column("Value", style="white")
    result.add_row("Files restored", str(moved))
    result.add_row("Errors", str(len(errors)))
    console.print(result)

    if errors:
        err_table = Table(title="Errors", box=SIMPLE)
        err_table.add_column("File", style="bold red")
        err_table.add_column("Error", style="red")
        for error in errors:
            parts = error.split(": ", 1)
            err_table.add_row(parts[0], parts[1] if len(parts) > 1 else "Unknown")
        console.print(err_table)

    console.print(
        Panel(
            "Album organization reverted successfully.",
            border_style="green",
            title="Completed",
        )
    )
