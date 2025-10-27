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
from rich.table import Table
from rich.traceback import install as rich_traceback_install

from constants.info import PARSER_DESCRIPTION
from core.audio_processor import AudioProcessor
from utils.dependencies import check_dependencies
from utils.tools import get_audio_files

load_dotenv()
rich_traceback_install(show_locals=False)

app = typer.Typer(help=PARSER_DESCRIPTION)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    help: bool = typer.Option(False, "--help", "-h", is_eager=True),
    directory: Path = typer.Option(
        Path.cwd(),
        "--directory",
        "-d",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Directory of the files, if not specified the current one is used",
    ),
    lyrics: bool = typer.Option(
        False, "--lyrics", "-l", help="Search and embed synchronized lyrics"
    ),
    recognition: bool = typer.Option(
        False, "--recognition", "-r", help="Use audio recognition with AcoustID"
    ),
    cover: bool = typer.Option(
        False, "--covers", "-c", help="Add album covers"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", "-k", help="AcoustID API key (optional)"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Execute everything without confirmations"
    ),
    albums: bool = typer.Option(
        False, "--albums", "-a", help="Organize files into album folders after processing"
    ),
):
    console.rule("[bold cyan]MusRen[/bold cyan]")
    with console.status("Checking dependencies...", spinner="dots"):
        if not check_dependencies(use_recognition=recognition):
            console.print(
                Panel.fit(
                    "Missing dependencies. Aborting...",
                    border_style="red",
                    title="Error",
                )
            )
            raise typer.Exit(1)

    opts_table = Table(
        title="Configuration",
        box=box.SIMPLE_HEAVY,
        show_header=False,
        padding=(0, 1),
    )
    opts_table.add_column("Key", style="bold cyan")
    opts_table.add_column("Value", style="white")
    opts_table.add_row("Directory (-d)", str(directory))
    opts_table.add_row("Lyrics (-l)", "Yes" if lyrics else "No")
    opts_table.add_row("Recognition (-r)", "Yes" if recognition else "No")
    opts_table.add_row("Covers (-c)", "Yes" if cover else "No")
    opts_table.add_row("Auto-confirm (-y)", "Yes" if yes else "No")
    opts_table.add_row("Organize albums (-a)", "Yes" if albums else "No")
    opts_table.add_row("Help (-h)", "Yes" if help else "No")
    console.print(Panel(opts_table, border_style="cyan"))

    if api_key is None:
        api_key = os.getenv("ACOUSTID_API_KEY")

    processor = AudioProcessor(directory=directory, acoustid_api_key=api_key)
    with console.status("Searching for audio files...", spinner="line"):
        files = get_audio_files(directory=directory)

    if not files:
        console.print(
            Panel.fit(
                "No audio files found in the selected directory.",
                border_style="yellow",
                title="Warning",
            )
        )
        raise typer.Exit(1)

    summary_table = Table(box=box.MINIMAL_DOUBLE_HEAD, show_header=False)
    summary_table.add_column("Item", style="bold green")
    summary_table.add_column("Value", style="white")
    summary_table.add_row("Files found", str(len(files)))
    console.print(summary_table)

    if cover:
        console.print(
            Panel.fit(
                "The album cover search and embedding function will be used.",
                border_style="magenta",
                title="Covers",
            )
        )
        try:
            with console.status("Adding covers...", spinner="bouncingBar"):
                add_covers(directory)
            console.print("[bold green]Covers added successfully.[/bold green]")
        except Exception as e:
            console.print(Panel.fit(str(e), border_style="red", title="Error"))
            raise typer.Exit(1)

    if lyrics:
        console.print(
            Panel.fit(
                "The synchronized lyrics search and embedding function will be used.",
                border_style="magenta",
                title="Lyrics",
            )
        )
        with console.status("Processing lyrics...", spinner="dots2"):
            stats = process_lyrics_and_stats(processor, use_recognition=recognition)

        stats_table = Table(title="Lyrics Processing Summary", box=box.SIMPLE)
        stats_table.add_column("Metric", style="bold cyan")
        stats_table.add_column("Value", style="white")
        stats_table.add_row("Total files", str(stats.get("total", 0)))
        stats_table.add_row("Recognized", str(stats.get("recognized", 0)))
        stats_table.add_row("Lyrics found", str(stats.get("lyrics_found", 0)))
        stats_table.add_row("Lyrics embedded", str(stats.get("lyrics_embedded", 0)))
        console.print(stats_table)

        results = stats.get("results", {}) or {}
        if results:
            detail = Table(title="Detail per file", box=box.SIMPLE_HEAVY)
            detail.add_column("File", style="bold")
            detail.add_column("Rec.", justify="center")
            detail.add_column("Artist - Title", overflow="fold", style="white")
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
                    artist_title = file.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

                error_msg = (
                    res.get("embed_error")
                    or res.get("lyrics_error")
                    or res.get("recognition_error")
                    or ""
                )

                detail.add_row(
                    file,
                    _tick(recognized),
                    artist_title,
                    _tick(lyrics_found),
                    _tick(embedded),
                    error_msg,
                )

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

    with console.status("Renaming files...", spinner="line"):
        changes = processor.rename_files()

    if changes:
        changes_table = Table(title="Name changes", box=box.SIMPLE_HEAVY)
        changes_table.add_column("Before", style="yellow")
        changes_table.add_column("After", style="green")
        for new_name, old_name in changes.items():
            changes_table.add_row(old_name, new_name)
        console.print(changes_table)

        keep_changes = True
        if not yes:
            keep_changes = typer.confirm("Do you want to keep the name changes?")

        if not keep_changes:
            with console.status("Reverting changes...", spinner="dots"):
                processor.undo_rename(changes)
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
        files = get_audio_files(directory=directory)
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


def process_lyrics_and_stats(processor, use_recognition: bool) -> Dict[str, Any]:
    lyrics_results = processor.process_files(
        use_recognition=use_recognition, process_lyrics=True
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
        1 for f, r in lyrics_results.items() if r.get("recognition", False)
    )
    stats["lyrics_found"] = sum(
        1 for f, r in lyrics_results.items() if r.get("lyrics_found", False)
    )
    stats["lyrics_embedded"] = sum(
        1 for f, r in lyrics_results.items() if r.get("lyrics_embedded", False)
    )

    return stats


def organize_files_by_albums(directory: Path, files: list[str]) -> None:
    album_groups = defaultdict(list)

    for file in files:
        file_path = directory / file
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(file_path)
            if audio and hasattr(audio, 'tags') and audio.tags:
                album = audio.tags.get('TALB', ['Unknown Album'])[0]
                if not album or album.strip() == '':
                    album = 'Unknown Album'
            else:
                album = 'Unknown Album'
        except Exception:
            album = 'Unknown Album'

        album_groups[album].append(file)

    singles_dir = directory / 'Singles'
    singles_dir.mkdir(exist_ok=True)

    for album, tracks in album_groups.items():
        if album != 'Unknown Album':
            # Sanitize album name for folder
            safe_album = "".join(c for c in album if c.isalnum() or c in (' ', '-', '_')).rstrip()
            if not safe_album:
                safe_album = 'Unknown Album'
            album_dir = directory / safe_album
            album_dir.mkdir(exist_ok=True)
            for track in tracks:
                try:
                    shutil.move(str(directory / track), str(album_dir / track))
                except Exception as e:
                    console.print(f"[red]Error moving {track} to {album_dir}: {e}[/red]")
        else:
            for track in tracks:
                try:
                    shutil.move(str(directory / track), str(singles_dir / track))
                except Exception as e:
                    console.print(f"[red]Error moving {track} to Singles: {e}[/red]")


def add_covers(directory: Path) -> None:
    try:
        import core.install_covers as install_covers

        install_covers.run(str(directory))
    except ImportError as e:
        raise RuntimeError(
            "Could not import the cover installation module."
        ) from e
    except Exception as e:
        raise RuntimeError(f"Error executing cover installation: {e}") from e
