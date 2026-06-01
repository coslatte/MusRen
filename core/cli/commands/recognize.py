from pathlib import Path
from typing import Dict

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
recognize_app = typer.Typer(help="Recognize audio files using AcoustID")


@recognize_app.command("run")
def recognize_run(
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
    shazam: bool = typer.Option(
        False,
        "--shazam",
        "-s",
        help="Use Shazam instead of AcoustID",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Execute without confirmations",
    ),
) -> None:
    """Recognize audio files and fetch metadata."""
    if not check_dependencies(use_recognition=True):
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

    if not api_key:
        console.print(
            Panel(
                "No AcoustID API key set. Run: musren config set acoustid YOUR_KEY",
                border_style="yellow",
                title="Warning",
            )
        )

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
    table.add_row("Recognition", "AcoustID" if not shazam else "Shazam")
    table.add_row("Files found", str(len(files)))
    console.print(table)

    processor = AudioProcessor(
        directory=audio_dir,
        acoustid_api_key=api_key,
        recursive=recursive,
        use_shazam=shazam,
    )

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
        task_id = progress.add_task("Recognizing...", total=len(files))

        def progress_callback(file_path: str, result: Dict) -> None:
            pause.wait_if_paused(console)
            filename = Path(file_path).name

            status = ""
            if result.get("error"):
                status = "[red]Error[/red]"
            elif result.get("recognition"):
                status = "[green]Recognized[/green]"
            elif result.get("metadata_updated"):
                status = "[green]Updated[/green]"
            else:
                status = "[dim]No match[/dim]"

            desc = format_progress_desc(f"Processing: {filename} - {status}")
            progress.update(
                task_id,
                advance=1,
                description=f"[bold white]{desc}[/bold white]",
            )

        results = processor.process_files(
            use_recognition=True,
            process_lyrics=False,
            fetch_covers=False,
            progress_callback=progress_callback,
        )

    pause.stop()

    recognized = sum(1 for _, r in results.items() if r.get("recognition", False))
    updated = sum(1 for _, r in results.items() if r.get("metadata_updated", False))

    stats_table = Table(title="Recognition Summary", box=SIMPLE)
    stats_table.add_column("Metric", style="bold cyan")
    stats_table.add_column("Value", style="white")
    stats_table.add_row("Total files", str(len(results)))
    stats_table.add_row("Recognized", str(recognized))
    stats_table.add_row("Metadata updated", str(updated))
    console.print(stats_table)

    if results:
        detail = Table(title="File Detail", box=SIMPLE_HEAVY)
        detail.add_column("File", style="bold")
        detail.add_column("Status", justify="center")
        detail.add_column("Artist - Title", overflow="fold", style="white")
        detail.add_column("Error", style="red")

        def tick(val: bool) -> str:
            return "[green]V[/green]" if val else "[red]X[/red]"

        for file, res in results.items():
            recognized = bool(res.get("recognition", False))
            updated = bool(res.get("metadata_updated", False))

            artist_title = ""
            if recognized:
                artist_title = (
                    f"{res.get('artist', '')} - {res.get('title', '')}".strip()
                )
            if not artist_title:
                artist_title = Path(file).name

            error_msg = res.get("recognition_error") or res.get("metadata_error") or ""

            if recognized and not error_msg:
                error_msg = "N/A"

            row_data = [Path(file).name]
            row_data.append(tick(recognized or updated))
            row_data.append(artist_title)
            row_data.append(error_msg)

            detail.add_row(*row_data)

        console.print(detail)

    console.print(
        Panel(
            "Recognition completed successfully.",
            border_style="green",
            title="Completed",
        )
    )
