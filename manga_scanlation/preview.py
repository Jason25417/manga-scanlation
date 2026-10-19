"""Side-by-side preview sheets: a page of originals next to their translations.

Eyeballing the result is the only reliable quality gate for this kind of
pipeline, and doing it in a file browser means opening 2x N images. This builds
one image per book instead.
"""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .util import Console, count_images, list_images, safe_name

GAP = 12
BACKGROUND = (255, 255, 255)


def build_sheet(
    originals: list[Path],
    translations: list[Path],
    dest: Path,
    *,
    target_height: int = 1200,
) -> Path:
    from PIL import Image

    pairs: list[tuple[Image.Image, Image.Image | None]] = []
    for index, original_path in enumerate(originals):
        translated_path = translations[index] if index < len(translations) else None
        with Image.open(original_path) as raw:
            original = raw.convert("RGB")
        translated = None
        if translated_path is not None:
            with Image.open(translated_path) as raw:
                translated = raw.convert("RGB")
        pairs.append((original, translated))

    scaled: list[tuple[Image.Image, Image.Image | None]] = []
    for original, translated in pairs:
        ratio = target_height / original.height
        width = max(1, int(original.width * ratio))
        left = original.resize((width, target_height), Image.LANCZOS)
        right = None
        if translated is not None:
            right = translated.resize((width, target_height), Image.LANCZOS)
        scaled.append((left, right))

    column_width = max(left.width for left, _ in scaled)
    columns = 2 if any(right is not None for _, right in scaled) else 1
    sheet_width = column_width * columns + GAP * (columns + 1)
    sheet_height = (target_height + GAP) * len(scaled) + GAP

    sheet = Image.new("RGB", (sheet_width, sheet_height), BACKGROUND)
    y = GAP
    for left, right in scaled:
        sheet.paste(left, (GAP, y))
        if right is not None:
            sheet.paste(right, (GAP * 2 + column_width, y))
        y += target_height + GAP

    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    return dest


def make(config: Config, console: Console, book: str | None, pages: int = 4) -> Path | None:
    from .sources import find_books

    books = find_books(config)
    if book:
        books = [item for item in books if item.name.casefold() == book.casefold()]
        if not books:
            console.error(f"no book named {book!r}")
            return None
    if not books:
        console.error(f"no books with images under {config.paths.source}")
        return None

    made: list[Path] = []
    for item in books:
        originals = item.images[:pages]
        translations = list_images(item.output_dir)
        if not translations:
            console.warn(f"{item.name}: no translated pages yet, skipping")
            continue
        translations = translations[: len(originals)]
        dest = config.paths.reports / f"compare-{safe_name(item.name)}.png"
        build_sheet(originals, translations, dest)
        console.ok(f"{item.name}: {dest}")
        made.append(dest)

    console.info(f"{count_images(books[0].source_dir)} pages in the first book, showed {pages}")
    return made[0] if made else None
