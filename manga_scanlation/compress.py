"""Post-processing: PNG from the engine into a smaller finished format.

Kept as its own step, not folded into the engine call. Two reasons:

* manga-image-translator only allows lossy quality control for JPEG, so asking it
  for a quality-controlled WebP is not possible;
* compressing once, after the last lossless step, means no lossy generation ever
  becomes the input of another.
"""

from __future__ import annotations

from pathlib import Path

from .config import IMAGE_EXTS, Config
from .util import Console, human_bytes

_PIL_FORMAT = {"webp": "WEBP", "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG"}


def _targets(directory: Path) -> list[Path]:
    """Source files worth converting: images whose suffix is not the target."""
    return sorted(
        item for item in directory.iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_EXTS
    )


def compress_book(directory: Path, config: Config, console: Console) -> tuple[int, int, int]:
    """Convert one book folder in place.

    Returns (converted, bytes_before, bytes_after).
    """
    from PIL import Image

    output = config.output
    if not output.compress or output.format == "png":
        return (0, 0, 0)

    pil_format = _PIL_FORMAT[output.format]
    target_suffix = "." + output.format
    converted = 0
    before = 0
    after = 0

    for source in _targets(directory):
        if source.suffix.lower() == target_suffix:
            continue
        target = source.with_suffix(target_suffix)
        if target.exists():
            # Previous run already produced it; drop the intermediate.
            if not output.keep_source:
                source.unlink(missing_ok=True)
            continue
        size_before = source.stat().st_size
        try:
            with Image.open(source) as image:
                frame = image.convert("RGBA") if image.mode in {"P", "LA"} else image.convert("RGB")
                save_kwargs = {}
                if pil_format in {"WEBP", "JPEG"}:
                    save_kwargs["quality"] = output.quality
                if pil_format == "WEBP":
                    save_kwargs["method"] = 6
                frame.save(target, pil_format, **save_kwargs)
        except OSError as exc:
            console.warn(f"{source.name}: could not convert ({exc})")
            continue
        size_after = target.stat().st_size
        before += size_before
        after += size_after
        converted += 1
        if not output.keep_source:
            source.unlink(missing_ok=True)

    if converted:
        saved = before - after
        percent = (saved / before * 100) if before else 0
        console.info(
            f"compressed {converted} page(s): {human_bytes(before)} -> "
            f"{human_bytes(after)} ({percent:.0f}% smaller)"
        )
    return (converted, before, after)


def compress_all(config: Config, console: Console) -> int:
    """Convert every book folder under paths.output."""
    from .sources import find_books

    total = 0
    for book in find_books(config):
        if not book.output_dir.is_dir():
            continue
        converted, _, _ = compress_book(book.output_dir, config, console)
        total += converted
    if not total:
        console.info("nothing to compress (already converted, or compression is off)")
    return total


def final_extension(config: Config) -> str:
    """Suffix of the finished artifact for this configuration."""
    if config.output.compress and config.output.format != "png":
        return "." + config.output.format
    return ".png"
