def main() -> None:
    """Entrypoint used by console_scripts and direct execution.

    Imports the CLI implementation lazily so importing `app` doesn't
    require all optional runtime dependencies to be installed.
    """
    from core.cli_typer import app as typer_app

    typer_app()


if __name__ == "__main__":
    main()
