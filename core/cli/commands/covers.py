from pathlib import Path

import typer
from rich.box import SIMPLE_HEAVY
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

from utils.dependencies import check_dependencies
from utils.tools import (
    format_progress_desc,
    get_audio_files,
    get_pause_manager,
    suppress_noisy_loggers,
)

console = Console()
covers_app = typer.Typer(help="Add album covers to audio files")


@covers_app.command("run")
def covers_run(
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
    """Add album covers to audio files."""
    if not check_dependencies(require_covers=True):
        console.print(
            Panel(
                "Missing dependencies. Aborting...",
                border_style="red",
                title="Error",
            )
        )
        raise typer.Exit(1)

    # Lazy import to avoid loading module if not installed
    try:
        import core.install_covers as install_covers
    except ImportError:
        console.print(
            Panel(
                "Could not import the cover installation module.",
                border_style="red",
                title="Error",
            )
        )
        raise typer.Exit(1)

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
        task_id = progress.add_task("Adding covers...", total=len(files))

        def progress_callback(file_path: str, result: dict) -> None:
            pause.wait_if_paused(console)
            filename = Path(file_path).name

            status = ""
            if not result.get("status"):
                status = "[red]Error[/red]"
            elif result.get("skipped"):
                status = "[yellow]Skipped[/yellow]"
            else:
                status = "[green]Added[/green]"

            desc = format_progress_desc(f"Processing: {filename} - {status}")
            progress.update(
                task_id,
                advance=1,
                description=f"[bold white]{desc}[/bold white]",
            )

        install_covers.run(audio_dir, progress_callback=progress_callback)

    pause.stop()

    console.print(
        Panel(
            "Covers added successfully.",
            border_style="green",
            title="Completed",
        )
    )
