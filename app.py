def main() -> None:
    """Entrypoint used by console_scripts and direct execution.

    Imports the CLI implementation lazily so importing `app` doesn't
    require all optional runtime dependencies to be installed.
    """
    from core.cli import Cli

    cli = Cli()
    cli.main()


if __name__ == "__main__":
    main()
