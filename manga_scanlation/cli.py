"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, doctor, pipeline, preview
from .config import ConfigError, load, summary
from .sources import find_books
from .state import StateStore
from .util import Console, table


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mscan",
        description="Batch translate and letter comic pages, one folder per book.",
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug details")
    parser.add_argument("--no-color", action="store_true", help="disable coloured output")
    parser.add_argument("--version", action="version", version=f"manga-scanlation {__version__}")

    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser(
        "run",
        help="download if configured, then translate and letter every pending book",
    )
    run.add_argument("--only", nargs="+", metavar="BOOK", help="process only these book folders")
    run.add_argument("--redo", action="store_true", help="rebuild books already marked done")
    run.add_argument("--dry-run", action="store_true", help="print the engine command, do nothing")
    run.add_argument("--no-download", action="store_true", help="skip the download step")
    run.add_argument("--limit", type=int, default=0, help="stop after N books")

    sub.add_parser("download", help="only fetch pages (requires source.type: gallerydl)")

    translate = sub.add_parser("translate", help="only translate; no download")
    translate.add_argument("--only", nargs="+", metavar="BOOK")
    translate.add_argument("--redo", action="store_true")
    translate.add_argument("--dry-run", action="store_true")
    translate.add_argument("--limit", type=int, default=0)

    sub.add_parser("doctor", help="check the environment before a long run")
    sub.add_parser("config", help="print the resolved configuration")
    sub.add_parser("status", help="list books with their progress")

    sub.add_parser("compress", help="convert finished PNG pages to the configured format")

    compare = sub.add_parser("compare", help="render a side-by-side preview sheet")
    compare.add_argument("--book", help="book folder name (default: all)")
    compare.add_argument("--pages", type=int, default=4, help="pages per sheet")

    return parser


def _config(args: argparse.Namespace):
    return load(args.config)


def cmd_run(args: argparse.Namespace, console: Console) -> int:
    config = _config(args)
    report = pipeline.run(
        config,
        console,
        only=args.only,
        redo=args.redo,
        dry_run=args.dry_run,
        download=not args.no_download,
        limit=args.limit,
    )
    return 0 if not report.failed else 1


def cmd_download(args: argparse.Namespace, console: Console) -> int:
    from .sources import download_gallerydl, prepare

    config = _config(args)
    if config.source.type != "gallerydl":
        console.error("source.type is not 'gallerydl'; nothing to download")
        return 2
    books = prepare(config, console)
    console.info(f"{len(books)} book(s) available")
    return 0


def cmd_translate(args: argparse.Namespace, console: Console) -> int:
    config = _config(args)
    report = pipeline.run(
        config,
        console,
        only=args.only,
        redo=args.redo,
        dry_run=args.dry_run,
        download=False,
        limit=args.limit,
    )
    return 0 if not report.failed else 1


def cmd_doctor(args: argparse.Namespace, console: Console) -> int:
    return doctor.report(_config(args), console)


def cmd_config(args: argparse.Namespace, console: Console) -> int:
    config = _config(args)
    rows = [["key", "value"]] + [[key, value] for key, value in summary(config)]
    table(rows, console=console)
    return 0


def cmd_status(args: argparse.Namespace, console: Console) -> int:
    config = _config(args)
    books = find_books(config)
    store = StateStore(config.paths.state)
    if not books:
        console.warn(f"no books with images under {config.paths.source}")
        return 0
    rows = [["book", "pages", "translated", "status", "note"]]
    for book in books:
        record = store.get(book.name)
        translated = pipeline.output_pages(config, book)
        rows.append(
            [
                book.name,
                str(book.pages),
                str(translated),
                record.status,
                record.error or "",
            ]
        )
    table(rows, console=console)
    return 0


def cmd_compress(args: argparse.Namespace, console: Console) -> int:
    from . import compress

    config = _config(args)
    if not config.output.compress or config.output.format == "png":
        console.info("output.compress is off (or format is png); nothing to do")
        return 0
    compress.compress_all(config, console)
    return 0


def cmd_compare(args: argparse.Namespace, console: Console) -> int:
    config = _config(args)
    made = preview.make(config, console, args.book, pages=max(1, args.pages))
    return 0 if made else 1


def _force_utf8_output() -> None:
    """Make our own output encoding deterministic.

    Chinese book titles are common in this domain, and a Windows console can
    otherwise hand us the legacy code page and mangle them.
    """
    for stream in (sys.stdout, sys.stderr):
        configure = getattr(stream, "reconfigure", None)
        if configure is None:
            continue
        try:
            configure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    console = Console(verbose=args.verbose, colour=False if args.no_color else None)
    handlers = {
        "run": cmd_run,
        "download": cmd_download,
        "translate": cmd_translate,
        "doctor": cmd_doctor,
        "config": cmd_config,
        "status": cmd_status,
        "compare": cmd_compare,
        "compress": cmd_compress,
    }
    try:
        return handlers[args.command](args, console)
    except ConfigError as exc:
        console.error(str(exc))
        return 2
    except KeyboardInterrupt:
        console.warn("interrupted")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
