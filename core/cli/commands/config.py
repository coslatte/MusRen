import typer
from rich.box import SIMPLE_HEAVY
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.cli.config import VALID_KEYS, get_config_manager

config_app = typer.Typer(help="Manage configuration and API keys")

console = Console()


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help=f"Key to set: {', '.join(VALID_KEYS.keys())}"),
    value: str = typer.Argument(..., help="Value to set"),
) -> None:
    """Set a configuration value or API key."""
    if key not in VALID_KEYS:
        typer.echo(f"Invalid key. Valid keys: {', '.join(VALID_KEYS.keys())}", err=True)
        raise typer.Exit(1)

    config = get_config_manager()
    config.set(key, value)

    panel = Panel(
        f"[green]Set {key}[/green] = [cyan]{value}[/cyan]",
        border_style="green",
        title="Config Updated",
    )
    console.print(panel)


@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help=f"Key to get: {', '.join(VALID_KEYS.keys())}"),
) -> None:
    """Get a configuration value or API key."""
    if key not in VALID_KEYS:
        console.print(
            f"[red]Invalid key. Valid keys: {', '.join(VALID_KEYS.keys())}[/red]"
        )
        raise typer.Exit(1)

    config = get_config_manager()
    value = config.get(key)

    if value:
        console.print(f"[cyan]{key}[/cyan] = [white]{value}[/white]")
    else:
        console.print(f"[yellow]{key}[/yellow] is not set")


@config_app.command("list")
def config_list() -> None:
    """List all configuration values and API keys."""
    config = get_config_manager()
    keys = config.list_keys()

    table = Table(title="API Keys", box=SIMPLE_HEAVY)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value", style="white")
    table.add_column("Description", style="dim")

    for key, description in VALID_KEYS.items():
        value = keys.get(key, "[dim]<not set>[/dim]")
        table.add_row(key, value, description)

    console.print(table)


@config_app.command("delete")
def config_delete(
    key: str = typer.Argument(
        ..., help=f"Key to delete: {', '.join(VALID_KEYS.keys())}"
    ),
) -> None:
    """Delete a configuration value or API key."""
    if key not in VALID_KEYS:
        typer.echo(f"Invalid key. Valid keys: {', '.join(VALID_KEYS.keys())}", err=True)
        raise typer.Exit(1)

    config = get_config_manager()
    deleted = config.delete(key)

    if deleted:
        panel = Panel(
            f"[green]Deleted {key}[/green]",
            border_style="yellow",
            title="Config Updated",
        )
        console.print(panel)
    else:
        console.print(f"[yellow]{key}[/yellow] was not set")


@config_app.command("clear")
def config_clear() -> None:
    """Clear all configuration values."""
    confirm = typer.confirm("Are you sure you want to clear all configuration?")
    if not confirm:
        console.print("[yellow]Cancelled[/yellow]")
        return

    config = get_config_manager()
    config.clear()

    panel = Panel(
        "[green]Configuration cleared[/green]",
        border_style="yellow",
        title="Config Cleared",
    )
    typer.echo(panel)
