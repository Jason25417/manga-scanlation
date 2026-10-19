"""Where pages come from.

Two adapters, no assumptions about a particular site:

* ``local``    -- books are folders you already have
* ``gallerydl`` -- gallery-dl fetches them; that covers every site gallery-dl
                   supports, which is the point: the downloader is a general
                   tool, not something wired to one gallery.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import IMAGE_EXTS, Config
from .util import Console, count_images, list_images, stream_command


@dataclass(frozen=True)
class Book:
    name: str
    source_dir: Path
    output_dir: Path

    @property
    def pages(self) -> int:
        return count_images(self.source_dir)

    @property
    def images(self) -> list[Path]:
        return list_images(self.source_dir)


def _book_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        (item for item in root.iterdir() if item.is_dir() and not item.name.startswith(".")),
        key=lambda item: item.name.lower(),
    )


def find_books(config: Config) -> list[Book]:
    """Every sub-folder of paths.source that actually contains images."""
    books: list[Book] = []
    for directory in _book_dirs(config.paths.source):
        if count_images(directory) == 0:
            continue
        books.append(
            Book(
                name=directory.name,
                source_dir=directory,
                output_dir=config.paths.output / directory.name,
            )
        )
    return books


def import_local(config: Config, console: Console) -> int:
    """Copy (or move) books from paths.inbox into paths.source.

    Idempotent: files that already exist with the same size are left alone, so
    interrupting and rerunning is safe.
    """
    if config.paths.inbox.resolve() == config.paths.source.resolve():
        console.debug("inbox and source are the same folder; nothing to import")
        return 0

    imported = 0
    console.step(f"importing from {config.paths.inbox}")
    for directory in _book_dirs(config.paths.inbox):
        images = list_images(directory)
        if not images:
            continue
        dest_dir = config.paths.source / directory.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for image in images:
            target = dest_dir / image.name
            if target.is_file() and target.stat().st_size == image.stat().st_size:
                continue
            shutil.copy2(image, target)
            copied += 1
        if copied:
            console.info(f"imported {copied} page(s) from {directory.name}")
            imported += copied
        if config.source.move and copied == len(images):
            shutil.rmtree(directory, ignore_errors=True)

    # A folder that is itself a flat pile of images counts as one book.
    flat = [item for item in config.paths.inbox.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_EXTS] \
        if config.paths.inbox.is_dir() else []
    if flat:
        console.warn(
            f"{config.paths.inbox} contains {len(flat)} loose image(s); "
            "expected one folder per book -- wrapping them into a single book"
        )
        dest_dir = config.paths.source / config.paths.inbox.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        for image in flat:
            target = dest_dir / image.name
            if not target.exists():
                shutil.copy2(image, target)
                imported += 1

    console.ok(f"import finished ({imported} new page(s))")
    return imported


def download_gallerydl(config: Config, console: Console) -> int:
    """Fetch pages with gallery-dl, if that source is configured."""
    source = config.source
    executable = shutil.which(source.executable) or source.executable
    argv: list[str] = [executable]
    if source.config is not None:
        argv += ["--config", str(source.config)]
    # Force the destination even when the gallery-dl config says otherwise.
    argv += ["-o", f"extractor.base-directory={config.paths.source}"]

    if source.links_file is not None:
        argv += ["--input-file", str(source.links_file)]
    elif source.urls:
        argv += list(source.urls)
    else:
        console.warn("source.type is gallerydl but no links were configured; skipping download")
        return -1

    argv += list(source.extra_args)
    console.step("downloading with gallery-dl")
    console.debug("exec: " + " ".join(argv))
    code = stream_command(argv, cwd=config.root, env=None, console=console)
    if code == 0:
        console.ok("download finished")
    else:
        console.error(f"gallery-dl exited with code {code}")
    return code


def prepare(config: Config, console: Console, *, download: bool = True) -> list[Book]:
    """Make sure pages are on disk, then list the books to process."""
    config.paths.ensure()
    if config.source.type == "gallerydl" and download:
        download_gallerydl(config, console)
    elif config.source.type == "local":
        import_local(config, console)
    return find_books(config)
