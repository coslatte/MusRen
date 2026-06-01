import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from dotenv import load_dotenv
from rich import box
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
from rich.traceback import install as rich_traceback_install

from constants.info import PARSER_DESCRIPTION
from core.audio_processor import AudioProcessor
from utils.dependencies import check_dependencies
from utils.tools import format_progress_desc, get_audio_files, suppress_noisy_loggers

load_dotenv()
rich_traceback_install(show_locals=False)

app = typer.Typer(help=PARSER_DESCRIPTION)
console = Console()


def resolve_directory_with_audio_files(
    directory: Path, recursive: bool
) -> tuple[Path, list[str]]:
    current_directory = directory

    while True:
        with console.status("Searching for audio files...", spinner="line"):
            files = get_audio_files(directory=current_directory, recursive=recursive)

        if files:
            return current_directory, files

        console.print(
            Panel.fit(
                f"No audio files found in '{current_directory}'.",
                border_style="yellow",
                title="Warning",
            )
        )

        if not typer.confirm("Do you want to search another directory?"):
            return current_directory, []

        while True:
            next_directory_raw = typer.prompt("Enter the exact directory to search")
            next_directory = Path(next_directory_raw).expanduser()

            if next_directory.is_dir():
                current_directory = next_directory
                break

            console.print(
                Panel.fit(
                    "The provided path is not a valid directory.",
                    border_style="red",
                    title="Error",
                )
            )


@app.callback(invoke_without_command=True)
def main(
    directory: Path = typer.Option(
        Path.cwd(),
        "--directory",
        "-d",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Directory of the files, if not specified the current one is used",
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-R", help="Search files in subdirectories"
    ),
    lyrics: bool = typer.Option(
        False, "--lyrics", "-l", help="Search and embed synchronized lyrics"
    ),
    recognition: bool = typer.Option(
        False, "--recognition", "-r", help="Use audio recognition with AcoustID"
    ),
    cover: bool = typer.Option(False, "--covers", "-c", help="Add album covers"),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", "-k", help="AcoustID API key (optional)"
    ),
    shazam: bool = typer.Option(
        False, "--shazam", "-s", help="Use Shazam instead of AcoustID"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Execute everything without confirmations"
    ),
    albums: bool = typer.Option(
        False,
        "--albums",
        "-a",
        help="Organize files into album folders after processing",
    ),
):
    console.rule("[bold cyan]musren[/bold cyan]")
    with console.status("Checking dependencies...", spinner="dots"):
        if not check_dependencies(
            use_recognition=recognition, require_lyrics=lyrics, require_covers=cover
        ):
            console.print(
                Panel.fit(
                    "Missing dependencies. Aborting...",
                    border_style="red",
                    title="Error",
                )
            )
            raise typer.Exit(1)

    if api_key is None:
        api_key = os.getenv("ACOUSTID_API_KEY")

    directory, files = resolve_directory_with_audio_files(directory, recursive)

    opts_table = Table(
        title="Configuration",
        box=box.SIMPLE_HEAVY,
        show_header=False,
        padding=(0, 1),
    )
    opts_table.add_column("Key", style="bold cyan")
    opts_table.add_column("Value", style="white")
    opts_table.add_row("Directory", str(directory))
    opts_table.add_row("Recursive (-R)", "Yes" if recursive else "No")
    opts_table.add_row("Lyrics (-l)", "Yes" if lyrics else "No")
    opts_table.add_row("Recognition (-r)", "Yes" if recognition else "No")
    opts_table.add_row("Shazam (-s)", "Yes" if shazam else "No")
    opts_table.add_row("Covers (-c)", "Yes" if cover else "No")
    opts_table.add_row("Auto-confirm (-y)", "Yes" if yes else "No")
    opts_table.add_row("Organize albums (-a)", "Yes" if albums else "No")
    console.print(Panel(opts_table, border_style="cyan"))

    if not files:
        return

    processor = AudioProcessor(
        directory=str(directory),
        acoustid_api_key=str(api_key) if api_key else os.getenv("ACOUSTID_API_KEY"),
        recursive=recursive,
        use_shazam=shazam,
    )

    summary_table = Table(box=box.MINIMAL_DOUBLE_HEAD, show_header=False)
    summary_table.add_column("Item", style="bold green")
    summary_table.add_column("Value", style="white")
    summary_table.add_row("Files found", str(len(files)))
    console.print(summary_table)

    if cover and not (lyrics or recognition):
        console.print(
            Panel.fit(
                "The album cover search and embedding function will be used.",
                border_style="magenta",
                title="Covers",
            )
        )
        try:
            # Use the main processor instead of the legacy add_covers function
            # This ensures recursion and centralized logic are respected
            stats = process_lyrics_and_stats(
                processor,
                use_recognition=False,
                process_lyrics=False,
                fetch_covers=True,
                yes=yes,
            )
            console.print("[bold green]Covers added successfully.[/bold green]")
        except Exception as e:
            console.print(Panel.fit(str(e), border_style="red", title="Error"))
            raise typer.Exit(1)

    if lyrics or recognition:
        title_text = "Lyrics"
        if recognition and not lyrics:
            title_text = "Recognition"
        elif recognition and lyrics:
            title_text = "Recognition and Lyrics"

        console.print(
            Panel.fit(
                f"The {title_text} function will be used.",
                border_style="magenta",
                title=title_text,
            )
        )

        stats = process_lyrics_and_stats(
            processor,
            use_recognition=recognition,
            process_lyrics=lyrics,
            fetch_covers=cover,
            yes=yes,
        )

        stats_table = Table(title=f"Processing Summary ({title_text})", box=box.SIMPLE)
        stats_table.add_column("Metric", style="bold cyan")
        stats_table.add_column("Value", style="white")
        stats_table.add_row("Total files", str(stats.get("total", 0)))
        if recognition:
            stats_table.add_row("Recognized", str(stats.get("recognized", 0)))
        if lyrics:
            stats_table.add_row("Lyrics found", str(stats.get("lyrics_found", 0)))
            stats_table.add_row("Lyrics embedded", str(stats.get("lyrics_embedded", 0)))
        console.print(stats_table)

        results = stats.get("results", {}) or {}
        if results:
            detail = Table(title="File Detail", box=box.SIMPLE_HEAVY)
            detail.add_column("File", style="bold")
            if recognition:
                detail.add_column("Rec.", justify="center")
            detail.add_column("Artist - Title", overflow="fold", style="white")
            if lyrics:
                detail.add_column("Lyrics", justify="center")
                detail.add_column("Embedded", justify="center")
            detail.add_column("Error", style="red")

            def _tick(val: bool) -> str:
                return "[green]✔[/green]" if val else "[red]✖[/red]"

            for file, res in results.items():
                recognized = bool(res.get("recognition", False))
                lyrics_found = bool(res.get("lyrics_found", False))
                embedded = bool(res.get("lyrics_embedded", False))
                artist_title = ""
                if recognized:
                    artist_title = (
                        f"{res.get('artist', '')} - {res.get('title', '')}".strip()
                    )
                if not artist_title:
                    artist_title = os.path.basename(file)

                error_msg = (
                    res.get("embed_error")
                    or res.get("lyrics_error")
                    or res.get("recognition_error")
                    or res.get("metadata_error")
                    or ""
                )

                # If recognition error, show explicitly
                if recognition and not recognized and not error_msg:
                    error_msg = "Not recognized (Low score or no match)"

                row_data = [os.path.basename(file)]
                if recognition:
                    row_data.append(_tick(recognized))

                row_data.append(artist_title)

                if lyrics:
                    row_data.append(_tick(lyrics_found))
                    row_data.append(_tick(embedded))

                row_data.append(error_msg)

                detail.add_row(*row_data)

            console.print(detail)

    proceed_rename = True
    if not yes:
        proceed_rename = typer.confirm("Start renaming files?")
    else:
        console.print("[bold yellow]Auto-confirmation enabled (-y).[/bold yellow]")

    if not proceed_rename:
        console.print(
            Panel.fit(
                "Renaming operation cancelled.",
                border_style="yellow",
                title="Cancelled",
            )
        )
        raise typer.Exit()

    # Count files for renaming progress bar
    files_to_rename = get_audio_files(directory, recursive=recursive)

    with Progress(
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=None, complete_style="cyan", finished_style="green"),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    ) as progress:
        task_id = progress.add_task("Renaming...", total=len(files_to_rename))

        def rename_callback(file_path, result):
            filename = os.path.basename(file_path)

            status = ""
            if result.get("renamed"):
                status = "[green]Renamed[/green]"
            elif result.get("skipped"):
                status = "[dim]Skipped[/dim]"
            elif result.get("error"):
                status = "[red]Error[/red]"
            else:
                status = "[dim]No changes[/dim]"

            desc = format_progress_desc(f"Renaming: {filename} - {status}")
            progress.update(
                task_id,
                advance=1,
                description=f"[bold white]{desc}[/bold white]",
            )

        changes = processor.rename_files(progress_callback=rename_callback)

    if changes:
        changes_table = Table(title="Name changes", box=box.SIMPLE_HEAVY)
        changes_table.add_column("Before", style="yellow")
        changes_table.add_column("After", style="green")
        for new_path, old_path in changes.items():
            # Show only filename to avoid giant table
            changes_table.add_row(
                os.path.basename(old_path), os.path.basename(new_path)
            )
        console.print(changes_table)

        keep_changes = True
        if not yes:
            keep_changes = typer.confirm("Do you want to keep the name changes?")

        if not keep_changes:
            with Progress(
                TextColumn("[bold yellow]{task.description}"),
                BarColumn(
                    bar_width=None, complete_style="yellow", finished_style="green"
                ),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console,
                expand=True,
            ) as progress:
                task_id = progress.add_task("Reverting...", total=len(changes))

                def undo_callback(file_path, result):
                    filename = os.path.basename(file_path)
                    desc = format_progress_desc(f"Reverting: {filename}")
                    progress.update(
                        task_id,
                        advance=1,
                        description=f"[bold white]{desc}[/bold white]",
                    )

                processor.undo_rename(changes, progress_callback=undo_callback)

            console.print(
                Panel.fit(
                    "The name changes have been reverted.",
                    border_style="yellow",
                    title="Reverted",
                )
            )
        else:
            console.print(
                Panel.fit(
                    "The name changes have been kept.",
                    border_style="green",
                    title="Ready",
                )
            )
    else:
        console.print("[bold]No name changes were made.[/bold]")

    console.rule("[bold green]Process completed[/bold green]")
    console.print(
        Panel.fit(
            "The process has completed successfully.",
            border_style="green",
            title="Completed",
        )
    )

    if albums:
        files = get_audio_files(directory=directory, recursive=recursive)
        if files:
            proceed_organize = True
            if not yes:
                proceed_organize = typer.confirm("Organize files into album folders?")
            if proceed_organize:
                with console.status("Organizing files by albums...", spinner="dots"):
                    organize_files_by_albums(directory, files)
                console.print("[bold green]Files organized by albums.[/bold green]")

    if not yes:
        try:
            try:
                import click

                click.pause(info="Press Enter to exit...", err=False)
            except Exception:
                input("Press Enter to exit...")
        finally:
            raise typer.Exit(0)


def process_lyrics_and_stats(
    processor,
    use_recognition: bool,
    process_lyrics: bool = True,
    fetch_covers: bool = False,
    yes: bool = False,
) -> Dict[str, Any]:
    # Count files first for progress bar
    files = get_audio_files(processor.directory, recursive=processor.recursive)
    total_files = len(files)

    if total_files == 0:
        return {
            "total": 0,
            "recognized": 0,
            "lyrics_found": 0,
            "lyrics_embedded": 0,
            "results": {},
        }

    lyrics_results = {}

    suppress_noisy_loggers()

    if total_files > 100 and not yes:
        seconds_per_file = 8 if use_recognition else 3
        if fetch_covers:
            seconds_per_file += 5
        est_seconds = total_files * seconds_per_file
        if est_seconds > 120:
            hours, remainder = divmod(est_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            parts = []
            if hours:
                parts.append(f"{hours}h")
            if minutes:
                parts.append(f"{minutes}m")
            parts.append(f"{seconds}s")
            est_str = " ".join(parts)

            if hours:
                console.print(
                    Panel(
                        f"[yellow]{total_files} files will be processed.[/yellow]\n"
                        f"Estimated time: [bold]{est_str}[/bold]\n"
                        "Consider using a smaller batch or be patient.",
                        border_style="yellow",
                        title="Large batch",
                    )
                )
                try:
                    typer.confirm("Continue?", default=True, abort=True)
                except typer.Abort:
                    return {
                        "total": 0,
                        "recognized": 0,
                        "lyrics_found": 0,
                        "lyrics_embedded": 0,
                        "results": {},
                    }

    with Progress(
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=None, complete_style="cyan", finished_style="green"),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    ) as progress:
        task_id = progress.add_task("Starting...", total=total_files)

        def progress_callback(file_path, result):
            filename = os.path.basename(file_path)

            status = ""
            if result.get("error"):
                status = "[red]Error[/red]"
            elif result.get("metadata_error"):
                status = "[red]Meta Error[/red]"
            elif result.get("recognition"):
                status = "[green]Recognized[/green]"
            elif result.get("lyrics_found"):
                status = "[green]Lyrics OK[/green]"
            elif result.get("metadata_updated"):
                status = "[green]Updated[/green]"
            else:
                status = "[dim]No changes[/dim]"

            desc = format_progress_desc(f"Processing: {filename} - {status}")
            progress.update(
                task_id,
                advance=1,
                description=f"[bold white]{desc}[/bold white]",
            )

        lyrics_results = processor.process_files(
            use_recognition=use_recognition,
            process_lyrics=process_lyrics,
            fetch_covers=fetch_covers,
            progress_callback=progress_callback,
        )

    stats = {
        "total": 0,
        "recognized": 0,
        "lyrics_found": 0,
        "lyrics_embedded": 0,
        "results": lyrics_results,
    }

    if not lyrics_results:
        return stats

    stats["total"] = len(lyrics_results)
    stats["recognized"] = sum(
        1 for _, r in lyrics_results.items() if r.get("recognition", False)
    )
    stats["lyrics_found"] = sum(
        1 for _, r in lyrics_results.items() if r.get("lyrics_found", False)
    )
    stats["lyrics_embedded"] = sum(
        1 for _, r in lyrics_results.items() if r.get("lyrics_embedded", False)
    )

    return stats


def organize_files_by_albums(directory: Path, files: list[str]) -> None:
    """
    Organizes audio files into album folders.

    Args:
        directory: Base directory where album folders will be created
        files: List of absolute file paths to organize
    """
    album_groups = defaultdict(list)

    for file_path in files:
        # file_path is already an absolute path from get_audio_files
        file_path = Path(file_path)
        try:
            from mutagen._file import File as MutagenFile

            audio = MutagenFile(file_path, easy=True)
            album = "Unknown Album"

            if audio:
                # With easy=True, we can use standardized tag names
                album_tags = audio.get("album", [])
                if album_tags:
                    album = album_tags[0] if album_tags[0] else "Unknown Album"
        except Exception:
            album = "Unknown Album"

        album_groups[album].append(file_path)

    singles_dir = directory / "Singles"
    singles_dir.mkdir(exist_ok=True)

    for album, tracks in album_groups.items():
        if album != "Unknown Album":
            # Sanitize album name for folder
            safe_album = "".join(
                c for c in album if c.isalnum() or c in (" ", "-", "_")
            ).rstrip()
            if not safe_album:
                safe_album = "Unknown Album"
            album_dir = directory / safe_album
            album_dir.mkdir(exist_ok=True)
            for track in tracks:
                try:
                    dest_path = album_dir / track.name
                    shutil.move(str(track), str(dest_path))
                    console.print(f"[dim]Moved {track.name} → {safe_album}/[/dim]")
                except Exception as e:
                    console.print(
                        f"[red]Error moving {track.name} to {album_dir}: {e}[/red]"
                    )
        else:
            for track in tracks:
                try:
                    dest_path = singles_dir / track.name
                    shutil.move(str(track), str(dest_path))
                    console.print(f"[dim]Moved {track.name} → Singles/[/dim]")
                except Exception as e:
                    console.print(
                        f"[red]Error moving {track.name} to Singles: {e}[/red]"
                    )


def add_covers(directory: Path) -> None:
    try:
        import core.install_covers as install_covers

        # Count files first
        files = get_audio_files(directory)
        total_files = len(files)

        if total_files == 0:
            console.print("[yellow]No audio files found.[/yellow]")
            return

        with Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=None, complete_style="cyan", finished_style="green"),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        ) as progress:
            task_id = progress.add_task("Adding covers...", total=total_files)

            def progress_callback(file_path, result):
                filename = os.path.basename(file_path)

                status = ""
                if not result.get("status"):
                    status = "[red]Error[/red]"
                elif result.get("skipped"):
                    status = "[dim]Already exists[/dim]"
                else:
                    status = "[green]Added[/green]"

                desc = format_progress_desc(f"Processing: {filename} - {status}")
                progress.update(
                    task_id,
                    advance=1,
                    description=f"[bold white]{desc}[/bold white]",
                )

            install_covers.run(str(directory), progress_callback=progress_callback)

    except ImportError as e:
        raise RuntimeError("Could not import the cover installation module.") from e
    except Exception as e:
        raise RuntimeError(f"Error executing cover installation: {e}") from e
