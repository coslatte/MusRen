from typing import Any, Callable, Dict, List, Optional

from rich.console import Console
from rich.table import Table

console = Console()


class CommandMeta:
    def __init__(
        self,
        name: str,
        help: str,
        aliases: Optional[List[str]] = None,
    ):
        self.name = name
        self.help = help
        self.aliases = aliases or []


class BaseCommand:
    name: str = "base"
    help: str = "Base command"
    aliases: List[str] = []

    def __init__(self):
        self.console = console

    def run(self, *args: Any, **kwargs: Any) -> int:
        raise NotImplementedError

    def table(self, title: str) -> Table:
        table = Table(title=title)
        table.add_column("Key", style="bold cyan")
        table.add_column("Value", style="white")
        return table


class CommandRegistry:
    _commands: Dict[str, BaseCommand] = {}

    @classmethod
    def register(cls, command: BaseCommand) -> None:
        cls._commands[command.name] = command

    @classmethod
    def get(cls, name: str) -> Optional[BaseCommand]:
        return cls._commands.get(name)

    @classmethod
    def list_all(cls) -> Dict[str, BaseCommand]:
        return cls._commands

    @classmethod
    def names(cls) -> List[str]:
        return list(cls._commands.keys())


def command(
    name: str,
    help: str,
    aliases: Optional[List[str]] = None,
) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        cls.name = name
        cls.help = help
        cls.aliases = aliases or []
        return cls

    return decorator
