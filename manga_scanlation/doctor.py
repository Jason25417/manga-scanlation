"""`mscan doctor`: find the boring reasons a run would fail, before it fails."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import Config, IMAGE_EXTS
from .util import Console, human_bytes, free_space, table

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass
class Check:
    label: str
    status: str
    detail: str = ""
    hint: str = ""


def _check_python() -> Check:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 10):
        return Check("python", FAIL, version, "manga-scanlation needs Python 3.10+")
    return Check("python", OK, version)


def _check_engine_python(config: Config) -> Check:
    python = config.mit.python
    if not python.is_file():
        return Check(
            "engine python",
            FAIL,
            str(python),
            "point engine.mit.python at the interpreter where manga-image-translator is installed",
        )
    try:
        proc = subprocess.run(
            [str(python), "-c", "import manga_translator"],
            cwd=str(config.mit.root) if config.mit.root.is_dir() else None,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("engine python", FAIL, str(python), f"could not run it: {exc}")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["unknown error"]
        return Check(
            "engine python",
            FAIL,
            str(python),
            f"'import manga_translator' failed: {tail[0]}",
        )
    return Check("engine python", OK, str(python))


def _check_mit_root(config: Config) -> Check:
    if not config.mit.root.is_dir():
        return Check(
            "manga-image-translator",
            FAIL,
            str(config.mit.root),
            "clone it: git clone https://github.com/zyddnys/manga-image-translator vendor/manga-image-translator",
        )
    models = config.mit.root / "models"
    if not models.is_dir():
        return Check(
            "models",
            WARN,
            str(models),
            "not downloaded yet; the first run fetches a few hundred MB of weights",
        )
    size = sum(f.stat().st_size for f in models.rglob("*") if f.is_file())
    return Check("models", OK, human_bytes(size))


def _check_base_config(config: Config) -> Check:
    path = config.mit.base_config
    if not path.is_file():
        return Check(
            "mit config",
            FAIL,
            str(path),
            "copy config/mit-config.example.json to config/mit-config.json",
        )
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return Check("mit config", FAIL, str(path), f"invalid JSON: {exc}")
    return Check("mit config", OK, str(path))


def _check_font(config: Config) -> Check:
    font = config.mit.font
    if font is None:
        return Check("font", WARN, "not set", "without it the renderer picks a font that may lack CJK glyphs")
    if not font.is_file():
        return Check("font", FAIL, str(font), "download a CJK font and point engine.mit.font at it")
    return Check("font", OK, font.name)


def _check_dicts(config: Config) -> list[Check]:
    checks: list[Check] = []
    for label, path in (
        ("pre-dict", config.translation.pre_dict),
        ("post-dict", config.translation.post_dict),
    ):
        if path is None:
            checks.append(Check(label, WARN, "not set (optional)"))
            continue
        if not path.is_file():
            checks.append(Check(label, FAIL, str(path), "file does not exist"))
            continue
        problems: list[str] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//")):
                continue
            content = stripped.split("#")[0].split("//")[0].strip()
            parts = content.split()
            if len(parts) not in (1, 2):
                problems.append(f"line {number}: expected 1 or 2 fields, got {len(parts)}")
                continue
            try:
                re.compile(parts[0])
            except re.error as exc:
                problems.append(f"line {number}: bad regex ({exc})")
            if len(parts) == 2 and " " in parts[1]:
                problems.append(f"line {number}: replacement cannot contain spaces")
        if problems:
            checks.append(Check(label, FAIL, f"{len(problems)} problem(s)", "; ".join(problems[:3])))
        else:
            checks.append(Check(label, OK, path.name))
    return checks


def _check_gpt_config(config: Config) -> Check:
    path = config.translation.gpt_config
    if path is None:
        return Check("gpt config", OK, "upstream default")
    if not path.is_file():
        return Check("gpt config", FAIL, str(path), "copy config/gpt_config.example.yaml")
    import yaml

    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return Check("gpt config", FAIL, path.name, f"invalid YAML: {exc}")
    return Check("gpt config", OK, path.name)


def _check_endpoint(config: Config) -> Check:
    base = config.translation.base_url
    if not base:
        return Check("llm endpoint", OK, "not set (provider default)")
    probe = base.rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(probe, timeout=5) as response:  # noqa: S310
            return Check("llm endpoint", OK, f"{base} (HTTP {response.status})")
    except urllib.error.HTTPError as exc:
        # A 401/403 still proves something is listening there.
        return Check("llm endpoint", OK, f"{base} (HTTP {exc.code})")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return Check(
            "llm endpoint",
            WARN,
            f"{base} unreachable",
            f"{exc}; start the server, or check translation.base_url",
        )


def _check_api_key(config: Config) -> Check:
    name = config.translation.api_key_env
    if not name:
        return Check("api key", OK, "not configured")
    import os

    if os.environ.get(name):
        return Check("api key", OK, f"${name} is set")
    return Check(
        "api key",
        WARN,
        f"${name} is empty",
        "local servers often accept any string; hosted APIs will reject the request",
    )


def _check_paths(config: Config) -> list[Check]:
    checks: list[Check] = []
    try:
        config.paths.ensure()
        checks.append(Check("output folder", OK, str(config.paths.output)))
    except OSError as exc:
        checks.append(Check("output folder", FAIL, str(config.paths.output), str(exc)))
    images = 0
    if config.paths.source.is_dir():
        images = sum(
            1 for folder in config.paths.source.iterdir() if folder.is_dir()
            for item in folder.iterdir()
            if item.is_file() and item.suffix.lower() in IMAGE_EXTS
        )
    if images:
        checks.append(Check("pages found", OK, f"{images} image(s)"))
    else:
        checks.append(
            Check(
                "pages found",
                WARN,
                "0 images",
                f"drop one folder per book into {config.paths.source}",
            )
        )
    free = free_space(config.paths.data)
    low = free < 2 * 1024**3
    checks.append(
        Check(
            "disk space",
            WARN if low else OK,
            human_bytes(free),
            "under 2 GiB free" if low else "",
        )
    )
    return checks


def collect(config: Config) -> list[Check]:
    checks = [_check_python()]
    if config.engine_type == "mit":
        checks += [
            _check_mit_root(config),
            _check_engine_python(config),
            _check_base_config(config),
            _check_font(config),
            _check_gpt_config(config),
            _check_endpoint(config),
            _check_api_key(config),
        ]
        checks += _check_dicts(config)
    checks += _check_paths(config)
    return checks


def report(config: Config, console: Console) -> int:
    checks = collect(config)
    rows = [["", "check", "detail"]]
    marks = {OK: "ok", WARN: "warn", FAIL: "FAIL"}
    for item in checks:
        rows.append([marks[item.status], item.label, item.detail])
    table(rows, console=console)
    hints = [item for item in checks if item.hint]
    for item in hints:
        level = console.error if item.status == FAIL else console.warn
        level(f"{item.label}: {item.hint}")
    failures = [item for item in checks if item.status == FAIL]
    if failures:
        console.error(f"{len(failures)} blocking problem(s)")
        return 1
    warnings = [item for item in checks if item.status == WARN]
    if warnings:
        console.warn(f"ready, with {len(warnings)} warning(s)")
    else:
        console.ok("all checks passed")
    return 0
