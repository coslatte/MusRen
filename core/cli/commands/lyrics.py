from pathlib import Path
from typing import Any, Dict

import typer
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

from core.audio_processor import AudioProcessor
from core.cli.config import get_config_manager
from utils.dependencies import check_dependencies
from utils.tools import (
    format_progress_desc,
    get_audio_files,
    get_pause_manager,
    suppress_noisy_loggers,
)

console = Console()
lyrics_app = typer.Typer(help="Search and embed synchronized lyrics")


def process_lyrics_and_stats(
    processor: AudioProcessor,
    use_recognition: bool = False,
    process_lyrics: bool = True,
    fetch_covers: bool = False,
) -> Dict[str, Any]:
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
        task_id = progress.add_task("Processing...", total=total_files)

        def progress_callback(file_path: str, result: Dict[str, Any]) -> None:
            pause.wait_if_paused(console)
            filename = Path(file_path).name

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

    pause.stop()

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


@lyrics_app.command("run")
def lyrics_run(
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
    recognition: bool = typer.Option(
        False,
        "--recognition",
        "-r",
        help="Use audio recognition before searching lyrics",
    ),
    covers: bool = typer.Option(
        False,
        "--covers",
        "-c",
        help="Also fetch album covers",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Execute without confirmations",
    ),
) -> None:
    """Search and embed synchronized lyrics."""
    if not check_dependencies(use_recognition=recognition, require_lyrics=True):
        console.print(
            Panel(
                "Missing dependencies. Aborting...",
                border_style="red",
                title="Error",
            )
        )
        raise typer.Exit(1)

    config = get_config_manager()
    api_key = config.get("acoustid")

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

    table = Table(title="Configuration", box="simple_heavy")
    table.add_column("Key", style="bold cyan")
    table.add_column("Value", style="white")
    table.add_row("Directory", str(directory))
    table.add_row("Recursive", "Yes" if recursive else "No")
    table.add_row("Recognition", "Yes" if recognition else "No")
    table.add_row("Covers", "Yes" if covers else "No")
    table.add_row("Files found", str(len(files)))
    console.print(table)

    processor = AudioProcessor(
        directory=audio_dir,
        acoustid_api_key=api_key,
        recursive=recursive,
    )

    stats = process_lyrics_and_stats(
        processor,
        use_recognition=recognition,
        process_lyrics=True,
        fetch_covers=covers,
    )

    stats_table = Table(title="Processing Summary", box="simple")
    stats_table.add_column("Metric", style="bold cyan")
    stats_table.add_column("Value", style="white")
    stats_table.add_row("Total files", str(stats.get("total", 0)))
    if recognition:
        stats_table.add_row("Recognized", str(stats.get("recognized", 0)))
    stats_table.add_row("Lyrics found", str(stats.get("lyrics_found", 0)))
    stats_table.add_row("Lyrics embedded", str(stats.get("lyrics_embedded", 0)))
    console.print(stats_table)

    results = stats.get("results", {}) or {}
    if results:
        detail = Table(title="File Detail", box="simple_heavy")
        detail.add_column("File", style="bold")
        if recognition:
            detail.add_column("Rec.", justify="center")
        detail.add_column("Artist - Title", overflow="fold", style="white")
        detail.add_column("Lyrics", justify="center")
        detail.add_column("Embedded", justify="center")
        detail.add_column("Error", style="red")

        def tick(val: bool) -> str:
            return "[green]V[/green]" if val else "[red]X[/red]"

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
                artist_title = Path(file).name

            error_msg = (
                res.get("embed_error")
                or res.get("lyrics_error")
                or res.get("recognition_error")
                or res.get("metadata_error")
                or ""
            )

            if recognition and not recognized and not error_msg:
                error_msg = "Not recognized"

            row_data = [Path(file).name]
            if recognition:
                row_data.append(tick(recognized))
            row_data.append(artist_title)
            row_data.append(tick(lyrics_found))
            row_data.append(tick(embedded))
            row_data.append(error_msg)

            detail.add_row(*row_data)

        console.print(detail)

    console.print(
        Panel(
            "Process completed successfully.",
            border_style="green",
            title="Completed",
        )
    )
