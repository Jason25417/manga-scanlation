from pathlib import Path

from manga_scanlation.config import load
from manga_scanlation.sources import find_books, import_local
from manga_scanlation.util import Console


def make_config(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
engine:
  type: passthrough
source:
  type: local
""",
        encoding="utf-8",
    )
    return load(config_path)


def touch_book(root: Path, name: str, pages: int = 2) -> Path:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(pages):
        (folder / f"{index:04d}.jpg").write_bytes(b"x")
    return folder


def test_find_books_ignores_folders_without_images(tmp_path):
    config = make_config(tmp_path)
    config.paths.source.mkdir(parents=True, exist_ok=True)
    touch_book(config.paths.source, "book-one", 3)
    (config.paths.source / "empty-folder").mkdir()
    (config.paths.source / "notes.txt").write_text("not a book", encoding="utf-8")

    books = find_books(config)
    assert [book.name for book in books] == ["book-one"]
    assert books[0].pages == 3


def test_find_books_is_case_insensitively_sorted(tmp_path):
    config = make_config(tmp_path)
    config.paths.source.mkdir(parents=True, exist_ok=True)
    touch_book(config.paths.source, "beta")
    touch_book(config.paths.source, "Alpha")
    assert [book.name for book in find_books(config)] == ["Alpha", "beta"]


def test_import_local_copies_once_and_is_idempotent(tmp_path):
    config = make_config(tmp_path)
    config.paths.ensure()
    touch_book(config.paths.inbox, "demo", 2)

    console = Console(colour=False)
    assert import_local(config, console) == 2
    assert (config.paths.source / "demo" / "0000.jpg").is_file()

    # Second import must not report anything new.
    assert import_local(config, console) == 0


def test_import_local_move_removes_source_folder(tmp_path):
    config = make_config(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
engine:
  type: passthrough
source:
  type: local
  local:
    move: true
""",
        encoding="utf-8",
    )
    config = load(config_path)
    config.paths.ensure()
    touch_book(config.paths.inbox, "moved", 1)

    import_local(config, Console(colour=False))
    assert not (config.paths.inbox / "moved").exists()
    assert (config.paths.source / "moved" / "0000.jpg").is_file()
