"""Batch orchestration: one book at a time, resumable, never silently skipping."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import compress
from . import state as st
from .config import Config
from .engines import MITEngine, PassthroughEngine, build
from .sources import Book, find_books, prepare
from .state import StateStore
from .util import Console, count_images, safe_name, table


def output_pages(config: Config, book: Book) -> int:
    """Finished pages: count the artifact extension this config produces."""
    return count_images(book.output_dir, {compress.final_extension(config)})


@dataclass
class BookResult:
    name: str
    status: str
    pages_src: int = 0
    pages_out: int = 0
    elapsed: float = 0.0
    error: str = ""
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return self.status == st.DONE


@dataclass
class RunReport:
    results: list[BookResult] = field(default_factory=list)

    @property
    def failed(self) -> list[BookResult]:
        return [item for item in self.results if not item.ok]

    @property
    def done(self) -> list[BookResult]:
        return [item for item in self.results if item.ok]


def _book_log(config: Config, book: Book) -> Path:
    return config.paths.logs / f"{safe_name(book.name)}.log"


def process_book(
    config: Config,
    engine: MITEngine | PassthroughEngine,
    store: StateStore,
    book: Book,
    console: Console,
    *,
    redo: bool = False,
    dry_run: bool = False,
) -> BookResult:
    """Run one book through the engine. Returns a result, never raises."""
    pages_src = book.pages
    record = store.get(book.name)

    if not redo and record.status == st.DONE and output_pages(config, book) >= pages_src > 0:
        console.debug(f"{book.name}: already done, skipping")
        return BookResult(
            name=book.name,
            status=st.DONE,
            pages_src=pages_src,
            pages_out=output_pages(config, book),
            elapsed=record.elapsed,
        )

    if pages_src == 0:
        console.warn(f"{book.name}: no images found, skipping")
        return BookResult(name=book.name, status=st.FAILED, error="no images")

    console.rule(f"{book.name}  ({pages_src} pages)")

    if dry_run:
        argv = engine.command(book.source_dir, book.output_dir) if isinstance(engine, MITEngine) else ["<passthrough>"]
        console.info("dry run, command would be:")
        for part in argv:
            console._emit(f"    {part}")
        return BookResult(name=book.name, status=st.DONE, pages_src=pages_src, dry_run=True)

    store.update(book.name, status=st.RUNNING, pages_src=pages_src, error="")
    store.save()

    started = time.time()
    attempts = max(1, config.batch.retries + 1)
    last_error = ""

    for attempt in range(1, attempts + 1):
        if attempt > 1:
            console.warn(f"{book.name}: retry {attempt}/{attempts} after: {last_error}")
        console.mirror_to(_book_log(config, book))
        try:
            run = engine.run(book.source_dir, book.output_dir, console, _book_log(config, book))
        finally:
            console.mirror_to(None)
        code = run.returncode
        pages_png = count_images(book.output_dir, {".png"})
        if code == 0 and pages_png >= pages_src:
            if config.output.compress:
                console.mirror_to(_book_log(config, book))
                try:
                    compress.compress_book(book.output_dir, config, console)
                finally:
                    console.mirror_to(None)
            pages_out = output_pages(config, book)
            elapsed = time.time() - started
            store.update(
                book.name,
                status=st.DONE,
                pages_src=pages_src,
                pages_out=pages_out,
                elapsed=round(elapsed, 1),
                attempts=attempt,
                error="",
            )
            store.save()
            console.ok(f"{book.name}: {pages_out}/{pages_src} pages in {elapsed / 60:.1f} min")
            return BookResult(
                name=book.name,
                status=st.DONE,
                pages_src=pages_src,
                pages_out=pages_out,
                elapsed=elapsed,
            )
        if code == 0:
            # Exit code 0 but fewer pages than we started with. Rerunning resumes:
            # the engine skips pages it already produced.
            last_error = f"only {pages_png}/{pages_src} pages written"
        else:
            last_error = f"engine exit code {code}"
        console.error(f"{book.name}: {last_error}")

    elapsed = time.time() - started
    store.update(
        book.name,
        status=st.FAILED,
        pages_src=pages_src,
        pages_out=output_pages(config, book),
        elapsed=round(elapsed, 1),
        attempts=attempts,
        error=last_error,
    )
    store.save()
    return BookResult(
        name=book.name,
        status=st.FAILED,
        pages_src=pages_src,
        pages_out=output_pages(config, book),
        elapsed=elapsed,
        error=last_error,
    )


def run(
    config: Config,
    console: Console,
    *,
    only: list[str] | None = None,
    redo: bool = False,
    dry_run: bool = False,
    download: bool = True,
    limit: int = 0,
) -> RunReport:
    config.paths.ensure()
    engine = build(config)

    books = prepare(config, console, download=download) if download or config.source.type == "local" \
        else find_books(config)
    if only:
        wanted = {name.casefold() for name in only}
        books = [book for book in books if book.name.casefold() in wanted]
        missing = wanted - {book.name.casefold() for book in books}
        for name in sorted(missing):
            console.warn(f"no book named {name!r} under {config.paths.source}")
    effective_limit = limit or config.batch.limit
    if effective_limit:
        books = books[:effective_limit]

    if not books:
        console.warn(f"no books found under {config.paths.source}")
        console.info("put one folder of images per book there, or check source.type")
        return RunReport()

    console.info(f"{len(books)} book(s) queued")
    engine.prepare(console)

    store = StateStore(config.paths.state)
    report = RunReport()
    for book in books:
        result = process_book(config, engine, store, book, console, redo=redo, dry_run=dry_run)
        report.results.append(result)
        if not result.ok and config.batch.fail_fast:
            console.error("batch.fail_fast is on, stopping")
            break

    print_summary(report, console)
    return report


def print_summary(report: RunReport, console: Console) -> None:
    if not report.results:
        return
    console.rule("summary")
    rows = [["book", "pages", "status", "time"]]
    for item in report.results:
        pages = "-" if item.dry_run else f"{item.pages_out}/{item.pages_src}"
        minutes = f"{item.elapsed / 60:.1f}m" if item.elapsed else "-"
        status = "dry-run" if item.dry_run else (item.status if item.ok else f"{item.status}: {item.error}")
        rows.append([item.name, pages, status, minutes])
    table(rows, console=console)
    total = len(report.results)
    console.info(f"{len(report.done)}/{total} succeeded")
