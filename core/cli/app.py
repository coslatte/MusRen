import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.traceback import install as rich_traceback_install

from constants.info import PARSER_DESCRIPTION, MUSIC_RENAMER_VERSION
from core.cli.commands import albums as albums_cmd
from core.cli.commands import config as config_cmd
from core.cli.commands import covers as covers_cmd
from core.cli.commands import lyrics as lyrics_cmd
from core.cli.commands import recognize as recognize_cmd
from core.cli.commands import rename as rename_cmd

load_dotenv()
rich_traceback_install(show_locals=False)

app = typer.Typer(
    name="musren",
    help=PARSER_DESCRIPTION,
    add_completion=False,
)

console = Console()

app.add_typer(config_cmd.config_app, name="config")
app.add_typer(rename_cmd.rename_app, name="rename")
app.add_typer(lyrics_cmd.lyrics_app, name="lyrics")
app.add_typer(covers_cmd.covers_app, name="covers")
app.add_typer(recognize_cmd.recognize_app, name="recognize")
app.add_typer(albums_cmd.albums_app, name="albums")


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
    ),
) -> None:
    """musren - Music file renamer based on metadata."""
    if version:
        console.print(f"[bold cyan]musren[/bold cyan] v{MUSIC_RENAMER_VERSION}")
        raise typer.Exit(0)


def cli() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    cli()
