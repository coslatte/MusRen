import sys
import warnings

from constants.info import MUSIC_RENAMER_VERSION


def main(interactive: bool = True) -> None:
    if "--version" in sys.argv or "-v" in sys.argv:
        print(f"musren {MUSIC_RENAMER_VERSION}")
        return

    warnings.filterwarnings("ignore", category=SyntaxWarning, module="pydub")

    if interactive and len(sys.argv) == 1:
        from core.cli.shell import cli as musren_shell

        musren_shell()
    else:
        from core.cli.shell import InteractiveShell

        shell = InteractiveShell()
        if len(sys.argv) > 1:
            cmd = " ".join(sys.argv[1:])
            shell.run_command(cmd)
        else:
            shell.run()


if __name__ == "__main__":
    main()
