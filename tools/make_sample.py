"""Generate a synthetic test book, so the pipeline can be exercised end to end
without any real material.

    python tools/make_sample.py data/source/sample-book --pages 2

The pages are plain white with black lettering, which is easy for the detector and
makes it obvious whether text was erased and whether the translation landed in the
right place.
"""

from __future__ import annotations

import argparse
from pathlib import Path

LINES = [
    ("WHERE AM I?", "THIS PLACE LOOKS STRANGE...", "I SHOULD HAVE STAYED HOME."),
    ("YOU FINALLY WOKE UP.", "WE HAVE BEEN WAITING FOR HOURS.", "GET DRESSED, WE ARE LEAVING."),
    ("THE DOOR WAS OPEN.", "SOMEONE HAS BEEN HERE.", "WE SHOULD NOT STAY."),
]
SOUND_EFFECT = "RUSTLE"


def find_font() -> str | None:
    """Return a font path that can render CJK, if the system has one."""
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def build(out: Path, pages: int, width: int = 1200, height: int = 1700) -> int:
    from PIL import Image, ImageDraw, ImageFont

    out.mkdir(parents=True, exist_ok=True)
    font_path = find_font()
    big = ImageFont.truetype(font_path, 62) if font_path else ImageFont.load_default()
    small = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()

    written = 0
    for index in range(pages):
        lines = LINES[index % len(LINES)]
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        y = 260
        for line in lines:
            draw.rectangle([110, y - 18, width - 110, y + 96], fill="white", outline="black", width=4)
            draw.text((150, y), line, font=big, fill="black")
            y += 300
        draw.ellipse([700, 1200, 1100, 1500], outline="black", width=6)
        draw.text((760, 1300), SOUND_EFFECT, font=small, fill="black")
        image.save(out / f"{index + 1:04d}.png")
        written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dest", help="folder to write pages into")
    parser.add_argument("--pages", type=int, default=2)
    args = parser.parse_args()
    count = build(Path(args.dest), max(1, args.pages))
    print(f"wrote {count} page(s) to {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
