import logging
import os
import re
import threading
import time

from constants.settings import AUDIO_EXTENSIONS


def get_audio_files(directory, recursive=False):
    """
    Gets all audio files in the specified directory.

    Args:
        directory (str): Directory to search
        recursive (bool): Whether to search in subdirectories

    Returns:
        list: List of absolute paths to audio files
    """

    directory = os.path.abspath(directory)
    audio_extensions = AUDIO_EXTENSIONS
    files = []

    if recursive:
        for root, _, filenames in os.walk(directory):
            for f in filenames:
                if f.lower().endswith(audio_extensions):
                    files.append(os.path.join(root, f))
    else:
        for f in os.listdir(directory):
            filepath = os.path.join(directory, f)
            if os.path.isfile(filepath) and f.lower().endswith(audio_extensions):
                files.append(filepath)
    return files


# ── Pause/Resume support ──────────────────────────────────────────────────────


class PauseManager:
    """Manages pause/resume state during processing with keyboard listener."""

    def __init__(self):
        self._paused = threading.Event()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._paused.clear()
        self._thread = threading.Thread(target=self._keyboard_listener, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._paused.clear()
        if self._thread:
            self._thread.join(timeout=1)

    @property
    def is_paused(self):
        return self._paused.is_set()

    def toggle(self):
        if self._paused.is_set():
            self._paused.clear()
        else:
            self._paused.set()

    def wait_if_paused(self, console=None):
        while self._paused.is_set() and not self._stop.is_set():
            if console:
                console.print(
                    "[yellow]⏸ PAUSED — press ESC or P to resume[/yellow]", end="\r"
                )
            time.sleep(0.2)

    def _keyboard_listener(self):
        try:
            import msvcrt

            while not self._stop.is_set():
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode("utf-8", errors="replace").lower()
                    if key in ("\x1b", "p", "c"):
                        self.toggle()
                time.sleep(0.05)
        except ImportError:
            try:
                import select
                import sys
                import tty
                import termios

                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setcbreak(fd)
                    while not self._stop.is_set():
                        if select.select([sys.stdin], [], [], 0.05) == (
                            [sys.stdin],
                            [],
                            [],
                        ):
                            key = sys.stdin.read(1).lower()
                            if key in ("\x1b", "p", "c"):
                                self.toggle()
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except (ImportError, AttributeError):
                pass


_PAUSE_MANAGER = PauseManager()


def get_pause_manager():
    return _PAUSE_MANAGER


# ── Internet connectivity check ───────────────────────────────────────────────


def check_internet_connection(timeout=2):
    """Returns True if a connection to the internet can be established."""
    import socket

    hosts = [
        ("one.one.one.one", 443),
        ("google.com", 443),
        ("cloudflare.com", 443),
    ]
    for host, port in hosts:
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            return True
        except (OSError, socket.gaierror):
            continue
    return False


# ── Logger suppression ────────────────────────────────────────────────────────

_NOISY_LOGGERS = {"syncedlyrics", "syncedlyrics.providers.musixmatch"}


def suppress_noisy_loggers():
    """Silence chatty third-party loggers (syncedlyrics, etc.)."""
    for name in _NOISY_LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(logging.CRITICAL)
        logger.handlers.clear()
        logger.propagate = False


# ── Progress display helpers ────────────────────────────────────────────────

PROGRESS_DESC_WIDTH = 60


def format_progress_desc(text: str, width: int = PROGRESS_DESC_WIDTH) -> str:
    """Strip Rich markup, then pad/truncate to fixed width for stable layout."""
    plain = re.sub(r"\[/?\w+(?:=\w+)?\]", "", text)
    if len(plain) > width:
        return plain[: width - 3] + "..."
    padding = width - len(plain)
    return text + " " * padding if padding > 0 else text
