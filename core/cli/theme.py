from rich.style import Style

PALETTE = {
    "primary": "cyan",
    "secondary": "magenta",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "info": "blue",
    "muted": "bright_black",
}

COLORS = {
    "primary": "#00B4D8",
    "secondary": "#E91E63",
    "success": "#4CAF50",
    "warning": "#FFC107",
    "error": "#F44336",
    "info": "#2196F3",
    "muted": "#757575",
    "background": "#1E1E1E",
    "surface": "#2D2D2D",
}

STYLES = {
    "title": Style(color="cyan", bold=True),
    "subtitle": Style(color="cyan", bold=False),
    "success": Style(color="green", bold=True),
    "warning": Style(color="yellow", bold=False),
    "error": Style(color="red", bold=True),
    "info": Style(color="blue", bold=False),
    "muted": Style(color="bright_black"),
    "header": Style(color="cyan", bold=True),
    "key": Style(color="cyan", bold=False),
    "value": Style(color="white", bold=False),
    "path": Style(color="magenta", bold=False),
    "command": Style(color="green", bold=True),
    "option": Style(color="yellow", bold=False),
    "flag": Style(color="magenta", bold=False),
}

PANEL_STYLES = {
    "primary": "cyan",
    "secondary": "magenta",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "info": "blue",
}

TABLE_STYLES = {
    "box": "simple_heavy",
    "header_style": "bold cyan",
    "row_styles": ["", "on #2D2D2D"],
}


class Theme:
    def __init__(self, dark: bool = True):
        self.dark = dark
        self.palette = PALETTE
        self.colors = COLORS
        self.styles = STYLES
        self.panel_styles = PANEL_STYLES
        self.table_styles = TABLE_STYLES

    def get_style(self, name: str) -> Style:
        return self.styles.get(name, STYLES["muted"])

    def get_color(self, name: str) -> str:
        return self.colors.get(name, COLORS["muted"])

    def get_panel_style(self, name: str) -> str:
        return self.panel_styles.get(name, "cyan")


DEFAULT_THEME = Theme()

theme = DEFAULT_THEME
