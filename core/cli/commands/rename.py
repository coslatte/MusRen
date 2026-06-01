from datetime import datetime
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

rename_app = typer.Typer(help="Rename audio files based on metadata")


@rename_app.command("run")
def rename_run(
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
    """Rename audio files based on their metadata."""
    if not check_dependencies(use_recognition=False):
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

    table = Table(title="Configuration", box=SIMPLE_HEAVY)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value", style="white")
    table.add_row("Directory", str(directory))
    table.add_row("Recursive", "Yes" if recursive else "No")
    table.add_row("Files found", str(len(files)))
    console.print(table)

    if not yes:
        console.print("\n[bold cyan]Select rename format:[/bold cyan]")
        console.print("  [bold]1[/bold] - artist - title")
        console.print("  [bold]2[/bold] - title")
        console.print("  [bold]3[/bold] - track_number - artist - title (if album)")
        rename_format = typer.prompt("Choose format", default="1", type=str)
    else:
        rename_format = "1"

    processor = AudioProcessor(
        directory=audio_dir,
        acoustid_api_key=api_key,
        recursive=recursive,
    )

    errors = []
    skipped = []
    renamed_count = 0
    no_change_count = 0
    start_time = datetime.now()

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
        task_id = progress.add_task("Renaming...", total=len(files))

        def rename_callback(file_path, result):
            nonlocal renamed_count, no_change_count
            pause.wait_if_paused(console)
            filename = Path(file_path).name

            status = ""
            if result.get("renamed"):
                status = "[green]Renamed[/green]"
                renamed_count += 1
            elif result.get("skipped"):
                reason = result.get("reason", "Unknown")
                skipped.append((filename, reason))
                status = "[dim]Skipped[/dim]"
            elif result.get("error"):
                errors.append((filename, result["error"]))
                status = "[red]Error[/red]"
            else:
                no_change_count += 1
                status = "[dim]No changes[/dim]"

            desc = format_progress_desc(f"Renaming: {filename} - {status}")
            progress.update(
                task_id,
                advance=1,
                description=f"[bold white]{desc}[/bold white]",
            )

        changes = processor.rename_files(
            progress_callback=rename_callback,
            rename_format=rename_format,
        )

    pause.stop()
    elapsed = datetime.now() - start_time
    elapsed_str = (
        f"{elapsed.seconds // 60}m {elapsed.seconds % 60}s"
        if elapsed.seconds >= 60
        else f"{elapsed.seconds}s"
    )

    summary = Table(title="Rename Summary", box=SIMPLE)
    summary.add_column("Metric", style="bold cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Total files", str(len(files)))
    summary.add_row("Renamed", str(renamed_count))
    summary.add_row("No changes", str(no_change_count))
    summary.add_row("Skipped", str(len(skipped)))
    summary.add_row("Errors", f"[red]{len(errors)}[/red]" if errors else "0")
    summary.add_row("Time", elapsed_str)
    console.print(summary)

    if skipped:
        skip_table = Table(title="Skipped Files", box=SIMPLE)
        skip_table.add_column("File", style="yellow")
        skip_table.add_column("Reason", style="dim")
        for fname, reason in skipped:
            skip_table.add_row(fname, reason)
        console.print(skip_table)

    if errors:
        err_table = Table(title="Error Details", box=SIMPLE)
        err_table.add_column("File", style="bold red")
        err_table.add_column("Cause", style="red")
        for fname, cause in errors:
            err_table.add_row(fname, cause)
        console.print(err_table)

    if changes:
        changes_table = Table(title="Name changes", box=SIMPLE_HEAVY)
        changes_table.add_column("Before", style="yellow")
        changes_table.add_column("After", style="green")
        for new_path, old_path in changes.items():
            changes_table.add_row(Path(old_path).name, Path(new_path).name)
        console.print(changes_table)

        keep_changes = yes or typer.confirm("Do you want to keep the name changes?")
        if not keep_changes:
            with Progress(
                TextColumn("  [bold yellow]{task.description}"),
                BarColumn(
                    bar_width=30, complete_style="yellow", finished_style="green"
                ),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console,
                expand=True,
            ) as progress:
                task_id = progress.add_task("Reverting...", total=len(changes))

                def undo_callback(file_path, result):
                    filename = Path(file_path).name
                    desc = format_progress_desc(f"Reverting: {filename}")
                    progress.update(
                        task_id,
                        advance=1,
                        description=f"[bold white]{desc}[/bold white]",
                    )

                processor.undo_rename(changes, progress_callback=undo_callback)

            console.print(
                Panel(
                    "The name changes have been reverted.",
                    border_style="yellow",
                    title="Reverted",
                )
            )
        else:
            console.print(
                Panel(
                    "The name changes have been kept.",
                    border_style="green",
                    title="Ready",
                )
            )
    else:
        console.print("[bold yellow]No name changes were made.[/bold yellow]")

    console.print(
        Panel(
            "Process completed successfully.",
            border_style="green",
            title="Completed",
        )
    )
