from pathlib import Path

from PIL import Image

from manga_scanlation import compress, pipeline
from manga_scanlation.config import load
from manga_scanlation.util import Console


def write_config(tmp_path: Path, extra: str = "") -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "engine:\n  type: passthrough\nsource:\n  type: local\n" + extra,
        encoding="utf-8",
    )
    return config_path


def make_png(path: Path, size: tuple[int, int] = (400, 600)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)
    return path


def test_compress_replaces_png_with_webp(tmp_path):
    config = load(write_config(tmp_path))
    config.paths.ensure()
    book = config.paths.output / "book"
    book.mkdir(parents=True)
    for index in range(3):
        make_png(book / f"{index:04d}.png")

    converted, before, after = compress.compress_book(book, config, Console(colour=False))

    assert converted == 3
    assert before > 0 and after > 0
    assert len(list(book.glob("*.webp"))) == 3
    assert not list(book.glob("*.png"))


def test_compress_keeps_source_when_asked(tmp_path):
    config = load(write_config(tmp_path, "output:\n  keep_source: true\n"))
    book = config.paths.output / "book"
    book.mkdir(parents=True, exist_ok=True)
    make_png(book / "0001.png")

    compress.compress_book(book, config, Console(colour=False))
    assert (book / "0001.png").is_file()
    assert (book / "0001.webp").is_file()


def test_compress_is_idempotent(tmp_path):
    config = load(write_config(tmp_path))
    book = config.paths.output / "book"
    book.mkdir(parents=True, exist_ok=True)
    make_png(book / "0001.png")

    console = Console(colour=False)
    assert compress.compress_book(book, config, console)[0] == 1
    # Nothing left to convert on the second pass.
    assert compress.compress_book(book, config, console)[0] == 0


def test_passthrough_run_processes_book_then_skips_it(tmp_path):
    config = load(write_config(tmp_path))
    config.paths.ensure()
    book = config.paths.source / "demo"
    book.mkdir(parents=True)
    for index in range(2):
        make_png(book / f"{index:04d}.png")

    console = Console(colour=False)
    first = pipeline.run(config, console, download=False)
    assert [item.status for item in first.results] == ["done"]
    assert first.results[0].pages_out == 2

    produced = list((config.paths.output / "demo").glob("*"))
    assert len(produced) == 2
    assert all(path.suffix == ".webp" for path in produced)
    stamps = {path: path.stat().st_mtime_ns for path in produced}

    second = pipeline.run(config, console, download=False)
    assert second.results[0].ok
    assert second.results[0].pages_out == 2
    # Already done and complete, so the engine was not called again.
    assert {path: path.stat().st_mtime_ns for path in produced} == stamps
