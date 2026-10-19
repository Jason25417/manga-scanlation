"""Console output, process streaming and small filesystem helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_IS_WINDOWS = os.name == "nt"


class Console:
    """Minimal console writer: optional colour, optional mirror to a log file."""

    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[36m"

    def __init__(self, verbose: bool = False, colour: bool | None = None) -> None:
        self.verbose = verbose
        if colour is None:
            colour = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.colour = colour
        self._mirror: Path | None = None

    def mirror_to(self, path: Path | None) -> None:
        """Append everything printed from now on to ``path`` (None disables)."""
        if path is None:
            self._mirror = None
            return
        self._mirror = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def _emit(self, text: str) -> None:
        print(text, flush=True)
        if self._mirror is not None:
            with self._mirror.open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")

    def _paint(self, code: str, text: str) -> str:
        return f"{code}{text}{self.RESET}" if self.colour else text

    def tag(self, tag: str, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        label = self._paint(self.BLUE, f"[{tag}]")
        self._emit(f"{self._paint(self.DIM, stamp)} {label} {message}")

    def info(self, message: str) -> None:
        self.tag("info", message)

    def step(self, message: str) -> None:
        self.tag("run", message)

    def ok(self, message: str) -> None:
        self.tag("ok", self._paint(self.GREEN, message))

    def warn(self, message: str) -> None:
        self.tag("warn", self._paint(self.YELLOW, message))

    def error(self, message: str) -> None:
        self.tag("error", self._paint(self.RED, message))

    def debug(self, message: str) -> None:
        if self.verbose:
            self.tag("debug", self._paint(self.DIM, message))

    def rule(self, title: str) -> None:
        line = "─" * max(8, 60 - len(title))
        self._emit(self._paint(self.BOLD, f"{title} {line}"))


def decode_line(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").rstrip("\r\n")


def display_width(text: str) -> int:
    """Terminal columns used by ``text`` (CJK glyphs occupy two)."""
    import unicodedata

    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1
    return width


def pad(text: str, width: int) -> str:
    """Left-align ``text`` in ``width`` terminal columns."""
    return text + " " * max(0, width - display_width(text))


def table(rows: list[list[str]], *, console: Console | None = None) -> list[str]:
    """Render a simple aligned table and return its lines."""
    if not rows:
        return []
    columns = max(len(row) for row in rows)
    widths = [0] * columns
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], display_width(cell))
    lines = []
    for row in rows:
        cells = [pad(cell, widths[index]) for index, cell in enumerate(row)]
        lines.append("  ".join(cells).rstrip())
    if console is not None:
        for line in lines:
            console._emit(line)
    return lines



def stream_command(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    console: Console | None = None,
    echo: bool = True,
) -> int:
    """Run a command, relaying its output line by line. Returns the exit code."""
    console = console or Console()
    console.debug("exec: " + " ".join(argv))
    creationflags = 0
    if _IS_WINDOWS:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        if echo:
            console._emit("    " + decode_line(raw))
    return proc.wait()


def human_bytes(count: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(count) < 1024 or unit == "TiB":
            return f"{count:.1f} {unit}" if unit != "B" else f"{int(count)} B"
        count /= 1024
    return f"{count:.1f} TiB"


def count_images(directory: Path, exts: set[str] | None = None) -> int:
    from .config import IMAGE_EXTS

    exts = exts or IMAGE_EXTS
    if not directory.is_dir():
        return 0
    return sum(
        1 for item in directory.iterdir() if item.is_file() and item.suffix.lower() in exts
    )


def list_images(directory: Path, exts: set[str] | None = None) -> list[Path]:
    from .config import IMAGE_EXTS

    exts = exts or IMAGE_EXTS
    if not directory.is_dir():
        return []
    return sorted(
        item for item in directory.iterdir()
        if item.is_file() and item.suffix.lower() in exts
    )


def safe_name(name: str) -> str:
    """Strip characters that cannot appear in a Windows file name."""
    cleaned = "".join(ch for ch in name if ch not in '<>:"/\\|?*').strip(" .")
    return cleaned or "book"


def free_space(path: Path) -> int:
    try:
        return shutil.disk_usage(str(path)).free
    except OSError:
        return 0
