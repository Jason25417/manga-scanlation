"""Configuration loading and validation.

One YAML file describes *wiring* (where things are, which engine, which model).
Quality knobs deliberately stay in manga-image-translator's own JSON config, so
there is exactly one place to tune them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
OUTPUT_FORMATS = {"png", "webp", "jpg", "jpeg"}
SOURCE_TYPES = {"local", "gallerydl"}
ENGINE_TYPES = {"mit", "passthrough"}


class ConfigError(Exception):
    """Raised when the configuration file is missing, malformed or inconsistent."""


def _resolve(value: str, base: Path) -> Path:
    """Expand env vars / ~ and resolve relative paths against the config dir."""
    expanded = os.path.expandvars(os.path.expanduser(str(value)))
    path = Path(expanded)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _unwrap(node: Any) -> Any:
    """Treat an empty YAML mapping as 'unset'."""
    if isinstance(node, dict) and not node:
        return None
    return node


def _section(node: Any, name: str) -> dict:
    if node is None:
        return {}
    if not isinstance(node, dict):
        raise ConfigError(f"'{name}' must be a mapping, got {type(node).__name__}")
    return node


def _get(node: dict, key: str, where: str, default: Any = None) -> Any:
    value = _unwrap(node.get(key, default))
    return default if value is None else value


def _as_bool(value: Any, where: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "yes", "1", "on"}:
        return True
    if isinstance(value, str) and value.lower() in {"false", "no", "0", "off"}:
        return False
    raise ConfigError(f"'{where}' must be true or false, got {value!r}")


def _as_int(value: Any, where: str, minimum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"'{where}' must be an integer, got {value!r}") from None
    if minimum is not None and number < minimum:
        raise ConfigError(f"'{where}' must be >= {minimum}, got {number}")
    return number


def _as_str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{where}' must be a non-empty string, got {value!r}")
    return value.strip()


def _opt_path(node: dict, key: str, where: str, base: Path) -> Path | None:
    value = _unwrap(node.get(key))
    if value is None:
        return None
    return _resolve(_as_str(value, where), base)


@dataclass(frozen=True)
class PathsConfig:
    data: Path
    inbox: Path
    source: Path
    output: Path
    logs: Path
    reports: Path
    state: Path
    work: Path

    def ensure(self) -> None:
        for directory in (
            self.data, self.inbox, self.source, self.output,
            self.logs, self.reports, self.work, self.state.parent,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class SourceConfig:
    type: str
    move: bool
    executable: str
    config: Path | None
    links_file: Path | None
    urls: tuple[str, ...]
    extra_args: tuple[str, ...]


@dataclass(frozen=True)
class MITConfig:
    root: Path
    python: Path
    base_config: Path
    font: Path | None
    gpu: bool
    verbose: bool
    attempts: int
    context_size: int
    extra_args: tuple[str, ...]


@dataclass(frozen=True)
class OutputConfig:
    """What the finished files look like.

    The engine always writes PNG: manga-image-translator only allows lossy quality
    control for JPEG, and PNG is exactly lossless. Compression to a lighter format
    is a separate step afterwards, so a lossy pass never feeds another one.
    """

    compress: bool
    format: str          # webp | jpg | png
    quality: int
    keep_source: bool


@dataclass(frozen=True)
class TranslationConfig:
    translator: str
    target_lang: str
    gpt_config: Path | None
    prompt: Path | None
    model: str | None
    base_url: str | None
    api_key_env: str | None
    pre_dict: Path | None
    post_dict: Path | None


@dataclass(frozen=True)
class BatchConfig:
    retries: int
    fail_fast: bool
    limit: int


@dataclass(frozen=True)
class Config:
    root: Path                 # directory holding config.yaml
    path: Path                 # config.yaml itself
    paths: PathsConfig
    source: SourceConfig
    engine_type: str
    mit: MITConfig
    output: OutputConfig
    translation: TranslationConfig
    batch: BatchConfig


DEFAULT_DATA = {
    "data": "./data",
    "inbox": "./inbox",
    "source": "./data/source",
    "output": "./data/output",
    "logs": "./data/logs",
    "reports": "./data/reports",
    "state": "./data/state.json",
    "work": "./data/work",
}


def load(path: str | Path = "config.yaml") -> Config:
    """Load and validate a configuration file."""
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ConfigError(
            f"config file not found: {config_path}\n"
            "Copy config.example.yaml to config.yaml and edit it."
        )
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"could not parse {config_path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path.name} must contain a mapping at the top level")

    base = config_path.parent

    raw_paths = _section(raw.get("paths"), "paths")
    paths = PathsConfig(
        **{
            key: _resolve(
                _as_str(_get(raw_paths, key, f"paths.{key}", default), f"paths.{key}"),
                base,
            )
            for key, default in DEFAULT_DATA.items()
        }
    )

    raw_source = _section(raw.get("source"), "source")
    source_type = _as_str(_get(raw_source, "type", "source.type", "local"), "source.type").lower()
    if source_type not in SOURCE_TYPES:
        raise ConfigError(
            f"'source.type' must be one of {sorted(SOURCE_TYPES)}, got {source_type!r}"
        )
    raw_local = _section(raw_source.get("local"), "source.local")
    raw_gallery = _section(raw_source.get("gallerydl"), "source.gallerydl")
    urls = _get(raw_gallery, "urls", "source.gallerydl.urls", default=[])
    if isinstance(urls, str):
        urls = [urls]
    if not isinstance(urls, list):
        raise ConfigError("'source.gallerydl.urls' must be a list of URLs")
    extra = _get(raw_gallery, "extra_args", "source.gallerydl.extra_args", default=[])
    if not isinstance(extra, list) or not all(isinstance(x, str) for x in extra):
        raise ConfigError("'source.gallerydl.extra_args' must be a list of strings")

    source = SourceConfig(
        type=source_type,
        move=_as_bool(_get(raw_local, "move", "source.local.move", False), "source.local.move"),
        executable=_as_str(
            _get(raw_gallery, "executable", "source.gallerydl.executable", "gallery-dl"),
            "source.gallerydl.executable",
        ),
        config=_opt_path(raw_gallery, "config", "source.gallerydl.config", base),
        links_file=_opt_path(raw_gallery, "links_file", "source.gallerydl.links_file", base),
        urls=tuple(urls),
        extra_args=tuple(extra),
    )

    raw_engine = _section(raw.get("engine"), "engine")
    engine_type = _as_str(_get(raw_engine, "type", "engine.type", "mit"), "engine.type").lower()
    if engine_type not in ENGINE_TYPES:
        raise ConfigError(
            f"'engine.type' must be one of {sorted(ENGINE_TYPES)}, got {engine_type!r}"
        )
    raw_mit = _section(raw_engine.get("mit"), "engine.mit")
    mit_extra = _get(raw_mit, "extra_args", "engine.mit.extra_args", default=[])
    if not isinstance(mit_extra, list) or not all(isinstance(x, str) for x in mit_extra):
        raise ConfigError("'engine.mit.extra_args' must be a list of strings")
    mit = MITConfig(
        root=_resolve(
            _as_str(
                _get(raw_mit, "root", "engine.mit.root", "./vendor/manga-image-translator"),
                "engine.mit.root",
            ),
            base,
        ),
        python=_resolve(
            _as_str(_get(raw_mit, "python", "engine.mit.python", "python"), "engine.mit.python"),
            base,
        ),
        base_config=_resolve(
            _as_str(
                _get(raw_mit, "base_config", "engine.mit.base_config",
                     "./config/mit-config.json"),
                "engine.mit.base_config",
            ),
            base,
        ),
        font=_opt_path(raw_mit, "font", "engine.mit.font", base),
        gpu=_as_bool(_get(raw_mit, "gpu", "engine.mit.gpu", True), "engine.mit.gpu"),
        verbose=_as_bool(
            _get(raw_mit, "verbose", "engine.mit.verbose", False), "engine.mit.verbose"
        ),
        attempts=_as_int(_get(raw_mit, "attempts", "engine.mit.attempts", 2),
                         "engine.mit.attempts", minimum=0),
        context_size=_as_int(_get(raw_mit, "context_size", "engine.mit.context_size", 3),
                             "engine.mit.context_size", minimum=0),
        extra_args=tuple(mit_extra),
    )

    raw_output = _section(raw.get("output"), "output")
    output_format = _as_str(
        _get(raw_output, "format", "output.format", "webp"), "output.format"
    ).lower()
    if output_format not in OUTPUT_FORMATS:
        raise ConfigError(
            f"'output.format' must be one of {sorted(OUTPUT_FORMATS)}, got {output_format!r}"
        )
    quality = _as_int(_get(raw_output, "quality", "output.quality", 95),
                      "output.quality", minimum=0)
    if quality > 100:
        raise ConfigError(f"'output.quality' must be <= 100, got {quality}")
    output = OutputConfig(
        compress=_as_bool(
            _get(raw_output, "compress", "output.compress", True), "output.compress"
        ),
        format=output_format,
        quality=quality,
        keep_source=_as_bool(
            _get(raw_output, "keep_source", "output.keep_source", False),
            "output.keep_source",
        ),
    )

    raw_tr = _section(raw.get("translation"), "translation")
    translation = TranslationConfig(
        translator=_as_str(
            _get(raw_tr, "translator", "translation.translator", "openai"),
            "translation.translator",
        ),
        target_lang=_as_str(
            _get(raw_tr, "target_lang", "translation.target_lang", "CHS"),
            "translation.target_lang",
        ),
        gpt_config=_opt_path(raw_tr, "gpt_config", "translation.gpt_config", base),
        prompt=_opt_path(raw_tr, "prompt", "translation.prompt", base),
        model=(_as_str(raw_tr["model"], "translation.model") if _unwrap(raw_tr.get("model")) else None),
        base_url=(
            _as_str(raw_tr["base_url"], "translation.base_url")
            if _unwrap(raw_tr.get("base_url")) else None
        ),
        api_key_env=(
            _as_str(raw_tr["api_key_env"], "translation.api_key_env")
            if _unwrap(raw_tr.get("api_key_env")) else None
        ),
        pre_dict=_opt_path(raw_tr, "pre_dict", "translation.pre_dict", base),
        post_dict=_opt_path(raw_tr, "post_dict", "translation.post_dict", base),
    )

    raw_batch = _section(raw.get("batch"), "batch")
    batch = BatchConfig(
        retries=_as_int(_get(raw_batch, "retries", "batch.retries", 1),
                        "batch.retries", minimum=0),
        fail_fast=_as_bool(
            _get(raw_batch, "fail_fast", "batch.fail_fast", False), "batch.fail_fast"
        ),
        limit=_as_int(_get(raw_batch, "limit", "batch.limit", 0),
                      "batch.limit", minimum=0),
    )

    config = Config(
        root=base,
        path=config_path,
        paths=paths,
        source=source,
        engine_type=engine_type,
        mit=mit,
        output=output,
        translation=translation,
        batch=batch,
    )
    validate_files(config)
    return config


def validate_files(config: Config) -> None:
    """Fail early on paths that are referenced but obviously wrong.

    Only paths that are *required to exist for the configured mode* are checked,
    so a config can be prepared before installing everything.
    """
    problems: list[str] = []

    if config.engine_type == "mit":
        if not config.mit.python.is_file():
            problems.append(
                f"engine.mit.python does not exist: {config.mit.python} "
                "(the interpreter where manga-image-translator is installed)"
            )
        if not config.mit.root.is_dir():
            problems.append(f"engine.mit.root does not exist: {config.mit.root}")
        if not config.mit.base_config.is_file():
            problems.append(
                f"engine.mit.base_config does not exist: {config.mit.base_config} "
                "(copy config/mit-config.example.json to config/mit-config.json)"
            )
        if config.mit.font is not None and not config.mit.font.is_file():
            problems.append(f"engine.mit.font does not exist: {config.mit.font}")

    if config.translation.translator in {"openai", "custom_openai", "ollama"}:
        if config.translation.gpt_config is None:
            pass  # optional: upstream defaults are used when absent
        elif not config.translation.gpt_config.is_file():
            problems.append(
                f"translation.gpt_config does not exist: {config.translation.gpt_config}"
            )

    for label, value in (
        ("translation.pre_dict", config.translation.pre_dict),
        ("translation.post_dict", config.translation.post_dict),
        ("translation.prompt", config.translation.prompt),
    ):
        if value is not None and not value.is_file():
            problems.append(f"{label} does not exist: {value}")

    if config.source.type == "gallerydl":
        if config.source.links_file is not None and not config.source.links_file.is_file():
            problems.append(f"source.gallerydl.links_file does not exist: {config.source.links_file}")
        if config.source.links_file is None and not config.source.urls:
            problems.append(
                "source.type is 'gallerydl' but neither 'links_file' nor 'urls' is set"
            )

    if problems:
        raise ConfigError("configuration problems:\n  - " + "\n  - ".join(problems))


def summary(config: Config) -> list[tuple[str, str]]:
    """Flat (label, value) pairs for `mscan config` / doctor output."""
    rows = [
        ("config", str(config.path)),
        ("data", str(config.paths.data)),
        ("source type", config.source.type),
        ("engine", config.engine_type),
    ]
    output = config.output
    rows.append(
        (
            "output",
            f"{output.format} (quality {output.quality})"
            if output.compress and output.format != "png"
            else "png (no compression)",
        )
    )
    if config.engine_type == "mit":
        rows += [
            ("manga-image-translator", str(config.mit.root)),
            ("engine python", str(config.mit.python)),
            ("gpu", "on" if config.mit.gpu else "off"),
            ("translator", config.translation.translator),
            ("target lang", config.translation.target_lang),
        ]
    return rows
