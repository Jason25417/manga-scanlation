"""Per-book progress, so a rerun resumes instead of redoing work."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"

STATUS_ORDER = {PENDING: 0, RUNNING: 1, FAILED: 2, DONE: 3}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class BookState:
    status: str = PENDING
    pages_src: int = 0
    pages_out: int = 0
    attempts: int = 0
    elapsed: float = 0.0
    updated: str = ""
    error: str = ""


class StateStore:
    """A tiny JSON store keyed by book name. Written atomically."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._books: dict[str, BookState] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt state file must never abort a run: worst case we redo
            # work, which is idempotent anyway.
            return
        books = raw.get("books") if isinstance(raw, dict) else None
        if not isinstance(books, dict):
            return
        valid = {f.name for f in fields(BookState)}
        for name, payload in books.items():
            if not isinstance(payload, dict):
                continue
            clean = {k: v for k, v in payload.items() if k in valid}
            try:
                self._books[str(name)] = BookState(**clean)
            except TypeError:
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "books": {name: asdict(state) for name, state in self._books.items()},
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, name: str) -> BookState:
        return self._books.setdefault(name, BookState())

    def names(self) -> list[str]:
        return list(self._books)

    def update(self, name: str, **changes) -> BookState:
        state = self.get(name)
        for key, value in changes.items():
            if not hasattr(state, key):
                raise KeyError(f"unknown book state field: {key}")
            setattr(state, key, value)
        state.updated = _now()
        return state
