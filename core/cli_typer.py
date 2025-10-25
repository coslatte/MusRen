import os
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
    directory: Path = typer.Option(
        Path.cwd(),
        "--directory",
        "-d",
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Directorio de los archivos, de no especificarse se utiliza el actual",
    ),
    lyrics: bool = typer.Option(
        False, "--lyrics", "-l", help="Buscar e incrustar letras sincronizadas"
    ),
    recognition: bool = typer.Option(
        False, "--recognition", "-r", help="Usar reconocimiento de audio con AcoustID"
    ),
    cover: bool = typer.Option(
        False, "--covers", "-c", help="Añadir portadas de álbum"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", "-k", help="AcoustID API key (opcional)"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Ejecutar todo sin confirmaciones"
    ),
):
    console.rule("[bold cyan]MusRen[/bold cyan]")
    with console.status("Verificando dependencias...", spinner="dots"):
        if not check_dependencies():
            console.print(
                Panel.fit(
                    "Dependencias faltantes. Abortando...",
                    border_style="red",
                    title="Error",
                )
            )
            raise typer.Exit(1)

    opts_table = Table(
        title="Configuración",
        box=box.SIMPLE_HEAVY,
        show_header=False,
        padding=(0, 1),
    )
    opts_table.add_column("Clave", style="bold cyan")
    opts_table.add_column("Valor", style="white")
    opts_table.add_row("Directorio", str(directory))
    opts_table.add_row("Letras (-l)", "Sí" if lyrics else "No")
    opts_table.add_row("Reconocimiento (-r)", "Sí" if recognition else "No")
    opts_table.add_row("Portadas (-c)", "Sí" if cover else "No")
    opts_table.add_row("Auto-confirmar (-y)", "Sí" if yes else "No")
    console.print(Panel(opts_table, border_style="cyan"))

    if api_key is None:
        api_key = os.getenv("ACOUSTID_API_KEY")

    processor = AudioProcessor(directory=directory, acoustid_api_key=api_key)
    with console.status("Buscando archivos de audio...", spinner="line"):
        files = get_audio_files(directory=directory)

    if not files:
        console.print(
            Panel.fit(
                "No se encontraron archivos de audio en el directorio seleccionado.",
                border_style="yellow",
                title="Aviso",
            )
        )
        raise typer.Exit(1)

    summary_table = Table(box=box.MINIMAL_DOUBLE_HEAD, show_header=False)
    summary_table.add_column("Item", style="bold green")
    summary_table.add_column("Valor", style="white")
    summary_table.add_row("Archivos encontrados", str(len(files)))
    console.print(summary_table)

    if cover:
        console.print(
            Panel.fit(
                "Se utilizará la función de búsqueda e incrustación de portadas de álbum.",
                border_style="magenta",
                title="Portadas",
            )
        )
        try:
            with console.status("Añadiendo portadas...", spinner="bouncingBar"):
                add_covers(directory)
            console.print("[bold green]Portadas añadidas correctamente.[/bold green]")
        except Exception as e:
            console.print(Panel.fit(str(e), border_style="red", title="Error"))
            raise typer.Exit(1)

    if lyrics:
        console.print(
            Panel.fit(
                "Se utilizará la función de búsqueda e incrustación de letras sincronizadas.",
                border_style="magenta",
                title="Letras",
            )
        )
        with console.status("Procesando letras...", spinner="dots2"):
            stats = process_lyrics_and_stats(processor, use_recognition=recognition)

        stats_table = Table(title="Resumen del procesamiento de letras", box=box.SIMPLE)
        stats_table.add_column("Métrica", style="bold cyan")
        stats_table.add_column("Valor", style="white")
        stats_table.add_row("Total de archivos", str(stats.get("total", 0)))
        stats_table.add_row("Reconocidos", str(stats.get("recognized", 0)))
        stats_table.add_row("Letras encontradas", str(stats.get("lyrics_found", 0)))
        stats_table.add_row("Letras incrustadas", str(stats.get("lyrics_embedded", 0)))
        console.print(stats_table)

        results = stats.get("results", {}) or {}
        if results:
            detail = Table(title="Detalle por archivo", box=box.SIMPLE_HEAVY)
            detail.add_column("Archivo", style="bold")
            detail.add_column("Recon.", justify="center")
            detail.add_column("Artista - Título", overflow="fold", style="white")
            detail.add_column("Letras", justify="center")
            detail.add_column("Incrustadas", justify="center")
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
        proceed_rename = typer.confirm("¿Comenzar renombramiento de archivos?")
    else:
        console.print("[bold yellow]Auto-confirmación activada (-y).[/bold yellow]")

    if not proceed_rename:
        console.print(
            Panel.fit(
                "Operación de renombramiento cancelada.",
                border_style="yellow",
                title="Cancelado",
            )
        )
        raise typer.Exit()

    with console.status("Renombrando archivos...", spinner="line"):
        changes = processor.rename_files()

    if changes:
        changes_table = Table(title="Cambios de nombre", box=box.SIMPLE_HEAVY)
        changes_table.add_column("Antes", style="yellow")
        changes_table.add_column("Después", style="green")
        for new_name, old_name in changes.items():
            changes_table.add_row(old_name, new_name)
        console.print(changes_table)

        keep_changes = True
        if not yes:
            keep_changes = typer.confirm("¿Desea mantener los cambios de nombre?")

        if not keep_changes:
            with console.status("Revirtiendo cambios...", spinner="dots"):
                processor.undo_rename(changes)
            console.print(
                Panel.fit(
                    "Los cambios de nombre se han revertido.",
                    border_style="yellow",
                    title="Revertido",
                )
            )
        else:
            console.print(
                Panel.fit(
                    "Los cambios de nombre se han mantenido.",
                    border_style="green",
                    title="Listo",
                )
            )
    else:
        console.print("[bold]No se realizaron cambios de nombre.[/bold]")

    console.rule("[bold green]Proceso completado[/bold green]")
    console.print(
        Panel.fit(
            "El proceso ha concluido correctamente.",
            border_style="green",
            title="Completado",
        )
    )
    if not yes:
        try:
            try:
                import click

                click.pause(info="Presiona Enter para salir...", err=False)
            except Exception:
                input("Presiona Enter para salir...")
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


def add_covers(directory: Path) -> None:
    try:
        import core.install_covers as install_covers

        install_covers.run(str(directory))
        return True
    except ImportError as e:
        raise RuntimeError(
            "No se pudo importar el módulo de instalación de portadas."
        ) from e
    except Exception as e:
        raise RuntimeError(f"Error al ejecutar la instalación de portadas: {e}") from e
